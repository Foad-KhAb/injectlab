"""Run one attacked episode on a real model and report both scores.

Usage:
    uv run python scripts/attack_episode.py USER_TASK INJECTION_TASK TEMPLATE [--slot S] [--model M]

Example:
    uv run python scripts/attack_episode.py package_arrival forward_bank_code important_message
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from injectlab.agent.render import render_trace
from injectlab.attacks.injection_tasks import get_injection_task
from injectlab.attacks.templates import get_template
from injectlab.llm.ollama_client import DEFAULT_MODEL, OllamaClient
from injectlab.tasks.harness import run_attack
from injectlab.tasks.user_tasks import get_task


def main(
    user_task: str,
    injection_task: str,
    template: str,
    slot: Annotated[list[str] | None, typer.Option(help="Only these slots.")] = None,
    model: Annotated[str, typer.Option()] = DEFAULT_MODEL,
    out_dir: Annotated[Path, typer.Option()] = Path("results/traces/attacks"),
) -> None:
    console = Console()
    result = run_attack(
        get_task(user_task),
        get_injection_task(injection_task),
        get_template(template),
        OllamaClient(model),
        slots=slot,
    )
    render_trace(result.trace, console)
    path = out_dir / f"{user_task}__{injection_task}__{template}.json"
    result.trace.save(path)

    def verdict(ok: bool | None, yes: str, no: str) -> str:
        return f"[green]{yes}[/green]" if ok else f"[red]{no}[/red]"

    console.print(f"User task:  {verdict(result.success, 'completed', 'failed')}")
    console.print(f"Attack:     {verdict(not result.attack_success, 'resisted', 'SUCCEEDED')}")
    console.print(f"Trace:      {path}")


if __name__ == "__main__":
    typer.run(main)
