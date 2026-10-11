"""Smoke test: ask a real Ollama model to call a dummy `get_time` tool.

Usage:
    uv run python scripts/smoke_ollama.py [MODEL]
"""

import sys

from rich.console import Console

from injectlab.llm.base import LLMError, Message, ToolSpec
from injectlab.llm.ollama_client import OllamaClient

FAKE_TIME = "2026-01-15T09:30:00+00:00"

GET_TIME = ToolSpec(
    name="get_time",
    description="Get the current date and time in ISO 8601 format.",
    parameters={
        "type": "object",
        "properties": {
            "timezone": {"type": "string", "description": "IANA timezone name, e.g. 'UTC'."}
        },
        "required": [],
    },
)


def main(model: str = "qwen2.5:3b-instruct") -> int:
    console = Console()
    client = OllamaClient(model)
    messages = [
        Message.system("You are a helpful assistant. Use tools when they help."),
        Message.user("What time is it right now? Use the get_time tool."),
    ]

    try:
        turn = client.chat(messages, [GET_TIME])
    except LLMError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    if turn.is_final:
        console.print(f"[red]No tool call. Model replied:[/red] {turn.content!r}")
        return 1

    for call in turn.tool_calls:
        console.print(f"[green]Tool call:[/green] {call.name}({call.arguments})  id={call.id}")

    messages.append(turn.to_message())
    for call in turn.tool_calls:
        messages.append(Message.tool(call, FAKE_TIME))

    final = client.chat(messages, [GET_TIME])
    console.print(f"[green]Final answer:[/green] {final.content}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
