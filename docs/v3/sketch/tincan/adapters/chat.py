"""Chat voice. Not the protocol."""

from __future__ import annotations

from ..types import Event, Inbox, Member, MemberId, Task


def display_name(members: dict[MemberId, Member], member: MemberId) -> str:
    row = members.get(member)
    return row.display if row else str(member)


def render_event(members: dict[MemberId, Member], event: Event) -> str:
    """Speech is **Display:** body.

    Task is **Display:** [task writer:seq] body.
    Claim, done, fail, grant, deny, revoke are one tagged line with the ref.
    Cot is **Display:** [hidden CoT under writer:seq] then the body.
    """
    raise NotImplementedError


def render_inbox(members: dict[MemberId, Member], inbox: Inbox) -> str:
    raise NotImplementedError


def render_task(members: dict[MemberId, Member], task: Task) -> str:
    raise NotImplementedError


def render_tasks(members: dict[MemberId, Member], tasks: list[Task]) -> str:
    raise NotImplementedError
