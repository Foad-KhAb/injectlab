"""Command-line interface: `injectlab run`, `injectlab analyze`, `injectlab show-trace`."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from injectlab import __version__

app = typer.Typer(
    help="InjectLab: measure indirect prompt injection attacks and defenses on LLM agents.",
    no_args_is_help=True,
)
console = Console()


def _not_implemented() -> None:
    console.print("[yellow]Not implemented yet.[/yellow]")
    raise typer.Exit(code=1)


@app.command()
def run(config: Annotated[Path, typer.Argument(help="Path to an experiment YAML config.")]) -> None:
    """Run every combination in an experiment config and write JSONL results."""
    _not_implemented()


@app.command()
def analyze(results: Annotated[Path, typer.Argument(help="Path to a results JSONL file.")]) -> None:
    """Print utility, utility under attack, and ASR tables for a results file."""
    _not_implemented()


@app.command("show-trace")
def show_trace(
    trace: Annotated[Path, typer.Argument(help="Path to a saved trace JSON file.")],
) -> None:
    """Pretty-print a saved agent trace."""
    _not_implemented()


@app.command()
def version() -> None:
    """Print the InjectLab version."""
    console.print(__version__)
