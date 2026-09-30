"""HTTP POST wake and key resolution. No cabinet policy beyond the key rule."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from .types import Member, MemberId, WakeMessage, WakeType

KEY_ENV_PREFIX = "TINCAN_WAKE_KEY_"
POST_TIMEOUT_SEC = 15


def key_env_name(member: MemberId) -> str:
    return f"{KEY_ENV_PREFIX}{member.upper().replace('-', '_')}"


def resolve_key(member: MemberId, file_key: str, public: bool) -> str:
    """TINCAN_WAKE_KEY_<ID> wins. Else file_key when not public. Empty if missing."""
    from_env = os.environ.get(key_env_name(member), "").strip()
    if from_env:
        return from_env
    if public:
        return ""
    return file_key.strip()


def post_http(url: str, key: str, note: WakeMessage) -> None:
    """POST {recipient, events: [writer:seq, ...]} with Authorization Bearer."""
    body = json.dumps(
        {
            "recipient": note.recipient,
            "events": [str(ref) for ref in note.events],
        }
    ).encode("utf-8")
    try:
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=POST_TIMEOUT_SEC) as answer:
            answer.read()
    except (OSError, ValueError, TimeoutError) as failure:
        if isinstance(failure, urllib.error.HTTPError):
            failure.close()  # an error status arrives as an open response
        print(f"wake {note.recipient} failed: {failure}", file=sys.stderr)


def notify_member(member: Member, note: WakeMessage, public: bool) -> None:
    """none returns. http resolves the key and POSTs. Missing url or key returns."""
    if member.wake.type is not WakeType.HTTP:
        return
    url = member.wake.url.strip()
    key = resolve_key(member.id, member.wake.key, public)
    if not url or not key:
        return
    post_http(url, key, note)
