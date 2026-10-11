from types import SimpleNamespace
from typing import Any

import httpx
import ollama
import pytest

from injectlab.llm.base import LLMError, Message, ToolCall, ToolSpec
from injectlab.llm.ollama_client import OllamaClient, parse_arguments, to_ollama_message

GET_TIME = ToolSpec(name="get_time", description="Current time.")


class FakeOllama:
    """Stands in for ollama.Client: records the request, returns or raises what we set."""

    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict[str, Any] = {}

    def chat(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def make_response(content: str = "", calls: list[tuple[str, Any]] | None = None) -> Any:
    tool_calls = [
        SimpleNamespace(function=SimpleNamespace(name=name, arguments=args))
        for name, args in (calls or [])
    ]
    return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls or None))


def client_with(fake: FakeOllama, **kwargs: Any) -> OllamaClient:
    client = OllamaClient("qwen2.5:3b-instruct", **kwargs)
    client._client = fake  # type: ignore[assignment]
    return client


def test_parses_tool_calls_with_stable_ids() -> None:
    fake = FakeOllama(make_response(calls=[("get_time", {"timezone": "UTC"}), ("get_time", {})]))
    turn = client_with(fake).chat([Message.system("s"), Message.user("u")], [GET_TIME])

    assert [c.name for c in turn.tool_calls] == ["get_time", "get_time"]
    assert turn.tool_calls[0].arguments == {"timezone": "UTC"}
    assert [c.id for c in turn.tool_calls] == ["call_2_0", "call_2_1"]


def test_plain_text_reply_is_final() -> None:
    turn = client_with(FakeOllama(make_response("It is noon."))).chat([], [GET_TIME])
    assert turn.is_final
    assert turn.content == "It is noon."


def test_sends_reproducible_options_and_tools() -> None:
    fake = FakeOllama(make_response("ok"))
    client_with(fake, seed=7).chat([Message.user("u")], [GET_TIME])

    assert fake.kwargs["model"] == "qwen2.5:3b-instruct"
    assert fake.kwargs["options"]["temperature"] == 0.0
    assert fake.kwargs["options"]["seed"] == 7
    assert fake.kwargs["tools"][0]["function"]["name"] == "get_time"


def test_no_tools_sends_none() -> None:
    fake = FakeOllama(make_response("ok"))
    client_with(fake).chat([Message.user("u")], [])
    assert fake.kwargs["tools"] is None


def test_connection_error_has_clear_message() -> None:
    fake = FakeOllama(error=ConnectionError("refused"))
    with pytest.raises(LLMError, match="ollama serve"):
        client_with(fake).chat([], [GET_TIME])


def test_missing_model_suggests_pull() -> None:
    fake = FakeOllama(error=ollama.ResponseError("model not found", status_code=404))
    with pytest.raises(LLMError, match="ollama pull qwen2.5:3b-instruct"):
        client_with(fake).chat([], [GET_TIME])


def test_other_response_errors_are_wrapped() -> None:
    fake = FakeOllama(error=ollama.ResponseError("boom", status_code=500))
    with pytest.raises(LLMError, match="500"):
        client_with(fake).chat([], [GET_TIME])


def test_message_conversion_round_trip_shapes() -> None:
    call = ToolCall(id="c", name="get_time", arguments={"timezone": "UTC"})
    assistant = to_ollama_message(Message(role="assistant", tool_calls=[call]))
    assert assistant["tool_calls"] == [
        {"function": {"name": "get_time", "arguments": {"timezone": "UTC"}}}
    ]

    tool = to_ollama_message(Message.tool(call, "09:30"))
    assert tool == {"role": "tool", "content": "09:30", "tool_name": "get_time"}

    assert to_ollama_message(Message.user("hi")) == {"role": "user", "content": "hi"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"a": 1}, {"a": 1}),
        ('{"a": 1}', {"a": 1}),
        ("not json", {}),
        ("[1, 2]", {}),
        (None, {}),
    ],
)
def test_parse_arguments(raw: Any, expected: dict[str, Any]) -> None:
    assert parse_arguments(raw) == expected


def _ollama_ready(model: str) -> bool:
    try:
        tags = httpx.get("http://localhost:11434/api/tags", timeout=2).json()
    except httpx.HTTPError:
        return False
    return any(m["name"] == model for m in tags.get("models", []))


@pytest.mark.ollama
@pytest.mark.skipif(not _ollama_ready("qwen2.5:3b-instruct"), reason="Ollama/model not available")
def test_real_model_calls_a_tool() -> None:
    client = OllamaClient("qwen2.5:3b-instruct")
    turn = client.chat(
        [Message.user("What time is it? Use the get_time tool.")],
        [GET_TIME],
    )
    assert [c.name for c in turn.tool_calls] == ["get_time"]
