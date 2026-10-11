"""Provider-independent chat types and the LLMClient protocol.

The rest of the codebase only talks to models through these types, so the agent loop,
the defenses, and the tests never depend on a specific backend.
"""

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    """A request from the model to run one tool with the given arguments."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    """One entry in the conversation sent to the model.

    - ``assistant`` messages may carry ``tool_calls``.
    - ``tool`` messages carry the output of one call, linked by ``tool_call_id`` and ``name``.
    """

    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    @classmethod
    def system(cls, content: str) -> "Message":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        return cls(role="user", content=content)

    @classmethod
    def tool(cls, call: ToolCall, content: str) -> "Message":
        return cls(role="tool", content=content, tool_call_id=call.id, name=call.name)


class AssistantTurn(BaseModel):
    """What the model returned for one chat request."""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)

    @property
    def is_final(self) -> bool:
        """True when the model answered in text instead of asking for tools."""
        return not self.tool_calls

    def to_message(self) -> Message:
        return Message(role="assistant", content=self.content, tool_calls=self.tool_calls)


class ToolSpec(BaseModel):
    """A tool the model may call: its name, description, and JSON schema for arguments."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "required": []}
    )

    def to_json_schema(self) -> dict[str, Any]:
        """The OpenAI-style function definition that Ollama expects."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class LLMError(RuntimeError):
    """Raised when a model backend cannot produce a turn."""


class LLMClient(Protocol):
    """Anything that can take a conversation plus tools and return the next assistant turn."""

    model: str

    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> AssistantTurn: ...
