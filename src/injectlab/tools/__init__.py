"""Simulated tools the agent can call."""

from injectlab.tools import calendar_tools, email_tools, web_tools
from injectlab.tools.registry import ToolRegistry


def default_registry() -> ToolRegistry:
    """A registry with every email, web and calendar tool."""
    return ToolRegistry(email_tools.TOOLS + web_tools.TOOLS + calendar_tools.TOOLS)
