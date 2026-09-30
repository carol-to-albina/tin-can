# Albina–Carol room

Grok Bot cannot seat two humans in one native channel. This plugin uses a
private GitHub repo as the shared log. Each person's Grok Bot pulls new
issues and speaks them in their own chat as the other person.

Albina's laptop can stay off. Work runs on each Grok Bot cloud computer.
Usage stays on each Cursor account. Skills and memory stay on each computer.

## What a room event is

One GitHub issue. Frontmatter plus a body.

```md
---
actor: carol
kind: speech
to: albina
---

can your research bot look at T
```

Kinds: `speech`, `grant_request`, `grant`, `cot`, `receipt`.
`cot` and `receipt` need `grant_id`.

Unread state is the label `unread:<recipient>`. The Actions workflow assigns
that person so GitHub notifies them. Their bot still has to `render` and embed.

## Setup

1. Push this tree to a **private** GitHub repo.
2. Put GitHub logins in `.room/members.json`. Leave `repo` as `owner/name`.
3. Install the plugin on both Grok Bot accounts. Set `ROOM_REPO` and `ROOM_ME`.
4. On each Grok Bot computer, `gh auth login` as that human.
5. `python3 scripts/room.py seed-labels --repo owner/name`
6. Add a five-minute routine. Prompt: `Check the room.`

## Commands

```sh
python3 scripts/room.py post --me carol --to albina --kind speech --body "hello"
python3 scripts/room.py render --me albina --ack
python3 scripts/room.py approve --me albina --issue 12
```

Offline checks:

```sh
python3 tests/test_room.py
```

## What this is not

Not a native Grok Bot group with two people in one transcript.
Not mutual repo write as the permission model. The grant labels are.
