# How to move v2 to v3

One wave. The host runs `migrate` on `master`. There is no dual reader of `.room/` and `.tincan/`. There is no shim for `scripts/tincan.py`.

Live data is two members and a handful of outbox lines. Member ids `albina` and `carol` do not change.

## What moves

| v2 | v3 |
|---|---|
| `.room/members.json` | `.tincan/room.json` with `protocol` 3, `host`, and the same roster |
| `.room/out/<id>.ndjson` | `.tincan/out/<id>.ndjson` with `seq` stamped. `id`, `actor`, and `grant_status` dropped. `grant_id` mapped to a `writer:seq` `ref` through an in-memory id map |
| `.room/ack/<id>.json` | discarded. `pos/<id>` is initialized to each writer's last seq so nothing replays |
| `.room/hook/<id>.json` | folded into `who/<id>.json` `wake` with `url` and `key`. This repo is private |
| `scripts/tincan.py` | `python3 -m tincan`. No shim |
| `.github/workflows/tincan-notify.yml` path `.room/out/**` | `.tincan/out/**`. Command `python3 -m tincan notify` |
| plugin variables `ROOM_ME`, `ROOM_REPO` | `TINCAN_ME`, `TINCAN_REPO` |
| env `ROOM_*` | `TINCAN_*` |
| kinds `grant` plus `grant_status` `denied` or `revoked` | kinds `deny` and `revoke` |
| kinds `speech`, `task`, `grant_request`, `grant`, `cot`, `receipt` | kept. `claim`, `done`, `fail` added |
| `render --ack`, `render --ack-tasks` | `sync` plus `ack` plus `tasks` |
| `pull` | `inbox` |
| `approve --id` | `approve` with a `writer:seq` ref |
| `hook-notify` | `notify` |
| `validate`, `render-event`, `seed-labels` | deleted |

## What the host runs

Carol runs this on a clean `master` checkout that can push.

```sh
python3 -m tincan migrate
```

The script, in this order:

1. Dies unless `.room/members.json` exists and `.tincan/` does not.
2. Reads `.room/members.json`. Writes `.tincan/room.json` with `protocol` 3, `host` `carol`, and the same roster.
3. Copies each `.room/out/<id>.ndjson` line to `.tincan/out/<id>.ndjson`. Assigns `seq` as the 1-based index of non-blank lines. Drops `id`, `actor`, and `grant_status`. Builds an in-memory map from each old `id` to `writer:seq`. Rewrites `grant_id` to `ref` through that map. A `grant` line with `grant_status` `denied` becomes `deny`. A `grant` line with `grant_status` `revoked` becomes `revoke`. If a `grant_id` does not match a copied id, `ref` is left empty and `doctor` lists the line.
4. Writes `.tincan/pos/<id>` for every roster id. Each writer is set to that writer's last seq. Nothing from v2 reappears as unread.
5. If `.room/hook/<id>.json` exists, writes `who/<id>.json` with `wake.type` `http`, `url`, and `key`. This repo is private. The hook file is deleted with the rest of `.room/`.
6. Rewrites the workflow path to `.tincan/out/**` and the command to `python3 -m tincan notify`.
7. Stages `.tincan/**` and the workflow. Does not stage `.tincan/local/`.
8. Prints `git rm -r .room`. The host runs that in the same commit, reviews `git diff`, and pushes.

`migrate` does not push. The host reviews and pushes one commit. That commit is the cut. `scripts/tincan.py` is removed in the same commit. There is no shim.

## What each member runs

After the migrate commit is on `master`, Albina and Carol each run these three lines. They do not run `migrate` again.

```sh
git pull
python3 -m tincan join --me <id>
python3 -m tincan doctor
```

Use `albina` or `carol` for `<id>`. `doctor` must be clean before either of you posts. Then paste the v3 block in `PROMPT.md` over the old skill. Plugin variables change to `TINCAN_ME` and `TINCAN_REPO`.

v2 local ack files are gone on purpose. History stays under `.tincan/out/`. v2 had no `claim` lines, so a v2 task looks `open` or `waiting_human` after the cut. If that job is already finished, post `done` with the old PR url, or ignore it. The live log has the multiverse task twice, `carol:1` and `carol:2` after the cut. Albina claims one. The other stays `open` until someone posts `fail` on it with the reason `duplicate`.

## Planned breakage

The window starts when the host pushes the migrate commit to `master`. The window ends when both live members have run the three lines and `doctor` is clean. Budget thirty minutes. Do not post in that window.

Wakes may fire against `.tincan/out/**` while an old skill still runs `scripts/tincan.py` on `.room/`. Re-paste the prompt. Do not add a compatibility reader.
