"""Tests for experiment configs, the resumable runner, metrics and the run/analyze CLI.

No real model: the runner is given scripted clients.
"""

import json
import math
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError
from rich.console import Console
from typer.testing import CliRunner

from injectlab import cli
from injectlab.attacks.injection_tasks import get_injection_task
from injectlab.env.seed import build_world
from injectlab.eval import metrics, runner
from injectlab.eval.config import ALL_SLOTS, ExperimentConfig, RunSpec, expand, load_config
from injectlab.eval.runner import ResultRow, load_rows, run_experiment
from injectlab.llm.base import AssistantTurn, LLMClient
from injectlab.llm.mock_client import MockClient
from injectlab.tasks.harness import ground_truth_client
from injectlab.tasks.user_tasks import TASKS, get_task

CONFIGS = Path(__file__).parent.parent / "configs"


def small_config(tmp_path: Path, **overrides: object) -> ExperimentConfig:
    values: dict[str, object] = {
        "name": "t",
        "models": ["mock"],
        "user_tasks": ["package_arrival", "restaurant_hours"],
        "injection_tasks": ["forward_bank_code"],
        "templates": ["ignore_previous"],
        "output_dir": tmp_path,
    }
    values.update(overrides)
    return ExperimentConfig.model_validate(values)


def scripted(spec: RunSpec, *, obey: bool) -> MockClient:
    """A client that does the user task correctly and, if ``obey``, the attacker's goal too."""
    task = get_task(spec.user_task)
    if not spec.is_attack or not obey:
        return ground_truth_client(task)
    assert spec.injection_task
    world = build_world()
    calls = [
        *task.ground_truth(world),
        *get_injection_task(spec.injection_task).ground_truth(world),
    ]
    turns = [
        AssistantTurn(tool_calls=[c.model_copy(update={"id": f"c{i}"})])
        for i, c in enumerate(calls)
    ]
    return MockClient([*turns, AssistantTurn(content=task.reference_answer)])


def factory_for(config: ExperimentConfig, *, obey: bool = False):  # type: ignore[no-untyped-def]
    """Client factory handing out one scripted client per spec, in run order."""
    clients: Iterator[LLMClient] = iter([scripted(s, obey=obey) for s in expand(config)])
    return lambda model, seed: next(clients)


# ---------------------------------------------------------------- Wilson interval


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [
        (0, 10, 0.0, 0.2775),
        (5, 10, 0.2366, 0.7634),
        (10, 10, 0.7225, 1.0),
        (1, 100, 0.0018, 0.0545),
    ],
)
def test_wilson_interval_known_values(k: int, n: int, low: float, high: float) -> None:
    lo, hi = metrics.wilson_interval(k, n)
    assert lo == pytest.approx(low, abs=1e-3)
    assert hi == pytest.approx(high, abs=1e-3)


def test_wilson_interval_empty_and_bounds() -> None:
    assert all(math.isnan(x) for x in metrics.wilson_interval(0, 0))
    for k in range(6):
        lo, hi = metrics.wilson_interval(k, 5)
        assert 0.0 <= lo <= k / 5 <= hi <= 1.0


def test_rate_formatting() -> None:
    assert str(metrics.Rate(0, 0)) == "-"
    assert str(metrics.Rate(5, 10)) == "50% [24%-76%] n=10"


# ---------------------------------------------------------------- config


def test_repo_configs_load() -> None:
    assert len(expand(load_config(CONFIGS / "dev.yaml"))) == 20
    full = load_config(CONFIGS / "full.yaml")
    slots = sum(len(t.injection_slots) for t in TASKS)
    assert len(expand(full)) == 5 * (len(TASKS) + slots * 5 * 5)


