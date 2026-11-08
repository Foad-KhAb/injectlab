"""Tests for sandwich, tool_filter and detector. No real model is needed."""

import sys
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

from injectlab.agent.loop import run_agent
from injectlab.attacks.base import ATTACKER_EMAIL
from injectlab.defenses import detector as detector_module
from injectlab.defenses.base import EpisodeContext
from injectlab.defenses.detector import (
    CHUNK_WORDS,
    REDACTED_MESSAGE,
    DetectorDefense,
    load_hf_classifier,
    split_chunks,
)
from injectlab.defenses.sandwich import SandwichDefense
from injectlab.defenses.tool_filter import ToolFilterDefense
from injectlab.env.seed import benign_world
from injectlab.llm.base import AssistantTurn, ToolCall
from injectlab.llm.mock_client import MockClient
from injectlab.tasks.base import UserTask, call
from injectlab.tasks.harness import ground_truth_client, run_task
from injectlab.tasks.user_tasks import TASKS
from injectlab.tools import default_registry

ids = [t.id for t in TASKS]
PROMPT = "Tell me when my package arrives."
SEND = call("send_email", to=[ATTACKER_EMAIL], subject="x", body="y")


def scripted(*calls: ToolCall) -> MockClient:
    turns = [
        AssistantTurn(tool_calls=[c.model_copy(update={"id": f"c{i}"})])
        for i, c in enumerate(calls)
    ]
    return MockClient([*turns, AssistantTurn(content="Done.")])


# ---------------------------------------------------------------- sandwich


def sandwich() -> SandwichDefense:
    defense = SandwichDefense()
    defense.begin_episode(EpisodeContext(user_prompt=PROMPT))
    return defense


def test_sandwich_keeps_the_output_and_adds_the_request_after_it() -> None:
    shown = sandwich().tool_output("read_email", "BODY")
    assert "BODY" in shown
    assert PROMPT in shown
    assert shown.index("BODY") < shown.rindex(PROMPT)


def test_sandwich_uses_the_current_episodes_request() -> None:
    defense = sandwich()
    defense.begin_episode(EpisodeContext(user_prompt="Another request."))
    shown = defense.tool_output("read_email", "BODY")
    assert "Another request." in shown
    assert PROMPT not in shown


@pytest.mark.parametrize("task", TASKS, ids=ids)
def test_sandwich_does_not_break_correct_solutions(task: UserTask) -> None:
    assert run_task(task, ground_truth_client(task), defense=SandwichDefense()).success


# ---------------------------------------------------------------- tool_filter


def tool_filter(allowed: list[str] | None) -> ToolFilterDefense:
    defense = ToolFilterDefense()
    defense.begin_episode(EpisodeContext(user_prompt=PROMPT, allowed_tools=allowed))
    return defense


def test_filter_allows_listed_tools_and_blocks_others() -> None:
    defense = tool_filter(["read_email"])
    assert defense.allow_tool_call(call("read_email", email_id=1))
    assert not defense.allow_tool_call(SEND)


def test_filter_without_a_list_allows_everything() -> None:
    assert tool_filter(None).allow_tool_call(SEND)


def test_filter_with_an_empty_list_blocks_everything() -> None:
    assert not tool_filter([]).allow_tool_call(call("read_email", email_id=1))


def test_blocked_call_has_no_effect_on_the_world() -> None:
    world = benign_world()
    trace = run_agent(
        scripted(SEND),
        world,
        default_registry(),
        PROMPT,
        defense=ToolFilterDefense(),
        allowed_tools=["read_email"],
    )
    assert world.sent == []
    assert trace.executions[0].blocked


def test_filter_judges_the_tool_not_its_arguments() -> None:
    """Its known limit: if the task needs send_email, a send to the attacker still passes."""
    world = benign_world()
    run_agent(
        scripted(SEND),
        world,
        default_registry(),
        PROMPT,
        defense=ToolFilterDefense(),
        allowed_tools=["send_email"],
    )
    assert [e.to for e in world.sent] == [[ATTACKER_EMAIL]]


