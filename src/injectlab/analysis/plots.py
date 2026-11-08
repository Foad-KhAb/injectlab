"""The report's figures and tables, from a results JSONL file.

Figures show rates with Wilson 95% intervals. ``tables.md`` holds every number behind them.
With several models in one file, each model gets its own subfolder.
"""

import re
from collections.abc import Callable
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from injectlab.attacks.injection_tasks import INJECTION_TASKS  # noqa: E402
from injectlab.attacks.templates import TEMPLATES  # noqa: E402
from injectlab.defenses import DEFENSES  # noqa: E402
from injectlab.eval import metrics  # noqa: E402
from injectlab.eval.metrics import Rate  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
# Fixed slot per defense, so a defense keeps its color when others are absent.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
DEFENSE_ORDER = list(DEFENSES)
DEFENSE_COLOR = dict(zip(DEFENSE_ORDER, SERIES, strict=True))
ASR_RAMP = LinearSegmentedColormap.from_list("asr", ["#cde2fb", "#86b6ef", "#2a78d6", "#104281"])

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.size": 10,
        "text.color": TEXT,
        "axes.labelcolor": TEXT_SECONDARY,
        "axes.edgecolor": AXIS,
        "xtick.color": TEXT_SECONDARY,
        "ytick.color": TEXT_SECONDARY,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlelocation": "left",
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
    }
)


def _attacked(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["is_attack"] & ~df["failed"]]


def _present(order: list[str], values: pd.Series) -> list[str]:
    seen = set(values.dropna())
    return [item for item in order if item in seen]


def _grid(ax: Axes, axis: str) -> None:
    ax.set_axisbelow(True)
    ax.grid(axis=axis, color=GRID, linewidth=0.8)


def _percent_axis(ax: Axes, axis: str) -> None:
    ticks = [0, 0.25, 0.5, 0.75, 1.0]
    labels = ["0%", "25%", "50%", "75%", "100%"]
    if axis == "x":
        ax.set_xlim(-0.03, 1.05)
        ax.set_xticks(ticks, labels)
    else:
        ax.set_ylim(0, 1.12)
        ax.set_yticks(ticks, labels)


def _error(rates: list[Rate]) -> list[list[float]]:
    """Asymmetric error-bar lengths for matplotlib (0 where a rate has no runs)."""
    low, high = [], []
    for rate in rates:
        if rate.n:
            ci = rate.ci
            low.append(rate.value - ci[0])
            high.append(ci[1] - rate.value)
        else:
            low.append(0.0)
            high.append(0.0)
    return [low, high]


def asr_heatmap(df: pd.DataFrame) -> Figure | None:
    """ASR for every template (rows) under every defense (columns)."""
    attacked = _attacked(df)
    if attacked.empty:
        return None
    templates = _present([t.id for t in TEMPLATES], attacked["attack_template"])
    defenses = _present(DEFENSE_ORDER, attacked["defense"])
    fig, ax = plt.subplots(figsize=(1.5 * len(defenses) + 2.4, 0.72 * len(templates) + 1.5))
    values = []
    for template in templates:
        row = []
        for defense in defenses:
            cell = attacked[
                (attacked["attack_template"] == template) & (attacked["defense"] == defense)
            ]
            rate = metrics.rate(cell["attack_success"])
            row.append(rate)
        values.append(row)
    numbers = [[r.value for r in row] for row in values]
    ax.imshow(numbers, cmap=ASR_RAMP, vmin=0, vmax=1, aspect="auto")
    for y, row in enumerate(values):
        for x, rate in enumerate(row):
            label = f"{rate.value:.0%}\nn={rate.n}" if rate.n else "no runs"
            color = "white" if rate.n and rate.value >= 0.5 else TEXT
            ax.text(x, y, label, ha="center", va="center", color=color, fontsize=9)
    ax.set_xticks(range(len(defenses)), defenses)
    ax.set_yticks(range(len(templates)), templates)
    ax.set_xticks([x - 0.5 for x in range(1, len(defenses))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(templates))], minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="both", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title("Attack success rate by template and defense")
    fig.tight_layout()
    return fig


