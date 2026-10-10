"""Placeholder tests: the package imports and the CLI is wired up."""

from typer.testing import CliRunner

import injectlab
from injectlab.cli import app

runner = CliRunner()


def test_package_has_version() -> None:
    assert injectlab.__version__ == "0.1.0"


def test_cli_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "analyze", "show-trace"):
        assert command in result.output


def test_unimplemented_command_exits_nonzero() -> None:
    result = runner.invoke(app, ["analyze", "results/none.jsonl"])
    assert result.exit_code == 1
    assert "Not implemented yet" in result.output
