"""The tool-calling agent loop.

    system + user prompt
    repeat up to max_steps:
        model turn
        no tool calls?  -> final answer, stop
        for each call:  defense may block it, otherwise run it against the World;
                        defense may rewrite the output; append it as a tool message

Everything that happens is recorded in a Trace.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from injectlab.agent.prompts import build_system_prompt
from injectlab.defenses.base import Defense, EpisodeContext
from injectlab.defenses.none import NoDefense
from injectlab.env.world import World
from injectlab.llm.base import LLMClient, LLMError, Message, ToolCall
from injectlab.tools.registry import ToolRegistry

DEFAULT_MAX_STEPS = 15
BLOCKED_MESSAGE = "Error: this tool call was blocked by a security policy."

StopReason = Literal["final_answer", "max_steps", "error"]


class ToolExecution(BaseModel):
    """One tool call and what came of it."""

    step: int
    call: ToolCall
    blocked: bool = False
    raw_output: str  # what the tool returned
    shown_output: str  # what the model saw, after the defense's tool_output hook


class Trace(BaseModel):
    model: str
    defense: str
    user_prompt: str
    messages: list[Message] = Field(default_factory=list)
    executions: list[ToolExecution] = Field(default_factory=list)
    final_answer: str | None = None
    num_steps: int = 0
    stop_reason: StopReason = "final_answer"
    error: str | None = None
    empty_retries: int = 0

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [e.call for e in self.executions]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Trace":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))


def run_agent(
    client: LLMClient,
    world: World,
    registry: ToolRegistry,
    user_prompt: str,
    *,
    defense: Defense | None = None,
    allowed_tools: list[str] | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> Trace:
    """Run one episode. ``world`` is modified in place by the tools."""
    defense = defense or NoDefense()
    defense.begin_episode(EpisodeContext(user_prompt=user_prompt, allowed_tools=allowed_tools))

    trace = Trace(model=client.model, defense=defense.id, user_prompt=user_prompt)
    trace.messages = [
        Message.system(defense.system_prompt(build_system_prompt(world))),
        Message.user(defense.user_prompt(user_prompt)),
    ]
    retries_before = getattr(client, "empty_retries_used", 0)
    specs = registry.specs()

    try:
        for step in range(1, max_steps + 1):
            trace.num_steps = step
            try:
                turn = client.chat(trace.messages, specs)
            except LLMError as exc:
                trace.stop_reason, trace.error = "error", str(exc)
                return trace

            trace.messages.append(turn.to_message())
            if turn.is_final:
                trace.final_answer = turn.content
                trace.stop_reason = "final_answer"
                return trace

            for call in turn.tool_calls:
                trace.messages.append(_execute(call, step, world, registry, defense, trace))

        trace.stop_reason = "max_steps"
        return trace
    finally:
        trace.empty_retries = getattr(client, "empty_retries_used", 0) - retries_before


def _execute(
    call: ToolCall,
    step: int,
    world: World,
    registry: ToolRegistry,
    defense: Defense,
    trace: Trace,
) -> Message:
    if defense.allow_tool_call(call):
        raw = registry.dispatch(world, call)
        shown = defense.tool_output(call.name, raw)
        blocked = False
    else:
        raw = shown = BLOCKED_MESSAGE
        blocked = True
    trace.executions.append(
        ToolExecution(step=step, call=call, blocked=blocked, raw_output=raw, shown_output=shown)
    )
    return Message.tool(call, shown)
