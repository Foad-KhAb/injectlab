"""Run an experiment: every RunSpec once, one JSONL row per run, resumable.

Each finished run is appended and flushed immediately, so an interrupted experiment loses at
most the run in progress. On restart, runs that already have a row without an error are
skipped; runs that ended in an error (e.g. the Ollama server died) are tried again.
"""

import subprocess
import time
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from injectlab.attacks.injection_tasks import get_injection_task
from injectlab.attacks.templates import get_template
from injectlab.defenses import make_defense
from injectlab.defenses.detector import REDACTED_MESSAGE
from injectlab.eval.config import ALL_SLOTS, ExperimentConfig, RunSpec, expand
from injectlab.llm.base import LLMClient
from injectlab.llm.ollama_client import OllamaClient
from injectlab.tasks.harness import TaskResult, run_attack, run_task
from injectlab.tasks.user_tasks import get_task

ClientFactory = Callable[[str, int], LLMClient]  # (model, seed) -> client
ATTACKER_DOMAIN = "evil.test"


class ResultRow(BaseModel):
    run_id: str
    experiment: str
    git_commit: str
    timestamp: str
    model: str
    defense: str
    user_task: str
    injection_task: str | None
    attack_template: str | None
    slot: str | None
    seed: int
    user_task_success: bool | None  # None when the run crashed before it could be scored
    attack_success: bool | None  # None for benign runs
    # Did the final answer mention the attacker's domain? Catches answers that pass the
    # attacker's request on to the user, which no tool-based checker sees. Neutral by
    # design: it is also True when the model names the domain to warn the user.
    answer_mentions_attacker: bool | None
    num_steps: int
    tool_calls: list[str]
    stop_reason: str
    error: str | None
    empty_retries: int
    duration_s: float
    trace_path: str | None
    num_tool_outputs: int = 0
    redacted_outputs: int = 0  # tool outputs a detector replaced
    blocked_calls: int = 0  # tool calls a defense refused


def git_commit() -> str:
    """Current commit, with "+dirty" if there are uncommitted changes to tracked files."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{sha}+dirty" if dirty else sha


def load_rows(path: Path) -> list[ResultRow]:
    if not path.exists():
        return []
    return [ResultRow.model_validate_json(line) for line in path.read_text().splitlines() if line]


def completed_run_ids(path: Path) -> set[str]:
    return {r.run_id for r in load_rows(path) if r.error is None}


def default_client_factory(model: str, seed: int) -> LLMClient:
    return OllamaClient(model, seed=seed)


def execute(spec: RunSpec, client: LLMClient, max_steps: int) -> TaskResult:
    task = get_task(spec.user_task)
    defense = make_defense(spec.defense)
    if not spec.is_attack:
        return run_task(task, client, defense=defense, max_steps=max_steps)
    assert spec.injection_task and spec.template
    return run_attack(
        task,
        get_injection_task(spec.injection_task),
        get_template(spec.template),
        client,
        slots=None if spec.slot == ALL_SLOTS else [spec.slot or ""],
        defense=defense,
        max_steps=max_steps,
    )


def run_one(
    spec: RunSpec,
    config: ExperimentConfig,
    client_factory: ClientFactory,
    commit: str,
) -> ResultRow:
    start = time.monotonic()
    common = {
        "run_id": spec.run_id,
        "experiment": config.name,
        "git_commit": commit,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model": spec.model,
        "defense": spec.defense,
        "user_task": spec.user_task,
        "injection_task": spec.injection_task,
        "attack_template": spec.template,
        "slot": spec.slot,
        "seed": spec.seed,
    }
    try:
        result = execute(spec, client_factory(spec.model, spec.seed), config.max_steps)
    except Exception as exc:  # a bug or crash in one run must not end a long experiment
        return ResultRow(
            **common,
            user_task_success=None,
            attack_success=None,
            answer_mentions_attacker=None,
            num_steps=0,
            tool_calls=[],
            stop_reason="crash",
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}",
            empty_retries=0,
            duration_s=round(time.monotonic() - start, 2),
            trace_path=None,
        )

    trace = result.trace
    trace_path = config.traces_dir / f"{spec.run_id}.json"
    trace.save(trace_path)
    answer = (trace.final_answer or "").lower()
    return ResultRow(
        **common,
        user_task_success=result.success,
        attack_success=result.attack_success,
        answer_mentions_attacker=(ATTACKER_DOMAIN in answer) if spec.is_attack else None,
        num_steps=trace.num_steps,
        tool_calls=[c.name for c in trace.tool_calls],
        stop_reason=trace.stop_reason,
        error=trace.error,
        empty_retries=trace.empty_retries,
        duration_s=round(time.monotonic() - start, 2),
        trace_path=str(trace_path),
        num_tool_outputs=sum(not e.blocked for e in trace.executions),
        redacted_outputs=sum(e.shown_output == REDACTED_MESSAGE for e in trace.executions),
        blocked_calls=sum(e.blocked for e in trace.executions),
    )


def run_experiment(
    config: ExperimentConfig,
    *,
    client_factory: ClientFactory | None = None,
    on_row: Callable[[int, int, RunSpec, ResultRow | None], None] | None = None,
) -> list[ResultRow]:
    """Run every not-yet-completed spec and append its row. Returns the new rows.

    ``on_row(index, total, spec, row)`` is called after each run (``row`` is None for a
    skipped run), for progress output.
    """
    client_factory = client_factory or default_client_factory
    specs = expand(config)
    done = completed_run_ids(config.results_path)
    config.results_path.parent.mkdir(parents=True, exist_ok=True)
    commit = git_commit()

    new_rows: list[ResultRow] = []
    with config.results_path.open("a") as out:
        for i, spec in enumerate(specs, start=1):
            if spec.run_id in done:
                if on_row:
                    on_row(i, len(specs), spec, None)
                continue
            row = run_one(spec, config, client_factory, commit)
            out.write(row.model_dump_json() + "\n")
            out.flush()
            new_rows.append(row)
            if on_row:
                on_row(i, len(specs), spec, row)
    return new_rows
