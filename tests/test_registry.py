from typing import Annotated

import pytest
from pydantic import Field

from injectlab.env.world import World
from injectlab.llm.base import ToolCall
from injectlab.tools import default_registry
from injectlab.tools.registry import ToolError, ToolRegistry


def greet(
    world: World,
    name: Annotated[str, Field(description="Who to greet.")],
    times: int = 1,
    note: str | None = None,
) -> str:
    """Greet someone.

    Extra detail that should not be in the tool description.
    """
    return " ".join([f"Hello {name}"] * times)


def fail(world: World) -> str:
    """Always fails."""
    raise ToolError("something expected went wrong")


def make(world: World) -> ToolRegistry:
    return ToolRegistry([greet, fail])


def test_schema_generated_from_type_hints() -> None:
    spec = ToolRegistry([greet]).specs()[0]
    assert spec.name == "greet"
    assert spec.description == "Greet someone."
    props = spec.parameters["properties"]
    assert props["name"] == {"type": "string", "description": "Who to greet."}
    assert props["times"]["type"] == "integer"
    assert props["note"]["type"] == "string"  # Optional collapsed to plain type
    assert "anyOf" not in props["note"]
    assert spec.parameters["required"] == ["name"]


def test_dispatch_runs_tool_and_logs(world: World) -> None:
    out = make(world).dispatch(world, ToolCall(id="1", name="greet", arguments={"name": "Ana"}))
    assert out == "Hello Ana"
    entry = world.action_log[-1]
    assert (entry.tool, entry.arguments, entry.ok, entry.output) == (
        "greet",
        {"name": "Ana"},
        True,
        "Hello Ana",
    )


def test_unknown_tool_is_an_error_not_a_crash(world: World) -> None:
    out = make(world).dispatch(world, ToolCall(id="1", name="rm_rf", arguments={}))
    assert out.startswith("Error: unknown tool 'rm_rf'")
    assert "greet" in out
    assert world.action_log[-1].ok is False


@pytest.mark.parametrize(
    ("arguments", "fragment"),
    [
        ({}, "name: Field required"),
        ({"name": "Ana", "times": "many"}, "times:"),
        ({"name": "Ana", "colour": "red"}, "colour: Extra inputs are not permitted"),
    ],
)
def test_bad_arguments_are_reported(world: World, arguments: dict, fragment: str) -> None:
    out = make(world).dispatch(world, ToolCall(id="1", name="greet", arguments=arguments))
    assert out.startswith("Error: invalid arguments for greet")
    assert fragment in out
    assert world.action_log[-1].ok is False


def test_numeric_strings_are_coerced(world: World) -> None:
    call = ToolCall(id="1", name="greet", arguments={"name": "Ana", "times": "2"})
    assert make(world).dispatch(world, call) == "Hello Ana Hello Ana"


def test_tool_error_is_shown_to_model(world: World) -> None:
    out = make(world).dispatch(world, ToolCall(id="1", name="fail", arguments={}))
    assert out == "Error: something expected went wrong"
    assert world.action_log[-1].ok is False


def test_registration_rules() -> None:
    registry = ToolRegistry([greet])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(greet)

    def no_world(name: str) -> str:
        return name

    with pytest.raises(TypeError, match="world"):
        ToolRegistry([no_world])

    def untyped(world: World, name) -> str:  # type: ignore[no-untyped-def]
        return name

    with pytest.raises(TypeError, match="type hint"):
        ToolRegistry([untyped])


def test_subset_keeps_only_named_tools() -> None:
    full = default_registry()
    small = full.subset(["read_email", "list_emails"])
    assert sorted(small.names) == ["list_emails", "read_email"]
    with pytest.raises(KeyError):
        full.subset(["send_email", "launch_rocket"])


def test_default_registry_specs_are_valid() -> None:
    specs = default_registry().specs()
    assert len(specs) == 9
    for spec in specs:
        assert spec.description
        assert spec.parameters["type"] == "object"
        for name in spec.parameters["required"]:
            assert name in spec.parameters["properties"]
        for prop in spec.parameters["properties"].values():
            assert prop.get("description"), f"{spec.name} has an undocumented parameter"
