"""Turn plain Python functions into model-callable tools.

A tool is a function whose first parameter is the World and whose other parameters are
type-hinted (optionally with ``Annotated[..., Field(description=...)]``). The registry builds
the JSON schema from those hints, validates the model's arguments, runs the function, and
records every call in ``world.action_log``.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from injectlab.env.world import ActionLogEntry, World
from injectlab.llm.base import ToolCall, ToolSpec

ToolFn = Callable[..., str]


class ToolError(Exception):
    """An expected failure the model should see, e.g. "no email with id 42"."""


@dataclass(frozen=True)
class Tool:
    name: str
    fn: ToolFn
    args_model: type[BaseModel]
    spec: ToolSpec


class ToolRegistry:
    def __init__(self, fns: list[ToolFn] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for fn in fns or []:
            self.register(fn)

    def register(self, fn: ToolFn) -> ToolFn:
        """Register ``fn`` as a tool. Usable as a decorator."""
        tool = _build_tool(fn)
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} is already registered.")
        self._tools[tool.name] = tool
        return fn

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def subset(self, names: list[str]) -> "ToolRegistry":
        """A registry containing only the named tools (used by the tool-filter defense)."""
        unknown = set(names) - set(self._tools)
        if unknown:
            raise KeyError(f"Unknown tool(s): {sorted(unknown)}")
        return ToolRegistry([self._tools[n].fn for n in names])

    def dispatch(self, world: World, call: ToolCall) -> str:
        """Run one tool call against ``world``, log it, and return the text the model sees."""
        ok, output = self._run(world, call)
        world.action_log.append(
            ActionLogEntry(tool=call.name, arguments=call.arguments, ok=ok, output=output)
        )
        return output

    def _run(self, world: World, call: ToolCall) -> tuple[bool, str]:
        tool = self._tools.get(call.name)
        if tool is None:
            return False, f"Error: unknown tool {call.name!r}. Available: {', '.join(self.names)}."
        try:
            args = tool.args_model.model_validate(call.arguments)
        except ValidationError as exc:
            return False, f"Error: invalid arguments for {call.name}: {_format_errors(exc)}"
        try:
            return True, tool.fn(world, **dict(args))
        except ToolError as exc:
            return False, f"Error: {exc}"


def _build_tool(fn: ToolFn) -> Tool:
    params = list(inspect.signature(fn).parameters.values())
    if not params or params[0].name != "world":
        raise TypeError(f"Tool {fn.__name__} must take `world` as its first parameter.")

    fields: dict[str, Any] = {}
    for p in params[1:]:
        if p.annotation is inspect.Parameter.empty:
            raise TypeError(f"Parameter {p.name!r} of tool {fn.__name__} needs a type hint.")
        default = ... if p.default is inspect.Parameter.empty else p.default
        fields[p.name] = (p.annotation, default)

    args_model = create_model(  # type: ignore[call-overload]
        f"{fn.__name__}_args", __config__=ConfigDict(extra="forbid"), **fields
    )
    description = inspect.getdoc(fn) or ""
    spec = ToolSpec(
        name=fn.__name__,
        description=description.split("\n\n")[0].replace("\n", " "),
        parameters=_clean_schema(args_model.model_json_schema()),
    )
    return Tool(name=fn.__name__, fn=fn, args_model=args_model, spec=spec)


def _clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip pydantic's cosmetic keys so the schema the model sees is short and plain.

    Optional parameters (``X | None``) become plain ``X``: the model expresses "none" by
    omitting the argument, and small models handle ``anyOf`` poorly.
    """
    properties = {}
    for name, prop in schema.get("properties", {}).items():
        prop = {k: v for k, v in prop.items() if k != "title"}
        variants = [v for v in prop.pop("anyOf", []) if v.get("type") != "null"]
        if len(variants) == 1:
            prop.update(variants[0])
        elif variants:
            prop["anyOf"] = variants
        properties[name] = prop
    return {
        "type": "object",
        "properties": properties,
        "required": schema.get("required", []),
    }


def _format_errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "arguments"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)
