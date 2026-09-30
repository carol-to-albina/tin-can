"""Public operations. Callers import Room. Seq, reducers, git, and wake stay here."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import git, wake
from .files import (
    append_outbox,
    cabinet_dir,
    find_cabinet,
    load_all_events,
    load_members,
    load_outbox,
    load_position,
    load_room,
    local_me_path,
    next_seq,
    out_path,
    parse_ts,
    pos_path,
    room_path,
    who_path,
    write_position,
    build_event,
)
from .reduce import (
    advance,
    build_inbox,
    drop_unauth,
    grant_is_live,
    reduce_grants,
    reduce_tasks,
    tasks_for,
)
from .types import (
    DEFAULT_AUTONOMY,
    DEFAULT_LATENCY_SEC,
    DEFAULT_MODE,
    PROTOCOL,
    AuthError,
    Autonomy,
    CotDraft,
    DoctorItem,
    Draft,
    Event,
    EventRef,
    Grant,
    GrantClosed,
    GrantRequestDraft,
    Inbox,
    Kind,
    MemberId,
    Mode,
    Position,
    ProtocolError,
    PublicKeyForbidden,
    ReceiptDraft,
    Seq,
    SpeechDraft,
    Task,
    TaskDraft,
    TaskState,
    WakeMessage,
    WakeType,
)


def github_login() -> str:
    """The login from `gh`, or empty when the command is missing or signed out."""
    try:
        run = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if run.returncode != 0:
        return ""
    return run.stdout.strip()


def _rev(root: Path, name: str) -> str:
    run = git._run(root, "rev-parse", "--verify", "--quiet", name)
    return run.stdout.strip() if run.returncode == 0 else ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _after(stamp: str) -> str:
    """One second after stamp, so a ref line sorts after the line it names."""
    return (parse_ts(stamp) + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _branch_name(root: Path) -> str:
    run = git._run(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    name = run.stdout.strip() if run.returncode == 0 else ""
    return name or "master"


def _ensure_layout(root: Path) -> None:
    cabinet = cabinet_dir(root)
    cabinet.mkdir(parents=True, exist_ok=True)
    for name in ("who", "out", "pos", "local"):
        (cabinet / name).mkdir(exist_ok=True)
    ignore = cabinet / ".gitignore"
    if not ignore.exists():
        ignore.write_text("local/\n", encoding="utf-8")


def _read_me(root: Path) -> str:
    path = local_me_path(root)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _enum_value(cls, raw: str, label: str):
    if not raw:
        return None
    try:
        return cls(raw)
    except ValueError as exc:
        raise ProtocolError(f"unknown {label} {raw!r}") from exc


class Room:
    def __init__(self, root: Path, me: MemberId) -> None:
        self.root = Path(root)
        self.me = MemberId(str(me))

    @staticmethod
    def open(start: str | Path | None = None) -> Room:
        """Find .tincan/room.json. Bind me from TINCAN_ME then .tincan/local/me."""
        root = find_cabinet(Path(start) if start else Path.cwd())
        me = os.environ.get("TINCAN_ME", "").strip() or _read_me(root)
        if not me:
            raise ProtocolError("set TINCAN_ME or .tincan/local/me")
        if MemberId(me) not in load_room(root).roster:
            raise ProtocolError(f"{me} is not in the roster")
        return Room(root, MemberId(me))

    def sync(self, only: tuple[EventRef, ...] | None = None) -> Inbox:
        """Pull ff-only, fold every outbox, return unread mail.

        Does not rewrite pos.
        """
        git.pull(self.root)
        return self._inbox(only)

    def ack(self, inbox: Inbox) -> Position:
        """Rewrite pos/<me> past every event in inbox. Does not push."""
        pos = advance(load_position(self.root, self.me), inbox)
        write_position(self.root, pos)
        return pos

    def post(self, draft: Draft) -> Event:
        """Assign next seq, check address and grant, append. Does not push."""
        members = self._members()
        if isinstance(draft, SpeechDraft):
            self._check_to(draft.to, members, allow_all=True)
            return self._append(Kind.SPEECH, draft.to, draft.body)
        if isinstance(draft, TaskDraft):
            self._check_to(draft.to, members, allow_all=True)
            return self._append(Kind.TASK, draft.to, draft.body)
        if isinstance(draft, GrantRequestDraft):
            self._check_to(draft.to, members, allow_all=False)
            return self._append(
                Kind.GRANT_REQUEST,
                draft.to,
                draft.body,
                capabilities=draft.capabilities,
                expires=draft.expires,
            )
        if isinstance(draft, (CotDraft, ReceiptDraft)):
            self._require_live(draft.ref)
            kind = Kind.COT if isinstance(draft, CotDraft) else Kind.RECEIPT
            return self._append(kind, draft.to, draft.body, ref=draft.ref)
        raise ProtocolError(f"unsupported draft {type(draft).__name__}")

    def claim(self, ref: EventRef) -> Event | None:
        """Append claim if this member may take it, publish, then return.

        None if another claim already wins. Own prior claim returns that event.
        Work starts only after this returns an Event.
        """
        members = self._members()
        if members[self.me].autonomy is Autonomy.OBSERVE:
            raise ProtocolError("observe cannot claim")
        task = self._task(ref)
        if task.to != "all" and task.to != self.me:
            raise ProtocolError(f"task {ref} is for {task.to}")
        if task.state in (TaskState.DONE, TaskState.FAILED, TaskState.IGNORED):
            return None
        if task.claimant is not None and task.claimant != self.me:
            return None
        if task.claimant != self.me:
            self._append(Kind.CLAIM, "", "", ref=ref)
        self.publish()
        events = self._events()
        folded = reduce_tasks(events, load_members(self.root)).get(ref)
        if (
            folded is None
            or folded.claimant != self.me
            or folded.claim is None
            or folded.state is not TaskState.CLAIMED
        ):
            return None
        return self._by_ref(events, folded.claim)

    def done(self, ref: EventRef, body: str) -> Event:
        """Append done. Only the winning claimant. Second done returns the first."""
        return self._finish(ref, Kind.DONE, body)

    def fail(self, ref: EventRef, body: str) -> Event:
        """Append fail. Only the winning claimant."""
        return self._finish(ref, Kind.FAIL, body)

    def approve(self, ref: EventRef) -> Event:
        """Append grant. Only the grant_request's to."""
        return self._decide(ref, Kind.GRANT, "")

    def deny(self, ref: EventRef, body: str) -> Event:
        """Append deny. Only the grant_request's to."""
        return self._decide(ref, Kind.DENY, body)

    def revoke(self, ref: EventRef) -> Event:
        """Append revoke. Only the grant_request's to."""
        return self._decide(ref, Kind.REVOKE, "")

    def tasks(self) -> tuple[Task, ...]:
        """Derived task rows addressed to me or all."""
        return tuple(tasks_for(self.me, reduce_tasks(self._events(), self._members())))

    def grants(self) -> tuple[Grant, ...]:
        """Derived grant rows this member requested or may decide."""
        rows = [
            grant
            for grant in reduce_grants(self._events(), _now()).values()
            if grant.requester == self.me or grant.granter == self.me
        ]
        rows.sort(key=lambda grant: (str(grant.requester), int(grant.ref.seq)))
        return tuple(rows)

    def publish(self) -> None:
        """Pull ff-only, commit dirty owned paths as room.json's login, push, notify.

        Dirty owned bytes after a crash become the same commit. No new bytes is a no-op.
        This is the retry after a failed --push. post is never re-run.
        """
        cfg = load_room(self.root)
        git.require_branch(self.root, cfg.branch)
        git.pull(self.root)
        before = _rev(self.root, "@{upstream}") or ("0" * 40)
        member = self._members()[self.me]
        git.commit_owned(
            self.root,
            [
                out_path(self.root, self.me),
                pos_path(self.root, self.me),
                who_path(self.root, self.me),
            ],
            f"tincan {self.me}",
            git.GitAuthor(member.github, f"{member.github}@users.noreply.github.com"),
        )
        head = _rev(self.root, "HEAD")
        upstream = _rev(self.root, "@{upstream}")
        if upstream and head == upstream:
            return
        git.push(self.root)
        self.notify_from_push(before)

    def notify_from_push(self, before_rev: str) -> tuple[WakeMessage, ...]:
        """Actions path. Diff outboxes since before_rev, POST one wake per recipient."""
        members = load_members(self.root)
        public = git.remote_is_public(self.root)
        buckets: dict[MemberId, list[EventRef]] = {}
        for member_id in members:
            path = out_path(self.root, member_id)
            if not path.exists():
                continue
            fresh = set(git.added_since(self.root, path, before_rev))
            if not fresh:
                continue
            for event in load_outbox(self.root, member_id):
                if int(event.meta.seq) not in fresh:
                    continue
                if event.meta.to == "all":
                    targets = [item for item in members if item != event.meta.writer]
                else:
                    targets = [MemberId(str(event.meta.to))]
                for target in targets:
                    if target not in members:
                        continue
                    buckets.setdefault(target, []).append(event.meta.ref())
        notes: list[WakeMessage] = []
        for recipient, refs in buckets.items():
            note = WakeMessage(recipient, tuple(refs))
            notes.append(note)
            wake.notify_member(members[recipient], note, public)
        return tuple(notes)

    def doctor(self) -> tuple[DoctorItem, ...]:
        """git, token, branch, protocol, author vs room.json github, public-key rule, gapless logs."""
        items: list[DoctorItem] = []
        try:
            git.require_repo(self.root)
        except ProtocolError as exc:
            return (DoctorItem("git", False, str(exc)),)
        items.append(DoctorItem("git", True, "work tree"))
        try:
            cfg = load_room(self.root)
        except ProtocolError as exc:
            items.append(DoctorItem("protocol", False, str(exc)))
            return tuple(items)
        items.append(DoctorItem("protocol", cfg.protocol == PROTOCOL, str(cfg.protocol)))
        try:
            git.require_branch(self.root, cfg.branch)
            items.append(DoctorItem("branch", True, cfg.branch))
        except ProtocolError as exc:
            items.append(DoctorItem("branch", False, str(exc)))
        members = load_members(self.root)
        if self.me in members:
            items.append(DoctorItem("identity", True, str(self.me)))
        else:
            items.append(DoctorItem("identity", False, f"{self.me} is not in the roster"))
        for member_id in members:
            try:
                load_outbox(self.root, member_id)
                items.append(DoctorItem(f"outbox {member_id}", True, "gapless"))
            except ProtocolError as exc:
                items.append(DoctorItem(f"outbox {member_id}", False, str(exc)))
        try:
            events = load_all_events(self.root, members)
        except ProtocolError as exc:
            items.append(DoctorItem("log", False, str(exc)))
        else:
            try:
                self._reject_forged(members, events)
                items.append(DoctorItem("author", True, "lines match room.json github"))
            except AuthError as exc:
                items.append(DoctorItem("author", False, str(exc)))
        url = ""
        try:
            url = git.remote_url(self.root)
        except ProtocolError as exc:
            items.append(DoctorItem("push", False, str(exc)))
        else:
            items.append(DoctorItem("push", bool(url), url or "no git remote"))
        public = git.remote_is_public(self.root) if url else False
        leaked = [str(member.id) for member in members.values() if member.wake.key.strip()]
        if public and leaked:
            items.append(DoctorItem("public-key", False, "committed wake key for " + ", ".join(leaked)))
        else:
            detail = "no committed wake key" if public else "remote is not a confirmed public GitHub repo"
            items.append(DoctorItem("public-key", True, detail))
        if url and "github.com" in url:
            login = github_login()
            items.append(
                DoctorItem("token", bool(login), login or "gh is not signed in")
            )
        else:
            items.append(DoctorItem("token", True, "remote is not GitHub"))
        if self.me in members:
            kind = members[self.me].wake.type.value
            items.append(DoctorItem("wake", True, kind))
        return tuple(items)

    def _members(self):
        members = load_members(self.root)
        if self.me not in members:
            raise ProtocolError(f"{self.me} is not in the roster")
        return members

    def _events(self) -> list[Event]:
        members = self._members()
        events = load_all_events(self.root, members)
        self._reject_forged(members, events)
        return events

    def _inbox(self, only: tuple[EventRef, ...] | None) -> Inbox:
        return build_inbox(
            self._members(),
            self._events(),
            self.me,
            load_position(self.root, self.me),
            _now(),
            only,
        )

    def _author_pair(self, path: Path, seq: Seq) -> tuple[str, str]:
        try:
            found = git.author_of_line(self.root, path, seq)
        except ProtocolError:
            return "", ""
        return found.name, found.email

    def _reject_forged(self, members, events: list[Event]) -> None:
        grouped: dict[MemberId, list[Event]] = {}
        for event in events:
            grouped.setdefault(event.meta.writer, []).append(event)
        for writer, rows in grouped.items():
            member = members.get(writer)
            if member is None:
                continue
            dropped = drop_unauth(self.root, writer, rows, member.github, self._author_pair)
            if dropped:
                raise AuthError(dropped[0].reason)

    def _check_to(self, to, members, allow_all: bool) -> None:
        if str(to) == "all":
            if not allow_all:
                raise ProtocolError("to all is not allowed on this kind")
            return
        if MemberId(str(to)) not in members:
            raise ProtocolError(f"to {to} is not in the roster")

    def _append(
        self,
        kind: Kind,
        to,
        body: str,
        *,
        ref: EventRef | None = None,
        capabilities: tuple[str, ...] = (),
        expires: str = "",
    ) -> Event:
        seq = next_seq(load_outbox(self.root, self.me))
        event = build_event(
            writer=self.me,
            seq=seq,
            to=to,
            kind=kind,
            body=body,
            ref=ref,
            capabilities=capabilities,
            expires=expires,
        )
        if ref is not None:
            prior = self._line_ts(ref)
            if prior and event.meta.ts <= prior:
                event = build_event(
                    writer=self.me,
                    seq=seq,
                    to=to,
                    kind=kind,
                    body=body,
                    ref=ref,
                    capabilities=capabilities,
                    expires=expires,
                    ts=_after(prior),
                )
        append_outbox(self.root, event)
        return event

    def _line_ts(self, ref: EventRef) -> str:
        try:
            rows = load_outbox(self.root, ref.writer)
        except ProtocolError:
            return ""
        for event in rows:
            if int(event.meta.seq) == int(ref.seq):
                return event.meta.ts
        return ""

    def _task(self, ref: EventRef) -> Task:
        task = reduce_tasks(self._events(), self._members()).get(ref)
        if task is None:
            raise ProtocolError(f"no task {ref}")
        return task

    def _by_ref(self, events: list[Event], ref: EventRef) -> Event:
        for event in events:
            if event.meta.ref() == ref:
                return event
        raise ProtocolError(f"missing event {ref}")

    def _require_live(self, ref: EventRef) -> None:
        grant = reduce_grants(self._events(), _now()).get(ref)
        if grant is None or not grant_is_live(grant):
            raise GrantClosed(f"grant {ref} is not live")

    def _finish(self, ref: EventRef, kind: Kind, body: str) -> Event:
        task = self._task(ref)
        events = self._events()
        if task.state in (TaskState.DONE, TaskState.FAILED):
            same = (task.state is TaskState.DONE and kind is Kind.DONE) or (
                task.state is TaskState.FAILED and kind is Kind.FAIL
            )
            if same and task.result is not None:
                return self._by_ref(events, task.result)
            raise ProtocolError(f"task {ref} is {task.state.value}")
        if task.state is not TaskState.CLAIMED or task.claimant != self.me:
            raise ProtocolError("only the winning claimant can finish this task")
        return self._append(kind, "", body, ref=ref)

    def _decide(self, ref: EventRef, kind: Kind, body: str) -> Event:
        events = self._events()
        grant = reduce_grants(events, _now()).get(ref)
        if grant is None:
            raise ProtocolError(f"no grant_request {ref}")
        if grant.granter != self.me:
            raise ProtocolError("only the grant_request's to can decide")
        if grant.decision is not None:
            prior = self._by_ref(events, grant.decision)
            if prior.kind is kind and prior.meta.writer == self.me:
                return prior
        return self._append(kind, "", body, ref=ref)


