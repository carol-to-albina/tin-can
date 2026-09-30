"""Cabinet paths, parse, format, position, reducers, migrate. No git. No HTTP."""

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
    Kind,
    Member,
    MemberId,
    Position,
    RoomConfig,
    Seq,
    Task,
    WhoFile,
)


def cabinet_dir(root: Path) -> Path:
    raise NotImplementedError


def room_path(root: Path) -> Path:
    raise NotImplementedError


def who_path(root: Path, member: MemberId) -> Path:
    raise NotImplementedError


def out_path(root: Path, member: MemberId) -> Path:
    raise NotImplementedError


def pos_path(root: Path, member: MemberId) -> Path:
    raise NotImplementedError


def local_me_path(root: Path) -> Path:
    raise NotImplementedError


def parse_room(raw: str) -> RoomConfig:
    """Die unless protocol is 3 and every roster id has a github login."""
    raise NotImplementedError


def parse_who(raw: str) -> WhoFile:
    """Missing fields become HUMAN, ASK, NONE, 86400."""
    raise NotImplementedError


def merge_member(
    member: MemberId,
    github: str,
    display: str,
    who: WhoFile | None,
) -> Member:
    """Missing who file uses HUMAN, ASK, NONE, 86400."""
    raise NotImplementedError


def load_members(root: Path) -> dict[MemberId, Member]:
    raise NotImplementedError


def parse_ref(raw: str) -> EventRef:
    raise NotImplementedError


def parse_line(writer: MemberId, seq: Seq, raw: str) -> Event:
    """Filename is the actor. Line seq must equal seq.

    Unknown kind or missing ref on a ref-kind is ProtocolError.
    """
    raise NotImplementedError


def format_line(event: Event) -> str:
    """One JSON object. No id, no actor, no grant_status."""
    raise NotImplementedError


def load_outbox(root: Path, writer: MemberId) -> list[Event]:
    """Empty file is ok. Blank lines are ignored and do not consume seq.

    Gap, duplicate, or seq mismatch is ProtocolError.
    """
    raise NotImplementedError


def next_seq(events: list[Event]) -> Seq:
    raise NotImplementedError


def append_outbox(root: Path, event: Event) -> Path:
    """Append one line. If the last line is byte-identical, do nothing.

    If the last line has the same seq and different bytes, ProtocolError.
    """
    raise NotImplementedError


def load_position(root: Path, me: MemberId) -> Position:
    """Missing file is seen={}."""
    raise NotImplementedError


def write_position(root: Path, pos: Position) -> Path:
    """Write to a temp file in the same dir, then rename onto pos/<me>."""
    raise NotImplementedError


def parse_position(me: MemberId, raw: str) -> Position:
    raise NotImplementedError


def format_position(pos: Position) -> str:
    """Two columns, writer then seq."""
    raise NotImplementedError


def merge_order(event: Event) -> tuple[str, str, int]:
    return (event.meta.ts, str(event.meta.writer), int(event.meta.seq))


def load_all_events(root: Path, members: dict[MemberId, Member]) -> list[Event]:
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
    """
    raise NotImplementedError


def advance(pos: Position, inbox: Inbox) -> Position:
    """Last seq per writer among inbox events, never moving backwards."""
    raise NotImplementedError


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
    """
    raise NotImplementedError


def tasks_for(me: MemberId, tasks: dict[EventRef, Task]) -> list[Task]:
    """Rows with to in (me, all), including ignored and waiting_human."""
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

    Must match author_matches(github, name, email).
    """
    raise NotImplementedError


def build_event(
    *,
    writer: MemberId,
    seq: Seq,
    to: MemberId | str,
    kind: Kind,
    body: str,
    ref: EventRef | None = None,
    capabilities: tuple[str, ...] = (),
    expires: str = "",
    ts: str | None = None,
) -> Event:
    """Refuse illegal kind/ref pairs."""
    raise NotImplementedError


def utc_now() -> str:
    raise NotImplementedError


def find_cabinet(start: Path) -> Path:
    """Walk parents for .tincan/room.json."""
    raise NotImplementedError


def migrate_v2(root: Path) -> list[Path]:
    """Host-only, one wave. Read .room/, write .tincan/.

    Stamp seq. Drop id, actor, grant_status. Map grant_id through an
    in-memory id map. Init pos to each writer's last seq. Fold hook
    url and key into who. Leave .room/ until the caller deletes it.
    Returns the paths that must be committed together.
    """
    raise NotImplementedError