def _free_label_spot(x: float, y: float, placed: list[tuple[float, float]]) -> tuple[int, int, str]:
    """First label position around a point that stays clear of the labels placed so far."""
    # Offset in points, the matching shift in axis units, and the text alignment.
    spots = [(8, 8, "left", 1), (8, -16, "left", -1), (-8, 8, "right", 1), (-8, -16, "right", -1)]
    for dx, dy, align, sign in spots:
        anchor = (x + (0.1 if dx > 0 else -0.1), y + sign * 0.03)
        if all(abs(anchor[0] - a) > 0.2 or abs(anchor[1] - b) > 0.06 for a, b in placed):
            placed.append(anchor)
            return dx, dy, align
    placed.append((x + 0.1, y + 0.03))
    return 8, 8, "left"


def tradeoff_scatter(df: pd.DataFrame) -> Figure | None:
    """One point per defense: ASR against benign utility and against utility under attack."""
    table = metrics.overview(df, ["defense"])
    if table.empty:
        return None
    table = table.set_index("defense")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), sharex=True, sharey=True)
    panels = [("utility", "Utility, no attack"), ("utility_under_attack", "Utility under attack")]
    for ax, (column, title) in zip(axes, panels, strict=True):
        placed: list[tuple[float, float]] = []
        for defense in _present(DEFENSE_ORDER, table.index.to_series()):
            asr, utility = table.loc[defense, "asr"], table.loc[defense, column]
            if not asr.n or not utility.n:
                continue
            ax.errorbar(
                asr.value,
                utility.value,
                xerr=_error([asr]),
                yerr=_error([utility]),
                fmt="o",
                markersize=8,
                color=SERIES[0],
                markeredgecolor=SURFACE,
                markeredgewidth=2,
                ecolor=AXIS,
                elinewidth=1.2,
            )
            x_offset, y_offset, align = _free_label_spot(asr.value, utility.value, placed)
            ax.annotate(
                defense,
                (asr.value, utility.value),
                xytext=(x_offset, y_offset),
                textcoords="offset points",
                ha=align,
                color=TEXT,
                fontsize=9,
            )
        _grid(ax, "both")
        _percent_axis(ax, "x")
        _percent_axis(ax, "y")
        ax.set_xlabel("Attack success rate (lower is better)")
        ax.set_title(title)
    axes[0].set_ylabel("Utility (higher is better)")
    fig.suptitle(
        "Best defenses sit top left. Lines show Wilson 95% intervals.",
        x=0.01,
        ha="left",
        fontsize=9.5,
        color=TEXT_SECONDARY,
    )
    fig.tight_layout()
    return fig


def _grouped_bars(
    ax: Axes,
    groups: list[str],
    series: list[str],
    color: Callable[[str], str],
    rate_of: Callable[[str, str], Rate],
) -> None:
    gap = 0.03
    width = min(0.8 / len(series), 0.2) - gap
    step = width + gap
    start = -(len(series) - 1) * step / 2
    for i, name in enumerate(series):
        rates = [rate_of(group, name) for group in groups]
        xs = [g + start + i * step for g in range(len(groups))]
        heights = [r.value if r.n else 0.0 for r in rates]
        ax.bar(xs, heights, width=width, color=color(name), label=name)
        ax.errorbar(
            xs, heights, yerr=_error(rates), fmt="none", ecolor=TEXT_SECONDARY, elinewidth=1
        )
    ax.set_xticks(range(len(groups)), groups)
    ax.tick_params(axis="x", length=0)
    _grid(ax, "y")
    _percent_axis(ax, "y")
    ax.set_ylabel("Attack success rate")


