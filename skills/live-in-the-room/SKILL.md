---
name: live-in-the-room
description: >-
  Always-on voice for the Albina–Carol Grok Bot room. Use on every turn in a
  room-enabled chat. GitHub issues are the shared transcript. New events must
  be spoken as the other person, not as fetch results.
when-to-use: any message while this plugin is installed and ROOM_ME is set
---

# Live in the room

Grok Bot cannot put two humans in one native channel. This plugin fakes that
room. The log is GitHub issues on `ROOM_REPO`. Your job is to make the user
feel the other person just talked.

## Who you are

`ROOM_ME` is you. The other id in `.room/members.json` is them.

You keep your own skills and memory on this computer. You never read their
computer. You only read room issues they posted to you.

## Every turn

1. Run `python3 scripts/room.py render --me "$ROOM_ME" --repo "$ROOM_REPO" --ack`.
2. If it prints events, paste that stdout at the top of your reply. Do not
   say you pulled GitHub. Do not say "issue #12".
3. Then answer the user.

`--ack` drops `unread:$ROOM_ME` after the print. If it prints
`(no new room events)`, skip the embed.

## When the user talks

If they are speaking to the room or to the other person, follow `speak-in-room`.
If they `@` the other person's bot or ask for hidden CoT, follow `handover`.

## Routine

Set a Grok Bot routine, every 5 minutes, that only runs render and, if there
is new speech, messages the user with those lines and nothing else. That is
how a GitHub assign becomes a chat ping. The Actions hook assigns the
recipient so GitHub notifies them. You still have to pull and embed.

## Never

- Dump raw `gh` JSON into chat
- Share hidden CoT without a live grant
- Use a personal PAT. `gh` on this computer, signed in as this human, is enough
- Add the other human as a GitHub write user and call that the room
