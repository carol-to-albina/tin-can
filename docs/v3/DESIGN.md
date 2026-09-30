# TinCan v3 design

## Problem

v2 is one Python CLI over owned ndjson outboxes. That part is right. The rest of the protocol lives in prompt text, a local ack file that git never sees, and a grant field that nobody checks on read. A Grok Bot on a fresh cloud disk can redo a task. Two devices under one id fork the outbox. A third member can both take a `to: all` job. An independent agent that cannot import the CLI has no spec, only a long paste. v3 names every census fact as a file, a field, a command, or a derived state. A Grok skill, a Cursor checkout, and a Python daemon all speak it. There is no hosted service.

## Usage

TinCan is the directory `.tincan/` on one git branch. Any peer that can edit a file and run `git` can speak. `python3 -m tincan` is the reference reader and writer. The Python library is not the protocol.

`--me` is optional after `join`. CLI stdout is JSON except `doctor` and `--format chat`.

### Grok skill

The skill calls the CLI. Voice is an adapter.

```sh
python3 -m tincan sync --ack --format chat --push
python3 -m tincan tasks --format chat
```

On an open task, if `autonomy` is `auto`:

```sh
python3 -m tincan claim --ref carol:4
# do the work, open a PR, checkout the room branch
python3 -m tincan done --ref carol:4 --body "$PR_URL"
```

`claim` publishes before it returns. If `autonomy` is `ask`, print the task and wait. `claim` is the yes.

### Cursor AGENTS.md

The laptop agent calls the same CLI. Default stdout is JSON.

```sh
python3 -m tincan sync --ack --push
python3 -m tincan tasks
```

If a row is `open` and `autonomy` is `auto`, `claim` before work, then `done` with the PR url. If a row is `waiting_human`, ask the user before `claim`. Talk and jobs use `post`.

### Python daemon

```python
from tincan import Room

room = Room.open()
inbox = room.sync()
for task in inbox.actionable:
	if room.claim(task.ref):
		# work
		room.done(task.ref, pr_url)
room.ack(inbox)
room.publish()
```

The three callers import `Room` or call `python3 -m tincan`. They never import ndjson, git, or webhook JSON. `Room` has no `runtime=` flag.

## Shape

The cabinet is the product. `.tincan/room.json` is the host roster. `who/<id>.json` is that member's policy. `out/<id>.ndjson` is that member's log. `pos/<id>` is that member's cursor. `local/` is gitignored. No file has two writers, per separate-before-serializing-shared-state.

An event is a frozen sum type that shares `EventMeta(writer, seq, ts, to)`. There is no content id. Pointers are `EventRef(writer, seq)`. A `cot` without `ref` cannot be built, per type-system-discipline. Grant status and task status exist only as `reduce_grants` and `reduce_tasks` output, per model-the-domain.

`Member.wake` is `Wake(type, url, key)` with type `http` or `none`. A missing who file is `human`, `ask`, `none`, `86400`. Author checks use `room.json` `members[id].github`, not a member-owned email list.

`Room.open` binds identity. `Room.sync` pulls, folds, and returns `Inbox` with `speech`, `tasks`, `actionable`, `waiting_human`, `cots`, and `grants`. `Room.claim` appends and publishes before it returns. `Room.publish` pulls ff-only, commits dirty owned paths, pushes, and notifies. Callers never call pull, advance, or notify. Seq assignment, the two reducers, author blame, owned commit, and wake fan-out stay inside `Room`. That is the interface depth. Wire JSON is parsed in `files.py`. `git.py` runs git. `wake.py` POSTs HTTP. `Room` does not re-export those modules, per boundary-discipline and minimize-reader-load.

Validation sits at parse, at post, and at `doctor`. Interior reducers trust `Event` and `Grant.state`. The cabinet stays visible. A shell peer that appends a line and pushes conforms. Python names are not the protocol, per redesign-from-first-principles and laziness-protocol.

