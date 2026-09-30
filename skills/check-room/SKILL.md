---
name: check-room
description: >-
  Pull unread Albina–Carol room events from GitHub and embed them as the
  other person talking. Use when the user says check the room, any /room
  check, after a GitHub notification, or on the five-minute routine.
---

# Check the room

Canonical phrases:

- Check the room
- What's new from Albina
- What's new from Carol

## Steps

```sh
python3 scripts/room.py render --me "$ROOM_ME" --repo "$ROOM_REPO" --ack
```

Show that stdout as chat. `--ack` marks the events read.

If you need machine-readable rows first:

```sh
python3 scripts/room.py pull --me "$ROOM_ME" --repo "$ROOM_REPO"
```

Still render for the human. Never paste the JSON.

## Voice

Wrong: "I found 2 new issues labeled unread:carol."

Right:

**Albina:** can your research bot look at T
