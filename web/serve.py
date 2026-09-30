#!/usr/bin/env python3
"""Local web UI for a TinCan v3 room.

Reads and appends the `.tincan/` cabinet directly, as docs/v3/SPEC.md allows
for any peer. Stdlib only.

    python3 web/serve.py --demo                 # seeded scratch room
    python3 web/serve.py --root . --me carol    # your clone
    python3 web/serve.py --root . --push        # also publish each line
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/duet": ("duet.html", "text/html; charset=utf-8"),
    "/duet.html": ("duet.html", "text/html; charset=utf-8"),
    "/duet.js": ("duet.js", "text/javascript; charset=utf-8"),
    "/shortcuts.json": ("shortcuts.json", "application/json"),
}
# The public demo swaps the landing page in at / and moves the room log to /log.
DEMO_STATIC = {
    **STATIC,
    "/": ("landing.html", "text/html; charset=utf-8"),
    "/host": ("landing.html", "text/html; charset=utf-8"),
    "/landing.js": ("landing.js", "text/javascript; charset=utf-8"),
    "/chat": ("chat.html", "text/html; charset=utf-8"),
    "/chat.js": ("chat.js", "text/javascript; charset=utf-8"),
    "/log": ("index.html", "text/html; charset=utf-8"),
}
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
# Model-written HTML: its own opaque origin, no scripts, no network, framable only by us.
HANDOVER_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; frame-ancestors 'self'"
MAX_BODY = 16_000

KINDS = {"speech", "task", "claim", "done", "fail", "grant_request", "grant", "deny", "revoke", "cot", "receipt"}
REF_KINDS = {"claim", "done", "fail", "grant", "deny", "revoke", "cot", "receipt"}
BODY_KINDS = {"speech", "task", "done", "fail", "grant_request", "cot", "receipt"}


class UIError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Cabinet:
    """The `.tincan/` directory. One lock serialises this process's writes."""

    def __init__(self, root: Path):
        self.root = root
        self.dir = root / ".tincan"
        self.lock = threading.Lock()

    def room(self) -> dict:
        path = self.dir / "room.json"
        if not path.is_file():
            raise UIError(f"no {path}")
        room = json.loads(path.read_text(encoding="utf-8"))
        if room.get("protocol") != 3:
            raise UIError("room.json protocol is not 3")
        return room

    def roster(self) -> dict:
        return self.room().get("members", {})

    def outbox(self, writer: str) -> list[dict]:
        path = self.dir / "out" / f"{writer}.ndjson"
        if not path.is_file():
            return []
        rows = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                row = json.loads(raw)
                row["writer"] = writer
                rows.append(row)
        return rows

    def lines(self) -> tuple[list[dict], list[str]]:
        rows, errors = [], []
        for writer in self.roster():
            try:
                box = self.outbox(writer)
            except (OSError, ValueError) as exc:
                errors.append(f"out/{writer}.ndjson: {exc}")
                continue
            for index, row in enumerate(box, 1):
                if row.get("seq") != index:
                    errors.append(f"out/{writer}.ndjson: seq {row.get('seq')} at line {index}")
                    break
                if row.get("kind") not in KINDS:
                    errors.append(f"{writer}:{index}: unknown kind {row.get('kind')!r}")
                    continue
                rows.append(row)
        return rows, errors

    def positions(self) -> dict:
        out = {}
        for writer in self.roster():
            path = self.dir / "pos" / writer
            cursor = {}
            if path.is_file():
                for raw in path.read_text(encoding="utf-8").splitlines():
                    parts = raw.split()
                    if len(parts) == 2 and parts[1].isdigit():
                        cursor[parts[0]] = int(parts[1])
            out[writer] = cursor
        return out

    def policies(self) -> dict:
        out = {}
        for writer in self.roster():
            path = self.dir / "who" / f"{writer}.json"
            if path.is_file():
                try:
                    policy = json.loads(path.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                policy.pop("wake", None)  # never ship wake keys to the browser
                out[writer] = policy
        return out

    def append(self, me: str, draft: dict) -> dict:
        kind = draft.get("kind", "")
        if kind not in KINDS:
            raise UIError(f"unknown kind {kind!r}")
        body = (draft.get("body") or "").strip()
        if kind in BODY_KINDS and not body:
            raise UIError(f"{kind} needs a body")
        roster = self.roster()
        with self.lock:
            line: dict = {"ts": utc_now(), "kind": kind}
            if kind in REF_KINDS:
                ref = draft.get("ref", "")
                target = self._find(ref)
                self._check_ref(me, kind, target)
                line["to"] = target["writer"]
                line["ref"] = ref
            else:
                to = draft.get("to", "")
                if to != "all" and to not in roster:
                    raise UIError(f"{to!r} is not in the roster")
                line["to"] = to
            if body:
                line["body"] = body
            if kind == "grant_request":
                caps = draft.get("capabilities") or []
                if caps:
                    line["capabilities"] = list(caps)
                if draft.get("expires"):
                    line["expires"] = draft["expires"]
            path = self.dir / "out" / f"{me}.ndjson"
            path.parent.mkdir(parents=True, exist_ok=True)
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            line = {"seq": sum(1 for raw in text.splitlines() if raw.strip()) + 1, **line}
            prefix = "" if not text or text.endswith("\n") else "\n"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(prefix + json.dumps(line, separators=(",", ":"), ensure_ascii=False) + "\n")
        return line

    def _find(self, ref: str) -> dict:
        writer, _, seq = ref.partition(":")
        if not seq.isdigit():
            raise UIError(f"bad ref {ref!r}")
        box = self.outbox(writer)
        if not 1 <= int(seq) <= len(box):
            raise UIError(f"no line {ref}")
        return box[int(seq) - 1]

    def _check_ref(self, me: str, kind: str, target: dict) -> None:
        if kind in {"claim", "done", "fail"} and target["kind"] != "task":
            raise UIError(f"{kind} must point at a task")
        if kind in {"grant", "deny", "revoke", "cot", "receipt"} and target["kind"] != "grant_request":
            raise UIError(f"{kind} must point at a grant_request")
        if kind in {"grant", "deny", "revoke"} and target.get("to") != me:
            raise UIError("only the person asked can decide a grant")

    def ack(self, me: str, upto: dict) -> dict:
        with self.lock:
            cursor = self.positions().get(me, {})
            for writer, seq in upto.items():
                if writer in self.roster() and isinstance(seq, int) and seq > cursor.get(writer, 0):
                    cursor[writer] = seq
            path = self.dir / "pos" / me
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{me}.")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("".join(f"{w} {s}\n" for w, s in sorted(cursor.items())))
            os.replace(tmp, path)
        return cursor

    def publish(self, me: str) -> str:
        """SPEC Publish: pull --ff-only, commit owned paths as the roster login, push."""
        room = self.room()
        login = room["members"][me]["github"]
        branch = room.get("branch", "master")

        def git(*args: str) -> str:
            done = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True)
            if done.returncode:
                raise UIError(f"git {args[0]}: {done.stderr.strip() or done.stdout.strip()}")
            return done.stdout.strip()

        with self.lock:
            git("pull", "--ff-only", "-q", "origin", branch)
            owned = [f".tincan/out/{me}.ndjson", f".tincan/pos/{me}", f".tincan/who/{me}.json"]
            owned = [p for p in owned if (self.root / p).exists()]
            git("add", "--", *owned)
            if not git("status", "--porcelain", "--", *owned):
                return "clean"
            git(
                "-c", f"user.name={login}", "-c", f"user.email={login}@users.noreply.github.com",
                "commit", "-q", "-m", f"tincan: {me}", "--", *owned,
            )
            git("push", "-q", "origin", f"HEAD:{branch}")
        return "pushed"

    def pull(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "pull", "--ff-only", "-q"], capture_output=True)


