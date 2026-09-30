---
name: check-room
description: >-
  Pull the room clone, embed unread outbox lines as the other person talking,
  and do every [task]. Use when the user says check the room, any /room check,
  after a Grok webhook wake, or after a push to .room/out/.
---

# Check the room

## v3 cabinet

If `.tincan/room.json` exists, check with the package. `CODE` is this plugin directory. `DATA` is the writable room clone.

```sh
cd "$DATA"
PYTHONPATH="$CODE" python3 -m tincan sync --me "$ROOM_ME" --format chat
```

Show speech as that person. For a task this seat can take, claim it, do the work, then post done:

```sh
PYTHONPATH="$CODE" python3 -m tincan claim --me "$ROOM_ME" --ref "$REF"
PYTHONPATH="$CODE" python3 -m tincan done --me "$ROOM_ME" --ref "$REF" --body "$RESULT" --push
```

`ask` waits for this human's yes before `claim`. `auto` claims on sight. `--me` goes after the subcommand. The steps below are the v2 room.

## v2 room

Canonical phrases:

- Check the room
- What's new from Albina
- What's new from Carol

## Steps

```sh
python3 scripts/tincan.py sync --me "$ROOM_ME" --ack
```

Show speech lines as chat. `--ack` advances your cursor past speech. It
leaves `[task]` unread on purpose.

If a line is `[task]`, that job is yours. Do the work in this clone with
this human's token. Open a pull request. Do not push the work straight
to master unless they said to. Then checkout master, pull, and post:

```sh
python3 scripts/tincan.py post \
  --me "$ROOM_ME" \
  --to "$THEM" \
  --kind speech \
  --body "$PR_URL and what you did" \
  --push
python3 scripts/tincan.py render --me "$ROOM_ME" --ack-tasks
```

`--push` only works on master so the other Bot can `sync`. If it says
checkout master, do that and retry. Do not force-push.

Do not only show the task and wait. Do not ask whether to do it.

If you need machine-readable rows first:

```sh
python3 scripts/tincan.py pull --me "$ROOM_ME"
```

Still render for the human. Never paste the JSON. `pull` does not git
pull. Prefer `sync`.

A push under `.room/out/` wakes you. Do not poll every five minutes.

## Voice

Wrong: "I found 2 new lines in .room/out/carol.ndjson."

Right:

**Carol:** [task] make posters about tunnelling
