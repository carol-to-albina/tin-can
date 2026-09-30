---
name: speak-in-room
description: >-
  Post the user's words into an owned ndjson outbox so the other person's
  Grok Bot can embed them. Use when the user talks to the room, to Albina,
  to Carol, or says tell them / send this over.
---

# Speak in the room

```sh
python3 scripts/room.py post \
  --me "$ROOM_ME" \
  --to "$THEM" \
  --kind speech \
  --body "$TEXT" \
  --push
```

`$THEM` is a member id from `.room/members.json`, or `all` when the user is
speaking to the room. `$TEXT` is what the user wants the other side to hear.
Prefer their words. Add a short bot note only when they asked you to explain.

`--push` commits only your outbox file and pushes the current branch.

After post, tell the user it is in the room. Do not claim the other person
has read it until their bot acks.

A push under `.room/out/` can wake their bot. Their next render will speak
this as you.