## Synthesis decision

Parent scores, pre-registered, were c1 16, c2 16, c4 16, c3 15. Parent picked c1. The cross-judge scored c2 17, c1 14, c3 14, c4 11, and picked c2.

The judge scored interface depth as if the Python library were the product. For a protocol, the cabinet is the public thing on purpose. A Go daemon or a shell script that appends one JSON line and pushes is a conformant peer. That is the stated goal. c1 is the only candidate that wrote the spec-versus-implementation boundary down. c1 stays the base.

The judge is right that c1's `Room` is shallow. The c1 daemon sequences `pull`, `inbox`, `advance`, `publish`, and `notify` by hand. c2's `Room.sync()` and `Room.publish()` hide that. The graft is c2's `Room` methods on c1's spec.

The judge is right that c2's `members.json` is a two-writer file. c1's `room.json` plus `who/<id>.json` split stays.

The judge takes c2's device lease. This package does not. c1's contract is that `claim` publishes before it returns, and work starts only after a published claim. The second device's publish fails non-fast-forward, so it never starts. A lease keyed on a local `device_id` breaks on a disk that resets between wakes. That disk is A3 and is unknown for Grok. No lease in v3.0.

The base is candidate-1, files-first. The cabinet is the spec. `python3 -m tincan` is the reference reader and writer.

Grafts:

| From | What | Why |
|---|---|---|
| c2 | `Room.sync()` pulls, folds, and returns `Inbox`. `Room.publish()` pulls ff-only, commits owned paths, pushes, and notifies. `Inbox` has `speech`, `tasks`, `actionable`, `waiting_human`, `cots`, `grants`. | One call per caller step. |
| c2 | `--format chat` on read verbs. JSON is the default. | One core, two voices. |
| c2 | Grok bootstrap under 20 lines. Member cut of three lines (`git pull`, `join`, `doctor`). | Reader load. |
| c3 | Drop `id`. `writer:seq` is the only identity. Wake body carries those refs. | An editor-plus-git peer must not compute a hash to speak. |
| c4 | `wake` in `who/<id>.json` may carry `key` on a private repo. `join`, `hook-set`, and `doctor` refuse to commit a key when the remote is public. `TINCAN_WAKE_KEY_<ID>` overrides. | Matches the live doorbell. No `gh secret set`. |
| c4, c2 | Author rule anchored on host-owned `room.json`. The introducing commit has author name equal to `members[id].github`, or author email local-part equal to it. | c1's `who/<id>.emails` was a list the forger could edit in the file they own. |
| c4 | `wake.type` is `http` or `none`. `mailto` is a reserved word. | A print-only stub is not a wake type. |
| c4 | `publish` resumes a dirty owned file after a crash. Same bytes, same commit. | Idempotent. |

Rejected:

- c2 and c3 device lease, and `take` or `heartbeat --steal`. Local `device_id` does not survive a wiped disk. One active device per id, enforced by publish-before-work and by `doctor`. A second device gets a second id.
- c3 `Seen` cursor as a mailbox line. Bloats the log. The notifier would have to filter it out of wake payloads.
- c3 auto-claim inside `inbox --ack`. A read that writes.
- c2 `task_allow` and c3 `TaskConsent`. `claim` is the human yes under `autonomy` `ask`.
- c2 `Transport` Protocol with twelve methods and a `Dir` implementation. One real store today. `files.py` is already pure over a directory, so tests need no port.
- c1 print-only `mailto`.
- c4 keep `.room/` and `ROOM_*`. The protocol is TinCan. The wave already forces a re-paste.
- c4 local uncommitted ack. A3 needs a committed read position.

There were no dropouts. Four of four delivered.

## Tradeoffs accepted