def init(
    room: str,
    repo: str,
    host: MemberId,
    github: str,
    display: str,
    *,
    root: Path | None = None,
) -> None:
    """Write room.json. Host only."""
    root = Path(root) if root else Path.cwd()
    if room_path(root).exists():
        raise ProtocolError(f"{room_path(root)} already exists")
    if not room or not repo or not str(host) or not github:
        raise ProtocolError("init needs room, repo, host, and github")
    _ensure_layout(root)
    _dump(
        room_path(root),
        {
            "protocol": PROTOCOL,
            "room": room,
            "repo": repo,
            "branch": _branch_name(root),
            "host": str(host),
            "members": {
                str(host): {"github": github, "display": display or str(host)},
            },
        },
    )


def join(
    me: MemberId,
    *,
    root: Path | None = None,
    display: str = "",
    mode: str = "",
    autonomy: str = "",
    latency_sec: int | None = None,
    wake_type: str = "none",
    wake_url: str = "",
    wake_key: str = "",
) -> None:
    """Write who/<me>.json and .tincan/local/me.

    Die if me is not in the roster. Die if wake_key is set and the remote is public.
    """
    base = find_cabinet(Path(root) if root else Path.cwd())
    member = MemberId(str(me))
    cfg = load_room(base)
    if member not in cfg.roster:
        raise ProtocolError(f"{member} is not in the roster")
    if wake_key and git.remote_is_public(base):
        raise PublicKeyForbidden("refusing to commit a wake key on a public remote")
    chosen_mode = _enum_value(Mode, mode, "mode") or DEFAULT_MODE
    chosen_auto = _enum_value(Autonomy, autonomy, "autonomy") or DEFAULT_AUTONOMY
    chosen_wake = _enum_value(WakeType, wake_type or "none", "wake.type") or WakeType.NONE
    if latency_sec is None:
        latency = DEFAULT_LATENCY_SEC
    elif isinstance(latency_sec, bool) or not isinstance(latency_sec, int) or latency_sec < 1:
        raise ProtocolError(f"latency_sec {latency_sec!r} is not a positive integer")
    else:
        latency = latency_sec
    path = who_path(base, member)
    if not path.exists():
        _dump(
            path,
            {
                "display": display or cfg.roster[member][1],
                "mode": chosen_mode.value,
                "autonomy": chosen_auto.value,
                "latency_sec": latency,
                "wake": {
                    "type": chosen_wake.value,
                    "url": wake_url,
                    "key": wake_key,
                },
            },
        )
    me_path = local_me_path(base)
    me_path.parent.mkdir(parents=True, exist_ok=True)
    me_path.write_text(str(member) + "\n", encoding="utf-8")


def hook_set(url: str, key: str, *, root: Path | None = None) -> None:
    """Write wake http url and key into who/<me>.json.

    Die if the remote is public and key is non-empty.
    """
    if not url:
        raise ProtocolError("hook-set needs a url")
    base = find_cabinet(Path(root) if root else Path.cwd())
    if key and git.remote_is_public(base):
        raise PublicKeyForbidden("refusing to commit a wake key on a public remote")
    me = os.environ.get("TINCAN_ME", "").strip() or _read_me(base)
    if not me:
        raise ProtocolError("set TINCAN_ME or .tincan/local/me")
    member = MemberId(me)
    if member not in load_room(base).roster:
        raise ProtocolError(f"{member} is not in the roster")
    path = who_path(base, member)
    data = {}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ProtocolError(f"{path} is not a json object")
    data["wake"] = {"type": "http", "url": url, "key": key}
    _dump(path, data)
