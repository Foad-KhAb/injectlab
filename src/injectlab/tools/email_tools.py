"""Simulated email tools. Nothing is ever sent; `send_email` appends to `world.sent`."""

from typing import Annotated

from pydantic import BeforeValidator, Field

from injectlab.env.world import Email, World
from injectlab.tools.registry import ToolError


def _split_addresses(value: object) -> object:
    """Models often pass one address as a string, or several as "a, b"; accept both."""
    if isinstance(value, str):
        return [a.strip() for a in value.split(",") if a.strip()]
    return value


Addresses = Annotated[list[str], BeforeValidator(_split_addresses)]


def _sender(email: Email) -> str:
    return f"{email.sender_name} <{email.sender}>" if email.sender_name else email.sender


def _summary(email: Email) -> str:
    status = "unread" if email.unread else "read"
    date = email.date.strftime("%Y-%m-%d %H:%M")
    return f"[id {email.id}] {date} | from: {_sender(email)} | {email.subject} ({status})"


def list_emails(
    world: World,
    unread_only: Annotated[bool, Field(description="Only list unread emails.")] = False,
) -> str:
    """List emails in the inbox, newest first, showing id, date, sender and subject.

    Use read_email to see an email's body.
    """
    emails = [e for e in world.inbox if e.unread or not unread_only]
    if not emails:
        return "No emails found."
    return "\n".join(_summary(e) for e in sorted(emails, key=lambda e: e.date, reverse=True))


def read_email(
    world: World,
    email_id: Annotated[int, Field(description="The id of the email, from list_emails.")],
) -> str:
    """Read the full content of one email and mark it as read."""
    email = world.get_email(email_id)
    if email is None:
        raise ToolError(f"no email with id {email_id}.")
    email.unread = False
    return (
        f"id: {email.id}\n"
        f"from: {_sender(email)}\n"
        f"to: {', '.join(email.to)}\n"
        f"date: {email.date.strftime('%Y-%m-%d %H:%M')}\n"
        f"subject: {email.subject}\n\n"
        f"{email.body}"
    )


def search_emails(
    world: World,
    query: Annotated[str, Field(description="Text to look for in sender, subject or body.")],
) -> str:
    """Search the inbox for emails whose sender, subject or body contains the query."""
    q = query.strip().lower()
    if not q:
        raise ToolError("query must not be empty.")
    hits = [
        e
        for e in world.inbox
        if q in e.subject.lower() or q in e.body.lower() or q in _sender(e).lower()
    ]
    if not hits:
        return f"No emails match {query!r}."
    return "\n".join(_summary(e) for e in sorted(hits, key=lambda e: e.date, reverse=True))


def send_email(
    world: World,
    to: Annotated[Addresses, Field(description="Recipient email addresses.")],
    subject: Annotated[str, Field(description="Subject line.")],
    body: Annotated[str, Field(description="Plain-text body.")],
) -> str:
    """Send an email from the user's account."""
    if not to:
        raise ToolError("at least one recipient is required.")
    bad = [a for a in to if "@" not in a or " " in a]
    if bad:
        raise ToolError(f"invalid email address(es): {', '.join(bad)}.")
    next_id = max((e.id for e in world.sent), default=0) + 1
    world.sent.append(
        Email(
            id=next_id,
            sender=world.user_email,
            sender_name=world.user_name,
            to=to,
            subject=subject,
            body=body,
            date=world.now,
            unread=False,
        )
    )
    return f"Email sent to {', '.join(to)}."


def search_contacts(
    world: World,
    query: Annotated[
        str, Field(description="Part of a name or email address. Empty lists all contacts.")
    ] = "",
) -> str:
    """Look up contacts by name or email address."""
    q = query.strip().lower()
    hits = [c for c in world.contacts if q in c.name.lower() or q in c.email.lower()]
    if not hits:
        return f"No contacts match {query!r}."
    return "\n".join(f"{c.name} <{c.email}>" for c in hits)


TOOLS = [list_emails, read_email, search_emails, send_email, search_contacts]
