"""Defenses by id. A fresh instance is made for every episode (defenses keep episode state)."""

from injectlab.defenses.base import Defense
from injectlab.defenses.delimiting import DelimitingDefense
from injectlab.defenses.detector import DetectorDefense
from injectlab.defenses.none import NoDefense
from injectlab.defenses.sandwich import SandwichDefense
from injectlab.defenses.tool_filter import ToolFilterDefense

DEFENSES: dict[str, type[Defense]] = {
    NoDefense.id: NoDefense,
    DelimitingDefense.id: DelimitingDefense,
    SandwichDefense.id: SandwichDefense,
    ToolFilterDefense.id: ToolFilterDefense,
    DetectorDefense.id: DetectorDefense,
}


def make_defense(defense_id: str) -> Defense:
    try:
        return DEFENSES[defense_id]()
    except KeyError:
        raise KeyError(f"Unknown defense {defense_id!r}. Known: {sorted(DEFENSES)}") from None
