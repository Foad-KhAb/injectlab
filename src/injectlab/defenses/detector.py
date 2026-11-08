"""Detector defense: classify each tool output and redact the ones flagged as injections.

The whole output is replaced, so a flagged email also loses its legitimate content: this
defense can cost utility under attack even when it works.
"""

from collections.abc import Callable
from functools import cache

from injectlab.defenses.base import Defense

# Takes a text, returns the probability that it contains a prompt injection (0.0 to 1.0).
Classifier = Callable[[str], float]

REDACTED_MESSAGE = "[This content was removed because it may contain a prompt injection.]"
DEFAULT_MODEL = "protectai/deberta-v3-base-prompt-injection-v2"

# The classifier reads about 512 tokens, so longer text is scored in overlapping pieces.
# Without this, a payload placed late in a long page would never be seen.
CHUNK_WORDS = 200
CHUNK_OVERLAP = 50


def split_chunks(text: str) -> list[str]:
    """Overlapping pieces of ``text``, each at most CHUNK_WORDS words."""
    words = text.split()
    if len(words) <= CHUNK_WORDS:
        return [text]
    step = CHUNK_WORDS - CHUNK_OVERLAP
    return [
        " ".join(words[i : i + CHUNK_WORDS]) for i in range(0, len(words) - CHUNK_OVERLAP, step)
    ]


@cache
def load_hf_classifier(model_name: str = DEFAULT_MODEL) -> Classifier:
    """Load a Hugging Face text classifier and wrap it as a ``Classifier``.

    Cached because every episode gets a fresh defense instance and loading takes seconds.
    Needs the optional dependencies: ``uv sync --extra detector``.
    """
    from transformers import pipeline

    classify = pipeline("text-classification", model=model_name, device="cpu", truncation=True)

    def score(text: str) -> float:
        # The pipeline reports its top label only, so a confident SAFE is a low probability.
        results = classify(split_chunks(text))
        return max(r["score"] if r["label"] == "INJECTION" else 1 - r["score"] for r in results)

    return score


class DetectorDefense(Defense):
    id = "detector"

    def __init__(self, classifier: Classifier | None = None, threshold: float = 0.5) -> None:
        super().__init__()
        self.classifier = classifier  # None: load the default model on first use
        self.threshold = threshold

    def tool_output(self, tool_name: str, output: str) -> str:
        if self.classifier is None:
            self.classifier = load_hf_classifier()
        return REDACTED_MESSAGE if self.classifier(output) >= self.threshold else output
