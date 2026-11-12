"""Command-line interface: `injectlab run`, `injectlab analyze`, `injectlab show-trace`."""

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console

from injectlab import __version__

if TYPE_CHECKING:
    import pandas as pd

app = typer.Typer(
    help="InjectLab: measure indirect prompt injection attacks and defenses on LLM agents.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(config: Annotated[Path, typer.Argument(help="Path to an experiment YAML config.")]) -> None:
    """Run every combination in an experiment config and write JSONL results."""
    from injectlab.eval.config import RunSpec, expand, load_config
    from injectlab.eval.runner import ResultRow, completed_run_ids, run_experiment

    if not config.exists():
        console.print(f"[red]No such file: {config}[/red]")
        raise typer.Exit(code=1)
    cfg = load_config(config)
    total = len(expand(cfg))
    todo = total - len(completed_run_ids(cfg.results_path) & {s.run_id for s in expand(cfg)})
    console.print(
        f"Experiment [bold]{cfg.name}[/bold]: {total} runs, {todo} to do -> {cfg.results_path}"
    )

    def progress(i: int, n: int, spec: RunSpec, row: ResultRow | None) -> None:
        if row is None:
            return
        label = spec.user_task
        if spec.is_attack:
            label += f" x {spec.injection_task} x {spec.template} @ {spec.slot}"
        user = (
            "-"
            if row.error
            else {True: "[green]ok[/green]", False: "[red]fail[/red]"}.get(
                row.user_task_success, "-"
            )
        )
        parts = [f"[{i}/{n}] {spec.model} {spec.defense} {label}: user {user}"]
        if spec.is_attack and not row.error:
            parts.append("attack " + ("[red]SUCCEEDED[/red]" if row.attack_success else "resisted"))
        if row.error:
            parts.append(f"[red]{row.stop_reason}: {row.error.splitlines()[0]}[/red]")
        parts.append(f"({row.duration_s:.0f}s)")
        console.print(" | ".join(parts))

    rows = run_experiment(cfg, on_row=progress)
    errors = sum(r.error is not None for r in rows)
    console.print(f"Done: {len(rows)} new runs, {errors} with errors.")
    console.print(f"Analyze with: injectlab analyze {cfg.results_path}")


@app.command()
def analyze(results: Annotated[Path, typer.Argument(help="Path to a results JSONL file.")]) -> None:
    """Print utility, utility under attack, and ASR tables for a results file."""
    from injectlab.eval import metrics

    if not results.exists():
        console.print(f"[red]No such file: {results}[/red]")
        raise typer.Exit(code=1)
    df = metrics.load_frame(results)
    if df.empty:
        console.print("[yellow]No rows.[/yellow]")
        raise typer.Exit(code=1)

    _print_frame("Overview", metrics.overview(df))
    for key in ("attack_template", "injection_task", "slot", "user_task"):
        _print_frame(f"Attacks by {key}", metrics.attack_breakdown(df, ["model", "defense", key]))
    _print_frame(
        "Benign utility by user task", metrics.utility_breakdown(df, ["model", "user_task"])
    )
    _print_frame("Detector", metrics.detector_summary(df))
    _print_frame("Each defense vs none (paired)", metrics.compare_defenses(df))
    _print_frame("English vs Persian (paired)", metrics.compare_templates(df))
    failed = int(df["failed"].sum())
    if failed:
        console.print(f"[yellow]{failed} run(s) ended in an error and are excluded.[/yellow]")
    console.print("Rates are shown as value [Wilson 95% CI] n=runs.")


def _print_frame(title: str, frame: "pd.DataFrame") -> None:
    from rich.table import Table

    if frame.empty:
        return
    table = Table(title=title, title_justify="left")
    for col in frame.columns:
        table.add_column(str(col))
    for record in frame.itertuples(index=False):
        table.add_row(*(str(v) for v in record))
    console.print(table)


@app.command()
def plot(
    results: Annotated[Path, typer.Argument(help="Path to a results JSONL file.")],
    out_dir: Annotated[Path, typer.Option(help="Where to write figures and tables.")] = Path(
        "figures"
    ),
) -> None:
    """Write the report's figures (PNG) and tables (Markdown) for a results file."""
    from injectlab.analysis.plots import write_report_assets

    if not results.exists():
        console.print(f"[red]No such file: {results}[/red]")
        raise typer.Exit(code=1)
    for path in write_report_assets(results, out_dir):
        console.print(f"wrote {path}")


@app.command("show-trace")
def show_trace(
    trace: Annotated[Path, typer.Argument(help="Path to a saved trace JSON file.")],
    full: Annotated[bool, typer.Option(help="Show the full system prompt.")] = False,
) -> None:
    """Pretty-print a saved agent trace."""
    from injectlab.agent.loop import Trace
    from injectlab.agent.render import render_trace

    if not trace.exists():
        console.print(f"[red]No such file: {trace}[/red]")
        raise typer.Exit(code=1)
    render_trace(Trace.load(trace), console, full=full)


@app.command()
def version() -> None:
    """Print the InjectLab version."""
    console.print(__version__)
