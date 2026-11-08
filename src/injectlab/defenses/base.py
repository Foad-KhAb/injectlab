"""The Defense interface: hooks the agent loop calls at fixed points in every episode.

A defense can rewrite the system prompt, the user prompt, and every tool output before the
model sees them, and can veto tool calls before they run. The base class passes everything
through unchanged, so a defense only overrides the hooks it needs.
"""

from pydantic import BaseModel

from injectlab.llm.base import ToolCall


class EpisodeContext(BaseModel):
    """What a defense may know about the current episode."""

    user_prompt: str
    allowed_tools: list[str] | None = None


class Defense:
    id: str = "base"

    def __init__(self) -> None:
        self.ctx = EpisodeContext(user_prompt="")

    def begin_episode(self, ctx: EpisodeContext) -> None:
        """Called once before the first model turn."""
        self.ctx = ctx

    def system_prompt(self, base: str) -> str:
        return base

    def user_prompt(self, prompt: str) -> str:
        return prompt

    def tool_output(self, tool_name: str, output: str) -> str:
        """Transform a tool's output before the model sees it."""
        return output

    def allow_tool_call(self, call: ToolCall) -> bool:
        """Return False to block a call; the tool is then not executed."""
        return True
