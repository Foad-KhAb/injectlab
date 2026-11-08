"""Run a UserTask end to end: prepare the world, run the agent, score the result."""

from dataclasses import dataclass

from injectlab.agent.loop import DEFAULT_MAX_STEPS, Trace, run_agent
from injectlab.attacks.base import AttackTemplate, InjectionTask, make_payloads
from injectlab.defenses.base import Defense
from injectlab.env.seed import build_world, fill_slots
from injectlab.env.world import World
from injectlab.llm.base import AssistantTurn, LLMClient
from injectlab.llm.mock_client import MockClient
from injectlab.tasks.base import UserTask
from injectlab.tools import default_registry
from injectlab.tools.registry import ToolRegistry


@dataclass
class TaskResult:
    task_id: str
    success: bool
    trace: Trace
    world: World  # after the episode
    initial: World  # before the episode
    # Set only for attacked runs: did the agent do what the attacker wanted?
    attack_success: bool | None = None


def prepare_world(task: UserTask, payloads: dict[str, str] | None = None) -> World:
    """A fresh world with slots filled (benign unless ``payloads`` says otherwise)."""
    world = fill_slots(build_world(), payloads)
    task.setup(world)
    return world


def run_task(
    task: UserTask,
    client: LLMClient,
    *,
    payloads: dict[str, str] | None = None,
    defense: Defense | None = None,
    registry: ToolRegistry | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> TaskResult:
    world = prepare_world(task, payloads)
    initial = world.model_copy(deep=True)
    trace = run_agent(
        client,
        world,
        registry or default_registry(),
        task.prompt,
        defense=defense,
        allowed_tools=task.allowed_tools,
        max_steps=max_steps,
    )
    success = task.check(world, initial, trace)
    return TaskResult(task.id, success, trace, world, initial)


def run_attack(
    task: UserTask,
    injection_task: InjectionTask,
    template: AttackTemplate,
    client: LLMClient,
    *,
    slots: list[str] | None = None,
    defense: Defense | None = None,
    registry: ToolRegistry | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> TaskResult:
    """Run ``task`` with the attack planted in ``slots`` (default: every slot it reads).

    Scores both sides of the same episode: ``success`` (user task) and ``attack_success``.
    """
    payloads = make_payloads(task, template, injection_task, build_world(), slots)
    result = run_task(
        task,
        client,
        payloads=payloads,
        defense=defense,
        registry=registry,
        max_steps=max_steps,
    )
    result.attack_success = injection_task.security_check(
        result.world, result.initial, result.trace
    )
    return result


def ground_truth_client(task: UserTask, payloads: dict[str, str] | None = None) -> MockClient:
    """A scripted client that performs the task's ground truth, one call per turn."""
    calls = task.ground_truth(prepare_world(task, payloads))
    turns = [
        AssistantTurn(tool_calls=[c.model_copy(update={"id": f"gt_{i}"})])
        for i, c in enumerate(calls)
    ]
    return MockClient([*turns, AssistantTurn(content=task.reference_answer)], model="ground_truth")