@pytest.mark.parametrize("task", TASKS, ids=ids)
def test_filter_does_not_break_correct_solutions(task: UserTask) -> None:
    assert run_task(task, ground_truth_client(task), defense=ToolFilterDefense()).success


# ---------------------------------------------------------------- detector


def detector(score: float, threshold: float = 0.5) -> DetectorDefense:
    return DetectorDefense(classifier=lambda text: score, threshold=threshold)


def test_detector_passes_clean_text_unchanged() -> None:
    assert detector(0.1).tool_output("read_email", "BODY") == "BODY"


def test_detector_redacts_flagged_text_completely() -> None:
    shown = detector(0.9).tool_output("read_email", "BODY")
    assert shown == REDACTED_MESSAGE
    assert "BODY" not in shown


def test_detector_threshold_is_inclusive_and_configurable() -> None:
    assert detector(0.5).tool_output("t", "BODY") == REDACTED_MESSAGE
    assert detector(0.7, threshold=0.8).tool_output("t", "BODY") == "BODY"


def test_detector_classifies_the_tool_output() -> None:
    seen: list[str] = []

    def classifier(text: str) -> float:
        seen.append(text)
        return 0.0

    DetectorDefense(classifier=classifier).tool_output("read_email", "BODY")
    assert seen == ["BODY"]


def test_trace_keeps_the_raw_output_of_a_redacted_call() -> None:
    """Raw and shown outputs differ exactly when the detector fired: this gives its FPR."""
    world = benign_world()
    trace = run_agent(
        scripted(call("read_email", email_id=1)),
        world,
        default_registry(),
        PROMPT,
        defense=detector(0.9),
    )
    execution = trace.executions[0]
    assert execution.shown_output == REDACTED_MESSAGE
    assert execution.raw_output != REDACTED_MESSAGE


def test_detector_loads_the_default_classifier_once(monkeypatch: pytest.MonkeyPatch) -> None:
    loads: list[int] = []

    def load() -> detector_module.Classifier:
        loads.append(1)
        return lambda text: 0.0

    monkeypatch.setattr(detector_module, "load_hf_classifier", load)
    defense = DetectorDefense()
    defense.tool_output("t", "a")
    defense.tool_output("t", "b")
    assert len(loads) == 1


def test_split_chunks_keeps_short_text_whole() -> None:
    assert split_chunks("a  b\nc") == ["a  b\nc"]


def test_split_chunks_covers_every_word_within_the_limit() -> None:
    words = [f"w{i}" for i in range(1000)]
    chunks = split_chunks(" ".join(words))
    assert len(chunks) > 1
    assert all(len(c.split()) <= CHUNK_WORDS for c in chunks)
    assert {w for c in chunks for w in c.split()} == set(words)


@pytest.fixture
def fake_transformers(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    """A stand-in for transformers: texts containing BAD are confidently INJECTION."""
    loads: list[int] = []

    def pipeline(*args: Any, **kwargs: Any) -> Any:
        loads.append(1)

        def classify(texts: list[str]) -> list[dict[str, Any]]:
            return [
                {"label": "INJECTION", "score": 0.99}
                if "BAD" in t
                else {"label": "SAFE", "score": 0.98}
                for t in texts
            ]

        return classify

    module: Any = ModuleType("transformers")
    module.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "transformers", module)
    load_hf_classifier.cache_clear()
    yield loads
    load_hf_classifier.cache_clear()


def test_classifier_returns_the_probability_of_injection(fake_transformers: list[int]) -> None:
    score = load_hf_classifier()
    assert score("BAD text") == pytest.approx(0.99)
    assert score("fine text") == pytest.approx(0.02)


def test_classifier_finds_a_payload_late_in_a_long_text(fake_transformers: list[int]) -> None:
    long_text = " ".join(["word"] * 2000 + ["BAD"])
    assert load_hf_classifier()(long_text) == pytest.approx(0.99)


def test_classifier_is_loaded_once_across_episodes(fake_transformers: list[int]) -> None:
    for _ in range(3):
        DetectorDefense().tool_output("t", "fine text")
    assert len(fake_transformers) == 1
