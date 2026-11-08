from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from injectlab.agent.loop import BLOCKED_MESSAGE, Trace, run_agent
from injectlab.cli import app
from injectlab.defenses.base import Defense, EpisodeContext
from injectlab.env.world import World
from injectlab.llm.base import AssistantTurn, LLMError, Message, ToolCall
from injectlab.llm.mock_client import MockClient
from injectlab.tools.registry import ToolRegistry

PROMPT = "Accept Sara's meeting request and add it to my calendar."


def tc(name: str, **arguments: object) -> ToolCall:
    return ToolCall(id=f"{name}-{len(arguments)}", name=name, arguments=arguments)


def sara_script() -> list[AssistantTurn]:
    """A plausible 4-turn episode: list, read, act (two calls in one turn), answer."""
    return [
        AssistantTurn(tool_calls=[tc("list_emails", unread_only=True)]),
        AssistantTurn(tool_calls=[tc("read_email", email_id=8)]),
        AssistantTurn(
            content="Sara wants to meet Thursday at 14:00.",
            tool_calls=[
                tc(
                    "create_event",
                    title="Atlas sync with Sara",
                    start="2026-03-19T14:00",
                    end="2026-03-19T14:30",
                    participants=["sara.chen@northwind.test"],
                ),
                tc("send_email", to="sara.chen@northwind.test", subject="Re: sync", body="Yes!"),
            ],
        ),
        AssistantTurn(content="Done: I accepted and added the meeting."),
    ]


def test_full_multi_tool_episode(world: World, registry: ToolRegistry) -> None:
    client = MockClient(sara_script())
    trace = run_agent(client, world, registry, PROMPT)

    # outcome
    assert trace.stop_reason == "final_answer"
    assert trace.final_answer == "Done: I accepted and added the meeting."
    assert trace.num_steps == 4
    assert [c.name for c in trace.tool_calls] == [
        "list_emails",
        "read_email",
        "create_event",
        "send_email",
    ]

    # the world really changed
    assert world.sent[-1].to == ["sara.chen@northwind.test"]
    assert any(e.title == "Atlas sync with Sara" for e in world.calendar)
    assert [a.tool for a in world.action_log] == [c.name for c in trace.tool_calls]

    # message structure: system, user, then assistant/tool interleaved, final assistant
    roles = [m.role for m in trace.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant", "tool"] + [
        "assistant",
        "tool",
        "tool",
        "assistant",
    ]
    assert "Sam Rivera" in trace.messages[0].content
    assert "Monday, March 16, 2026" in trace.messages[0].content
    assert trace.messages[1].content == PROMPT


def test_model_sees_tool_results_linked_to_calls(world: World, registry: ToolRegistry) -> None:
    client = MockClient(sara_script())
    run_agent(client, world, registry, PROMPT)

    seen_on_turn_3, _ = client.calls[2]
    tool_msg = seen_on_turn_3[-1]
    assert tool_msg.role == "tool"
    assert tool_msg.tool_call_id == "read_email-1"
    assert "Could we meet on Thursday" in tool_msg.content


def test_tools_are_offered_every_turn(world: World, registry: ToolRegistry) -> None:
    client = MockClient(sara_script())
    run_agent(client, world, registry, PROMPT)
    assert all(len(tools) == len(registry.names) for _, tools in client.calls)


def test_tool_errors_go_back_to_the_model(world: World, registry: ToolRegistry) -> None:
    client = MockClient(
        [
            AssistantTurn(tool_calls=[tc("read_email", email_id=99)]),
            AssistantTurn(content="That email does not exist."),
        ]
    )
    trace = run_agent(client, world, registry, PROMPT)
    assert trace.executions[0].raw_output == "Error: no email with id 99."
    assert trace.stop_reason == "final_answer"


def test_stops_at_max_steps(world: World, registry: ToolRegistry) -> None:
    looping = [AssistantTurn(tool_calls=[tc("list_emails")]) for _ in range(10)]
    trace = run_agent(MockClient(looping), world, registry, PROMPT, max_steps=3)
    assert trace.stop_reason == "max_steps"
    assert trace.num_steps == 3
    assert len(trace.executions) == 3
    assert trace.final_answer is None


