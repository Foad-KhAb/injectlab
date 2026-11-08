"""Experiment configs (YAML) and their expansion into a list of individual runs."""

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from injectlab.agent.loop import DEFAULT_MAX_STEPS
from injectlab.attacks.injection_tasks import INJECTION_TASKS, get_injection_task
from injectlab.attacks.templates import TEMPLATES, get_template
from injectlab.defenses import DEFENSES
from injectlab.tasks.user_tasks import TASKS, get_task

ALL = "all"
ALL_SLOTS = "all"  # value of RunSpec.slot when every slot of the task holds the attack


class ExperimentConfig(BaseModel):
    """One experiment. Lists may be the string "all" to mean every registered item."""

    model_config = ConfigDict(extra="forbid")

    name: str
    models: list[str]
    defenses: list[str] = Field(default_factory=lambda: ["none"])
    user_tasks: list[str] | Literal["all"] = ALL
    injection_tasks: list[str] | Literal["all"] = ALL
    templates: list[str] | Literal["all"] = ALL
    # "each": one run per slot the user task reads (gives the per-slot breakdown).
    # "all": one run with every slot of the task attacked at once (AgentDojo style).
    slot_mode: Literal["each", "all"] = "each"
    seeds: list[int] = Field(default_factory=lambda: [0])
    include_benign: bool = True  # also run every user task without an attack (utility)
    max_steps: int = DEFAULT_MAX_STEPS
    output_dir: Path = Path("results")

    @field_validator("defenses")
    @classmethod
    def _known_defenses(cls, value: list[str]) -> list[str]:
        unknown = [d for d in value if d not in DEFENSES]
        if unknown:
            raise ValueError(f"unknown defense(s) {unknown}; known: {sorted(DEFENSES)}")
        return value

    @model_validator(mode="after")
    def _known_ids(self) -> "ExperimentConfig":
        # Fail on a typo at load time, not hours into a run.
        try:
            for task_id in self.user_task_ids():
                get_task(task_id)
            for task_id in self.injection_task_ids():
                get_injection_task(task_id)
            for template_id in self.template_ids():
                get_template(template_id)
        except KeyError as exc:
            raise ValueError(exc.args[0]) from None
        return self

    def user_task_ids(self) -> list[str]:
        return [t.id for t in TASKS] if self.user_tasks == ALL else list(self.user_tasks)

    def injection_task_ids(self) -> list[str]:
        if self.injection_tasks == ALL:
            return [t.id for t in INJECTION_TASKS]
        return list(self.injection_tasks)

    def template_ids(self) -> list[str]:
        return [t.id for t in TEMPLATES] if self.templates == ALL else list(self.templates)

    @property
    def results_path(self) -> Path:
        return self.output_dir / f"{self.name}.jsonl"

    @property
    def traces_dir(self) -> Path:
        return self.output_dir / self.name / "traces"


def load_config(path: Path) -> ExperimentConfig:
    return ExperimentConfig.model_validate(yaml.safe_load(path.read_text()))


class RunSpec(BaseModel):
    """One episode to run. ``injection_task``/``template``/``slot`` are None for benign runs."""

    model: str
    defense: str
    user_task: str
    injection_task: str | None = None
    template: str | None = None
    slot: str | None = None
    seed: int = 0

    @property
    def is_attack(self) -> bool:
        return self.injection_task is not None

    @property
    def run_id(self) -> str:
        """Stable id from the run's settings, so a resumed experiment recognizes it."""
        key = json.dumps(self.model_dump(), sort_keys=True)
        return hashlib.sha256(key.encode()).hexdigest()[:16]


def expand(config: ExperimentConfig) -> list[RunSpec]:
    """Every run in the experiment, in a fixed order (benign runs of a cell come first)."""
    specs: list[RunSpec] = []
    for model in config.models:
        for defense in config.defenses:
            for seed in config.seeds:
                for task_id in config.user_task_ids():
                    base = {"model": model, "defense": defense, "user_task": task_id, "seed": seed}
                    if config.include_benign:
                        specs.append(RunSpec(**base))
                    task = get_task(task_id)
                    slots = task.injection_slots if config.slot_mode == "each" else [ALL_SLOTS]
                    for injection_id in config.injection_task_ids():
                        for template_id in config.template_ids():
                            for slot in slots:
                                specs.append(
                                    RunSpec(
                                        **base,
                                        injection_task=injection_id,
                                        template=template_id,
                                        slot=slot,
                                    )
                                )
    return specs
