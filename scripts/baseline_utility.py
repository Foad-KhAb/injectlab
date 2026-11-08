"""Measure baseline utility: run every user task on a real model with no attack.

Usage:
    uv run python scripts/baseline_utility.py [--model M] [--task ID ...]
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from injectlab.llm.ollama_client import DEFAULT_MODEL, OllamaClient
from injectlab.tasks.harness import run_task
from injectlab.tasks.user_tasks import TASKS, get_task


def main(
    model: Annotated[str, typer.Option()] = DEFAULT_MODEL,
    task: Annotated[list[str] | None, typer.Option(help="Only these task ids.")] = None,
    out_dir: Annotated[Path, typer.Option()] = Path("results/traces/baseline"),
) -> None:
    console = Console()
    tasks = [get_task(t) for t in task] if task else TASKS
    client = OllamaClient(model)

    table = Table(title=f"Baseline utility, {model}, no attack")
    for col in ("task", "success", "steps", "tool calls", "stop", "trace"):
        table.add_column(col)

    successes = 0
    for t in tasks:
        console.print(f"running [bold]{t.id}[/bold] ...")
        result = run_task(t, client)
        path = out_dir / f"{t.id}.json"
        result.trace.save(path)
        successes += result.success
        table.add_row(
            t.id,
            "[green]yes[/green]" if result.success else "[red]no[/red]",
            str(result.trace.num_steps),
            ", ".join(c.name for c in result.trace.tool_calls),
            result.trace.stop_reason,
            str(path),
        )

    console.print(table)
    console.print(f"Utility: {successes}/{len(tasks)} = {successes / len(tasks):.0%}")


if __name__ == "__main__":
    typer.run(main)
