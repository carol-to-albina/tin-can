"""HTTP POST wake and key resolution. No cabinet policy beyond the key rule."""

from __future__ import annotations

from .types import Member, MemberId, WakeMessage


def resolve_key(member: MemberId, file_key: str, public: bool) -> str:
    """TINCAN_WAKE_KEY_<ID> wins. Else file_key when not public. Empty if missing."""
    raise NotImplementedError


def post_http(url: str, key: str, note: WakeMessage) -> None:
    """POST {recipient, events: [writer:seq, ...]} with Authorization Bearer."""
    raise NotImplementedError


def notify_member(member: Member, note: WakeMessage, public: bool) -> None:
    """none returns. http resolves the key and POSTs. Missing url or key returns."""
    raise NotImplementedError
