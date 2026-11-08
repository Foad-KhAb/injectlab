"""Run one real-model episode on the benign world and save its trace.

Usage:
    uv run python scripts/run_episode.py "Summarize my unread emails." [--model M] [--out PATH]
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from injectlab.agent.loop import run_agent
from injectlab.agent.render import render_trace
from injectlab.env.seed import benign_world
from injectlab.llm.ollama_client import DEFAULT_MODEL, OllamaClient
from injectlab.tools import default_registry


def main(
    prompt: str,
    model: Annotated[str, typer.Option()] = DEFAULT_MODEL,
    out: Annotated[Path, typer.Option()] = Path("results/traces/episode.json"),
    max_steps: Annotated[int, typer.Option()] = 15,
) -> None:
    world = benign_world()
    trace = run_agent(OllamaClient(model), world, default_registry(), prompt, max_steps=max_steps)
    trace.save(out)
    render_trace(trace, Console())
    print(f"\nTrace saved to {out}. Emails sent: {len(world.sent)}. Events: {len(world.calendar)}.")


if __name__ == "__main__":
    typer.run(main)
