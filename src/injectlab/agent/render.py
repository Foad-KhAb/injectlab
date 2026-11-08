"""Readable console rendering of a Trace."""

import json

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from injectlab.agent.loop import Trace

SYSTEM_PREVIEW_LINES = 3


def render_trace(trace: Trace, console: Console, *, full: bool = False) -> None:
    """Print a trace. ``full`` shows the whole system prompt instead of a preview."""
    blocked_ids = {e.call.id for e in trace.executions if e.blocked}
    header = (
        f"model: {trace.model}   defense: {trace.defense}   steps: {trace.num_steps}   "
        f"stop: {trace.stop_reason}   tool calls: {len(trace.executions)}"
    )
    if trace.empty_retries:
        header += f"   empty retries: {trace.empty_retries}"
    console.print(Panel(header, title="trace", border_style="cyan"))

    for msg in trace.messages:
        if msg.role == "system":
            lines = msg.content.splitlines()
            shown = lines if full else lines[:SYSTEM_PREVIEW_LINES]
            body = "\n".join(shown) + ("" if full or len(lines) <= len(shown) else "\n…")
            console.print(Panel(Text(body), title="system", border_style="dim", style="dim"))
        elif msg.role == "user":
            console.print(Panel(Text(msg.content), title="user", border_style="green"))
        elif msg.role == "assistant":
            parts = [msg.content] if msg.content else []
            parts += [f"→ {c.name}({json.dumps(c.arguments)})" for c in msg.tool_calls]
            console.print(Panel(Text("\n".join(parts)), title="assistant", border_style="blue"))
        else:
            blocked = msg.tool_call_id in blocked_ids
            title = f"tool: {msg.name}" + (" [BLOCKED]" if blocked else "")
            style = "red" if blocked or msg.content.startswith("Error:") else "yellow"
            console.print(Panel(Text(msg.content), title=title, border_style=style))

    if trace.error:
        console.print(f"[red]error:[/red] {trace.error}")
