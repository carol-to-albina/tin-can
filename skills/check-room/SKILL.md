---
name: check-room
description: >-
  Pull unread Albina–Carol room events from owned ndjson outboxes and embed
  them as the other person talking. Use when the user says check the room,
  any /room check, after a Grok webhook wake, or after a push to .room/out/.
---

# Check the room

Canonical phrases:

- Check the room
- What's new from Albina
- What's new from Carol

## Steps

```sh
python3 scripts/room.py render --me "$ROOM_ME" --ack
```

Show that stdout as chat. `--ack` advances your cursor.

If you need machine-readable rows first:

```sh
python3 scripts/room.py pull --me "$ROOM_ME"
```

Still render for the human. Never paste the JSON.

A push under `.room/out/` wakes you. Do not poll every five minutes.

## Voice

Wrong: "I found 2 new lines in .room/out/carol.ndjson."

Right:

**Albina:** can your research bot look at T
