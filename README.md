# Albina–Carol room

**v2.** The room log is owned ndjson outboxes. v1 used one GitHub issue per
event. That piled issues and serialized everyone onto one tracker. v2 gives
each member their own file so two or more bots can post at the same time.

Grok Bot cannot seat two humans in one native channel. This plugin uses a
private GitHub repo as the shared log. Each member appends to their own
outbox. Each Grok Bot pulls unread lines and speaks them in that person's
chat as the writer.

Albina's laptop can stay off. Work runs on each Grok Bot cloud computer.
Usage stays on each Cursor account. Skills and memory stay on each computer.

## What a room event is

One JSON object. One line in the actor's owned outbox
`.room/out/<actor>.ndjson`.

```json
{
  "id": "<12 hex chars>",
  "ts": "<ISO-8601 UTC>",
  "actor": "<member id>",
  "to": "<member id or all>",
  "kind": "speech|grant_request|grant|cot|receipt",
  "body": "<text>",
  "grant_id": "",
  "expires": "",
  "capabilities": "",
  "grant_status": ""
}
```

`id` is the first 12 hex characters of the SHA-1 of the canonical JSON
without `id`, keys sorted.

`to` is a member id or the literal `all`. `all` means every member except
`actor`.

Kinds: `speech`, `grant_request`, `grant`, `cot`, `receipt`.
`cot` and `receipt` need `grant_id`.

Unread state is the reader's cursor file `.room/ack/<me>.json`. The cursor
is the last processed event id from each writer. A push under `.room/out/`
runs `hook-notify`, which can POST to each recipient's Grok webhook.

## Setup

1. Push this tree to a **private** GitHub repo.
2. Put GitHub logins in `.room/members.json`. Leave `repo` as `owner/name`.
   Add more people as more keys under `members`. The files work with two
   members. A third person does not need a schema change.
3. Install the plugin on each Grok Bot account. Set `ROOM_REPO` and `ROOM_ME`.
4. On each Grok Bot computer, `gh auth login` as that human.
5. `python3 scripts/room.py seed-labels --repo owner/name` is optional.
   `post` no longer uses labels.
6. Set repo secrets `GROK_WEBHOOK_URL_ALBINA`, `GROK_WEBHOOK_KEY_ALBINA`,
   `GROK_WEBHOOK_URL_CAROL`, and `GROK_WEBHOOK_KEY_CAROL`. A push to
   `.room/out/` wakes those bots. Add a third member later by adding
   matching secrets.

## Commands

```sh
python3 scripts/room.py post --me carol --to albina --kind speech --body "hello" --push
python3 scripts/room.py post --me carol --to all --kind speech --body "hello room" --push
python3 scripts/room.py render --me albina --ack
python3 scripts/room.py approve --me albina --id <event-id>
```

Offline checks:

```sh
python3 tests/test_room.py
```

## What this is not

Not a native Grok Bot group with two people in one transcript.
Not mutual repo write as the permission model. The grant events are.
Not v1. Do not open a GitHub issue for a room line.
