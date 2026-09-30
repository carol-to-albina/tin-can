"""Chat voice. Not the protocol."""

from __future__ import annotations

from ..types import Event, Inbox, Kind, Member, MemberId, Task


def display_name(members: dict[MemberId, Member], member: MemberId) -> str:
    row = members.get(member)
    return row.display if row else str(member)


def render_event(members: dict[MemberId, Member], event: Event) -> str:
    """Speech is **Display:** body.

    Task is **Display:** [task writer:seq] body.
    Claim, done, fail, grant, deny, revoke are one tagged line with the ref.
    Cot is **Display:** [hidden CoT under writer:seq] then the body.
    """
    name = display_name(members, event.meta.writer)
    kind = event.kind
    if kind is Kind.SPEECH:
        return f"**{name}:** {event.body}"
    if kind is Kind.TASK:
        return f"**{name}:** [task {event.meta.ref()}] {event.body}"
    if kind is Kind.COT:
        return f"**{name}:** [hidden CoT under {event.ref}]\n{event.body}"
    if kind is Kind.RECEIPT:
        return f"**{name}:** [receipt {event.ref}] {event.body}"
    if kind in (Kind.DONE, Kind.FAIL, Kind.DENY):
        extra = f" {event.body}" if getattr(event, "body", "") else ""
        return f"**{name}:** [{kind.value} {event.ref}]{extra}"
    if kind in (Kind.CLAIM, Kind.GRANT, Kind.REVOKE):
        return f"**{name}:** [{kind.value} {event.ref}]"
    if kind is Kind.GRANT_REQUEST:
        caps = ", ".join(event.capabilities)
        ask = f" [asks for {caps}]" if caps else ""
        return f"**{name}:**{ask} {event.body}".rstrip()
    return f"**{name}:** [{kind.value}] {getattr(event, 'body', '')}".rstrip()


def render_inbox(members: dict[MemberId, Member], inbox: Inbox) -> str:
    return "\n".join(render_event(members, event) for event in inbox.unread)


def render_task(members: dict[MemberId, Member], task: Task) -> str:
    name = display_name(members, task.writer)
    holder = f" by {task.claimant}" if task.claimant else ""
    return f"**{name}:** [task {task.ref}] {task.state.value}{holder} {task.body}"


def render_tasks(members: dict[MemberId, Member], tasks: list[Task]) -> str:
    return "\n".join(render_task(members, task) for task in tasks)
