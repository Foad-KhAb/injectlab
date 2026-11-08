# InjectLab

A small research testbed for **indirect prompt injection** against tool-using LLM agents.

An agent running on a local open model does ordinary tasks for a simulated user: reading
email, fetching web pages, and managing a calendar. Some of the content it reads has been
planted by an attacker. InjectLab measures:

- **Utility**: how often the agent completes the user's task when no attack is present.
- **Utility under attack**: how often it still completes the user's task when attacked.
- **Attack success rate (ASR)**: how often the agent carries out the attacker's goal.

It then measures how much each defense (spotlighting, sandwiching, tool filtering, an injection
detector) lowers ASR and how much utility it costs. The design follows
[AgentDojo](https://arxiv.org/abs/2406.13352) (Debenedetti et al., 2024) at a smaller scale.

Success is judged by deterministic checkers that inspect the final simulated world state, never
by an LLM judge.

> **Scope:** everything is simulated. Tools never send real email or make network calls, all
> addresses use the reserved `.test` domain, and models run locally.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# install uv (once)
curl -LsSf https://astral.sh/uv/install.sh | sh

# install the project and dev tools into .venv
uv sync

# optional: dependencies for the classifier-based detector defense
uv sync --extra detector
```

A later plain `uv sync` removes the optional dependencies again, so keep `--extra detector`.

## Local models with Ollama

Install Ollama from <https://ollama.com/download>. The official installer needs sudo:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Without sudo, unpack the release into your home directory:

```bash
mkdir -p ~/.local/ollama
curl -fsSL https://ollama.com/download/ollama-linux-amd64.tar.zst | zstd -d | tar -x -C ~/.local/ollama
ln -sf ~/.local/ollama/bin/ollama ~/.local/bin/ollama
```

Start the server (it isn't needed if the official installer set up the systemd service), then pull the models:

```bash
ollama serve &                     # leave running
ollama pull qwen2.5:7b-instruct    # default model (experiments)
ollama pull qwen2.5:3b-instruct    # optional: faster, but weak at multi-step tool use
ollama pull llama3.1:8b
```

`qwen2.5:7b-instruct` is the default. On a CPU-only machine it takes a minute or more per task;
pass `--model qwen2.5:3b-instruct` to the scripts for quicker (but less reliable) runs.

## Usage

```bash
uv run injectlab --help
uv run python scripts/run_episode.py "Summarize my unread emails."  # one real-model episode
uv run python scripts/baseline_utility.py                          # all user tasks, no attack
uv run python scripts/attack_episode.py package_arrival forward_bank_code important_message
uv run injectlab run configs/dev.yaml    # small end-to-end experiment; rerun to resume
uv run injectlab analyze results/<run>.jsonl
uv run injectlab show-trace results/<trace>.json
```

## Development

```bash
uv run pytest                  # all tests
uv run pytest -m "not ollama"  # skip tests that need a running Ollama server
uv run python scripts/smoke_ollama.py  # check the local model can make a tool call
uv run ruff check .            # lint
uv run ruff format .           # format
```