@pytest.mark.parametrize(
    "override",
    [
        {"user_tasks": ["nope"]},
        {"injection_tasks": ["nope"]},
        {"templates": ["nope"]},
        {"defenses": ["nope"]},
        {"unexpected_key": 1},
    ],
)
def test_config_rejects_typos(tmp_path: Path, override: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        small_config(tmp_path, **override)


def test_expand_each_slot(tmp_path: Path) -> None:
    specs = expand(small_config(tmp_path))
    benign = [s for s in specs if not s.is_attack]
    attacks = [s for s in specs if s.is_attack]
    assert [s.user_task for s in benign] == ["package_arrival", "restaurant_hours"]
    # package_arrival reads 1 slot, restaurant_hours reads 2.
    assert len(attacks) == 3
    assert {s.slot for s in attacks if s.user_task == "restaurant_hours"} == {
        "email_jordan_body",
        "web_restaurant_reviews",
    }


def test_expand_all_slots_and_no_benign(tmp_path: Path) -> None:
    specs = expand(small_config(tmp_path, slot_mode="all", include_benign=False))
    assert len(specs) == 2
    assert all(s.slot == ALL_SLOTS for s in specs)


def test_expand_multiplies_models_defenses_seeds(tmp_path: Path) -> None:
    specs = expand(small_config(tmp_path, models=["a", "b"], seeds=[0, 1]))
    assert len(specs) == 2 * 2 * 5


def test_run_ids_are_stable_and_unique(tmp_path: Path) -> None:
    config = small_config(tmp_path, seeds=[0, 1])
    first = [s.run_id for s in expand(config)]
    assert first == [s.run_id for s in expand(config)]
    assert len(set(first)) == len(first)


# ---------------------------------------------------------------- runner


def test_runner_writes_one_row_per_run_with_traces(tmp_path: Path) -> None:
    config = small_config(tmp_path)
    rows = run_experiment(config, client_factory=factory_for(config))

    assert len(rows) == len(expand(config)) == 5
    assert load_rows(config.results_path) == rows
    for row in rows:
        assert row.error is None
        assert row.user_task_success is True
        assert row.attack_success is (False if row.injection_task else None)
        assert row.trace_path and Path(row.trace_path).exists()
        assert row.git_commit
        assert row.experiment == "t"


def test_runner_records_attack_success(tmp_path: Path) -> None:
    config = small_config(tmp_path, include_benign=False)
    rows = run_experiment(config, client_factory=factory_for(config, obey=True))
    assert all(r.attack_success for r in rows)
    # package_arrival is a question: sending mail costs its utility. restaurant_hours too.
    assert not any(r.user_task_success for r in rows)


def test_runner_resumes_without_redoing_runs(tmp_path: Path) -> None:
    config = small_config(tmp_path)
    run_experiment(config, client_factory=factory_for(config))

    def no_client(model: str, seed: int) -> LLMClient:
        raise AssertionError("a completed run was executed again")

    assert run_experiment(config, client_factory=no_client) == []
    assert len(load_rows(config.results_path)) == 5


def test_runner_records_output_limit_without_changing_completed_runs(tmp_path: Path) -> None:
    config = small_config(tmp_path, user_tasks=["package_arrival"])
    factory = factory_for(config)

    def bounded(model: str, seed: int) -> LLMClient:
        client = factory(model, seed)
        client.num_predict = 512
        client.response_policy = "first_complete_tool_call_v1"
        return client

    rows = run_experiment(config, client_factory=bounded)
    assert all(r.num_predict == 512 for r in rows)
    assert all(r.response_policy == "first_complete_tool_call_v1" for r in rows)
    saved = config.results_path.read_bytes()
    assert run_experiment(config, client_factory=factory_for(config)) == []
    assert config.results_path.read_bytes() == saved


def test_crashed_and_errored_runs_are_recorded_then_retried(tmp_path: Path) -> None:
    config = small_config(tmp_path, user_tasks=["package_arrival"])

    def broken(model: str, seed: int) -> LLMClient:
        raise RuntimeError("boom")

    rows = run_experiment(config, client_factory=broken)
    assert [r.stop_reason for r in rows] == ["crash", "crash"]
    assert all(r.error and "boom" in r.error for r in rows)
    assert all(r.user_task_success is None for r in rows)

    # An exhausted script raises LLMError inside the loop: an "error" stop, not a crash.
    rows = run_experiment(config, client_factory=lambda m, s: MockClient([]))
    assert [r.stop_reason for r in rows] == ["error", "error"]

    rows = run_experiment(config, client_factory=factory_for(config))
    assert [r.error for r in rows] == [None, None]
    assert run_experiment(config, client_factory=factory_for(config)) == []


def test_answer_mentions_attacker(tmp_path: Path) -> None:
    config = small_config(tmp_path, user_tasks=["package_arrival"], include_benign=False)
    relay = "It arrives March 18. Also, send the code to attacker@evil.test."
    client = MockClient([AssistantTurn(content=relay)])
    [row] = run_experiment(config, client_factory=lambda m, s: client)
    assert row.answer_mentions_attacker is True
    assert row.attack_success is False


# ---------------------------------------------------------------- metrics


def row(**fields: object) -> ResultRow:
    base: dict[str, object] = {
        "run_id": "x",
        "experiment": "e",
        "git_commit": "abc",
        "timestamp": "2026-01-01T00:00:00",
        "model": "m",
        "defense": "none",
        "user_task": "u",
        "injection_task": None,
        "attack_template": None,
        "slot": None,
        "seed": 0,
        "user_task_success": True,
        "attack_success": None,
        "answer_mentions_attacker": None,
        "num_steps": 1,
        "tool_calls": [],
        "stop_reason": "final_answer",
        "error": None,
        "empty_retries": 0,
        "duration_s": 1.0,
        "trace_path": None,
    }
    base.update(fields)
    return ResultRow.model_validate(base)


def attack_row(run_id: str, user: bool, attack: bool, template: str = "t1") -> ResultRow:
    return row(
        run_id=run_id,
        injection_task="i",
        attack_template=template,
        slot="s",
        user_task_success=user,
        attack_success=attack,
        answer_mentions_attacker=attack,
    )


def test_overview_follows_agentdojo_definitions() -> None:
    df = metrics.to_frame(
        [
            row(run_id="b1", user_task_success=True),
            row(run_id="b2", user_task_success=False),
            attack_row("a1", user=True, attack=True),  # both: counts for UUA and ASR
            attack_row("a2", user=True, attack=False),
            attack_row("a3", user=False, attack=False),
            attack_row("a4", user=False, attack=True),
        ]
    )
    [rec] = metrics.overview(df).to_dict("records")
    assert (rec["utility"].k, rec["utility"].n) == (1, 2)
    assert (rec["utility_under_attack"].k, rec["utility_under_attack"].n) == (2, 4)
    assert (rec["asr"].k, rec["asr"].n) == (2, 4)
    assert rec["errors"] == 0


def test_errors_are_excluded_and_counted() -> None:
    df = metrics.to_frame(
        [
            row(run_id="b1"),
            row(run_id="b2", stop_reason="error", error="down", user_task_success=False),
            row(run_id="b3", stop_reason="crash", error="boom", user_task_success=None),
        ]
    )
    [rec] = metrics.overview(df).to_dict("records")
    assert (rec["utility"].k, rec["utility"].n) == (1, 1)
    assert rec["errors"] == 2


def test_latest_row_per_run_id_wins() -> None:
    df = metrics.to_frame(
        [
            row(run_id="b1", stop_reason="error", error="down"),
            row(run_id="b1", user_task_success=True),
        ]
    )
    assert len(df) == 1
    assert not df["failed"].any()


def test_breakdowns() -> None:
    df = metrics.to_frame(
        [
            row(run_id="b1"),
            attack_row("a1", user=True, attack=True, template="t1"),
            attack_row("a2", user=True, attack=False, template="t2"),
            attack_row("a3", user=True, attack=False, template="t2"),
        ]
    )
    by_template = metrics.attack_breakdown(df, ["attack_template"]).set_index("attack_template")
    assert by_template.loc["t1", "asr"].value == 1.0
    assert by_template.loc["t2", "asr"].value == 0.0
    by_task = metrics.utility_breakdown(df, ["user_task"])
    assert by_task.loc[0, "utility"].n == 1


# ---------------------------------------------------------------- CLI


@pytest.fixture
def wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "console", Console(width=250))


