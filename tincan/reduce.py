"""Pure fold over the outboxes. Task and grant state, unread mail, the inbox. No IO."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .files import out_path, parse_ts
from .types import (
    Autonomy,
    Cot,
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
    Seq,
    Speech,
    Task,
    TaskState,
)


def merge_order(event: Event) -> tuple[str, str, int]:
    return (event.meta.ts, str(event.meta.writer), int(event.meta.seq))


def _ordered(events: list[Event]) -> list[Event]:
    return sorted(events, key=merge_order)


def reduce_grants(events: list[Event], now: datetime) -> dict[EventRef, Grant]:
    """grant_request opens requested.

    grant from request.to -> live.
    deny from request.to -> denied.
    revoke from request.to -> revoked.
    live plus expires <= now -> expired.
    Other decision lines stay in the log and do not count.
    """
    grants: dict[EventRef, Grant] = {}
    decisions = {
        Kind.GRANT: GrantState.LIVE,
        Kind.DENY: GrantState.DENIED,
        Kind.REVOKE: GrantState.REVOKED,
    }
    for event in _ordered(events):
        if event.kind is Kind.GRANT_REQUEST:
            grants[event.meta.ref()] = Grant(
                ref=event.meta.ref(),
                requester=event.meta.writer,
                granter=event.meta.to,
                capabilities=event.capabilities,
                expires=event.expires,
                state=GrantState.REQUESTED,
                decision=None,
            )
            continue
        state = decisions.get(event.kind)
        if state is None:
            continue
        grant = grants.get(event.ref)
        if grant is None or event.meta.writer != grant.granter:
            continue
        grants[event.ref] = Grant(
            ref=grant.ref,
            requester=grant.requester,
            granter=grant.granter,
            capabilities=grant.capabilities,
            expires=grant.expires,
            state=state,
            decision=event.meta.ref(),
        )
    expired: dict[EventRef, Grant] = {}
    for ref, grant in grants.items():
        if (
            grant.state is GrantState.LIVE
            and grant.expires
            and parse_ts(grant.expires) <= now
        ):
            grant = Grant(
                ref=grant.ref,
                requester=grant.requester,
                granter=grant.granter,
                capabilities=grant.capabilities,
                expires=grant.expires,
                state=GrantState.EXPIRED,
                decision=grant.decision,
            )
        expired[ref] = grant
    return expired


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
    tasks: dict[EventRef, Task] = {}
    for event in _ordered(events):
        if event.kind is Kind.TASK:
            state = TaskState.OPEN
            if event.meta.to != "all":
                target = members.get(event.meta.to)
                if target is not None and target.autonomy is Autonomy.OBSERVE:
                    state = TaskState.IGNORED
                elif target is not None and target.autonomy is Autonomy.ASK:
                    state = TaskState.WAITING_HUMAN
            tasks[event.meta.ref()] = Task(
                ref=event.meta.ref(),
                writer=event.meta.writer,
                to=event.meta.to,
                body=event.body,
                state=state,
                claim=None,
                claimant=None,
                result=None,
            )
            continue
        if event.kind is Kind.CLAIM:
            task = tasks.get(event.ref)
            if task is None or task.claimant is not None:
                continue
            if task.state in (TaskState.DONE, TaskState.FAILED, TaskState.IGNORED):
                continue
            claimant = members.get(event.meta.writer)
            if claimant is not None and claimant.autonomy is Autonomy.OBSERVE:
                continue
            tasks[event.ref] = Task(
                ref=task.ref,
                writer=task.writer,
                to=task.to,
                body=task.body,
                state=TaskState.CLAIMED,
                claim=event.meta.ref(),
                claimant=event.meta.writer,
                result=None,
            )
            continue
        if event.kind not in (Kind.DONE, Kind.FAIL):
            continue
        task = tasks.get(event.ref)
        if task is None or task.state is not TaskState.CLAIMED:
            continue
        if event.meta.writer != task.claimant:
            continue
        tasks[event.ref] = Task(
            ref=task.ref,
            writer=task.writer,
            to=task.to,
            body=task.body,
            state=TaskState.DONE if event.kind is Kind.DONE else TaskState.FAILED,
            claim=task.claim,
            claimant=task.claimant,
            result=event.meta.ref(),
        )
    return tasks


def tasks_for(me: MemberId, tasks: dict[EventRef, Task]) -> list[Task]:
    """Rows with to in (me, all), including ignored and waiting_human."""
    rows = [task for task in tasks.values() if task.to in (me, "all")]
    return sorted(rows, key=lambda task: (str(task.writer), int(task.ref.seq)))


def _reader_views(
    me: MemberId,
    members: dict[MemberId, Member],
    rows: list[Task],
) -> tuple[tuple[Task, ...], tuple[Task, ...]]:
    reader = members.get(me)
    if reader is None or reader.autonomy is Autonomy.OBSERVE:
        return (), ()
    actionable: list[Task] = []
    waiting: list[Task] = []
    for task in rows:
        if task.state in (
            TaskState.CLAIMED,
            TaskState.DONE,
            TaskState.FAILED,
            TaskState.IGNORED,
        ):
            continue
        asks = reader.autonomy is Autonomy.ASK or task.state is TaskState.WAITING_HUMAN
        if task.to == "all" and reader.autonomy is Autonomy.AUTO:
            asks = False
        if asks:
            waiting.append(task)
        else:
            actionable.append(task)
    return tuple(actionable), tuple(waiting)


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
    del members
    grants = reduce_grants(events, now)
    seen = pos.seen
    rows: list[Event] = []
    for event in _ordered(events):
        if event.meta.writer == me:
            continue
        if event.meta.to not in (me, "all"):
            continue
        if int(event.meta.seq) <= int(seen.get(event.meta.writer, Seq(0))):
            continue
        if isinstance(event, Cot):
            grant = grants.get(event.ref)
            if grant is None or not grant_is_live(grant):
                continue
        rows.append(event)
    return rows


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
    want = set(only) if only is not None else None
    unread = unread_events(members, events, me, pos, now)
    if want is not None:
        unread = [event for event in unread if event.meta.ref() in want]
    speech = tuple(event for event in unread if isinstance(event, Speech))
    cots = tuple(event for event in unread if isinstance(event, Cot))
    task_rows = tasks_for(me, reduce_tasks(events, members))
    grant_rows = [
        grant
        for grant in reduce_grants(events, now).values()
        if grant.requester == me or grant.granter == me
    ]
    if want is not None:
        task_rows = [task for task in task_rows if task.ref in want]
        grant_rows = [grant for grant in grant_rows if grant.ref in want]
    actionable, waiting = _reader_views(me, members, task_rows)
    return Inbox(
        unread=tuple(unread),
        speech=speech,
        tasks=tuple(task_rows),
        actionable=actionable,
        waiting_human=waiting,
        cots=cots,
        grants=tuple(grant_rows),
    )


def advance(pos: Position, inbox: Inbox) -> Position:
    """Last seq per writer among inbox events, never moving backwards."""
    seen = dict(pos.seen)
    for event in inbox.unread:
        writer = event.meta.writer
        current = int(seen.get(writer, Seq(0)))
        if int(event.meta.seq) > current:
            seen[writer] = event.meta.seq
    return Position(pos.me, seen)


def author_matches(github: str, name: str, email: str) -> bool:
    """name == github, or email local-part == github, or local-part ends with +github."""
    login = github.strip()
    if not login:
        return False
    if name.strip() == login:
        return True
    local = email.split("@", 1)[0]
    return local == login or local.endswith("+" + login)


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
    path = out_path(root, writer)
    dropped: list[Dropped] = []
    for event in events:
        if event.meta.writer != writer:
            continue
        name, email = author_of_line(path, event.meta.seq)
        if not name and not email:
            continue
        if author_matches(github, name, email):
            continue
        dropped.append(
            Dropped(path, event.meta.seq, f"author {name} <{email}> is not {github}")
        )
    return dropped
