from collections.abc import Callable
from typing import Any

import pytest

from injectlab.env.seed import benign_world
from injectlab.env.world import World
from injectlab.llm.base import ToolCall
from injectlab.tools import default_registry
from injectlab.tools.registry import ToolRegistry

CallTool = Callable[..., str]


@pytest.fixture
def world() -> World:
    return benign_world()


@pytest.fixture
def registry() -> ToolRegistry:
    return default_registry()


@pytest.fixture
def call(world: World, registry: ToolRegistry) -> CallTool:
    """Dispatch a tool call against the fixture world: call("read_email", email_id=3)."""

    def _call(name: str, **arguments: Any) -> str:
        return registry.dispatch(world, ToolCall(id="t", name=name, arguments=arguments))

    return _call
