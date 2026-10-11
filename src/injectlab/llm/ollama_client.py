"""LLMClient backed by a local Ollama server and its tool-calling chat API."""

import json
from typing import Any

import ollama

from injectlab.llm.base import AssistantTurn, LLMError, Message, ToolCall, ToolSpec

DEFAULT_HOST = "http://localhost:11434"


class OllamaClient:
    """Chat with a local Ollama model, passing tool definitions on every request.

    Defaults are chosen for reproducibility: temperature 0 and a fixed seed.
    """

    def __init__(
        self,
        model: str,
        *,
        temperature: float = 0.0,
        seed: int = 0,
        num_ctx: int = 8192,
        host: str = DEFAULT_HOST,
        timeout: float = 300.0,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.num_ctx = num_ctx
        self.host = host
        self._client = ollama.Client(host=host, timeout=timeout)

    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> AssistantTurn:
        try:
            response = self._client.chat(
                model=self.model,
                messages=[to_ollama_message(m) for m in messages],
                tools=[t.to_json_schema() for t in tools] or None,
                options={
                    "temperature": self.temperature,
                    "seed": self.seed,
                    "num_ctx": self.num_ctx,
                },
            )
        except ConnectionError as exc:
            raise LLMError(
                f"Cannot reach Ollama at {self.host}. Is it running? Start it with `ollama serve`."
            ) from exc
        except ollama.ResponseError as exc:
            if exc.status_code == 404:
                raise LLMError(
                    f"Model {self.model!r} is not available. Pull it with "
                    f"`ollama pull {self.model}`."
                ) from exc
            raise LLMError(f"Ollama error ({exc.status_code}): {exc.error}") from exc

        msg = response.message
        # Ollama does not return call ids, so derive stable ones from the conversation position.
        tool_calls = [
            ToolCall(
                id=f"call_{len(messages)}_{i}",
                name=tc.function.name,
                arguments=parse_arguments(tc.function.arguments),
            )
            for i, tc in enumerate(msg.tool_calls or [])
        ]
        return AssistantTurn(content=msg.content or "", tool_calls=tool_calls)


def to_ollama_message(message: Message) -> dict[str, Any]:
    """Convert our Message into the dict shape Ollama's chat endpoint accepts."""
    out: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        out["tool_calls"] = [
            {"function": {"name": tc.name, "arguments": tc.arguments}} for tc in message.tool_calls
        ]
    if message.role == "tool" and message.name:
        out["tool_name"] = message.name
    return out


def parse_arguments(raw: Any) -> dict[str, Any]:
    """Tool arguments usually arrive as a dict, but some models send a JSON string."""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
