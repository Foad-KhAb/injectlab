"""Tool filter: only allow the tools that the user's task actually needs.

Enforced outside the model, so it holds however convincing the injection is. It needs the tool
list in advance, and it judges the tool name only: if the task needs ``send_email``, a message
to the attacker still passes.
"""

from injectlab.defenses.base import Defense
from injectlab.llm.base import ToolCall


class ToolFilterDefense(Defense):
    id = "tool_filter"

    def allow_tool_call(self, call: ToolCall) -> bool:
        allowed = self.ctx.allowed_tools
        return allowed is None or call.name in allowed