def asr_by_goal(df: pd.DataFrame) -> Figure | None:
    """ASR of each attacker goal, per defense."""
    attacked = _attacked(df)
    if attacked.empty:
        return None
    goals = _present([t.id for t in INJECTION_TASKS], attacked["injection_task"])
    defenses = _present(DEFENSE_ORDER, attacked["defense"])

    def rate_of(goal: str, defense: str) -> Rate:
        cell = attacked[(attacked["injection_task"] == goal) & (attacked["defense"] == defense)]
        return metrics.rate(cell["attack_success"])

    fig, ax = plt.subplots(figsize=(1.9 * len(goals) + 1.6, 4.6))
    _grouped_bars(ax, goals, defenses, DEFENSE_COLOR.__getitem__, rate_of)
    ax.tick_params(axis="x", labelsize=8.5)
    ax.set_title("Attack success rate by attacker goal")
    ax.legend(title="defense", frameon=False, ncols=len(defenses), loc="upper right", fontsize=9)
    fig.tight_layout()
    return fig


def english_vs_persian(df: pd.DataFrame) -> Figure | None:
    """ignore_previous and its Persian version, per defense: only the language differs."""
    attacked = _attacked(df)
    pair = ["ignore_previous", "persian"]
    if not set(pair) <= set(attacked["attack_template"]):
        return None
    defenses = _present(DEFENSE_ORDER, attacked["defense"])
    colors = dict(zip(pair, SERIES[:2], strict=True))
    labels = {"ignore_previous": "English", "persian": "Persian"}

    def rate_of(defense: str, template: str) -> Rate:
        cell = attacked[
            (attacked["defense"] == defense) & (attacked["attack_template"] == template)
        ]
        return metrics.rate(cell["attack_success"])

    fig, ax = plt.subplots(figsize=(1.5 * len(defenses) + 2, 4.4))
    _grouped_bars(ax, defenses, pair, colors.__getitem__, rate_of)
    handles, _ = ax.get_legend_handles_labels()
    ax.legend(handles, [labels[p] for p in pair], frameon=False, loc="upper right")
    ax.set_title("Same attack in English and Persian")
    fig.tight_layout()
    return fig


FIGURES: dict[str, Callable[[pd.DataFrame], Figure | None]] = {
    "asr_heatmap": asr_heatmap,
    "tradeoff_scatter": tradeoff_scatter,
    "asr_by_goal": asr_by_goal,
    "english_vs_persian": english_vs_persian,
}


def markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(columns) + " |", "|" + " --- |" * len(columns)]
    lines += [
        "| " + " | ".join(str(v) for v in row) + " |" for row in frame.itertuples(index=False)
    ]
    return "\n".join(lines)


def tables_markdown(df: pd.DataFrame) -> str:
    sections: list[tuple[str, pd.DataFrame]] = [
        ("Overview", metrics.overview(df)),
        ("Benign utility by user task", metrics.utility_breakdown(df, ["defense", "user_task"])),
    ]
    for key in ("attack_template", "injection_task", "slot", "user_task"):
        sections.append((f"Attacks by {key}", metrics.attack_breakdown(df, ["defense", key])))
    sections += [
        ("Detector", metrics.detector_summary(df)),
        ("Each defense vs none (paired, exact McNemar)", metrics.compare_defenses(df)),
        ("English vs Persian (paired, exact McNemar)", metrics.compare_templates(df)),
    ]
    parts = ["Rates are value [Wilson 95% CI] n=runs. Runs that ended in an error are excluded."]
    parts += [
        f"## {title}\n\n{markdown_table(table)}" for title, table in sections if not table.empty
    ]
    failed = int(df["failed"].sum())
    parts.append(f"Runs excluded because of errors: {failed}")
    return "\n\n".join(parts) + "\n"


def write_report_assets(results: Path, out_dir: Path) -> list[Path]:
    """Write every figure and ``tables.md``. Returns the files written."""
    df = metrics.load_frame(results)
    if df.empty:
        return []
    models = sorted(df["model"].unique())
    written: list[Path] = []
    for model in models:
        target = out_dir if len(models) == 1 else out_dir / re.sub(r"[^\w.-]+", "_", model)
        target.mkdir(parents=True, exist_ok=True)
        subset = df[df["model"] == model]
        for name, build in FIGURES.items():
            figure = build(subset)
            if figure is None:
                continue
            path = target / f"{name}.png"
            figure.savefig(path, dpi=200)
            plt.close(figure)
            written.append(path)
        path = target / "tables.md"
        path.write_text(tables_markdown(subset), encoding="utf-8")
        written.append(path)
    return written
