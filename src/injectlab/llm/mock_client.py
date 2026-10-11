"""A scripted LLMClient for deterministic tests."""

from injectlab.llm.base import AssistantTurn, LLMError, Message, ToolSpec


class MockClient:
    """Replays a fixed list of assistant turns, one per ``chat`` call.

    Every request is recorded in ``calls`` so tests can assert on exactly what the
    model would have seen (for example, that a defense wrapped a tool output).
    """

    def __init__(self, turns: list[AssistantTurn], model: str = "mock") -> None:
        self.model = model
        self._turns = list(turns)
        self.calls: list[tuple[list[Message], list[ToolSpec]]] = []

    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> AssistantTurn:
        self.calls.append(([m.model_copy(deep=True) for m in messages], list(tools)))
        if len(self.calls) > len(self._turns):
            raise LLMError(f"MockClient script exhausted after {len(self._turns)} turns.")
        return self._turns[len(self.calls) - 1]

    @property
    def remaining(self) -> int:
        return len(self._turns) - len(self.calls)
