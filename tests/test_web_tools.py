import pytest

from injectlab.env.seed import BENIGN_SLOT_TEXT
from injectlab.env.world import World
from injectlab.tools.web_tools import normalize_url
from tests.conftest import CallTool


def test_fetch_known_page(call: CallTool) -> None:
    out = call("fetch_url", url="https://lantern-noodles.test")
    assert out.startswith("Lantern Noodle House\n\n")
    assert "Closed on Mondays" in out
    assert BENIGN_SLOT_TEXT["web_restaurant_reviews"] in out


@pytest.mark.parametrize(
    "url",
    [
        "https://news.example.test/ai/",
        "http://news.example.test/ai",
        "news.example.test/ai",
        "  https://news.example.test/ai  ",
    ],
)
def test_fetch_tolerates_url_variants(call: CallTool, url: str) -> None:
    assert "Small language models" in call("fetch_url", url=url)


def test_unknown_url_is_404(call: CallTool, world: World) -> None:
    out = call("fetch_url", url="https://nowhere.test/page")
    assert out == "Error: 404 Not Found: https://nowhere.test/page"
    assert world.action_log[-1].ok is False


def test_fetch_missing_argument(call: CallTool) -> None:
    assert call("fetch_url").startswith("Error: invalid arguments")


def test_normalize_url() -> None:
    assert normalize_url("example.test/") == "https://example.test"
