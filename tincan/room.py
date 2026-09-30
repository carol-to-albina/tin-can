"""Public operations. Callers import Room. Seq, reducers, git, and wake stay here."""

from __future__ import annotations

from pathlib import Path

from .types import (
    DoctorItem,
    Draft,
    Event,
    EventRef,
    Grant,
    Inbox,
    MemberId,
    Position,
    Task,
    WakeMessage,
)


class Room:
    def __init__(self, root: Path, me: MemberId) -> None:
        self.root = root
        self.me = me

    @staticmethod
    def open(start: str | Path | None = None) -> Room:
        """Find .tincan/room.json. Bind me from TINCAN_ME then .tincan/local/me."""
        raise NotImplementedError

    def sync(self, only: tuple[EventRef, ...] | None = None) -> Inbox:
        """Pull ff-only, fold every outbox, return unread mail.

        Does not rewrite pos.
        """
        raise NotImplementedError

    def ack(self, inbox: Inbox) -> Position:
        """Rewrite pos/<me> past every event in inbox. Does not push."""
        raise NotImplementedError

    def post(self, draft: Draft) -> Event:
        """Assign next seq, check address and grant, append. Does not push."""
        raise NotImplementedError

    def claim(self, ref: EventRef) -> Event | None:
        """Append claim if this member may take it, publish, then return.

        None if another claim already wins. Own prior claim returns that event.
        Work starts only after this returns an Event.
        """
        raise NotImplementedError

    def done(self, ref: EventRef, body: str) -> Event:
        """Append done. Only the winning claimant. Second done returns the first."""
        raise NotImplementedError

    def fail(self, ref: EventRef, body: str) -> Event:
        """Append fail. Only the winning claimant."""
        raise NotImplementedError

    def approve(self, ref: EventRef) -> Event:
        """Append grant. Only the grant_request's to."""
        raise NotImplementedError

    def deny(self, ref: EventRef, body: str) -> Event:
        """Append deny. Only the grant_request's to."""
        raise NotImplementedError

    def revoke(self, ref: EventRef) -> Event:
        """Append revoke. Only the grant_request's to."""
        raise NotImplementedError

    def tasks(self) -> tuple[Task, ...]:
        """Derived task rows addressed to me or all."""
        raise NotImplementedError

    def grants(self) -> tuple[Grant, ...]:
        """Derived grant rows this member requested or may decide."""
        raise NotImplementedError

    def publish(self) -> None:
        """Pull ff-only, commit dirty owned paths as room.json's login, push, notify.

        Dirty owned bytes after a crash become the same commit. No new bytes is a no-op.
        This is the retry after a failed --push. post is never re-run.
        """
        raise NotImplementedError

    def notify_from_push(self, before_rev: str) -> tuple[WakeMessage, ...]:
        """Actions path. Diff outboxes since before_rev, POST one wake per recipient."""
        raise NotImplementedError

    def doctor(self) -> tuple[DoctorItem, ...]:
        """git, token, branch, protocol, author vs room.json github, public-key rule, gapless logs."""
        raise NotImplementedError


def init(
    room: str,
    repo: str,
    host: MemberId,
    github: str,
    display: str,
    *,
    root: Path | None = None,
) -> None:
    """Write room.json. Host only."""
    raise NotImplementedError


def join(
    me: MemberId,
    *,
    root: Path | None = None,
    display: str = "",
    mode: str = "",
    autonomy: str = "",
    latency_sec: int | None = None,
    wake_type: str = "none",
    wake_url: str = "",
    wake_key: str = "",
) -> None:
    """Write who/<me>.json and .tincan/local/me.

    Die if me is not in the roster. Die if wake_key is set and the remote is public.
    """
    raise NotImplementedError


def hook_set(url: str, key: str, *, root: Path | None = None) -> None:
    """Write wake http url and key into who/<me>.json.

    Die if the remote is public and key is non-empty.
    """
    raise NotImplementedError
