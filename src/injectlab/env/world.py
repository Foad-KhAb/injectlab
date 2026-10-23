"""The simulated environment the agent acts on.

A World holds everything the tools can read or change. Success checkers inspect the final
World (and its action log) to decide whether the user's task or the attacker's goal happened.
All times are naive datetimes in the user's local time.
"""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

SLOT_PATTERN = re.compile(r"\{injection:([a-z0-9_]+)\}")


def slot_placeholder(slot_id: str) -> str:
    return f"{{injection:{slot_id}}}"


def find_slots(text: str) -> list[str]:
    """Slot ids that appear in ``text``, in order."""
    return SLOT_PATTERN.findall(text)


class Email(BaseModel):
    id: int
    sender: str
    sender_name: str = ""
    to: list[str]
    subject: str
    body: str
    date: datetime
    unread: bool = True


class WebPage(BaseModel):
    url: str
    title: str
    content: str


class CalendarEvent(BaseModel):
    id: int
    title: str
    start: datetime
    end: datetime
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    description: str = ""


class Contact(BaseModel):
    name: str
    email: str


class ActionLogEntry(BaseModel):
    """One tool call the agent made, recorded by the tool registry."""

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    output: str = ""


class World(BaseModel):
    user_name: str
    user_email: str
    now: datetime
    inbox: list[Email] = Field(default_factory=list)
    sent: list[Email] = Field(default_factory=list)
    web: dict[str, WebPage] = Field(default_factory=dict)
    calendar: list[CalendarEvent] = Field(default_factory=list)
    contacts: list[Contact] = Field(default_factory=list)
    action_log: list[ActionLogEntry] = Field(default_factory=list)

    def get_email(self, email_id: int) -> Email | None:
        return next((e for e in self.inbox if e.id == email_id), None)

    def get_event(self, event_id: int) -> CalendarEvent | None:
        return next((e for e in self.calendar if e.id == event_id), None)

    def slot_locations(self) -> dict[str, str]:
        """Map each slot id to where it lives, e.g. ``email:3.body`` or ``web:<url>.content``."""
        locations: dict[str, str] = {}
        for where, text in self._text_fields():
            for slot in find_slots(text):
                locations[slot] = where
        return locations

    def map_text(self, fn: Callable[[str], str]) -> "World":
        """Return a deep copy with ``fn`` applied to every field that may contain a slot."""
        world = self.model_copy(deep=True)
        for email in world.inbox:
            email.subject = fn(email.subject)
            email.body = fn(email.body)
        for page in world.web.values():
            page.title = fn(page.title)
            page.content = fn(page.content)
        for event in world.calendar:
            event.title = fn(event.title)
            event.description = fn(event.description)
        return world

    def _text_fields(self) -> list[tuple[str, str]]:
        fields: list[tuple[str, str]] = []
        for e in self.inbox:
            fields += [(f"email:{e.id}.subject", e.subject), (f"email:{e.id}.body", e.body)]
        for url, p in self.web.items():
            fields += [(f"web:{url}.title", p.title), (f"web:{url}.content", p.content)]
        for ev in self.calendar:
            fields += [
                (f"event:{ev.id}.title", ev.title),
                (f"event:{ev.id}.description", ev.description),
            ]
        return fields
