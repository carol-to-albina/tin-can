#!/usr/bin/env python3
"""GitHub issue log for a two-person Grok Bot room."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MEMBERS_PATH = ROOT / ".room" / "members.json"

KINDS = ("speech", "grant_request", "grant", "cot", "receipt")
GRANT_STATUSES = ("requested", "live", "denied", "expired", "revoked")
KIND_ALIASES = {
    "grant-request": "grant_request",
    "grant_request": "grant_request",
}

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)


def die(msg: str, code: int = 2) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def load_members() -> dict[str, Any]:
    return json.loads(MEMBERS_PATH.read_text())


def member_ids(cfg: dict[str, Any]) -> list[str]:
    return list(cfg["members"])


def display_name(cfg: dict[str, Any], actor: str) -> str:
    row = cfg["members"].get(actor) or {}
    return str(row.get("display") or actor)


def github_login(cfg: dict[str, Any], actor: str) -> str:
    row = cfg["members"].get(actor) or {}
    return str(row.get("github") or "").strip()


def normalize_kind(kind: str) -> str:
    k = KIND_ALIASES.get(kind, kind)
    if k not in KINDS:
        die(f"unknown kind {kind!r}. want one of {', '.join(KINDS)}")
    return k


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


def render_frontmatter(meta: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key in ("actor", "kind", "to", "grant_id", "expires", "capabilities"):
        if key not in meta:
            continue
        val = meta[key]
        if val is None or val == "":
            lines.append(f"{key}:")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    lines.append("")
    lines.append(body.rstrip())
    lines.append("")
    return "\n".join(lines)


def labels_for(actor: str, kind: str, to: str, grant_status: str | None) -> list[str]:
    labels = ["room", f"from:{actor}", f"kind:{kind.replace('_', '-')}", f"unread:{to}"]
    if kind in ("grant_request", "grant") and grant_status:
        labels.append(f"grant:{grant_status}")
    return labels


def event_from_meta(meta: dict[str, str], body: str, cfg: dict[str, Any]) -> dict[str, Any]:
    actors = member_ids(cfg)
    actor = meta.get("actor", "")
    kind = normalize_kind(meta.get("kind", ""))
    to = meta.get("to", "")
    if actor not in actors:
        die(f"actor {actor!r} is not in .room/members.json")
    if to not in actors:
        die(f"to {to!r} is not in .room/members.json")
    if actor == to:
        die("actor and to must differ")
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


def title_for(ev: dict[str, Any]) -> str:
    return f"[{ev['kind']}] {ev['actor']} → {ev['to']}"


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
    return repo


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
    env = os.environ.copy()
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
    except FileNotFoundError:
        die("gh is not installed")
    except subprocess.CalledProcessError as e:
        die(e.stderr.strip() or e.stdout.strip() or "gh failed")
    return out.stdout if raw else out.stdout.strip()


def cmd_validate(args: argparse.Namespace) -> None:
    cfg = load_members()
    text = Path(args.file).read_text() if args.file else sys.stdin.read()
    meta, body = parse_frontmatter(text)
    ev = event_from_meta(meta, body, cfg)
    print(json.dumps(ev, indent=2))


def cmd_render_text(args: argparse.Namespace) -> None:
    cfg = load_members()
    text = Path(args.file).read_text() if args.file else sys.stdin.read()
    meta, body = parse_frontmatter(text)
    ev = event_from_meta(meta, body, cfg)
    ev["grant_status"] = meta.get("grant_status") or ""
    print(render_line(cfg, ev))


def cmd_post(args: argparse.Namespace) -> None:
    cfg = load_members()
    me = args.me or os.environ.get("ROOM_ME") or ""
    if not me:
        die("pass --me or set ROOM_ME")
    kind = normalize_kind(args.kind)
    to = args.to
    if to not in member_ids(cfg):
        die(f"unknown to {to!r}")
    if me == to:
        die("cannot post to yourself")
    body = args.body
    if args.body_file:
        body = Path(args.body_file).read_text()
    if not body.strip():
        die("empty body")
    grant_status = "requested" if kind == "grant_request" else ("live" if kind == "grant" else "")
    ev = event_from_meta(
        {
            "actor": me,
            "kind": kind,
            "to": to,
            "grant_id": args.grant_id or "",
            "expires": args.expires or "",
            "capabilities": args.capabilities or "",
        },
        body.strip(),
        cfg,
    )
    ev["grant_status"] = grant_status
    repo = repo_from_env(cfg, args.repo)
    ensure_labels(repo, cfg)
    issue_body = render_frontmatter(
        {
            "actor": ev["actor"],
            "kind": ev["kind"],
            "to": ev["to"],
            "grant_id": ev["grant_id"],
            "expires": ev["expires"],
            "capabilities": ev["capabilities"],
        },
        ev["body"],
    )
    label_args: list[str] = []
    for lab in labels_for(me, kind, to, grant_status or None):
        label_args.extend(["--label", lab])
    assignee = github_login(cfg, to)
    extra: list[str] = []
    if assignee:
        extra.extend(["--assignee", assignee])
    out = gh(
        [
            "issue",
            "create",
            "--title",
            title_for(ev),
            "--body",
            issue_body,
            *label_args,
            *extra,
        ],
        repo,
    )
    print(out)


def cmd_pull(args: argparse.Namespace) -> None:
    cfg = load_members()
    me = args.me or os.environ.get("ROOM_ME") or ""
    if not me:
        die("pass --me or set ROOM_ME")
    repo = repo_from_env(cfg, args.repo)
    raw = gh(
        [
            "issue",
            "list",
            "--label",
            f"unread:{me}",
            "--label",
            "room",
            "--state",
            "open",
            "--json",
            "number,title,body,labels,createdAt,author",
        ],
        repo,
        raw=True,
    )
    issues = json.loads(raw or "[]")
    events = []
    for issue in issues:
        try:
            meta, body = parse_frontmatter(issue.get("body") or "")
            ev = event_from_meta(meta, body, cfg)
        except SystemExit:
            continue
        ev["number"] = issue["number"]
        ev["created_at"] = issue.get("createdAt")
        ev["grant_status"] = next(
            (lab["name"].split(":", 1)[1] for lab in issue.get("labels", []) if lab["name"].startswith("grant:")),
            "",
        )
        events.append(ev)
    events.sort(key=lambda e: e.get("created_at") or "")
    print(json.dumps(events, indent=2))


def cmd_render_unread(args: argparse.Namespace) -> None:
    cfg = load_members()
    me = args.me or os.environ.get("ROOM_ME") or ""
    if not me:
        die("pass --me or set ROOM_ME")
    repo = repo_from_env(cfg, args.repo)
    raw = gh(
        [
            "issue",
            "list",
            "--label",
            f"unread:{me}",
            "--label",
            "room",
            "--state",
            "open",
            "--json",
            "number,body,labels,createdAt",
        ],
        repo,
        raw=True,
    )
    issues = json.loads(raw or "[]")
    lines: list[str] = []
    numbers: list[int] = []
    rows: list[dict[str, Any]] = []
    for issue in issues:
        try:
            meta, body = parse_frontmatter(issue.get("body") or "")
            ev = event_from_meta(meta, body, cfg)
        except SystemExit:
            continue
        ev["grant_status"] = next(
            (lab["name"].split(":", 1)[1] for lab in issue.get("labels", []) if lab["name"].startswith("grant:")),
            "",
        )
        ev["created_at"] = issue.get("createdAt")
        ev["number"] = issue["number"]
        rows.append(ev)
    rows.sort(key=lambda e: e.get("created_at") or "")
    for ev in rows:
        lines.append(render_line(cfg, ev))
        numbers.append(int(ev["number"]))
    if not lines:
        print("(no new room events)")
        return
    print("\n\n".join(lines))
    if args.ack:
        for n in numbers:
            ack_issue(repo, me, n)


def ack_issue(repo: str, me: str, number: int) -> None:
    gh(["issue", "edit", str(number), "--remove-label", f"unread:{me}"], repo)


def cmd_ack(args: argparse.Namespace) -> None:
    cfg = load_members()
    me = args.me or os.environ.get("ROOM_ME") or ""
    if not me:
        die("pass --me or set ROOM_ME")
    repo = repo_from_env(cfg, args.repo)
    ack_issue(repo, me, int(args.issue))
    print(f"acked #{args.issue} for {me}")


def cmd_approve(args: argparse.Namespace) -> None:
    cfg = load_members()
    me = args.me or os.environ.get("ROOM_ME") or ""
    if not me:
        die("pass --me or set ROOM_ME")
    repo = repo_from_env(cfg, args.repo)
    raw = gh(["issue", "view", str(args.issue), "--json", "body,labels"], repo, raw=True)
    issue = json.loads(raw)
    meta, body = parse_frontmatter(issue.get("body") or "")
    ev = event_from_meta(meta, body, cfg)
    if ev["kind"] != "grant_request":
        die(f"#{args.issue} is {ev['kind']}, not grant_request")
    if ev["to"] != me:
        die(f"only {ev['to']} can approve #{args.issue}")
    gh(
        [
            "issue",
            "edit",
            str(args.issue),
            "--add-label",
            "grant:live",
            "--remove-label",
            "grant:requested",
            "--remove-label",
            f"unread:{me}",
        ],
        repo,
    )
    print(f"grant #{args.issue} is live")


def cmd_hook_notify(args: argparse.Namespace) -> None:
    cfg = load_members()
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path or not Path(path).exists():
        die("GITHUB_EVENT_PATH missing")
    event = json.loads(Path(path).read_text())
    issue = event.get("issue") or event.get("pull_request")
    if not issue:
        print("no issue in event")
        return
    body = issue.get("body") or ""
    if not body.startswith("---"):
        print("not a room event")
        return
    meta, text = parse_frontmatter(body)
    ev = event_from_meta(meta, text, cfg)
    login = github_login(cfg, ev["to"])
    repo = repo_from_env(cfg, "")
    if not login:
        print(f"no github login for {ev['to']}, skip assign")
        return
    number = issue["number"]
    if event.get("pull_request"):
        gh(["pr", "edit", str(number), "--add-assignee", login], repo)
    else:
        gh(["issue", "edit", str(number), "--add-assignee", login], repo)
    print(f"assigned {login} on #{number}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Albina–Carol room over GitHub issues")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate a room event file")
    v.add_argument("--file")
    v.set_defaults(fn=cmd_validate)

    rt = sub.add_parser("render-event", help="render one event file as chat")
    rt.add_argument("--file")
    rt.set_defaults(fn=cmd_render_text)

    post = sub.add_parser("post", help="create a room issue")
    post.add_argument("--me")
    post.add_argument("--to", required=True)
    post.add_argument("--kind", required=True)
    post.add_argument("--body", default="")
    post.add_argument("--body-file")
    post.add_argument("--grant-id", default="")
    post.add_argument("--expires", default="")
    post.add_argument("--capabilities", default="")
    post.add_argument("--repo", default="")
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

    ack = sub.add_parser("ack", help="drop unread label after embedding")
    ack.add_argument("--me")
    ack.add_argument("--issue", required=True)
    ack.add_argument("--repo", default="")
    ack.set_defaults(fn=cmd_ack)

    ap = sub.add_parser("approve", help="flip a grant_request to live")
    ap.add_argument("--me")
    ap.add_argument("--issue", required=True)
    ap.add_argument("--repo", default="")
    ap.set_defaults(fn=cmd_approve)

    hk = sub.add_parser("hook-notify", help="Actions: assign the recipient")
    hk.set_defaults(fn=cmd_hook_notify)

    seed = sub.add_parser("seed-labels", help="create room labels on the repo")
    seed.add_argument("--repo", default="")
    seed.set_defaults(fn=cmd_seed_labels)
    return p


def cmd_seed_labels(args: argparse.Namespace) -> None:
    cfg = load_members()
    ensure_labels(repo_from_env(cfg, args.repo), cfg)
    print("labels ready")


def main() -> None:
    args = build_parser().parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
