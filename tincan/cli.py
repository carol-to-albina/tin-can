"""Argv in, JSON or chat out. No cabinet rules beyond flag mapping."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path

from .adapters.chat import render_inbox, render_tasks
from .files import find_cabinet, load_members, load_room, local_me_path, migrate_v2
from .room import Room, hook_set, init, join
from .types import (
    CotDraft,
    EventRef,
    GrantRequestDraft,
    Kind,
    MemberId,
    ReceiptDraft,
    SpeechDraft,
    TaskDraft,
    TinCanError,
)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--me", default="")
    common.add_argument("--root", default="")
    common.add_argument("--repo", default="")
    parser = argparse.ArgumentParser(prog="tincan", description="TinCan room on a git branch")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sync = sub.add_parser("sync", parents=[common], help="pull and print unread mail")
    sync.add_argument("--ack", action="store_true")
    sync.add_argument("--push", action="store_true")
    sync.add_argument("--format", choices=("json", "chat"), default="json")
    sync.add_argument("--only", action="append", default=[])

    inbox = sub.add_parser("inbox", parents=[common], help="print unread mail without pulling")
    inbox.add_argument("--format", choices=("json", "chat"), default="json")
    inbox.add_argument("--only", action="append", default=[])

    ack = sub.add_parser("ack", parents=[common], help="advance pos past the current unread mail")
    ack.add_argument("--only", action="append", default=[])

    post = sub.add_parser("post", parents=[common], help="append one line")
    post.add_argument("--to", required=True)
    post.add_argument("--kind", required=True)
    post.add_argument("--body", default="")
    post.add_argument("--ref", default="")
    post.add_argument("--capabilities", default="")
    post.add_argument("--expires", default="")
    post.add_argument("--push", action="store_true")

    for name, help_text in (
        ("claim", "claim a task and publish"),
        ("approve", "grant a request"),
        ("revoke", "revoke a live grant"),
    ):
        cmd = sub.add_parser(name, parents=[common], help=help_text)
        cmd.add_argument("--ref", required=True)
        if name != "claim":
            cmd.add_argument("--push", action="store_true")

    for name, help_text in (
        ("done", "finish a claimed task"),
        ("fail", "fail a claimed task"),
        ("deny", "deny a grant request"),
    ):
        cmd = sub.add_parser(name, parents=[common], help=help_text)
        cmd.add_argument("--ref", required=True)
        cmd.add_argument("--body", required=True)
        cmd.add_argument("--push", action="store_true")

    tasks = sub.add_parser("tasks", parents=[common], help="derived task rows")
    tasks.add_argument("--format", choices=("json", "chat"), default="json")
    grants = sub.add_parser("grants", parents=[common], help="derived grant rows")
    grants.add_argument("--format", choices=("json", "chat"), default="json")

    sub.add_parser("publish", parents=[common], help="commit owned paths, push, notify")
    sub.add_parser("doctor", parents=[common], help="check the clone")

    created = sub.add_parser("init", parents=[common], help="write room.json")
    created.add_argument("--room", required=True)
    created.add_argument("--host", required=True)
    created.add_argument("--github", required=True)
    created.add_argument("--display", default="")

    entered = sub.add_parser("join", parents=[common], help="write who/<me>.json and local/me")
    entered.add_argument("--display", default="")
    entered.add_argument("--mode", default="")
    entered.add_argument("--autonomy", default="")
    entered.add_argument("--latency-sec", type=int, default=None)
    entered.add_argument("--wake-type", default="none")
    entered.add_argument("--wake-url", default="")
    entered.add_argument("--wake-key", default="")

    bell = sub.add_parser("hook-set", parents=[common], help="write the wake url and key")
    bell.add_argument("--url", required=True)
    bell.add_argument("--key", default="")

    note = sub.add_parser("notify", parents=[common], help="wake recipients of lines added since a rev")
    note.add_argument("--before", default="")

    moved = sub.add_parser("migrate", parents=[common], help="copy .room/ into .tincan/")
    moved.add_argument("--host", default="")
    return parser


def resolve_me(args: argparse.Namespace, room: Room) -> MemberId:
    """args.me, then TINCAN_ME, then .tincan/local/me."""
    chosen = (getattr(args, "me", "") or "").strip()
    if not chosen:
        chosen = os.environ.get("TINCAN_ME", "").strip()
    if not chosen:
        path = local_me_path(room.root)
        if path.is_file():
            chosen = path.read_text(encoding="utf-8").strip()
    if not chosen:
        raise TinCanError("set --me, TINCAN_ME, or .tincan/local/me")
    return MemberId(chosen)


def _root_of(args: argparse.Namespace) -> Path:
    return Path(args.root).resolve() if args.root else Path.cwd()


def bind(args: argparse.Namespace) -> Room:
    root = find_cabinet(_root_of(args))
    me = resolve_me(args, Room(root, MemberId("pending")))
    if me not in load_room(root).roster:
        raise TinCanError(f"{me} is not in the roster")
    return Room(root, me)


def _only(args: argparse.Namespace) -> tuple[EventRef, ...] | None:
    raw = getattr(args, "only", None) or []
    if not raw:
        return None
    return tuple(EventRef.parse(item) for item in raw)


def _address(raw: str):
    if raw == "all":
        return "all"
    return MemberId(raw)


def _caps(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def convert(value):
    if isinstance(value, EventRef):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: convert(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): convert(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [convert(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def emit(value, fmt: str, chat: str) -> None:
    if fmt == "chat":
        if chat:
            print(chat)
        return
    print(json.dumps(convert(value), ensure_ascii=False, indent=2))


def print_inbox(inbox, members, fmt: str) -> None:
    emit(inbox, fmt, render_inbox(members, inbox))


def _print_event(room: Room, event) -> None:
    emit(event, "json", "")


def _maybe_push(room: Room, args: argparse.Namespace) -> None:
    if getattr(args, "push", False):
        room.publish()


def cmd_init(args: argparse.Namespace) -> None:
    if not args.repo:
        raise TinCanError("init needs --repo")
    init(
        args.room,
        args.repo,
        MemberId(args.host),
        args.github,
        args.display,
        root=_root_of(args),
    )


def cmd_join(args: argparse.Namespace) -> None:
    if not args.me:
        raise TinCanError("join needs --me")
    join(
        MemberId(args.me),
        root=_root_of(args),
        display=args.display,
        mode=args.mode,
        autonomy=args.autonomy,
        latency_sec=args.latency_sec,
        wake_type=args.wake_type,
        wake_url=args.wake_url,
        wake_key=args.wake_key,
    )


def cmd_doctor(args: argparse.Namespace) -> int:
    items = bind(args).doctor()
    failed = False
    for item in items:
        mark = "ok" if item.ok else "FAIL"
        if not item.ok:
            failed = True
        print(f"{mark} {item.name} {item.detail}")
    return 1 if failed else 0


def cmd_sync(args: argparse.Namespace) -> None:
    """Room.sync, optional ack and publish, print JSON or chat."""
    room = bind(args)
    inbox = room.sync(_only(args))
    if args.ack:
        room.ack(inbox)
    _maybe_push(room, args)
    print_inbox(inbox, load_members(room.root), args.format)


def cmd_inbox(args: argparse.Namespace) -> None:
    room = bind(args)
    inbox = room._inbox(_only(args))
    print_inbox(inbox, load_members(room.root), args.format)


def cmd_ack(args: argparse.Namespace) -> None:
    room = bind(args)
    inbox = room._inbox(_only(args))
    _print_event(room, room.ack(inbox))


def cmd_post(args: argparse.Namespace) -> None:
    room = bind(args)
    kind = Kind(args.kind)
    to = _address(args.to)
    ref = EventRef.parse(args.ref) if args.ref else None
    if kind is Kind.SPEECH:
        draft = SpeechDraft(to, args.body)
    elif kind is Kind.TASK:
        draft = TaskDraft(to, args.body)
    elif kind is Kind.GRANT_REQUEST:
        draft = GrantRequestDraft(MemberId(str(to)), args.body, _caps(args.capabilities), args.expires)
    elif kind is Kind.COT:
        if ref is None:
            raise TinCanError("cot needs --ref")
        draft = CotDraft(MemberId(str(to)), ref, args.body)
    elif kind is Kind.RECEIPT:
        if ref is None:
            raise TinCanError("receipt needs --ref")
        draft = ReceiptDraft(MemberId(str(to)), ref, args.body)
    else:
        raise TinCanError(f"post does not write {args.kind}")
    event = room.post(draft)
    _maybe_push(room, args)
    _print_event(room, event)


def cmd_claim(args: argparse.Namespace) -> None:
    room = bind(args)
    event = room.claim(EventRef.parse(args.ref))
    print(json.dumps(convert(event), ensure_ascii=False, indent=2))


def cmd_done(args: argparse.Namespace) -> None:
    room = bind(args)
    event = room.done(EventRef.parse(args.ref), args.body)
    _maybe_push(room, args)
    _print_event(room, event)


def cmd_fail(args: argparse.Namespace) -> None:
    room = bind(args)
    event = room.fail(EventRef.parse(args.ref), args.body)
    _maybe_push(room, args)
    _print_event(room, event)


def cmd_approve(args: argparse.Namespace) -> None:
    room = bind(args)
    event = room.approve(EventRef.parse(args.ref))
    _maybe_push(room, args)
    _print_event(room, event)


def cmd_deny(args: argparse.Namespace) -> None:
    room = bind(args)
    event = room.deny(EventRef.parse(args.ref), args.body)
    _maybe_push(room, args)
    _print_event(room, event)


def cmd_revoke(args: argparse.Namespace) -> None:
    room = bind(args)
    event = room.revoke(EventRef.parse(args.ref))
    _maybe_push(room, args)
    _print_event(room, event)


def cmd_tasks(args: argparse.Namespace) -> None:
    room = bind(args)
    rows = list(room.tasks())
    chat = render_tasks(load_members(room.root), rows) if args.format == "chat" else ""
    emit(rows, args.format, chat)


def cmd_grants(args: argparse.Namespace) -> None:
    room = bind(args)
    rows = list(room.grants())
    emit(rows, args.format, "")


def cmd_publish(args: argparse.Namespace) -> None:
    bind(args).publish()


def cmd_notify(args: argparse.Namespace) -> None:
    before = (args.before or "").strip()
    if not before:
        raw = os.environ.get("GITHUB_EVENT_PATH", "")
        if raw:
            payload = json.loads(Path(raw).read_text(encoding="utf-8"))
            before = str(payload.get("before") or "")
    if not before:
        raise TinCanError("notify needs --before or GITHUB_EVENT_PATH")
    try:
        room = bind(args)
    except TinCanError:
        if (args.me or "").strip() or os.environ.get("TINCAN_ME", "").strip():
            raise
        root = find_cabinet(_root_of(args))
        room = Room(root, load_room(root).host)
    notes = room.notify_from_push(before)
    print(json.dumps(convert(notes), ensure_ascii=False, indent=2))


def cmd_hook_set(args: argparse.Namespace) -> None:
    previous = os.environ.get("TINCAN_ME")
    if args.me:
        os.environ["TINCAN_ME"] = args.me
    try:
        hook_set(args.url, args.key, root=_root_of(args))
    finally:
        if args.me:
            if previous is None:
                os.environ.pop("TINCAN_ME", None)
            else:
                os.environ["TINCAN_ME"] = previous


def cmd_migrate(args: argparse.Namespace) -> None:
    host = (args.host or args.me or os.environ.get("TINCAN_ME", "")).strip()
    if not host:
        raise TinCanError("migrate needs --host")
    root = _root_of(args)
    paths = migrate_v2(root, MemberId(host))
    for path in paths:
        print(path.relative_to(root))
    print("git rm -r .room")


COMMANDS = {
    "init": cmd_init,
    "join": cmd_join,
    "doctor": cmd_doctor,
    "sync": cmd_sync,
    "inbox": cmd_inbox,
    "ack": cmd_ack,
    "post": cmd_post,
    "claim": cmd_claim,
    "done": cmd_done,
    "fail": cmd_fail,
    "approve": cmd_approve,
    "deny": cmd_deny,
    "revoke": cmd_revoke,
    "tasks": cmd_tasks,
    "grants": cmd_grants,
    "publish": cmd_publish,
    "notify": cmd_notify,
    "hook-set": cmd_hook_set,
    "migrate": cmd_migrate,
}


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = COMMANDS[args.cmd](args)
        return int(result or 0)
    except TinCanError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