def seed_demo(root: Path, history: bool = True, permission: bool = False) -> None:
    cab = root / ".tincan"
    for sub in ("out", "pos", "who", "local"):
        (cab / sub).mkdir(parents=True, exist_ok=True)
        if sub in ("out", "pos"):
            for old in (cab / sub).iterdir():
                old.unlink()
    (cab / "room.json").write_text(json.dumps({
        "protocol": 3,
        "room": "tincan",
        "repo": "carol-to-albina/tin-can",
        "branch": "master",
        "host": "carol",
        "members": {
            "carol": {"github": "rainbowpuffpuff", "display": "Carol"},
            "albina": {"github": "enjojoy", "display": "Albina"},
        },
    }, indent=2) + "\n", encoding="utf-8")
    # permission: both knots tied when they joined, so each Grok takes the other's tasks without asking.
    (cab / "who" / "carol.json").write_text(json.dumps({"mode": "webhook", "autonomy": "auto" if permission else "ask"}) + "\n")
    (cab / "who" / "albina.json").write_text(json.dumps({"mode": "webhook", "autonomy": "auto"}) + "\n")
    if not history:
        return

    start = datetime.now(timezone.utc) - timedelta(minutes=42)

    def at(minutes: int) -> str:
        return (start + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    expires = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    carol = [
        {"ts": at(0), "to": "albina", "kind": "speech", "body": "Grok found that tunnelling paper you asked about. Want me to send the notes over?"},
        {"ts": at(3), "to": "albina", "kind": "task", "body": "Research quantum tunnelling for the poster: three good sources and a one-paragraph brief. My notes are in notes/tunnelling.md."},
        {"ts": at(30), "to": "all", "kind": "speech", "body": "Poster review is Friday at 5. Bring whatever you have."},
    ]
    albina = [
        {"ts": at(1), "to": "carol", "kind": "speech", "body": "yes please! my Grok can read them to me on the train"},
        {"ts": at(4), "to": "carol", "kind": "claim", "ref": "carol:2"},
        {"ts": at(26), "to": "carol", "kind": "done", "ref": "carol:2", "body": "Brief and sources are up: https://github.com/carol-to-albina/tin-can/pull/12"},
        {"ts": at(38), "to": "carol", "kind": "grant_request", "capabilities": ["share_hidden_cot"], "expires": expires, "body": "Can I see how your Grok ranked the sources? Mine picked different ones."},
        {"ts": at(40), "to": "all", "kind": "speech", "body": "I'll bring the printouts"},
    ]
    for name, rows in (("carol", carol), ("albina", albina)):
        text = "".join(json.dumps({"seq": i, **r}, ensure_ascii=False) + "\n" for i, r in enumerate(rows, 1))
        (cab / "out" / f"{name}.ndjson").write_text(text, encoding="utf-8")
    (cab / "pos" / "carol").write_text("albina 2\n")
    (cab / "pos" / "albina").write_text("carol 2\n")


def find_root(start: Path) -> Path:
    for path in (start, *start.parents):
        if (path / ".tincan" / "room.json").is_file():
            return path
    raise SystemExit(f"no .tincan/room.json at or above {start}. Try --demo.")


def default_me(root: Path, cli_me: str) -> str:
    me = cli_me or os.environ.get("TINCAN_ME", "")
    local = root / ".tincan" / "local" / "me"
    if not me and local.is_file():
        me = local.read_text(encoding="utf-8").strip()
    return me


class Base(BaseHTTPRequestHandler):
    server_version = "TinCan"
    sys_version = ""

    def log_message(self, fmt, *args):  # quiet
        pass

    def _send(self, code: int, payload, ctype="application/json", headers: dict | None = None) -> None:
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in {**SECURITY_HEADERS, **(headers or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise UIError("request too large")
        if length and not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise UIError("send JSON")
        body = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(body, dict):
            raise UIError("bad json")
        return body


def make_handler(cab: Cabinet, me_default: str, push: bool):
    """Your own clone, on this computer."""

    class Handler(Base):
        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path in STATIC:
                name, ctype = STATIC[url.path]
                return self._send(200, (HERE / name).read_bytes(), ctype)
            if url.path == "/api/state":
                try:
                    lines, errors = cab.lines()
                    room = cab.room()
                    return self._send(200, {
                        "me": me_default, "demo": False, "push": push,
                        "room": {k: room.get(k) for k in ("room", "repo", "branch", "host", "members")},
                        "who": cab.policies(), "pos": cab.positions(), "lines": lines, "errors": errors, "now": utc_now(),
                    })
                except (UIError, OSError, ValueError) as exc:
                    return self._send(500, {"error": str(exc)})
            self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            url = urlparse(self.path)
            try:
                body = self._body()
                if url.path == "/api/post":
                    line = cab.append(me_default, body)
                    published = cab.publish(me_default) if push else "local"
                    return self._send(200, {"line": line, "published": published})
                if url.path == "/api/ack":
                    cursor = cab.ack(me_default, body.get("upto") or {})
                    if push:
                        threading.Thread(target=lambda: _quiet(cab.publish, me_default), daemon=True).start()
                    return self._send(200, {"pos": cursor})
                self._send(404, {"error": "not found"})
            except (UIError, OSError, ValueError, KeyError) as exc:
                self._send(400, {"error": str(exc)})

    return Handler


class Throttle:
    """At most `n` events per `window` seconds per key."""

    def __init__(self, n: int, window: float):
        self.n, self.window = n, window
        self.hits: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def ok(self, key: str) -> bool:
        now = time.time()
        with self.lock:
            recent = [t for t in self.hits.get(key, []) if now - t < self.window]
            if len(recent) >= self.n:
                self.hits[key] = recent
                return False
            self.hits[key] = recent + [now]
            return True


def make_demo_handler(live, duet, public_url: str, host_token: str = ""):
    """The public demo: landing, your Grok's chat, the room log, and the scripted duet."""
    import re
    import secrets

    say_limit = Throttle(8, 60)
    verify_limit = Throttle(30, 60)
    file_name = re.compile(r"^[a-z0-9-]{1,90}\.html$")
    host_ok = re.compile(r"^[A-Za-z0-9.-]{1,120}(:\d{1,5})?$")

    class Handler(Base):
        def _ip(self) -> str:
            return self.headers.get("CF-Connecting-IP") or self.client_address[0]

        def _token(self) -> str:
            # The seat rides in an HttpOnly cookie (page scripts cannot read it); the header is a fallback.
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "tc_seat" and v:
                    return v
            return self.headers.get("X-TinCan-Seat") or ""

        def _seat(self) -> str | None:
            token = self._token()
            if token and host_token and secrets.compare_digest(token, host_token):
                return live.host
            return live.seats.who(token)

        def _cookie(self, token: str, max_age: int = 604800) -> dict:
            secure = "; Secure" if self._origin().startswith("https") else ""
            return {"Set-Cookie": f"tc_seat={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict{secure}"}

        def _need_seat(self) -> str:
            me = self._seat()
            if not me or me not in live.cab.roster():
                raise PermissionError("join the room first")
            return me

        def _origin(self) -> str:
            if public_url:
                return public_url.rstrip("/")
            host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or ""
            if not host_ok.match(host):
                host = "localhost"
            proto = "https" if "https" in (self.headers.get("CF-Visitor") or "") or self.headers.get("X-Forwarded-Proto") == "https" else "http"
            return f"{proto}://{host}"

        def _file(self, folder: Path, name: str) -> None:
            path = folder / name
            if not file_name.match(name) or not path.is_file():
                return self._send(404, {"error": "no such handover"})
            self._send(200, path.read_bytes(), "text/html; charset=utf-8",
                       {"Content-Security-Policy": HANDOVER_CSP, "X-Frame-Options": "SAMEORIGIN"})

        def do_GET(self) -> None:
            url = urlparse(self.path)
            try:
                if url.path in DEMO_STATIC:
                    name, ctype = DEMO_STATIC[url.path]
                    return self._send(200, (HERE / name).read_bytes(), ctype)
                if url.path.startswith("/h/"):
                    return self._file(live.bots.files_dir, url.path[3:])
                if url.path.startswith("/d/"):
                    return self._file(duet.bots.files_dir, url.path[3:])
                if url.path == "/qr.svg":
                    return self._send(200, qr_svg(self._origin() + "/"), "image/svg+xml")
                if url.path == "/api/hello":
                    me = self._seat()
                    room = live.cab.roster()
                    return self._send(200, {"me": me if me in room else None, "url": self._origin() + "/",
                                            "host": live.host_name, "people": len(room), "asks": [a["label"] for a in live_asks()]})
                if url.path == "/api/live":
                    return self._send(200, live.state(self._need_seat()))
                if url.path == "/api/verify":
                    me = self._need_seat()
                    if not verify_limit.ok(me):
                        raise PermissionError("slow down a little")
                    gen = (parse_qs(url.query).get("id") or [""])[0]
                    return self._send(200, live.llm.verify(gen))
                if url.path == "/api/duet":
                    return self._send(200, duet.state())
                if url.path == "/api/state":  # the room log page, read only
                    lines, errors = live.cab.lines()
                    room = live.cab.room()
                    me = self._seat() or live.host
                    return self._send(200, {
                        "me": me if me in room["members"] else live.host, "demo": False, "push": False, "readonly": True,
                        "room": {k: room.get(k) for k in ("room", "repo", "branch", "host", "members")},
                        "who": live.cab.policies(), "pos": live.cab.positions(), "lines": lines, "errors": errors, "now": utc_now(),
                    })
                self._send(404, {"error": "not found"})
            except PermissionError as exc:
                self._send(403, {"error": str(exc)})
            except LookupError as exc:
                self._send(404, {"error": str(exc).strip("'\"")})
            except (UIError, OSError, ValueError) as exc:
                self._send(400, {"error": str(exc)})

        def do_POST(self) -> None:
            url = urlparse(self.path)
            try:
                body = self._body()
                if url.path == "/api/join":
                    token, me = live.join(str(body.get("name") or ""), self._ip())
                    return self._send(200, {"seat": token, "me": me}, headers=self._cookie(token))
                if url.path == "/api/host":
                    token = str(body.get("token") or "")
                    if not host_token or not secrets.compare_digest(token, host_token):
                        raise PermissionError("that is not the host link")
                    return self._send(200, {"me": live.host}, headers=self._cookie(token))
                if url.path == "/api/leave":
                    return self._send(200, {"ok": True}, headers=self._cookie("", 0))
                if url.path == "/api/duet/start":
                    return self._send(200, {"run": duet.start(), "script": duet.SCRIPT})
                if url.path == "/api/duet/say":
                    duet.say(str(body.get("run") or ""), str(body.get("me") or ""), str(body.get("text") or "").strip())
                    return self._send(202, {"ok": True})
                me = self._need_seat()
                is_host = me == live.host
                if url.path == "/api/say":
                    text = str(body.get("text") or "").strip()
                    if not text:
                        raise UIError("say something first")
                    if not is_host and not say_limit.ok(me):
                        raise PermissionError("that is a lot of messages; give the Groks a minute")
                    if not is_host and not live.ledger.can_spend(me):
                        raise PermissionError("you are out of credits")
                    if not is_host and open_tasks_by(live, me) >= 3:
                        raise PermissionError(f"{live.host_name}'s Grok is still on your last three; wait for one to come back")
                    live.bots.say(me, text[:600] if not is_host else text[:2000])
                    return self._send(202, {"ok": True})
                if url.path == "/api/accept":
                    live.bots.accept(me, str(body.get("ref") or ""))
                    return self._send(202, {"ok": True})
                if url.path == "/api/decline":
                    live.bots.decline(me, str(body.get("ref") or ""))
                    return self._send(200, {"ok": True})
                if url.path == "/api/autonomy":
                    live.set_autonomy(me, str(body.get("mode") or ""))
                    if body.get("mode") == "auto":
                        for ref in live.state(me)["pending"]:
                            live.bots.accept(me, ref)
                    return self._send(200, {"ok": True})
                if url.path == "/api/delegate":
                    if not is_host:
                        raise PermissionError(f"only {live.host_name} hands out jobs here")
                    to = str(body.get("to") or "")
                    if to not in live.cab.roster() or to == live.host:
                        raise UIError("pick someone in the room")
                    job = str(body.get("job") or "").strip()[:1200]
                    if not job:
                        raise UIError("what is the job?")
                    return self._send(200, live.bots.delegate(me, to, job))
                if url.path == "/api/reset":
                    if not is_host:
                        raise PermissionError(f"only {live.host_name} can reset the room")
                    live.reset()
                    return self._send(200, {"ok": True})
                self._send(404, {"error": "not found"})
            except PermissionError as exc:
                self._send(403, {"error": str(exc)})
            except (UIError, OSError, ValueError, KeyError) as exc:
                self._send(400, {"error": str(exc).strip("'\"")})

    return Handler


def live_asks():
    from demo import ASKS

    return ASKS


def open_tasks_by(live, me: str) -> int:
    lines, _ = live.cab.lines()
    finished = {l.get("ref") for l in lines if l["kind"] in ("done", "fail")}
    return sum(1 for l in lines if l["writer"] == me and l["kind"] == "task" and f"{me}:{l['seq']}" not in finished)


_qr_cache: dict[str, bytes] = {}


def qr_svg(text: str) -> bytes:
    if text not in _qr_cache:
        import io

        import qrcode
        import qrcode.image.svg

        img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathFillImage, box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf)
        _qr_cache[text] = buf.getvalue()
    return _qr_cache[text]


def _quiet(fn, *args) -> None:
    try:
        fn(*args)
    except UIError as exc:
        print(f"publish: {exc}", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description="TinCan room web UI")
    ap.add_argument("--root", default="", help="clone that holds .tincan/ (default: cwd upwards)")
    ap.add_argument("--me", default="", help="your roster id (else TINCAN_ME or .tincan/local/me)")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--push", action="store_true", help="publish every line (pull --ff-only, commit owned paths, push)")
    ap.add_argument("--pull-every", type=int, default=0, metavar="SEC", help="git pull --ff-only in the background")
    demo = ap.add_argument_group("public demo")
    demo.add_argument("--demo", action="store_true", help="the public demo: a live room anyone with the link can join")
    demo.add_argument("--data", default=str(Path.home() / ".local" / "share" / "tincan-demo"), help="where the demo keeps its rooms")
    demo.add_argument("--budget", type=float, default=3.00, help="total USD the demo may spend on the model")
    demo.add_argument("--credit", type=float, default=0.30, help="USD of model work each guest may ask for")
    demo.add_argument("--host-id", default="carol")
    demo.add_argument("--host-name", default="Carol")
    demo.add_argument("--github", default="rainbowpuffpuff")
    demo.add_argument("--public-url", default=os.environ.get("TINCAN_PUBLIC_URL", ""), help="the address guests use (for the QR code)")
    args = ap.parse_args()

    if args.demo:
        return run_demo(args)

    root = find_root(Path(args.root).resolve() if args.root else Path.cwd())
    cab = Cabinet(root)
    me = default_me(root, args.me)
    if me not in cab.roster():
        raise SystemExit(f"--me {me or '(unset)'} is not in {root}/.tincan/room.json")
    if args.pull_every:
        def loop() -> None:
            while True:
                time.sleep(args.pull_every)
                cab.pull()
        threading.Thread(target=loop, daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(cab, me, args.push))
    print(f"TinCan UI on http://{args.host}:{args.port}/  room={root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def run_demo(args) -> None:
    from bots import LLM, load_key
    from demo import Duet, Live

    key = load_key()
    if not key:
        raise SystemExit("no model key: set OPENROUTER_API_KEY or write ~/.config/tincan/openrouter.env")
    data = Path(args.data)
    data.mkdir(parents=True, exist_ok=True)
    llm = LLM(key, args.budget)
    live = Live(Cabinet, data, llm, args.host_id, args.host_name, args.github, args.credit)
    duet = Duet(Cabinet, data, llm, seed_demo)
    token = live.host_token(Path.home() / ".config" / "tincan" / "host-token")
    server = ThreadingHTTPServer((args.host, args.port), make_demo_handler(live, duet, args.public_url, token))
    local = f"http://{args.host}:{args.port}"
    print(f"TinCan demo on {local}/   data={data}")
    print(f"  your seat ({args.host_name}): {local}/host#{token}")
    print(f"  model {llm.model} effort={llm.effort}  budget ${args.budget:.2f}  guest credit ${args.credit:.2f}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
