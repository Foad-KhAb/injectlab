import pytest

from injectlab.llm.base import AssistantTurn, LLMError, Message, ToolCall, ToolSpec
from injectlab.llm.mock_client import MockClient

TOOLS = [ToolSpec(name="list_emails", description="List emails.")]


def test_replays_turns_in_order() -> None:
    first = AssistantTurn(tool_calls=[ToolCall(id="c0", name="list_emails")])
    second = AssistantTurn(content="You have no email.")
    client = MockClient([first, second])

    assert client.chat([Message.user("hi")], TOOLS) == first
    assert client.chat([Message.user("hi")], TOOLS) == second
    assert client.remaining == 0


def test_records_what_the_model_saw() -> None:
    client = MockClient([AssistantTurn(content="ok")])
    messages = [Message.system("sys"), Message.user("hello")]
    client.chat(messages, TOOLS)

    seen_messages, seen_tools = client.calls[0]
    assert [m.content for m in seen_messages] == ["sys", "hello"]
    assert seen_tools == TOOLS


def test_recorded_messages_are_snapshots() -> None:
    client = MockClient([AssistantTurn(content="ok")])
    messages = [Message.user("original")]
    client.chat(messages, TOOLS)
    messages[0].content = "mutated later"
    assert client.calls[0][0][0].content == "original"


def test_raises_when_script_runs_out() -> None:
    client = MockClient([AssistantTurn(content="only one")])
    client.chat([], TOOLS)
    with pytest.raises(LLMError, match="exhausted"):
        client.chat([], TOOLS)