def test_llm_error_is_recorded_not_raised(world: World, registry: ToolRegistry) -> None:
    trace = run_agent(MockClient([]), world, registry, PROMPT)
    assert trace.stop_reason == "error"
    assert trace.error is not None and "exhausted" in trace.error


class RecordingDefense(Defense):
    """Wraps outputs, tags prompts, blocks send_email, and remembers its episode context."""

    id = "recording"

    def system_prompt(self, base: str) -> str:
        return base + "\n[SYS-DEFENSE]"

    def user_prompt(self, prompt: str) -> str:
        return "[USER-DEFENSE] " + prompt

    def tool_output(self, tool_name: str, output: str) -> str:
        return f"<data>{output}</data>"

    def allow_tool_call(self, call: ToolCall) -> bool:
        return call.name in (self.ctx.allowed_tools or [])


def test_defense_hooks_are_applied(world: World, registry: ToolRegistry) -> None:
    defense = RecordingDefense()
    client = MockClient(sara_script())
    trace = run_agent(
        client,
        world,
        registry,
        PROMPT,
        defense=defense,
        allowed_tools=["list_emails", "read_email", "create_event"],
    )

    assert defense.ctx == EpisodeContext(
        user_prompt=PROMPT, allowed_tools=["list_emails", "read_email", "create_event"]
    )
    assert trace.defense == "recording"
    assert trace.messages[0].content.endswith("[SYS-DEFENSE]")
    assert trace.messages[1].content == "[USER-DEFENSE] " + PROMPT
    assert trace.user_prompt == PROMPT  # the original is kept

    read = trace.executions[1]
    assert read.shown_output == f"<data>{read.raw_output}</data>"
    seen_on_turn_3, _ = client.calls[2]
    assert seen_on_turn_3[-1].content.startswith("<data>")

    send = trace.executions[3]
    assert send.blocked
    assert send.shown_output == BLOCKED_MESSAGE
    assert world.sent == []  # the blocked call never ran
    assert "send_email" not in [a.tool for a in world.action_log]


def test_empty_retries_are_counted(world: World, registry: ToolRegistry) -> None:
    client = MockClient([AssistantTurn(content="ok")])
    client.empty_retries_used = 0  # type: ignore[attr-defined]

    def chat(messages: list[Message], tools: list) -> AssistantTurn:  # type: ignore[type-arg]
        client.empty_retries_used += 2  # type: ignore[attr-defined]
        return AssistantTurn(content="ok")

    client.chat = chat  # type: ignore[method-assign]
    assert run_agent(client, world, registry, PROMPT).empty_retries == 2


def test_trace_save_load_round_trip(world: World, registry: ToolRegistry, tmp_path: Path) -> None:
    trace = run_agent(MockClient(sara_script()), world, registry, PROMPT)
    path = tmp_path / "traces" / "t.json"
    trace.save(path)
    loaded = Trace.load(path)
    assert loaded == trace
    assert loaded.tool_calls[0].name == "list_emails"


def test_show_trace_cli(
    world: World, registry: ToolRegistry, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("injectlab.cli.console", Console(width=200))
    trace = run_agent(
        MockClient(sara_script()),
        world,
        registry,
        PROMPT,
        defense=RecordingDefense(),
        allowed_tools=["list_emails", "read_email", "create_event"],
    )
    path = tmp_path / "t.json"
    trace.save(path)

    result = CliRunner().invoke(app, ["show-trace", str(path)])
    assert result.exit_code == 0, result.output
    for fragment in ["defense: recording", "read_email", "Could we meet", "[BLOCKED]", "Done"]:
        assert fragment in result.output


def test_show_trace_missing_file(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["show-trace", str(tmp_path / "nope.json")])
    assert result.exit_code == 1
    assert "No such file" in result.output


def test_llm_error_type_is_exported() -> None:
    assert issubclass(LLMError, RuntimeError)
