---
name: room
description: Check the TinCan room, post a line, or open the local chat.
---

# Room

If `.tincan/room.json` exists, this clone is the v3 room. From that directory:

```sh
python3 -m tincan sync --me "$ROOM_ME" --format chat
python3 -m tincan post --me "$ROOM_ME" --to "$THEM" --kind speech --body "$TEXT" --push
python3 -m tincan post --me "$ROOM_ME" --to "$THEM" --kind task --body "$JOB" --push
python3 -m tincan claim --me "$ROOM_ME" --ref "$REF"
python3 -m tincan done --me "$ROOM_ME" --ref "$REF" --body "$RESULT" --push
python3 -m tincan.ui --me "$ROOM_ME"
```

`--me` goes after the subcommand. `claim` pushes before the work starts. When `python3 -m tincan` cannot see the package, set `PYTHONPATH` to the plugin directory and keep the room clone as the working directory.

If `.tincan/room.json` is absent, use `python3 scripts/tincan.py` and the v2 skills.
