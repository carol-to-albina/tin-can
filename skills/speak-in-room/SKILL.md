---
name: speak-in-room
description: >-
  Post the user's words into an owned ndjson outbox so the other person's
  Grok Bot can embed them. Use when the user talks to the room, to Albina,
  to Carol, says tell them / send this over, or asks someone to help / cowork.
---

# Speak in the room

Talk:

```sh
python3 scripts/tincan.py post \
  --me "$ROOM_ME" \
  --to "$THEM" \
  --kind speech \
  --body "$TEXT" \
  --push
```

A job for their Bot:

```sh
python3 scripts/tincan.py post \
  --me "$ROOM_ME" \
  --to "$THEM" \
  --kind task \
  --body "$JOB" \
  --push
```

Use `--kind task` when the user says ask them, tell them to help, have
their Bot, cowork, or gives them a job. `$JOB` is the work, the paths,
and what this side already did. Do not do their work.

`$THEM` is a member id from `.room/members.json`, or `all` when the user is
speaking to the room. `$TEXT` is what the user wants the other side to hear.
Prefer their words. Add a short bot note only when they asked you to explain.

`--push` commits only your outbox file and pushes. It dies unless this
clone is on master (or `ROOM_BRANCH`). Checkout master before `--push`
so the other Bot can `sync`.

After post, tell the user it is in the room. Do not claim the other person
has read it until their bot acks.

A push under `.room/out/` can wake their bot. Their next `sync` will speak
this as you, and a `[task]` line is theirs to do.
