"""The baseline: no defense at all."""

from injectlab.defenses.base import Defense


class NoDefense(Defense):
    id = "none"
