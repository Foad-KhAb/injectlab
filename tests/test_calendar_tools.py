from injectlab.env.seed import BENIGN_SLOT_TEXT
from injectlab.env.world import World
from tests.conftest import CallTool


def test_list_events_in_order_with_descriptions(call: CallTool) -> None:
    out = call("list_events")
    titles = [line for line in out.splitlines() if line.startswith("[id")]
    assert titles[0] == "[id 1] Team standup"
    assert titles[-1] == "[id 4] 1:1 with Priya"
    assert BENIGN_SLOT_TEXT["event_vendor_demo_description"] in out


def test_list_events_by_day(call: CallTool) -> None:
    out = call("list_events", day="2026-03-19")
    assert "Vendor demo" in out
    assert "Dentist" not in out
    assert call("list_events", day="2026-12-25") == "No events found."
    assert call("list_events", day="next week").startswith("Error: invalid arguments")


def test_create_event(call: CallTool, world: World) -> None:
    out = call(
        "create_event",
        title="Project sync with Sara",
        start="2026-03-19T14:00",
        end="2026-03-19 14:30",
        location="Conference Room B",
        participants="sara.chen@northwind.test",
    )
    assert out.startswith("Created event:\n[id 5] Project sync with Sara")
    event = world.get_event(5)
    assert event is not None
    assert (event.start.hour, event.end.minute) == (14, 30)
    assert event.participants == ["sara.chen@northwind.test"]


def test_create_event_strips_timezone(call: CallTool, world: World) -> None:
    call("create_event", title="t", start="2026-03-19T14:00:00Z", end="2026-03-19T15:00:00Z")
    assert world.calendar[-1].start.tzinfo is None


def test_create_event_rejects_bad_times(call: CallTool, world: World) -> None:
    n = len(world.calendar)
    assert call("create_event", title="t", start="2026-03-19T15:00", end="2026-03-19T14:00") == (
        "Error: end must be after start."
    )
    assert call("create_event", title="t", start="tomorrow", end="later").startswith(
        "Error: invalid arguments"
    )
    assert len(world.calendar) == n


def test_create_event_default_participants_not_shared(call: CallTool, world: World) -> None:
    call("create_event", title="a", start="2026-03-19T14:00", end="2026-03-19T15:00")
    world.calendar[-1].participants.append("x@x.test")
    call("create_event", title="b", start="2026-03-19T16:00", end="2026-03-19T17:00")
    assert world.calendar[-1].participants == []


def test_delete_event(call: CallTool, world: World) -> None:
    assert call("delete_event", event_id=2) == "Deleted event 2: Dentist appointment."
    assert world.get_event(2) is None
    assert call("delete_event", event_id=2) == "Error: no event with id 2."
