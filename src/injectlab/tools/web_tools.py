"""Simulated web access. No network calls: pages come from `world.web`."""

from typing import Annotated

from pydantic import Field

from injectlab.env.world import World
from injectlab.tools.registry import ToolError


def normalize_url(url: str) -> str:
    """Treat `example.test/page`, `http://...` and a trailing slash as the same page."""
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    return url.rstrip("/")


def fetch_url(
    world: World,
    url: Annotated[
        str, Field(description="The full URL of the page, e.g. https://site.test/page.")
    ],
) -> str:
    """Fetch a web page and return its title and text content."""
    page = world.web.get(normalize_url(url))
    if page is None:
        raise ToolError(f"404 Not Found: {url}")
    return f"{page.title}\n\n{page.content}"


TOOLS = [fetch_url]