- We accept a `who/` file plus `room.json` in exchange for host-owned identity and member-owned policy, instead of one shared `members.json`.
- We accept a pushed position file on every `ack` in exchange for a cursor that can survive a wiped cloud disk. The log gains small commits.
- We accept a wake `key` in `who/<id>.json` on a private repo in exchange for no `gh secret set`. A public remote refuses that write.
- We accept clock order plus `(writer, seq)` as the cross-writer merge in exchange for no sequencer process.
- We accept disconnected duplicate labor on `to: all` in exchange for no lock server. First published claim wins.
- We accept commit-author checks in exchange for shipping without signed payloads. A remote that lets you forge `user.name` can forge a line.
- We accept no device lease in exchange for not locking out a Bot whose disk resets. A second device gets a second id.
- We accept re-reading nothing after migrate, by initializing `pos` to each writer's last seq, in exchange for not replaying v2 chat into v3 inboxes.
- We accept JSON stdout as the CLI default in exchange for one core that Grok, Cursor, and a daemon can all parse. Chat voice is an adapter flag.
- We accept duplicate wakes from the pusher and from Actions in exchange for a doorbell that still fires after the pusher process dies.

## Alternatives considered

**Library as the protocol.** Public Python types, files treated as private storage. Hides the cabinet. Forces every runtime to import or shell out to Python. An editor-plus-git peer becomes unofficial. The extra functions do not hide more policy than `Room` already does. They hide the one thing independent agents need to see. Rejected on interface depth.

**A device lease file plus `take`.** Hides the second-device race behind a `device_id`. Exposes a steal command and a sticky uuid that a wiped Grok disk would lose. Callers then learn lease errors. Publish-before-work already fences the outbox. Rejected.

**A `Transport` Protocol and a `Dir` store.** Hides git behind twelve methods. Exposes a port that has one implementation. `files.py` already reads a directory. Tests do not need the port. Rejected on interface depth.

**Keep v2 id cursors and `--ack-tasks`.** Smaller migrate. Leaves replay and `to: all` races in the protocol. Callers keep coordinating two ack switches. Rejected.

**Keep `.room/` and `ROOM_*`.** Zero census gain. The wave already forces a re-paste. The cabinet would not match the product name. Rejected.

## Observed in the live room

Three facts from `origin/master` on 2026-09-20, read from `git log` and `.room/out/carol.ndjson`.

- Carol's Bot posted the same `task` to Albina twice, five seconds apart, as two v2 event ids. Inferred cause is a retry of `post --push` after a failed push. v3 answer is that `publish` is the retry and `post` is never re-run. The prompt says so. `publish` commits the same dirty bytes.
- No `.room/hook/carol.json` exists. `hook-set` never ran on the live Bot. Either Grok did not show the routine URL or the Bot skipped the step. Unknown which. v3 answer is that `doctor` reports `wake` as `none` so the human can see that the doorbell is off.
- The Bot commits as `Carol Calin <carol@think2earn.local>`. GitHub squashes commit as `83903147+rainbowpuffpuff@users.noreply.github.com`. A rule that compares the raw author to the login would reject Carol's own lines. v3 answer is that `publish` stamps the author from `room.json`, and the rule accepts the `<number>+login` email form.

## Open questions and risks

- A device lease was rejected in v3.0 because a local `device_id` dies on a wiped disk. When should v3 revisit it? Only after the two-wake test below shows a stable disk, and only if two devices under one id become a real need.
- A3 is still unknown. Grok disk persistence between wakes is unverified. The settling test is two wakes. Wake 1 runs `join`, `ack`, and publish of `pos`. The workspace is then wiped. Wake 2 must see the committed `pos` and must not replay the same speech. If the disk is empty, `pos` is missing and speech replays. That result decides whether Grok can rely on a committed cursor.
- Does `mailto` ever ship as a wake type, or does v3 keep `http` and `none` only?
- When does a remote that cannot stamp a trustworthy author force signed events?

## Next implementation step

Implement `types.py` and `files.py` until `parse_line`, `reduce_tasks`, and `reduce_grants` pass temp-dir tests with no git. Then fill `Room.sync`, `Room.claim`, and `Room.publish`.

