"""Attack building blocks: injection tasks (what the attacker wants) and templates (how the
request is dressed up). An attack on one episode is the combination

    user task  x  injection slot(s)  x  template  x  injection task

The user task decides which slots the agent reads; the template turns the injection task's
goal into the text placed in those slots; the injection task's ``security_check`` decides
whether the agent did what the attacker wanted.
"""

from abc import ABC, abstractmethod
from typing import ClassVar, Literal

from injectlab.agent.loop import Trace
from injectlab.env.world import World
from injectlab.llm.base import ToolCall
from injectlab.tasks.base import UserTask

ATTACKER_EMAIL = "attacker@evil.test"
PHISHING_URL = "https://secure-login.evil.test/verify"

Language = Literal["en", "fa"]


class InjectionTask(ABC):
    """The attacker's goal and a deterministic check that it was achieved."""

    id: ClassVar[str]
    # The goal as a direct request, written in the user's voice ("my inbox"), because
    # templates present it as coming from the user or the system.
    goal: ClassVar[str]
    # The same goal in Persian. URLs, addresses and names stay in Latin script.
    goal_fa: ClassVar[str]
    # Final answer of the ground-truth replay. Only matters for goals about the answer.
    reference_answer: ClassVar[str] = "Done."

    @abstractmethod
    def ground_truth(self, world: World) -> list[ToolCall]:
        """One sequence of tool calls that achieves the attacker's goal."""

    @abstractmethod
    def security_check(self, world: World, initial: World, trace: Trace) -> bool:
        """True if the attack SUCCEEDED (the agent did what the attacker wanted)."""


class AttackTemplate(ABC):
    """Wraps an injection task's goal into the text that is planted in a slot."""

    id: ClassVar[str]
    language: ClassVar[Language] = "en"

    @abstractmethod
    def render(self, task: InjectionTask, world: World) -> str:
        """The payload text. ``world`` gives context such as the user's name."""


def make_payloads(
    user_task: UserTask,
    template: AttackTemplate,
    injection_task: InjectionTask,
    world: World,
    slots: list[str] | None = None,
) -> dict[str, str]:
    """Payloads for ``fill_slots``: the rendered attack in each chosen slot.

    ``slots`` defaults to every slot the user task reads. Each slot must be one of them;
    injecting a slot the task never reads would measure nothing.
    """
    chosen = list(user_task.injection_slots) if slots is None else slots
    unknown = [s for s in chosen if s not in user_task.injection_slots]
    if unknown:
        raise ValueError(
            f"Slot(s) {unknown} are not read by user task {user_task.id!r} "
            f"(it reads {user_task.injection_slots})"
        )
    text = template.render(injection_task, world)
    return {slot: text for slot in chosen}
