from injectlab.llm.base import AssistantTurn, Message, ToolCall, ToolSpec


def test_tool_message_links_to_its_call() -> None:
    call = ToolCall(id="call_1_0", name="read_email", arguments={"email_id": 3})
    msg = Message.tool(call, "Hello")
    assert msg.role == "tool"
    assert msg.tool_call_id == "call_1_0"
    assert msg.name == "read_email"
    assert msg.content == "Hello"


def test_assistant_turn_is_final_only_without_tool_calls() -> None:
    assert AssistantTurn(content="done").is_final
    call = ToolCall(id="c", name="list_emails")
    assert not AssistantTurn(tool_calls=[call]).is_final


def test_assistant_turn_to_message_keeps_tool_calls() -> None:
    call = ToolCall(id="c", name="list_emails", arguments={"unread": True})
    msg = AssistantTurn(content="", tool_calls=[call]).to_message()
    assert msg.role == "assistant"
    assert msg.tool_calls == [call]


def test_tool_spec_json_schema_shape() -> None:
    spec = ToolSpec(
        name="fetch_url",
        description="Fetch a web page.",
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    )
    schema = spec.to_json_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "fetch_url"
    assert schema["function"]["parameters"]["required"] == ["url"]


def test_tool_spec_defaults_to_no_arguments() -> None:
    spec = ToolSpec(name="get_time", description="Current time.")
    assert spec.to_json_schema()["function"]["parameters"]["properties"] == {}