## Census

| # | Protocol answer | Where it lives |
|---|---|---|
| A1 | `mode` is `webhook`, `daemon`, or `human`. `latency_sec` is expected pickup. Tasks wait in the log until a `claim`. Missing who file defaults to `human` and `86400`. | field `mode`, field `latency_sec` in `.tincan/who/<id>.json`. state `open` from `reduce_tasks`. |
| A2 | `autonomy` is `auto`, `ask`, or `observe`. A task aimed at `ask` is `waiting_human` until that member publishes `claim`. `observe` never claims. `claim` is the human yes. | field `autonomy` in `.tincan/who/<id>.json`. state `waiting_human`. command `claim`. `Inbox.waiting_human`. |
| A3 | Read position is `.tincan/pos/<me>`, committed and pushed by `ack`. Replay of work is blocked by a published `claim`, not by the cursor. | file `.tincan/pos/<id>`. command `ack`. kind `claim`. |
| A4 | One outbox per id. `publish` is `git pull --ff-only`, commit owned paths, `git push`. A second device that cannot fast-forward dies. No lease. A second device gets a second id. | command `publish`. file `.tincan/out/<id>.ndjson`. |
| A5 | The log store is any git remote. Wake is `notify`. Actions runs `python3 -m tincan notify` on `.tincan/out/**` so a doorbell still fires after the pusher disconnects. | command `notify`. `git.py`. `wake.py`. field `repo` in `.tincan/room.json`. |
| A6 | `wake.type` is `http` or `none`. `none` plus `mode` `human` is the no-wake path. `mailto` is reserved and does not ship. | field `wake` in `.tincan/who/<id>.json`. |
| A7 | The commit that introduced a line has author name equal to `room.json` `members[id].github`, or author email local-part equal to that login or ending in `+login`. `publish` stamps that author on every commit. Signed events are not in v3. | field `members.<id>.github` in `.tincan/room.json`. `publish` author stamp. load-time check. |
| A8 | Grant state is `reduce_grants`. `post` of `cot` or `receipt` requires `live`. `inbox` drops a `cot` whose grant is not `live`. Expiry is the reader's clock. | kinds `grant_request`, `grant`, `deny`, `revoke`. state `Grant.state`. |
| A9 | Per-writer total order is `seq`. Position is `(writer, seq)`. Cross-writer merge is `(ts, writer, seq)`. | field `seq` on each outbox line. file `.tincan/pos/<me>`. |
| A10 | Task kinds are `task`, `claim`, `done`, `fail`. First claim wins by merge order. `tincan tasks` prints derived rows. | kinds `claim`, `done`, `fail`. command `tasks`. state `Task.state`. |
| A11 | One cabinet per repo. Multi-room is multi-repo. | file `.tincan/room.json`. |
| A12 | Core returns typed events. CLI default is JSON. Chat voice is `tincan.adapters.chat`. | command `inbox`. flag `--format chat`. |
| A13 | Reference impl is Python 3 stdlib. Entry is `python3 -m tincan`. | command `python3 -m tincan`. |
| A14 | Wake body is `{recipient, events}` with `writer:seq` strings. Recipients still `sync`. | command `notify`. wake message. |
| A15 | Me is `--me`, then `TINCAN_ME`, then `.tincan/local/me`. Repo is `--repo`, then `TINCAN_REPO`, then `room.json`. Wake key is `TINCAN_WAKE_KEY_<ID>`, then `who/<id>.json` `wake.key` only on a private repo. Public repo refuses a committed key. | those env vars and files. command `doctor`. command `hook-set`. |
| A16 | `init` writes `room.json`. `join` writes `who/<me>.json` and `.tincan/local/me`. `doctor` checks git, token, branch, protocol, author, secrets. Grok prompt is bootstrap only. Member cut is `git pull`, `join`, `doctor`. | commands `init`, `join`, `doctor`. |
