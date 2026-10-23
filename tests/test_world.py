from datetime import datetime

from injectlab.env.world import (
    ActionLogEntry,
    CalendarEvent,
    Email,
    World,
    find_slots,
    slot_placeholder,
)


def tiny_world() -> World:
    return World(
        user_name="Test User",
        user_email="user@example.test",
        now=datetime(2026, 1, 1, 9, 0),
        inbox=[
            Email(
                id=1,
                sender="a@example.test",
                to=["user@example.test"],
                subject="Hi {injection:subj}",
                body="Body {injection:body}",
                date=datetime(2026, 1, 1, 8, 0),
            )
        ],
        calendar=[
            CalendarEvent(
                id=7,
                title="Sync",
                start=datetime(2026, 1, 2, 10, 0),
                end=datetime(2026, 1, 2, 11, 0),
                description="{injection:desc}",
            )
        ],
    )


def test_find_slots_and_placeholder_round_trip() -> None:
    text = f"a {slot_placeholder('x_1')} b {slot_placeholder('y')}"
    assert find_slots(text) == ["x_1", "y"]
    assert find_slots("no slots {injection:} {other:x}") == []


def test_slot_locations() -> None:
    assert tiny_world().slot_locations() == {
        "subj": "email:1.subject",
        "body": "email:1.body",
        "desc": "event:7.description",
    }


def test_map_text_returns_copy_and_leaves_original() -> None:
    world = tiny_world()
    upper = world.map_text(str.upper)
    assert upper.inbox[0].body == "BODY {INJECTION:BODY}"
    assert world.inbox[0].body == "Body {injection:body}"


def test_lookups() -> None:
    world = tiny_world()
    assert world.get_email(1) is not None
    assert world.get_email(99) is None
    assert world.get_event(7) is not None
    assert world.get_event(1) is None


def test_action_log_entry_defaults() -> None:
    entry = ActionLogEntry(tool="list_emails")
    assert entry.ok
    assert entry.arguments == {}
