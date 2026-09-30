"""Cabinet paths, parse, format, position, migrate. No git. No HTTP. The fold is reduce.py."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from .types import (
    BODY_REQUIRED,
    DEFAULT_AUTONOMY,
    DEFAULT_LATENCY_SEC,
    DEFAULT_MODE,
    DEFAULT_WAKE,
    KIND_CLASSES,
    PROTOCOL,
    REF_KINDS,
    Autonomy,
    Event,
    EventMeta,
    EventRef,
    Kind,
    Member,
    MemberId,
    Mode,
    Position,
    ProtocolError,
    RoomConfig,
    Seq,
    Wake,
    WakeType,
    WhoFile,
    kind_fields,
)

E = TypeVar("E", bound=Enum)


def cabinet_dir(root: Path) -> Path:
    return root / ".tincan"


def room_path(root: Path) -> Path:
    return cabinet_dir(root) / "room.json"


def who_path(root: Path, member: MemberId) -> Path:
    return cabinet_dir(root) / "who" / f"{member}.json"


def out_path(root: Path, member: MemberId) -> Path:
    return cabinet_dir(root) / "out" / f"{member}.ndjson"


def pos_path(root: Path, member: MemberId) -> Path:
    return cabinet_dir(root) / "pos" / str(member)


def local_me_path(root: Path) -> Path:
    return cabinet_dir(root) / "local" / "me"


def _object(raw: str, label: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"bad json in {label}: {e}") from e
    if not isinstance(data, dict):
        raise ProtocolError(f"{label} is not a json object")
    return data


def _enum(cls: type[E], raw: Any, default: E, label: str) -> E:
    if raw is None or raw == "":
        return default
    try:
        return cls(raw)
    except ValueError as e:
        raise ProtocolError(f"unknown {label} {raw!r}") from e


def parse_room(raw: str) -> RoomConfig:
    """Die unless protocol is 3 and every roster id has a github login."""
    data = _object(raw, "room.json")
    if data.get("protocol") != PROTOCOL:
        raise ProtocolError(
            f"room.json protocol is {data.get('protocol')!r}, want {PROTOCOL}"
        )
    rows = data.get("members")
    if not isinstance(rows, dict) or not rows:
        raise ProtocolError("room.json needs a members object")
    roster: dict[MemberId, tuple[str, str]] = {}
    for raw_id, row in rows.items():
        member = MemberId(str(raw_id))
        if not isinstance(row, dict):
            raise ProtocolError(f"room.json member {member} is not an object")
        github = str(row.get("github") or "")
        if not github:
            raise ProtocolError(f"room.json member {member} has no github login")
        roster[member] = (github, str(row.get("display") or member))
    host = MemberId(str(data.get("host") or ""))
    if host not in roster:
        raise ProtocolError(f"room.json host {str(host)!r} is not in the roster")
    return RoomConfig(
        protocol=PROTOCOL,
        room=str(data.get("room") or ""),
        repo=str(data.get("repo") or ""),
        branch=str(data.get("branch") or "master"),
        host=host,
        roster=roster,
    )


def load_room(root: Path) -> RoomConfig:
    path = room_path(root)
    if not path.exists():
        raise ProtocolError(f"missing {path}")
    return parse_room(path.read_text(encoding="utf-8"))


def parse_who(raw: str) -> WhoFile:
    """Missing fields become HUMAN, ASK, NONE, 86400."""
    data = _object(raw, "who file")
    wake = data.get("wake") or {}
    if not isinstance(wake, dict):
        raise ProtocolError("who wake is not an object")
    latency = data.get("latency_sec", DEFAULT_LATENCY_SEC)
    if isinstance(latency, bool) or not isinstance(latency, int) or latency < 1:
        raise ProtocolError(f"who latency_sec {latency!r} is not a positive integer")
    return WhoFile(
        display=str(data.get("display") or ""),
        mode=_enum(Mode, data.get("mode"), DEFAULT_MODE, "mode"),
        autonomy=_enum(Autonomy, data.get("autonomy"), DEFAULT_AUTONOMY, "autonomy"),
        latency_sec=latency,
        wake=Wake(
            type=_enum(WakeType, wake.get("type"), DEFAULT_WAKE.type, "wake.type"),
            url=str(wake.get("url") or ""),
            key=str(wake.get("key") or ""),
        ),
    )


def merge_member(
    member: MemberId,
    github: str,
    display: str,
    who: WhoFile | None,
) -> Member:
    """Missing who file uses HUMAN, ASK, NONE, 86400."""
    policy = who or WhoFile(
        "", DEFAULT_MODE, DEFAULT_AUTONOMY, DEFAULT_LATENCY_SEC, DEFAULT_WAKE
    )
    return Member(
        id=member,
        github=github,
        display=policy.display or display or str(member),
        mode=policy.mode,
        autonomy=policy.autonomy,
        latency_sec=policy.latency_sec,
        wake=policy.wake,
    )


def load_members(root: Path) -> dict[MemberId, Member]:
    members: dict[MemberId, Member] = {}
    for member, (github, display) in load_room(root).roster.items():
        path = who_path(root, member)
        who = parse_who(path.read_text(encoding="utf-8")) if path.exists() else None
        members[member] = merge_member(member, github, display, who)
    return members


def parse_ref(raw: str) -> EventRef:
    return EventRef.parse(raw)


def parse_ts(raw: str) -> datetime:
    """UTC ISO-8601 with a trailing Z."""
    if raw.endswith("Z"):
        try:
            return datetime.fromisoformat(raw[:-1] + "+00:00")
        except ValueError:
            pass
    raise ProtocolError(f"ts {raw!r} is not UTC ISO-8601 with a Z")


def parse_line(writer: MemberId, seq: Seq, raw: str) -> Event:
    """Filename is the actor. Line seq must equal seq.

    Unknown kind or missing ref on a ref-kind is ProtocolError. A cot or
    receipt whose ref misses a grant_request needs the whole cabinet, so
    load_all_events owns that check.
    """
    where = f"{writer} line {int(seq)}"
    data = _object(raw, where)
    if data.get("seq") != int(seq):
        raise ProtocolError(f"{where}: seq is {data.get('seq')!r}")
    try:
        kind = Kind(data.get("kind"))
    except ValueError as e:
        raise ProtocolError(f"{where}: unknown kind {data.get('kind')!r}") from e
    ts = str(data.get("ts") or "")
    if not ts:
        raise ProtocolError(f"{where}: no ts")
    caps = data.get("capabilities") or []
    if not isinstance(caps, list):
        raise ProtocolError(f"{where}: capabilities is not a json array")
    ref = str(data.get("ref") or "")
    try:
        return build_event(
            writer=writer,
            seq=seq,
            to=str(data.get("to") or ""),
            kind=kind,
            body=str(data.get("body") or ""),
            ref=parse_ref(ref) if ref else None,
            capabilities=tuple(str(cap) for cap in caps),
            expires=str(data.get("expires") or ""),
            ts=ts,
        )
    except ProtocolError as e:
        raise ProtocolError(f"{where}: {e}") from e


def format_line(event: Event) -> str:
    """One JSON object. No id, no actor, no grant_status."""
    row: dict[str, Any] = {
        "seq": int(event.meta.seq),
        "ts": event.meta.ts,
        "to": str(event.meta.to),
        "kind": event.kind.value,
    }
    for key, value in (
        ("body", getattr(event, "body", "")),
        ("ref", str(getattr(event, "ref", "") or "")),
        ("capabilities", list(getattr(event, "capabilities", ()))),
        ("expires", getattr(event, "expires", "")),
    ):
        if value:
            row[key] = value
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"))


def _nonblank(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_outbox(root: Path, writer: MemberId) -> list[Event]:
    """Empty file is ok. Blank lines are ignored and do not consume seq.

    Gap, duplicate, or seq mismatch is ProtocolError.
    """
    events: list[Event] = []
    for line in _nonblank(out_path(root, writer)):
        events.append(parse_line(writer, next_seq(events), line))
    return events


def next_seq(events: list[Event]) -> Seq:
    return Seq(len(events) + 1)


def append_outbox(root: Path, event: Event) -> Path:
    """Append one line. If the last line is byte-identical, do nothing.

    If the last line has the same seq and different bytes, ProtocolError.
    """
    path = out_path(root, event.meta.writer)
    line = format_line(event)
    held = _nonblank(path)
    if held and held[-1] == line:
        return path
    seq = int(event.meta.seq)
    if seq <= len(held):
        raise ProtocolError(f"{path} already holds seq {seq} with different bytes")
    if seq > len(held) + 1:
        raise ProtocolError(f"{path} next seq is {len(held) + 1}, not {seq}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return path


def load_position(root: Path, me: MemberId) -> Position:
    """Missing file is seen={}."""
    path = pos_path(root, me)
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    return parse_position(me, raw)


def write_position(root: Path, pos: Position) -> Path:
    """Write to a temp file in the same dir, then rename onto pos/<me>."""
    path = pos_path(root, pos.me)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(format_position(pos))
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return path


def parse_position(me: MemberId, raw: str) -> Position:
    seen: dict[MemberId, Seq] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        columns = line.split(" ")
        if len(columns) != 2 or not columns[0] or not columns[1].isascii() or not columns[1].isdigit():
            raise ProtocolError(f"pos/{me} line {line!r} is not writer then seq")
        writer = MemberId(columns[0])
        if writer in seen:
            raise ProtocolError(f"pos/{me} names {columns[0]} twice")
        seen[writer] = Seq(int(columns[1]))
    return Position(me, seen)


def format_position(pos: Position) -> str:
    """Two columns, writer then seq."""
    rows = sorted((str(writer), int(seq)) for writer, seq in pos.seen.items())
    return "".join(f"{writer} {seq}\n" for writer, seq in rows)


def load_all_events(root: Path, members: dict[MemberId, Member]) -> list[Event]:
    """Every member's outbox, concatenated in roster order. Not sorted."""
    raise NotImplementedError


