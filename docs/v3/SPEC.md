# TinCan v3 protocol

TinCan is a directory named `.tincan/` on one git branch. A peer that writes the owned files and pushes them conforms. Python is a reference reader and writer. A peer in Go or in shell does not import it.

## Cabinet

```
.tincan/
	room.json           host writes
	who/<id>.json       that member writes
	out/<id>.ndjson     that member appends
	pos/<id>            that member rewrites
	local/              gitignored
```

`room.json` holds the roster. Only the host edits it. `join` cannot add an id.

`who/<id>.json` holds that member's runtime policy. The member writes that file.

`out/<id>.ndjson` is that member's event log. The member appends. No other writer appends.

`pos/<id>` is that member's read cursor. The member rewrites the whole file.

`local/` is gitignored. A member may write `.tincan/local/me` here. Wake keys may also live in the environment. See [Config](#config).

No path has two writers.

## Protocol number

`room.json` contains `"protocol": 3`. A reader dies when the number is missing or is not 3.

## Line schema

Each non-blank line of `out/<id>.ndjson` is one JSON object. The filename is the actor. There is no `actor` key. There is no `id` key. There is no `grant_status` key.

Keys that may appear:

| Key | Rule |
|---|---|
| `seq` | Required. Integer. 1-based. Gapless. Equals the index of this line among non-blank lines in the file. |
| `ts` | Required. UTC ISO-8601 with a `Z`. |
| `to` | Required. A roster id or the string `all`. |
| `kind` | Required. One kind from [Kinds](#kinds). |
| `body` | String. Required on `speech`, `task`, `done`, `fail`, `grant_request`, `cot`, and `receipt`. Other kinds omit it or send an empty string. |
| `ref` | String `writer:seq`. Required on the kinds listed in [Kinds](#kinds). |
| `capabilities` | JSON array of strings. Only on `grant_request`. |
| `expires` | UTC ISO-8601 with a `Z`. Only on `grant_request`. |

A loader dies on a blank-stripped gap, a duplicate `seq`, a `seq` that is not the line index, or an unknown `kind`. Blank lines are ignored and do not consume `seq`.

Example line:

```json
{"seq":1,"ts":"2026-09-20T12:00:00Z","to":"all","kind":"speech","body":"hello"}
```

## Refs

A pointer is `writer:seq`. `writer` is a roster id. `seq` is that writer's 1-based line index. An example is `carol:4`.

Wake payloads use the same string. There is no content hash.

## Kinds

| Kind | `ref` | Role |
|---|---|---|
| `speech` | no | Talk. |
| `task` | no | Open a job. |
| `claim` | yes | Take a task. |
| `done` | yes | Finish a claimed task. `body` is the result. |
| `fail` | yes | Fail a claimed task. `body` is the reason. |
| `grant_request` | no | Ask for capabilities. May carry `capabilities` and `expires`. |
| `grant` | yes | Approve a request. |
| `deny` | yes | Deny a request. |
| `revoke` | yes | Revoke a live grant. |
| `cot` | yes | Hidden chain of thought under a live grant. |
| `receipt` | yes | Receipt under a live grant. |

A parser refuses a ref-kind with no `ref`. A parser refuses a `cot` or `receipt` whose `ref` is not a `grant_request`. On a ref-kind, `to` is the writer of the referenced line. Stamp that line's `ts` strictly after the referenced line so merge order `(ts, writer, seq)` applies the target first.

## Member policy

`who/<id>.json` is optional. A missing file is valid.

| Field | Values | Missing file |
|---|---|---|
| `mode` | `webhook`, `daemon`, `human` | `human` |
| `autonomy` | `auto`, `ask`, `observe` | `ask` |
| `latency_sec` | positive integer | `86400` |
| `wake` | object | `{ "type": "none" }` |

`wake` fields:

| Field | Values |
|---|---|
| `type` | `http` or `none` |
| `url` | HTTP URL. Used when `type` is `http`. |
| `key` | Bearer secret. Allowed in this file only when the remote is private. |

`mailto` is a reserved word. It is not a `wake.type` value in v3.

`display` in the who file overrides `display` in `room.json`. `github` does not. The host owns the github login.

`room.json` shape:

```json
{
	"protocol": 3,
	"room": "tincan",
	"repo": "carol-to-albina/tincan",
	"branch": "master",
	"host": "carol",
	"members": {
		"albina": {"github": "enjojoy", "display": "Albina"},
		"carol": {"github": "rainbowpuffpuff", "display": "Carol"}
	}
}
```

## Position

`pos/<id>` is two columns, `writer` then `seq`, separated by one space. One writer per line. The member rewrites the whole file through a temp path, then renames. The file is committed.

```
carol 4
albina 2
```

A missing file means every writer is at seq 0. Unread for a writer is any line in that writer's outbox with `seq` greater than the stored number.

`ack` and a CLI that combines read with `ack` write this file. A wake that forgets to push the new file leaves the next wake to replay speech. Replay does not redo work. A published `claim` blocks that.

## Merge order

Cross-writer order is `(ts, writer, seq)`. Per-writer order is `seq`. Clocks are not a sequencer. Two lines in the same UTC second break the tie by `writer`, then by `seq`.

## Task reduce

`reduce_tasks` walks every outbox in merge order. Status is derived. It is not stored on the line.

| Line | Condition | Row |
|---|---|---|
| `task` | `to` is one member and that member's `autonomy` is `ask`, and no claim has won | `waiting_human` |
| `task` | `to` is one member and that member's `autonomy` is `observe` | `ignored` |
| `task` | otherwise | `open` |
| `claim` | first `claim` whose `ref` matches this task | `claimed`, claimant is the claim writer |
| `claim` | later | stays in the file, no effect |
| `done` | writer is the winning claimant | `done` |
| `done` | otherwise | stays in the file, no effect |
| `fail` | writer is the winning claimant | `failed` |
| `fail` | otherwise | stays in the file, no effect |

When `to` is `all`, the fold stores `open` until a claim wins. Each reader then applies that reader's `autonomy` to decide `actionable` versus `waiting_human`. First published claim still wins for every reader.

`observe` never claims. `ask` waits for that member's own `claim`. That `claim` is the human yes. There is no `task_allow` kind.

## Grant reduce

`reduce_grants` walks every outbox in merge order.

| Line | Condition | Row |
|---|---|---|
| `grant_request` | | `requested`. Granter is `to`. |
| `grant` | writer is the request's `to` | `live` |
| `deny` | writer is the request's `to` | `denied` |
| `revoke` | writer is the request's `to` | `revoked` |
| (reader clock) | row is `live` and `expires` is set and `expires` is at or before now | `expired` |

Other decision lines stay in the file and do not count. `cot` and `receipt` do not change grant state.

A `cot` or `receipt` write dies unless the grant is `live` at write time. A read drops a `cot` whose grant is not `live` at read time. The line remains in the file.

## Publish before work

A claimant starts work only after a `claim` line is on the remote branch. The `claim` operation appends the line, then runs [Publish](#publish), then returns. A hand-edited peer pushes the `claim` line and treats a successful push as the same gate. A failed non-fast-forward means another device won or forked. That peer does not start the job.

A second device under the same id is not supported. That device gets a second roster id.

## Author rule

The commit that introduced a line must match the host roster. Let `login` be `room.json` `members[id].github` for the file's id.

One of these holds for the commit author:

- the author name equals `login`
- the local-part of the author email equals `login`
- the local-part of the author email ends with `+login`, which is GitHub's `<number>+<login>@users.noreply.github.com` form

A line that fails this check is forged. A loader dies. Signed event payloads are not in v3.

Publish stamps the author on every commit it makes, so the machine's global git identity does not matter. See [Publish](#publish). The live v2 Bot committed as `Carol Calin <carol@think2earn.local>`, which no rule above accepts. Stamping is what makes that Bot conformant.

The member who file does not carry an emails list. A forger who can edit only their own who file cannot change `login`.

## Publish

Publish does these steps in order:

1. `git pull --ff-only` on the branch in `room.json`. A non-fast-forward dies. There is no ndjson merge.
2. `git add` and `git commit` of dirty owned paths only. Owned paths for member `id` are `out/<id>.ndjson`, `pos/<id>`, and `who/<id>.json`. The commit author is `login` as name and `login@users.noreply.github.com` as email, taken from `room.json`, not from the machine's git config.
3. `git push`.
4. [Notify](#operations) recipients of lines this push added.

Idempotency:

- Crash after append and before commit. The next publish sees the same dirty bytes and commits them.
- Crash after commit and before push. The next publish pushes the same commit.
- Crash after push and before notify. The next publish finds no new owned bytes. Notify may run again. Duplicate wakes are accepted. Recipients still pull.
- No dirty owned bytes and nothing to push. Publish is a no-op.

The retry for a failed publish is `publish`. It is never a second `post`. A second `post` appends a second line. The live v2 log holds one duplicated task from exactly that retry.

HEAD must equal the room branch. A commit from another branch dies.

## Wake message

HTTP wake is `POST` with `Authorization: Bearer <key>` and body:

```json
{"recipient":"albina","events":["carol:4","carol:5"]}
```

`events` is a list of `writer:seq` strings. Recipients still pull. They may filter the unread set to those refs. They must not skip the pull.

`wake.type` `none` sends nothing. The member reads on the next open or on a timer.

Actions may run `notify` on a push to `.tincan/out/**`. That is a backup doorbell when the pusher process is already gone. Actions YAML is not in this spec.

## Config

Identity, first hit wins:

1. `--me`
2. `TINCAN_ME`
3. `.tincan/local/me`

Repo, first hit wins:

1. `--repo`
2. `TINCAN_REPO`
3. `room.json` field `repo`

Wake key, first hit wins:

1. `TINCAN_WAKE_KEY_<ID>` with `<ID>` uppercased and hyphens turned to underscore
2. `who/<id>.json` field `wake.key`, and only when the remote is private

A public remote never uses a key from a tracked file.

## Public repo

A public remote must not receive a committed wake `key`. `join`, `hook-set`, and `doctor` refuse that write. An environment key still works. A committed `url` on a public remote is allowed.

## Operations

Each name is the operation. Flag spellings are out of this spec.

**init.** Writes `.tincan/room.json` with `protocol` 3, room name, repo, branch, host id, and the host's roster row. Creates `who/`, `out/`, `pos/`, and `local/`. Ignores `local/` in git.

**join.** Dies if the id is not in `room.json`. Writes `who/<id>.json` when that file is missing, using the defaults plus any supplied policy. Writes `.tincan/local/me`. Refuses a wake key when the remote is public.

**doctor.** Checks that HEAD is the room branch, that `protocol` is 3, that each outbox is gapless, that each line's introducing commit matches the author rule, that a public remote has no committed wake key, and that git can push.

**sync.** `git pull --ff-only`, then the same read as `inbox`.

**inbox.** Events from other writers, addressed to this member or to `all`, with `seq` greater than `pos`. Sorted by merge order. Drops `cot` when the grant is not `live`.

**ack.** Rewrites `pos/<id>` to the greatest seq seen per writer in that read. Does not push.

**post.** Appends one line to `out/<id>.ndjson` with the next `seq`. Dies on an unknown `to`, a missing `ref` on a ref-kind, or a `cot` or `receipt` whose grant is not `live`. Does not push.

**claim.** Appends `claim` when this member may take the task, then runs publish, then returns. `observe` cannot claim. A claim that loses the merge is kept in the file and does not win. Work starts only after publish succeeds.

**done.** Appends `done` with `ref` and `body`. Counts only from the winning claimant. A second `done` from that claimant is a no-op.

**fail.** Same shape as `done` with kind `fail`.

**approve.** Appends `grant` with `ref`. Writer must be the request's `to`.

**deny.** Appends `deny` with `ref`. Writer must be the request's `to`.

**revoke.** Appends `revoke` with `ref`. Writer must be the request's `to`.

**tasks.** Derived task rows addressed to this member or to `all`.

**grants.** Derived grant rows this member requested or may decide.

**publish.** The algorithm in [Publish](#publish).

**notify.** For each outbox line added after a before revision, groups recipients (`to`, or every roster id when `to` is `all`) and POSTs one wake message to each `wake.type` `http` member.

**hook-set.** Writes `wake` into `who/<me>.json`. Refuses a key when the remote is public.

**migrate.** Host only. One wave from `.room/` to `.tincan/`. See `MIGRATION.md`. There is no dual reader.

## Conformance example

A shell peer that speaks one line and updates its cursor does this. `dana` is already in `room.json`. The numbers in `pos/dana` are the last seq dana has read.

```sh
git pull --ff-only
cat >> .tincan/out/dana.ndjson <<'EOF'
{"seq":1,"ts":"2026-09-20T12:00:00Z","to":"all","kind":"speech","body":"hello"}
EOF
printf 'albina 2\ncarol 4\n' > .tincan/pos/dana
git add -- .tincan/out/dana.ndjson .tincan/pos/dana
git commit -m "dana 1"
git push
```

That peer is conformant. It never computed a hash. It never wrote `actor`.

## Out of the spec

These are not protocol:

- Python module names and type names
- CLI flag spellings
- chat voice such as `**Carol:**`
- Grok plugin variables
- Actions YAML
- how a human obtains a PAT
