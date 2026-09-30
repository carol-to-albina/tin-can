"""Pure fold over the outboxes. Task and grant state, unread mail, the inbox. No IO."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .types import (
    Dropped,
    Event,
    EventRef,
    Grant,
    GrantState,
    Inbox,
    Member,
    MemberId,
    Position,
    Task,
)


def merge_order(event: Event) -> tuple[str, str, int]:
    return (event.meta.ts, str(event.meta.writer), int(event.meta.seq))


def reduce_grants(events: list[Event], now: datetime) -> dict[EventRef, Grant]:
    """grant_request opens requested.

    grant from request.to -> live.
    deny from request.to -> denied.
    revoke from request.to -> revoked.
    live plus expires <= now -> expired.
    Other decision lines stay in the log and do not count.
    """
    raise NotImplementedError


def grant_is_live(grant: Grant) -> bool:
    return grant.state is GrantState.LIVE


def reduce_tasks(
    events: list[Event],
    members: dict[MemberId, Member],
) -> dict[EventRef, Task]:
    """First claim in merge_order wins.

    done and fail count only from that claimant.
    waiting_human when target.autonomy is ASK and no claim.
    ignored when target.autonomy is OBSERVE and to is that member.
    A claim by an OBSERVE member never wins.
    """
    raise NotImplementedError


def tasks_for(me: MemberId, tasks: dict[EventRef, Task]) -> list[Task]:
    """Rows with to in (me, all), including ignored and waiting_human."""
    raise NotImplementedError


def unread_events(
    members: dict[MemberId, Member],
    events: list[Event],
    me: MemberId,
    pos: Position,
    now: datetime,
) -> list[Event]:
    """Addressed to me or all, from other writers, with seq > seen[writer].

    Sorted by merge_order. Drops Cot when reduce_grants says the grant is not LIVE.
    """
    raise NotImplementedError


def build_inbox(
    members: dict[MemberId, Member],
    events: list[Event],
    me: MemberId,
    pos: Position,
    now: datetime,
    only: tuple[EventRef, ...] | None = None,
) -> Inbox:
    """Unread events plus derived tasks and grants for this member.

    only keeps rows whose EventRef is in that set.
    An OBSERVE member has empty actionable and empty waiting_human.
    """
    raise NotImplementedError


def advance(pos: Position, inbox: Inbox) -> Position:
    """Last seq per writer among inbox events, never moving backwards."""
    raise NotImplementedError


def author_matches(github: str, name: str, email: str) -> bool:
    """name == github, or email local-part == github, or local-part ends with +github."""
    raise NotImplementedError


def drop_unauth(
    root: Path,
    writer: MemberId,
    events: list[Event],
    github: str,
    author_of_line,
) -> list[Dropped]:
    """author_of_line(path, seq) -> (name, email).

    A line whose author fails author_matches is Dropped. A line no commit
    holds yet (empty name and email) is kept.
    """
    raise NotImplementedError
