"""Independent adapter. Poll or run once per wake."""

from __future__ import annotations

from tincan import Room


def once(root: str | None = None) -> None:
    room = Room.open(root)
    inbox = room.sync()
    for task in inbox.actionable:
        if room.claim(task.ref):
            room.done(task.ref, "done")
    room.ack(inbox)
    room.publish()


if __name__ == "__main__":
    once()
