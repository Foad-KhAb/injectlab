from injectlab.env.seed import BANK_VERIFICATION_CODE, BENIGN_SLOT_TEXT
from injectlab.env.world import World
from tests.conftest import CallTool


def test_list_emails_newest_first(call: CallTool) -> None:
    lines = call("list_emails").splitlines()
    assert len(lines) == 10
    assert lines[0].startswith("[id 10]")
    assert lines[-1].startswith("[id 1]")
    assert "SecureBank" in lines[0]


def test_list_emails_unread_only(call: CallTool, world: World) -> None:
    unread = [e.id for e in world.inbox if e.unread]
    lines = call("list_emails", unread_only=True).splitlines()
    assert len(lines) == len(unread)
    assert all("(unread)" in line for line in lines)


def test_list_emails_does_not_show_bodies(call: CallTool) -> None:
    assert BANK_VERIFICATION_CODE not in call("list_emails")


def test_read_email_returns_body_and_marks_read(call: CallTool, world: World) -> None:
    assert world.get_email(8).unread  # type: ignore[union-attr]
    out = call("read_email", email_id=8)
    assert "from: Sara Chen <sara.chen@northwind.test>" in out
    assert "subject: Project sync on Thursday?" in out
    assert BENIGN_SLOT_TEXT["email_sara_body"] in out
    assert not world.get_email(8).unread  # type: ignore[union-attr]


def test_read_email_accepts_numeric_string(call: CallTool) -> None:
    assert "SecureBank" in call("read_email", email_id="10")


def test_read_email_unknown_id(call: CallTool, world: World) -> None:
    assert call("read_email", email_id=99) == "Error: no email with id 99."
    assert world.action_log[-1].ok is False


def test_read_email_bad_argument(call: CallTool) -> None:
    assert call("read_email", email_id="eight").startswith("Error: invalid arguments")
    assert call("read_email").startswith("Error: invalid arguments")


def test_search_emails(call: CallTool) -> None:
    out = call("search_emails", query="noodle")
    assert out.startswith("[id 4]")
    assert call("search_emails", query="SARA").startswith("[id 8]")  # case-insensitive, sender
    assert call("search_emails", query="zebra") == "No emails match 'zebra'."
    assert call("search_emails", query="  ").startswith("Error:")


def test_send_email_appends_to_sent(call: CallTool, world: World) -> None:
    out = call("send_email", to=["sara.chen@northwind.test"], subject="Re: sync", body="Yes!")
    assert out == "Email sent to sara.chen@northwind.test."
    sent = world.sent[-1]
    assert sent.sender == world.user_email
    assert sent.to == ["sara.chen@northwind.test"]
    assert (sent.subject, sent.body, sent.date) == ("Re: sync", "Yes!", world.now)


def test_send_email_accepts_string_recipients(call: CallTool, world: World) -> None:
    call("send_email", to="a@x.test, b@x.test", subject="s", body="b")
    assert world.sent[-1].to == ["a@x.test", "b@x.test"]


def test_send_email_ids_increment(call: CallTool, world: World) -> None:
    call("send_email", to="a@x.test", subject="1", body="b")
    call("send_email", to="a@x.test", subject="2", body="b")
    assert [e.id for e in world.sent] == [1, 2]


def test_send_email_rejects_bad_input(call: CallTool, world: World) -> None:
    assert call("send_email", to="not-an-address", subject="s", body="b").startswith(
        "Error: invalid email address"
    )
    assert call("send_email", to=[], subject="s", body="b").startswith("Error:")
    assert call("send_email", to="a@x.test", subject="s").startswith("Error: invalid arguments")
    assert world.sent == []


def test_search_contacts(call: CallTool, world: World) -> None:
    assert call("search_contacts", query="sara") == "Sara Chen <sara.chen@northwind.test>"
    assert len(call("search_contacts").splitlines()) == len(world.contacts)
    assert call("search_contacts", query="nobody") == "No contacts match 'nobody'."
