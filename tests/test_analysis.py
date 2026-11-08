"""Tests for paired comparisons, the report's figures and tables, and the plot command."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from injectlab import cli
from injectlab.analysis import plots
from injectlab.attacks.injection_tasks import INJECTION_TASKS
from injectlab.attacks.templates import TEMPLATES
from injectlab.defenses import DEFENSES
from injectlab.eval import metrics
from injectlab.eval.config import RunSpec
from injectlab.eval.runner import ResultRow


def make_row(spec: RunSpec, user: bool, attack: bool | None) -> ResultRow:
    return ResultRow(
        run_id=spec.run_id,
        experiment="t",
        git_commit="abc",
        timestamp="2026-01-01T00:00:00",
        model=spec.model,
        defense=spec.defense,
        user_task=spec.user_task,
        injection_task=spec.injection_task,
        attack_template=spec.template,
        slot=spec.slot,
        seed=spec.seed,
        user_task_success=user,
        attack_success=attack,
        answer_mentions_attacker=attack,
        num_steps=2,
        tool_calls=["read_email"],
        stop_reason="final_answer",
        error=None,
        empty_retries=0,
        duration_s=1.0,
        trace_path=None,
    )


def full_rows(model: str = "m") -> list[ResultRow]:
    rows = []
    for defense in DEFENSES:
        for task in ("u1", "u2"):
            rows.append(make_row(RunSpec(model=model, defense=defense, user_task=task), True, None))
            for injection in INJECTION_TASKS:
                for template in TEMPLATES:
                    spec = RunSpec(
                        model=model,
                        defense=defense,
                        user_task=task,
                        injection_task=injection.id,
                        template=template.id,
                        slot="s",
                    )
                    rows.append(make_row(spec, task == "u1", defense == "none" and task == "u1"))
    return rows


def write_rows(path: Path, rows: list[ResultRow]) -> Path:
    path.write_text("".join(r.model_dump_json() + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("only_a", "only_b", "expected"),
    [(0, 0, 1.0), (5, 5, 1.0), (6, 0, 0.03125), (0, 6, 0.03125), (10, 2, 0.03857)],
)
def test_exact_mcnemar_known_values(only_a: int, only_b: int, expected: float) -> None:
    assert metrics.exact_mcnemar(only_a, only_b) == pytest.approx(expected, abs=1e-4)


def test_compare_defenses_pairs_identical_attacks() -> None:
    df = metrics.to_frame(full_rows())
    table = metrics.compare_defenses(df)
    row = table[(table["defense"] == "sandwich") & (table["metric"] == "asr")].iloc[0]
    assert (row["none"].k, row["none"].n) == (25, 50)
    assert (row["defense_rate"].k, row["defense_rate"].n) == (0, 50)
    assert (row["only_a"], row["only_b"]) == (25, 0)
    assert row["p"] < 0.001
    assert "none" not in set(table["defense"])


def test_compare_templates_reports_each_defense() -> None:
    table = metrics.compare_templates(metrics.to_frame(full_rows()))
    assert set(table["defense"]) == set(DEFENSES)
    assert table.iloc[0]["ignore_previous"].n == 10


def test_write_report_assets_creates_all_files(tmp_path: Path) -> None:
    results = write_rows(tmp_path / "r.jsonl", full_rows())
    written = plots.write_report_assets(results, tmp_path / "fig")
    assert {p.name for p in written} == {f"{n}.png" for n in plots.FIGURES} | {"tables.md"}
    assert all(p.stat().st_size > 0 for p in written)
    tables = (tmp_path / "fig" / "tables.md").read_text(encoding="utf-8")
    assert "## Overview" in tables
    assert "## Each defense vs none" in tables
    assert "Runs excluded because of errors: 0" in tables


def test_each_model_gets_its_own_folder(tmp_path: Path) -> None:
    results = write_rows(tmp_path / "r.jsonl", full_rows("a:1") + full_rows("b:2"))
    plots.write_report_assets(results, tmp_path / "fig")
    assert (tmp_path / "fig" / "a_1" / "asr_heatmap.png").exists()
    assert (tmp_path / "fig" / "b_2" / "tables.md").exists()


def test_partial_results_skip_figures_that_have_no_data(tmp_path: Path) -> None:
    keep = [r for r in full_rows() if r.attack_template in (None, "important_message")]
    results = write_rows(tmp_path / "r.jsonl", keep)
    names = {p.name for p in plots.write_report_assets(results, tmp_path / "fig")}
    assert "english_vs_persian.png" not in names
    assert "asr_heatmap.png" in names


def test_benign_only_results_still_write_tables(tmp_path: Path) -> None:
    keep = [r for r in full_rows() if r.injection_task is None]
    results = write_rows(tmp_path / "r.jsonl", keep)
    names = {p.name for p in plots.write_report_assets(results, tmp_path / "fig")}
    assert "tables.md" in names
    assert "asr_heatmap.png" not in names


def test_cli_plot(tmp_path: Path) -> None:
    results = write_rows(tmp_path / "r.jsonl", full_rows())
    outcome = CliRunner().invoke(
        cli.app, ["plot", str(results), "--out-dir", str(tmp_path / "fig")]
    )
    assert outcome.exit_code == 0, outcome.output
    assert (tmp_path / "fig" / "tradeoff_scatter.png").exists()
    assert CliRunner().invoke(cli.app, ["plot", str(tmp_path / "x.jsonl")]).exit_code == 1
