---
name: speak-in-room
description: >-
  Post the user's words into the GitHub room log so the other person's Grok
  Bot can embed them. Use when the user talks to the room, to Albina, to
  Carol, or says tell them / send this over.
---

# Speak in the room

```sh
python3 scripts/room.py post \
  --me "$ROOM_ME" \
  --to "$THEM" \
  --kind speech \
  --body "$TEXT" \
  --repo "$ROOM_REPO"
```

`$THEM` is the other id in `.room/members.json`. `$TEXT` is what the user
wants the other side to hear. Prefer their words. Add a short bot note only
when they asked you to explain.

After post, tell the user it is in the room. Do not claim the other person
has read it until their bot acks.

The Actions hook assigns them. Their bot's next render will speak this as you.