def build_event(
    *,
    writer: MemberId,
    seq: Seq,
    to: MemberId | str,
    kind: Kind,
    body: str,
    ref: EventRef | None = None,
    capabilities: tuple[str, ...] = (),
    expires: str = "",
    ts: str | None = None,
) -> Event:
    """Refuse illegal kind/ref pairs.

    A ref-kind addresses the referenced writer. Pass to as "" to take it
    from the ref, or pass that same writer.
    """
    if int(seq) < 1:
        raise ProtocolError(f"seq {int(seq)} is not 1-based")
    stamp = ts or utc_now()
    parse_ts(stamp)
    if kind in REF_KINDS:
        if ref is None:
            raise ProtocolError(f"{kind.value} needs a ref")
        if to and str(to) != str(ref.writer):
            raise ProtocolError(
                f"{kind.value} to {str(to)!r} is not the referenced writer {str(ref.writer)!r}"
            )
        to = ref.writer
    elif ref is not None:
        raise ProtocolError(f"{kind.value} takes no ref")
    if not to:
        raise ProtocolError(f"{kind.value} needs a to")
    text = body.strip()
    carries = kind_fields(kind)
    if kind in BODY_REQUIRED and not text:
        raise ProtocolError(f"{kind.value} needs a body")
    if text and "body" not in carries:
        raise ProtocolError(f"{kind.value} takes no body")
    if capabilities and "capabilities" not in carries:
        raise ProtocolError(f"{kind.value} takes no capabilities")
    if expires and "expires" not in carries:
        raise ProtocolError(f"{kind.value} takes no expires")
    if expires:
        parse_ts(expires)
    row: dict[str, Any] = {
        "meta": EventMeta(writer=writer, seq=Seq(int(seq)), ts=stamp, to=to)
    }
    if "ref" in carries:
        row["ref"] = ref
    if "body" in carries:
        row["body"] = text
    if "capabilities" in carries:
        row["capabilities"] = tuple(capabilities)
        row["expires"] = expires
    return KIND_CLASSES[kind](**row)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_cabinet(start: Path) -> Path:
    """Walk parents for .tincan/room.json."""
    here = Path(start).resolve()
    for candidate in (here, *here.parents):
        if room_path(candidate).exists():
            return candidate
    raise ProtocolError(f"no .tincan/room.json at or above {here}")


def migrate_v2(root: Path, host: MemberId) -> list[Path]:
    """Host-only, one wave. Read .room/, write .tincan/.

    Stamp seq. Drop id, actor, grant_status. Map grant_id through an
    in-memory id map. Init pos to each writer's last seq. Fold hook
    url and key into who. Leave .room/ until the caller deletes it.
    Refuse when .tincan/ already exists.
    Returns the sorted paths that must be committed together.
    """
    raise NotImplementedError
