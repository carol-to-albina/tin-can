"""Domain types. Wire JSON is not imported from here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, NewType, Union

MemberId = NewType("MemberId", str)
Seq = NewType("Seq", int)


class Kind(Enum):
    SPEECH = "speech"
    TASK = "task"
    CLAIM = "claim"
    DONE = "done"
    FAIL = "fail"
    GRANT_REQUEST = "grant_request"
    GRANT = "grant"
    DENY = "deny"
    REVOKE = "revoke"
    COT = "cot"
    RECEIPT = "receipt"


class Mode(Enum):
    WEBHOOK = "webhook"
    DAEMON = "daemon"
    HUMAN = "human"


class Autonomy(Enum):
    AUTO = "auto"
    ASK = "ask"
    OBSERVE = "observe"


class WakeType(Enum):
    HTTP = "http"
    NONE = "none"


class GrantState(Enum):
    REQUESTED = "requested"
    LIVE = "live"
    DENIED = "denied"
    EXPIRED = "expired"
    REVOKED = "revoked"


class TaskState(Enum):
    OPEN = "open"
    WAITING_HUMAN = "waiting_human"
    CLAIMED = "claimed"
    DONE = "done"
    FAILED = "failed"
    IGNORED = "ignored"


class TinCanError(Exception):
    pass


class ProtocolError(TinCanError):
    pass


class AuthError(TinCanError):
    pass


class ConflictError(TinCanError):
    pass


class PublicKeyForbidden(TinCanError):
    """join, hook-set, or doctor tried to commit a wake key on a public remote."""


class GrantClosed(TinCanError):
    """cot or receipt posted without a live grant."""


@dataclass(frozen=True)
class EventRef:
    writer: MemberId
    seq: Seq

    def __str__(self) -> str:
        return f"{self.writer}:{int(self.seq)}"

    @staticmethod
    def parse(raw: str) -> EventRef:
        writer, sep, digits = raw.partition(":")
        if not (sep and writer and digits.isascii() and digits.isdigit() and int(digits) > 0):
            raise ProtocolError(f"bad ref {raw!r}, want writer:seq")
        return EventRef(MemberId(writer), Seq(int(digits)))


@dataclass(frozen=True)
class EventMeta:
    writer: MemberId
    seq: Seq
    ts: str
    to: MemberId | Literal["all"]

    def ref(self) -> EventRef:
        return EventRef(self.writer, self.seq)


@dataclass(frozen=True)
class Speech:
    meta: EventMeta
    body: str
    kind: Literal[Kind.SPEECH] = Kind.SPEECH


@dataclass(frozen=True)
class TaskPosted:
    meta: EventMeta
    body: str
    kind: Literal[Kind.TASK] = Kind.TASK


@dataclass(frozen=True)
class Claim:
    meta: EventMeta
    ref: EventRef
    kind: Literal[Kind.CLAIM] = Kind.CLAIM


@dataclass(frozen=True)
class Done:
    meta: EventMeta
    ref: EventRef
    body: str
    kind: Literal[Kind.DONE] = Kind.DONE


@dataclass(frozen=True)
class Fail:
    meta: EventMeta
    ref: EventRef
    body: str
    kind: Literal[Kind.FAIL] = Kind.FAIL


@dataclass(frozen=True)
class GrantRequest:
    meta: EventMeta
    body: str
    capabilities: tuple[str, ...]
    expires: str
    kind: Literal[Kind.GRANT_REQUEST] = Kind.GRANT_REQUEST


@dataclass(frozen=True)
class GrantApproved:
    meta: EventMeta
    ref: EventRef
    kind: Literal[Kind.GRANT] = Kind.GRANT


@dataclass(frozen=True)
class Deny:
    meta: EventMeta
    ref: EventRef
    body: str
    kind: Literal[Kind.DENY] = Kind.DENY


@dataclass(frozen=True)
class Revoke:
    meta: EventMeta
    ref: EventRef
    kind: Literal[Kind.REVOKE] = Kind.REVOKE


@dataclass(frozen=True)
class Cot:
    meta: EventMeta
    ref: EventRef
    body: str
    kind: Literal[Kind.COT] = Kind.COT


@dataclass(frozen=True)
class Receipt:
    meta: EventMeta
    ref: EventRef
    body: str
    kind: Literal[Kind.RECEIPT] = Kind.RECEIPT


Event = Union[
    Speech,
    TaskPosted,
    Claim,
    Done,
    Fail,
    GrantRequest,
    GrantApproved,
    Deny,
    Revoke,
    Cot,
    Receipt,
]


@dataclass(frozen=True)
class SpeechDraft:
    to: MemberId | Literal["all"]
    body: str


@dataclass(frozen=True)
class TaskDraft:
    to: MemberId | Literal["all"]
    body: str


@dataclass(frozen=True)
class GrantRequestDraft:
    to: MemberId
    body: str
    capabilities: tuple[str, ...]
    expires: str = ""


@dataclass(frozen=True)
class CotDraft:
    to: MemberId
    ref: EventRef
    body: str


@dataclass(frozen=True)
class ReceiptDraft:
    to: MemberId
    ref: EventRef
    body: str


Draft = SpeechDraft | TaskDraft | GrantRequestDraft | CotDraft | ReceiptDraft


@dataclass(frozen=True)
class Wake:
    type: WakeType
    url: str
    key: str


@dataclass(frozen=True)
class WhoFile:
    display: str
    mode: Mode
    autonomy: Autonomy
    latency_sec: int
    wake: Wake


@dataclass(frozen=True)
class Member:
    id: MemberId
    github: str
    display: str
    mode: Mode
    autonomy: Autonomy
    latency_sec: int
    wake: Wake


@dataclass(frozen=True)
class RoomConfig:
    protocol: Literal[3]
    room: str
    repo: str
    branch: str
    host: MemberId
    roster: dict[MemberId, tuple[str, str]]


@dataclass(frozen=True)
class Position:
    me: MemberId
    seen: dict[MemberId, Seq]


@dataclass(frozen=True)
class Task:
    ref: EventRef
    writer: MemberId
    to: MemberId | Literal["all"]
    body: str
    state: TaskState
    claim: EventRef | None
    claimant: MemberId | None
    result: EventRef | None


@dataclass(frozen=True)
class Grant:
    ref: EventRef
    requester: MemberId
    granter: MemberId
    capabilities: tuple[str, ...]
    expires: str
    state: GrantState
    decision: EventRef | None


@dataclass(frozen=True)
class Inbox:
    speech: tuple[Speech, ...]
    tasks: tuple[Task, ...]
    actionable: tuple[Task, ...]
    waiting_human: tuple[Task, ...]
    cots: tuple[Cot, ...]
    grants: tuple[Grant, ...]


@dataclass(frozen=True)
class WakeMessage:
    recipient: MemberId
    events: tuple[EventRef, ...]


@dataclass(frozen=True)
class Dropped:
    path: Path
    seq: Seq
    reason: str


@dataclass(frozen=True)
class DoctorItem:
    name: str
    ok: bool
    detail: str


DEFAULT_MODE = Mode.HUMAN
DEFAULT_AUTONOMY = Autonomy.ASK
DEFAULT_WAKE = Wake(WakeType.NONE, "", "")
DEFAULT_LATENCY_SEC = 86400
PROTOCOL = 3
CAP_HIDDEN_COT = "share_hidden_cot"
