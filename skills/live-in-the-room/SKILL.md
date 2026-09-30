---
name: live-in-the-room
description: >-
  Always-on voice for TinCan. Use on every turn in a
  room-enabled chat. Owned ndjson outboxes are the shared transcript. New
  events must be spoken as the other person, not as fetch results. A [task]
  line is work. Do it and post the result.
when-to-use: any message while this plugin is installed and ROOM_ME is set
---

# Live in the room

Grok Bot cannot put two humans in one native channel. This plugin fakes that
room. The log is owned ndjson outboxes under `.room/out/` on `ROOM_REPO`.
Your job is to make the user feel the other person just talked.

## Who you are

`ROOM_ME` is you. Other ids in `.room/members.json` are the rest of the room.

You keep your own skills and memory on this computer. You never read their
computer. You only read outbox events addressed to you or to `all`.

ROOM PACT in the start skill is already true.

## Every turn

1. Run `python3 scripts/tincan.py sync --me "$ROOM_ME" --ack`.
2. If it prints events, paste speech lines at the top of your reply. Do not
   say you pulled GitHub. Do not say an event id.
3. If a line is `[task]`, do that work now. Open a pull request. Checkout
   master, pull, post `--kind speech` with the PR url, then
   `render --ack-tasks`. `--push` only works on master. Do not only show
   the task and wait.
4. Then answer the user.

`--ack` writes your cursor in `.room/ack/$ROOM_ME.json` after the print,
but it leaves `[task]` unread. If it prints `(no new room events)`, skip
the embed.

## When the user talks

If they are speaking to the room or to another person, follow `speak-in-room`.
Use `--to all` when they are speaking to the whole room.
If they ask someone to help, cowork, or give a job, follow `speak-in-room`
and post `--kind task`.
If they `@` another person's bot or ask for hidden CoT, follow `handover`.

## Wake

A push under `.room/out/` runs `hook-notify`. It POSTs
`.room/hook/<recipient>.json` (`url` and `key`) when that file exists.
Otherwise it uses `GROK_WEBHOOK_URL_$ROOM_ME` and
`GROK_WEBHOOK_KEY_$ROOM_ME` (id uppercased, hyphens to underscore). Then
do the same as Check the room. Sync, embed, do every `[task]`, post the
result. Do not poll every five minutes.

## Never

- Dump raw `pull` JSON into chat
- Share hidden CoT without a live grant
- Print a PAT or ask them to type it as ordinary chat
- Sign in as a GitHub username. Present a Grok Bot secure secret
  request for a PAT that can write `ROOM_REPO`, then use that
- Add the other human as a GitHub write user and call that the room
- Stop after showing a `[task]` line
