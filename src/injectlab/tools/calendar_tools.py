"""Simulated calendar tools operating on `world.calendar`."""

from datetime import date, datetime
from typing import Annotated

from pydantic import Field

from injectlab.env.world import CalendarEvent, World
from injectlab.tools.email_tools import Addresses
from injectlab.tools.registry import ToolError


def _format_event(event: CalendarEvent) -> str:
    lines = [
        f"[id {event.id}] {event.title}",
        f"  when: {event.start.strftime('%Y-%m-%d %H:%M')} to {event.end.strftime('%H:%M')}",
    ]
    if event.location:
        lines.append(f"  where: {event.location}")
    if event.participants:
        lines.append(f"  participants: {', '.join(event.participants)}")
    if event.description:
        lines.append(f"  description: {event.description}")
    return "\n".join(lines)


def list_events(
    world: World,
    day: Annotated[
        date | None, Field(description="Only events on this date (YYYY-MM-DD). Omit for all.")
    ] = None,
) -> str:
    """List calendar events in start-time order, with details and descriptions."""
    events = [e for e in world.calendar if day is None or e.start.date() == day]
    if not events:
        return "No events found."
    return "\n".join(_format_event(e) for e in sorted(events, key=lambda e: e.start))


def create_event(
    world: World,
    title: Annotated[str, Field(description="Event title.")],
    start: Annotated[datetime, Field(description="Start time, ISO format: YYYY-MM-DDTHH:MM.")],
    end: Annotated[datetime, Field(description="End time, ISO format: YYYY-MM-DDTHH:MM.")],
    location: Annotated[str, Field(description="Where the event takes place.")] = "",
    participants: Annotated[Addresses, Field(description="Email addresses of participants.")] = [],  # noqa: B006 - pydantic copies defaults, so a list literal is safe here
    description: Annotated[str, Field(description="Notes about the event.")] = "",
) -> str:
    """Create a calendar event."""
    if end <= start:
        raise ToolError("end must be after start.")
    next_id = max((e.id for e in world.calendar), default=0) + 1
    event = CalendarEvent(
        id=next_id,
        title=title,
        start=start.replace(tzinfo=None),
        end=end.replace(tzinfo=None),
        location=location,
        participants=participants,
        description=description,
    )
    world.calendar.append(event)
    return f"Created event:\n{_format_event(event)}"


def delete_event(
    world: World,
    event_id: Annotated[int, Field(description="The id of the event, from list_events.")],
) -> str:
    """Delete a calendar event."""
    event = world.get_event(event_id)
    if event is None:
        raise ToolError(f"no event with id {event_id}.")
    world.calendar.remove(event)
    return f"Deleted event {event_id}: {event.title}."


TOOLS = [list_events, create_event, delete_event]