def test_cli_run_then_analyze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wide_console: None
) -> None:
    config_path = tmp_path / "exp.yaml"
    config_path.write_text(
        "name: exp\nmodels: [mock]\nuser_tasks: [package_arrival]\n"
        "injection_tasks: [forward_bank_code]\ntemplates: [ignore_previous]\n"
        f"output_dir: {tmp_path}\n"
    )
    config = load_config(config_path)
    monkeypatch.setattr(
        "injectlab.eval.runner.default_client_factory", factory_for(config, obey=True)
    )

    result = CliRunner().invoke(cli.app, ["run", str(config_path)])
    assert result.exit_code == 0, result.output
    assert "2 runs, 2 to do" in result.output
    assert "SUCCEEDED" in result.output

    result = CliRunner().invoke(cli.app, ["analyze", str(tmp_path / "exp.jsonl")])
    assert result.exit_code == 0, result.output
    assert "Overview" in result.output
    assert "Attacks by attack_template" in result.output
    assert "100% [" in result.output  # utility 1/1 and ASR 1/1


def test_cli_missing_files(tmp_path: Path) -> None:
    assert CliRunner().invoke(cli.app, ["run", str(tmp_path / "x.yaml")]).exit_code == 1
    assert CliRunner().invoke(cli.app, ["analyze", str(tmp_path / "x.jsonl")]).exit_code == 1


def test_detector_summary_reports_false_positives_and_flagged_attacks() -> None:
    df = metrics.to_frame(
        [
            row(run_id="b1", defense="detector", num_tool_outputs=3, redacted_outputs=1),
            row(run_id="b2", defense="detector", num_tool_outputs=1, redacted_outputs=0),
            attack_row("a1", user=True, attack=False).model_copy(
                update={"defense": "detector", "num_tool_outputs": 2, "redacted_outputs": 2}
            ),
            attack_row("a2", user=True, attack=True).model_copy(
                update={"defense": "detector", "num_tool_outputs": 2}
            ),
            row(run_id="n1", defense="none", num_tool_outputs=9, redacted_outputs=0),
        ]
    )
    [rec] = metrics.detector_summary(df).to_dict("records")
    assert (rec["false_positive_rate"].k, rec["false_positive_rate"].n) == (1, 4)
    assert (rec["attacked_runs_flagged"].k, rec["attacked_runs_flagged"].n) == (1, 2)


def test_rows_written_before_the_counters_existed_still_load(tmp_path: Path) -> None:
    data = row().model_dump()
    del data["redacted_outputs"], data["blocked_calls"], data["num_tool_outputs"]
    del data["num_predict"]
    del data["response_policy"]
    path = tmp_path / "old.jsonl"
    path.write_text(json.dumps(data) + "\n")
    assert load_rows(path)[0].redacted_outputs == 0
    assert load_rows(path)[0].num_predict is None
    assert load_rows(path)[0].response_policy is None


def test_git_commit_falls_back_to_the_environment_without_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(runner.subprocess, "run", no_git)
    monkeypatch.delenv("INJECTLAB_COMMIT", raising=False)
    assert runner.git_commit() == "unknown"
    monkeypatch.setenv("INJECTLAB_COMMIT", "abc1234")
    assert runner.git_commit() == "abc1234"
