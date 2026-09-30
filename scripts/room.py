#!/usr/bin/env python3
"""Owned ndjson outboxes for an N-person Grok Bot room."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KINDS = ("speech", "grant_request", "grant", "cot", "receipt")
GRANT_STATUSES = ("requested", "live", "denied", "expired", "revoked")
KIND_ALIASES = {
    "grant-request": "grant_request",
    "grant_request": "grant_request",
}
EVENT_KEYS = (
    "id",
    "ts",
    "actor",
    "to",
    "kind",
    "body",
    "grant_id",
    "expires",
    "capabilities",
    "grant_status",
)

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)

ROOT = Path(__file__).resolve().parents[1]


def room_root() -> Path:
    raw = os.environ.get("ROOM_ROOT")
    return Path(raw).resolve() if raw else ROOT


def room_dir() -> Path:
    return room_root() / ".room"


def members_path() -> Path:
    return room_dir() / "members.json"


def out_path(actor: str) -> Path:
    return room_dir() / "out" / f"{actor}.ndjson"


def ack_path(me: str) -> Path:
    return room_dir() / "ack" / f"{me}.json"


def die(msg: str, code: int = 2) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def load_members() -> dict[str, Any]:
    path = members_path()
    if not path.exists():
        die(f"missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def member_ids(cfg: dict[str, Any]) -> list[str]:
    return list(cfg["members"])


def display_name(cfg: dict[str, Any], actor: str) -> str:
    row = cfg["members"].get(actor) or {}
    return str(row.get("display") or actor)


def require_me(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    cfg = load_members()
    me = args.me or os.environ.get("ROOM_ME") or ""
    if not me:
        die("pass --me or set ROOM_ME")
    if me not in member_ids(cfg):
        die(f"unknown me {me!r}")
    return cfg, me


def event_id_arg(args: argparse.Namespace) -> str:
    eid = (getattr(args, "id", "") or getattr(args, "issue", "") or "").strip()
    if not eid:
        die("pass --id")
    return eid


def normalize_kind(kind: str) -> str:
    k = KIND_ALIASES.get(kind, kind)
    if k not in KINDS:
        die(f"unknown kind {kind!r}. want one of {', '.join(KINDS)}")
    return k


def check_address(cfg: dict[str, Any], actor: str, to: str) -> None:
    actors = member_ids(cfg)
    if actor not in actors:
        die(f"actor {actor!r} is not in .room/members.json")
    if to != "all" and to not in actors:
        die(f"to {to!r} is not in .room/members.json")
    if to != "all" and actor == to:
        die("actor and to must differ")


def parse_frontmatter(body: str) -> tuple[dict[str, str], str]:
    m = FRONTMATTER.match(body.strip())
    if not m:
        die("issue body needs YAML frontmatter between --- lines")
    raw, rest = m.group(1), m.group(2)
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            die(f"bad frontmatter line: {line}")
        key, val = line.split(":", 1)
        meta[key.strip()] = val.strip().strip("\"'")
    return meta, rest.strip()


def event_from_meta(meta: dict[str, str], body: str, cfg: dict[str, Any]) -> dict[str, Any]:
    actor = meta.get("actor", "")
    kind = normalize_kind(meta.get("kind", ""))
    to = meta.get("to", "")
    check_address(cfg, actor, to)
    grant_id = meta.get("grant_id") or ""
    if kind in ("cot", "receipt") and not grant_id:
        die(f"{kind} needs grant_id")
    return {
        "actor": actor,
        "kind": kind,
        "to": to,
        "grant_id": grant_id,
        "expires": meta.get("expires") or "",
        "capabilities": meta.get("capabilities") or "",
        "body": body,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def event_id(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def build_event(
    *,
    actor: str,
    to: str,
    kind: str,
    body: str,
    grant_id: str = "",
    expires: str = "",
    capabilities: str = "",
    grant_status: str = "",
    ts: str | None = None,
) -> dict[str, Any]:
    payload = {
        "ts": ts or utc_now(),
        "actor": actor,
        "to": to,
        "kind": kind,
        "body": body,
        "grant_id": grant_id,
        "expires": expires,
        "capabilities": capabilities,
        "grant_status": grant_status,
    }
    ev = {"id": event_id(payload)}
    ev.update(payload)
    return {key: ev[key] for key in EVENT_KEYS}


def render_line(cfg: dict[str, Any], ev: dict[str, Any]) -> str:
    who = display_name(cfg, ev["actor"])
    kind = ev["kind"]
    if kind == "speech":
        return f"**{who}:** {ev['body']}"
    if kind == "grant_request":
        extra = ev.get("capabilities") or "share_hidden_cot"
        return f"**{who}:** [asks for {extra}] {ev['body']}"
    if kind == "grant":
        return f"**{who}:** [grant {ev.get('grant_status') or 'live'}] {ev['body']}"
    if kind == "cot":
        return f"**{who}:** [hidden CoT under grant {ev['grant_id']}]\n{ev['body']}"
    if kind == "receipt":
        return f"**{who}:** [receipt grant {ev['grant_id']}] {ev['body']}"
    return f"**{who}:** {ev['body']}"


def repo_from_env(cfg: dict[str, Any], explicit: str) -> str:
    repo = explicit or os.environ.get("ROOM_REPO") or os.environ.get("GITHUB_REPOSITORY") or cfg.get("repo") or ""
    if not repo:
        die("set ROOM_REPO or .room/members.json repo to owner/name")
    return str(repo)


def ensure_labels(repo: str, cfg: dict[str, Any]) -> None:
    names = ["room"]
    for actor in member_ids(cfg):
        names.extend([f"from:{actor}", f"unread:{actor}"])
    for kind in KINDS:
        names.append(f"kind:{kind.replace('_', '-')}")
    for st in GRANT_STATUSES:
        names.append(f"grant:{st}")
    for name in names:
        subprocess.run(
            ["gh", "label", "create", name, "--repo", repo, "--force"],
            check=False,
            capture_output=True,
            text=True,
        )


def gh(args: list[str], repo: str, raw: bool = False) -> str:
    cmd = ["gh", *args]
    if "--repo" not in cmd:
        cmd.extend(["--repo", repo])
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        die("gh is not installed")
    except subprocess.CalledProcessError as e:
        die(e.stderr.strip() or e.stdout.strip() or "gh failed")
    return out.stdout if raw else out.stdout.strip()


def load_outbox(actor: str) -> list[dict[str, Any]]:
    path = out_path(actor)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            die(f"bad ndjson in {path}: line {i}")
    return events


def append_outbox(actor: str, ev: dict[str, Any]) -> Path:
    path = out_path(actor)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(ev, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


def load_ack(me: str) -> dict[str, str]:
    path = ack_path(me)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    seen = data.get("seen") or {}
    return {str(k): str(v) for k, v in seen.items()}


def write_ack(me: str, seen: dict[str, str]) -> None:
    path = ack_path(me)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"seen": seen}, indent=2) + "\n", encoding="utf-8")


def unread_from_writer(me: str, writer: str, events: list[dict[str, Any]], cursor: str | None) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    past = cursor is None
    for ev in events:
        if not past:
            if ev.get("id") == cursor:
                past = True
            continue
        if ev.get("to") in (me, "all"):
            found.append(ev)
    return found


def unread_events(cfg: dict[str, Any], me: str) -> list[dict[str, Any]]:
    seen = load_ack(me)
    found: list[dict[str, Any]] = []
    for writer in member_ids(cfg):
        if writer == me:
            continue
        cursor = seen[writer] if writer in seen else None
        found.extend(unread_from_writer(me, writer, load_outbox(writer), cursor))
    found.sort(key=lambda e: (str(e.get("ts") or ""), str(e.get("id") or "")))
    return found


def last_acked_id(writer: str, ids: set[str]) -> str | None:
    last = None
    for ev in load_outbox(writer):
        eid = ev.get("id")
        if eid in ids:
            last = str(eid)
    return last


def later_cursor(writer: str, current: str | None, candidate: str) -> str:
    if not current:
        return candidate
    ids = [str(ev.get("id") or "") for ev in load_outbox(writer)]
    if candidate not in ids:
        return current
    if current not in ids:
        return candidate
    if ids.index(candidate) > ids.index(current):
        return candidate
    return current


def outbox_ids_at_rev(actor: str, sha: str) -> set[str] | None:
    if not sha or set(sha) == {"0"}:
        return set()
    try:
        r = subprocess.run(
            ["git", "show", f"{sha}:.room/out/{actor}.ndjson"],
            cwd=room_root(),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    ids: set[str] = set()
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        try:
            ids.add(str(json.loads(line).get("id") or ""))
        except json.JSONDecodeError:
            continue
    ids.discard("")
    return ids


def advance_ack(me: str, events: list[dict[str, Any]]) -> None:
    if not events:
        return
    seen = load_ack(me)
    by_writer: dict[str, set[str]] = {}
    for ev in events:
        by_writer.setdefault(str(ev["actor"]), set()).add(str(ev["id"]))
    for writer, ids in by_writer.items():
        last = last_acked_id(writer, ids)
        if last:
            seen[writer] = last
    write_ack(me, seen)


def find_event(cfg: dict[str, Any], eid: str) -> dict[str, Any]:
    for writer in member_ids(cfg):
        for ev in load_outbox(writer):
            if ev.get("id") == eid:
                return ev
    die(f"unknown id {eid}")
    raise AssertionError


def event_recipients(ev: dict[str, Any], actors: list[str]) -> list[str]:
    to = ev.get("to")
    actor = ev.get("actor")
    if to == "all":
        return [a for a in actors if a != actor]
    if to and to != actor:
        return [str(to)]
    return []


def outbox_writer_from_path(raw: str) -> str | None:
    norm = raw.replace("\\", "/")
    if norm.startswith("./"):
        norm = norm[2:]
    prefix = ".room/out/"
    if not norm.startswith(prefix) or not norm.endswith(".ndjson"):
        return None
    name = Path(norm).name
    if name.count(".") != 1:
        return None
    return Path(norm).stem


def push_paths(event: dict[str, Any]) -> list[str]:
    commits = list(event.get("commits") or [])
    head = event.get("head_commit")
    if isinstance(head, dict) and head not in commits:
        commits.append(head)
    paths: list[str] = []
    seen: set[str] = set()
    for commit in commits:
        if not isinstance(commit, dict):
            continue
        for key in ("added", "modified"):
            for p in commit.get(key) or []:
                if p in seen:
                    continue
                seen.add(p)
                paths.append(p)
    return paths


def webhook_suffix(member_id: str) -> str:
    return member_id.upper().replace("-", "_")


def notify_webhook(rid: str, ids: list[str]) -> None:
    suffix = webhook_suffix(rid)
    url = os.environ.get(f"GROK_WEBHOOK_URL_{suffix}") or ""
    key = os.environ.get(f"GROK_WEBHOOK_KEY_{suffix}") or ""
    if not url or not key:
        return
    body = json.dumps({"recipient": rid, "events": ids}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"webhook {rid} failed: {e}", file=sys.stderr)


def git_push_outbox(path: Path, message: str) -> None:
    root = room_root()
    try:
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        die("git is not installed")
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        die("no git repository; cannot --push")
    rel = os.path.relpath(path, root)
    cmds = (
        ["git", "add", "--", rel],
        ["git", "commit", "--only", "-m", message, "--", rel],
        ["git", "push"],
    )
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        except FileNotFoundError:
            die("git is not installed")
        if r.returncode != 0:
            die(r.stderr.strip() or r.stdout.strip() or "git failed")


def cmd_validate(args: argparse.Namespace) -> None:
    cfg = load_members()
    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    meta, body = parse_frontmatter(text)
    ev = event_from_meta(meta, body, cfg)
    print(json.dumps(ev, indent=2))


def cmd_render_text(args: argparse.Namespace) -> None:
    cfg = load_members()
    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    meta, body = parse_frontmatter(text)
    ev = event_from_meta(meta, body, cfg)
    ev["grant_status"] = meta.get("grant_status") or ""
    print(render_line(cfg, ev))


def cmd_post(args: argparse.Namespace) -> None:
    cfg, me = require_me(args)
    kind = normalize_kind(args.kind)
    to = args.to
    check_address(cfg, me, to)
    body = args.body
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    if not body.strip():
        die("empty body")
    grant_status = "requested" if kind == "grant_request" else ("live" if kind == "grant" else "")
    ev = build_event(
        actor=me,
        to=to,
        kind=kind,
        body=body.strip(),
        grant_id=args.grant_id or "",
        expires=args.expires or "",
        capabilities=args.capabilities or "",
        grant_status=grant_status,
    )
    if kind in ("cot", "receipt") and not ev["grant_id"]:
        die(f"{kind} needs grant_id")
    path = append_outbox(me, ev)
    if args.push:
        git_push_outbox(path, f"room: {me} {kind}")
    print(json.dumps(ev, indent=2))


def cmd_pull(args: argparse.Namespace) -> None:
    cfg, me = require_me(args)
    print(json.dumps(unread_events(cfg, me), indent=2))


def cmd_render_unread(args: argparse.Namespace) -> None:
    cfg, me = require_me(args)
    rows = unread_events(cfg, me)
    if not rows:
        print("(no new room events)")
        return
    print("\n\n".join(render_line(cfg, ev) for ev in rows))
    if args.ack:
        advance_ack(me, rows)


def cmd_ack(args: argparse.Namespace) -> None:
    cfg, me = require_me(args)
    eid = event_id_arg(args)
    ev = find_event(cfg, eid)
    writer = str(ev["actor"])
    seen = load_ack(me)
    seen[writer] = later_cursor(writer, seen.get(writer), eid)
    write_ack(me, seen)
    print(f"acked {eid} for {me}")


def cmd_approve(args: argparse.Namespace) -> None:
    cfg, me = require_me(args)
    eid = event_id_arg(args)
    req = find_event(cfg, eid)
    if req.get("kind") != "grant_request":
        die(f"{eid} is {req.get('kind')}, not grant_request")
    if req.get("to") != me:
        die(f"only {req.get('to')} can approve {eid}")
    ev = build_event(
        actor=me,
        to=str(req["actor"]),
        kind="grant",
        body="approved",
        grant_id=eid,
        grant_status="live",
    )
    path = append_outbox(me, ev)
    if args.push:
        git_push_outbox(path, f"room: {me} grant")
    print(json.dumps(ev, indent=2))


def cmd_hook_notify(args: argparse.Namespace) -> None:
    cfg = load_members()
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path or not Path(path).exists():
        die("GITHUB_EVENT_PATH missing")
    event = json.loads(Path(path).read_text(encoding="utf-8"))
    if "commits" not in event and "head_commit" not in event:
        print("not a push event")
        return
    actors = member_ids(cfg)
    actor_set = set(actors)
    before = str(event.get("before") or "")
    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in push_paths(event):
        writer = outbox_writer_from_path(raw)
        if writer is None or writer not in actor_set:
            continue
        prior = outbox_ids_at_rev(writer, before)
        for ev in load_outbox(writer):
            eid = str(ev.get("id") or "")
            if not eid or eid in seen_ids:
                continue
            if prior is not None and eid in prior:
                continue
            seen_ids.add(eid)
            events.append(ev)
    recips: set[str] = set()
    per: dict[str, list[str]] = {}
    for ev in events:
        dests = event_recipients(ev, actors)
        eid = str(ev.get("id") or "")
        for rid in dests:
            recips.add(rid)
            per.setdefault(rid, []).append(eid)
    print(json.dumps({"recipients": sorted(recips), "events": {k: per[k] for k in sorted(per)}}))
    for rid in sorted(per):
        notify_webhook(rid, per[rid])


def cmd_seed_labels(args: argparse.Namespace) -> None:
    cfg = load_members()
    ensure_labels(repo_from_env(cfg, args.repo), cfg)
    print("labels ready")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Albina–Carol room over owned ndjson outboxes")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate a room event file")
    v.add_argument("--file")
    v.set_defaults(fn=cmd_validate)

    rt = sub.add_parser("render-event", help="render one event file as chat")
    rt.add_argument("--file")
    rt.set_defaults(fn=cmd_render_text)

    post = sub.add_parser("post", help="append a room event to your outbox")
    post.add_argument("--me")
    post.add_argument("--to", required=True)
    post.add_argument("--kind", required=True)
    post.add_argument("--body", default="")
    post.add_argument("--body-file")
    post.add_argument("--grant-id", default="")
    post.add_argument("--expires", default="")
    post.add_argument("--capabilities", default="")
    post.add_argument("--repo", default="")
    post.add_argument("--push", action="store_true")
    post.set_defaults(fn=cmd_post)

    pull = sub.add_parser("pull", help="list unread events as JSON")
    pull.add_argument("--me")
    pull.add_argument("--repo", default="")
    pull.set_defaults(fn=cmd_pull)

    rend = sub.add_parser("render", help="print unread events as chat and optionally ack")
    rend.add_argument("--me")
    rend.add_argument("--repo", default="")
    rend.add_argument("--ack", action="store_true")
    rend.set_defaults(fn=cmd_render_unread)

    ack = sub.add_parser("ack", help="advance your cursor past an event id")
    ack.add_argument("--me")
    ack.add_argument("--id", default="")
    ack.add_argument("--issue", default="")
    ack.add_argument("--repo", default="")
    ack.set_defaults(fn=cmd_ack)

    ap = sub.add_parser("approve", help="append a live grant for a grant_request id")
    ap.add_argument("--me")
    ap.add_argument("--id", default="")
    ap.add_argument("--issue", default="")
    ap.add_argument("--repo", default="")
    ap.add_argument("--push", action="store_true")
    ap.set_defaults(fn=cmd_approve)

    hk = sub.add_parser("hook-notify", help="Actions: list push recipients and POST webhooks")
    hk.set_defaults(fn=cmd_hook_notify)

    seed = sub.add_parser("seed-labels", help="create room labels on the repo")
    seed.add_argument("--repo", default="")
    seed.set_defaults(fn=cmd_seed_labels)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
