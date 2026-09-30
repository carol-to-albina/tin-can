# Cursor caller

You are the member in `.tincan/local/me`. If that file is missing, run
`python3 -m tincan join --me <id>` once. Then `python3 -m tincan doctor`.

Every turn, from this clone, on the branch in `.tincan/room.json`:

```sh
python3 -m tincan sync --ack --push
python3 -m tincan tasks
```

Stdout is JSON. Speak speech as the other member. Do not narrate git.

If a row is `open` and your `autonomy` is `auto`, `claim` before you
start. After the PR exists, `done` with the PR url. If a row is
`waiting_human`, ask the user before `claim`. If a row is `claimed` by
someone else, skip it.

When the user talks to a member or to the room:

```sh
python3 -m tincan post --to <id-or-all> --kind speech --body "<their words>" --push
```

When they assign work:

```sh
python3 -m tincan post --to <id> --kind task --body "<job>" --push
```

Write only `.tincan/out/<you>.ndjson`, `.tincan/pos/<you>`, and
`.tincan/who/<you>.json`. Never another member's files.
