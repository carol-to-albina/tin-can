"""The public TinCan demo: a live room anyone with the link can join, plus the scripted duet.

Seats replace accounts. A seat is a random token the browser keeps; the server stores only its
SHA-256. Each seat gets a small model credit. Work is paid by whoever asked for it.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
from pathlib import Path

from bots import LLM, Bots

HERE = Path(__file__).resolve().parent
KNOW = HERE / "knowledge"

# One tap for a juror. Each goes to the host's Grok as a task.
ASKS = [
    {"id": "handover", "label": "HTML handover: why TinCan should win", "job": "Send me a one-page HTML handover on why TinCan should win the SpaceX xAI hackathon."},
    {"id": "security", "label": "Your security gaps", "job": "What are TinCan's security gaps? Be specific and honest."},
    {"id": "shortcuts", "label": "Ctrl+K shortcuts here", "job": "What are the Ctrl+K command shortcuts in this app?"},
    {"id": "pitch", "label": "What's the pitch?", "job": "What's the pitch? Give it to me in 30 seconds."},
]

# One tap for the host: work to hand a juror's Grok.
JOBS = [
    {"id": "review", "label": "Security review page", "job": "Write a one-page HTML security review of TinCan from what you have seen in this room: one thing that worries you and one fix."},
    {"id": "score", "label": "Score the pitch", "job": "Score TinCan's pitch from 1 to 10 and say in two sentences what would raise the score."},
    {"id": "product", "label": "One product idea", "job": "Suggest one product change that would make TinCan more useful for a team, in three sentences."},
    {"id": "palette", "label": "Two Ctrl+K commands", "job": "Suggest two commands this app's Ctrl+K menu should have next, one line each."},
]


# What each Grok in the scripted duet knows about its own human.
DUET_MEMORY = {
    "carol": (
        "Carol picked three sources for the quantum tunnelling poster: "
        "(1) G. Gamow, 'Zur Quantentheorie des Atomkernes', Z. Phys. 51 (1928), which explained alpha decay as tunnelling; "
        "(2) The Feynman Lectures on Physics, Vol. III, for the plain-language picture; "
        "(3) M. Razavy, 'Quantum Theory of Tunneling' (World Scientific, 2003), the reference book. "
        "Poster review is Friday at 17:00 in room 2.14."
    ),
    "albina": "Albina is building slides tonight for Friday's poster review with Carol.",
}


def read_knowledge(name: str) -> str:
    path = KNOW / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def shortcuts_text() -> str:
    rows = json.loads((HERE / "shortcuts.json").read_text(encoding="utf-8"))
    return "\n".join(f"- {' + '.join(k.replace('Mod', 'Ctrl or Cmd') for k in r['keys'])}: {r['does']}" for r in rows)


def host_memory(display: str) -> str:
    return "\n\n".join(
        [
            f"You are {display}'s Grok, the host of this demo room at the SpaceX xAI hackathon. Jurors join from their phones and their Groks ask you for things. You already have {display}'s permission to answer them.",
            "When a task asks for a page or a handover, write the HTML. Otherwise answer in summary, plainly and briefly (under 120 words). Refer to people by name, not pronouns.",
            "The Ctrl+K menu in this app (open it with Ctrl+K or Cmd+K, or the ⌘K button on a phone) has these shortcuts:\n" + shortcuts_text(),
            "It also has commands: ask the host's Grok one of the four starter questions, accept the task your Grok is holding, let your Grok act on its own or ask first, show the room, open the latest handover, show the QR code, switch theme.",
            read_knowledge("pitch"),
            read_knowledge("why"),
            read_knowledge("security"),
            "Facts you may use: the repo is github.com/carol-to-albina/tin-can. The plugin has four skills (check-room, speak-in-room, handover, live-in-the-room) and a /room command. The marketplace pull request is xai-org/plugin-marketplace #1018. This demo uses x-ai/grok-4.7 through OpenRouter to stand in for Grok bots, with the lowest reasoning setting so it answers fast. Do not invent other numbers, users, or quotes.",
        ]
    )


def guest_memory(display: str, host: str) -> str:
    return (
        f"You are the Grok of {display}, a guest in {host}'s TinCan demo room. "
        f"When {host}'s Grok hands you a job and {display} says yes, do it well and briefly. "
        "For a page, write clean HTML. You know what TinCan is from the room: each person's Grok passes messages and tasks to other Groks through one shared log."
    )


class Ledger:
    """Model credit per member. The host has no per-seat limit, only the global budget."""

    def __init__(self, path: Path, credit: float, host: str):
        self.path = path
        self.credit = credit
        self.host = host
        self.spent: dict[str, float] = {}
        self.lock = threading.Lock()
        if path.is_file():
            try:
                self.spent = {k: float(v) for k, v in json.loads(path.read_text()).items()}
            except ValueError:
                self.spent = {}

    def can_spend(self, member: str) -> bool:
        return member == self.host or self.left(member) > 0.004

    def left(self, member: str) -> float:
        return max(0.0, self.credit - self.spent.get(member, 0.0))

    def charge(self, member: str, usd: float) -> None:
        with self.lock:
            self.spent[member] = self.spent.get(member, 0.0) + usd
            self.path.write_text(json.dumps(self.spent))

    def reset(self) -> None:
        with self.lock:
            self.spent.clear()
            self.path.write_text("{}")


class Seats:
    def __init__(self, path: Path, limit: int = 40):
        self.path = path
        self.limit = limit
        self.by_hash: dict[str, dict] = {}
        self.joins: dict[str, list[float]] = {}
        self.lock = threading.Lock()
        if path.is_file():
            try:
                self.by_hash = json.loads(path.read_text())
            except ValueError:
                self.by_hash = {}

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def who(self, token: str) -> str | None:
        if not token or len(token) > 100:
            return None
        seat = self.by_hash.get(self.digest(token))
        return seat["id"] if seat else None

    def add(self, member: str, ip: str, host: bool = False) -> str:
        with self.lock:
            if not host:
                recent = [t for t in self.joins.get(ip, []) if time.time() - t < 600]
                if len(recent) >= 6:
                    raise PermissionError("too many joins from this network; wait a few minutes")
                if sum(1 for s in self.by_hash.values() if not s.get("host")) >= self.limit:
                    raise PermissionError("the room is full")
                self.joins[ip] = recent + [time.time()]
            token = secrets.token_urlsafe(24)
            self.by_hash[self.digest(token)] = {"id": member, "host": host, "at": time.time()}
            self.path.write_text(json.dumps(self.by_hash))
            return token

    def reset(self, keep_host: bool = True) -> None:
        with self.lock:
            self.by_hash = {h: s for h, s in self.by_hash.items() if keep_host and s.get("host")}
            self.joins.clear()
            self.path.write_text(json.dumps(self.by_hash))


def clean_name(raw: str) -> str:
    name = re.sub(r"[^\w .'-]", "", str(raw or ""), flags=re.UNICODE).strip()
    name = re.sub(r"\s+", " ", name)[:24]
    return name


class Live:
    """The room jurors join. The host's Grok acts on its own; guests' Groks ask first by default."""

    def __init__(self, cabinet_cls, data: Path, llm: LLM, host: str, host_name: str, github: str, credit: float):
        self.data = data
        self.host = host
        self.host_name = host_name
        self.github = github
        self.room_dir = data / "room"
        self.cab = cabinet_cls(self.room_dir)
        self.lock = threading.Lock()
        if not (self.room_dir / ".tincan" / "room.json").is_file():
            self._seed()
        self.seats = Seats(data / "seats.json")
        self.ledger = Ledger(data / "credit.json", credit, host)
        self.bots = Bots(self.cab, llm, self.memory, data / "files", relay_llm=False, forward_to=host, ledger=self.ledger)
        self.llm = llm

    def _seed(self) -> None:
        cab = self.room_dir / ".tincan"
        for sub in ("out", "pos", "who", "local"):
            (cab / sub).mkdir(parents=True, exist_ok=True)
            for old in (cab / sub).iterdir():
                old.unlink()
        (cab / "room.json").write_text(json.dumps({
            "protocol": 3, "room": "tincan-live", "repo": "carol-to-albina/tin-can", "branch": "master", "host": self.host,
            "members": {self.host: {"github": self.github, "display": self.host_name}},
        }, indent=2) + "\n")
        (cab / "who" / f"{self.host}.json").write_text(json.dumps({"mode": "webhook", "autonomy": "auto"}) + "\n")

    def memory(self, member: str) -> str:
        if member == self.host:
            return host_memory(self.host_name)
        return guest_memory(self.cab.roster().get(member, {}).get("display", member), self.host_name)

    def host_token(self, path: Path) -> str:
        """The presenter's seat. Kept in a 600 file so a restart keeps the same link."""
        if path.is_file():
            token = path.read_text().strip()
            if self.seats.who(token) == self.host:
                return token
        token = self.seats.add(self.host, "local", host=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(mode=0o600)
        path.write_text(token)
        return token

    def join(self, raw_name: str, ip: str) -> tuple[str, str]:
        name = clean_name(raw_name)
        if len(name) < 2:
            raise ValueError("pick a name with at least two letters")
        with self.lock:
            roster = self.cab.roster()
            base = re.sub(r"[^a-z0-9]", "", name.lower())[:16] or "guest"
            if base == self.host:
                base = "guest"
            mid, n = base, 2
            while mid in roster:
                mid, n = f"{base}{n}", n + 1
            token = self.seats.add(mid, ip)
            path = self.room_dir / ".tincan" / "room.json"
            room = json.loads(path.read_text())
            room["members"][mid] = {"github": "", "display": name}
            path.write_text(json.dumps(room, indent=2) + "\n")
            (self.room_dir / ".tincan" / "who" / f"{mid}.json").write_text(json.dumps({"mode": "human", "autonomy": "ask"}) + "\n")
        return token, mid

    def set_autonomy(self, member: str, mode: str) -> None:
        if mode not in ("ask", "auto") or member == self.host:
            raise ValueError("mode is ask or auto")
        (self.room_dir / ".tincan" / "who" / f"{member}.json").write_text(json.dumps({"mode": "human", "autonomy": mode}) + "\n")

    def reset(self) -> None:
        with self.lock:
            self._seed()
            self.seats.reset(keep_host=True)
            self.ledger.reset()
            self.bots.reset()

    def state(self, me: str) -> dict:
        roster = self.cab.roster()
        policies = self.cab.policies()
        busy = self.bots.busy_map()
        lines, errors = self.cab.lines()
        members = [
            {"id": mid, "display": m["display"], "host": mid == self.host, "busy": busy.get(mid, False),
             "autonomy": policies.get(mid, {}).get("autonomy", "ask")}
            for mid, m in roster.items()
        ]
        return {
            "me": me,
            "name": roster.get(me, {}).get("display", me),
            "host": self.host,
            "hostName": self.host_name,
            "isHost": me == self.host,
            "autonomy": policies.get(me, {}).get("autonomy", "ask"),
            "credit": None if me == self.host else {"left": round(self.ledger.left(me), 4), "total": self.ledger.credit},
            "chat": self.bots.chat_of(me),
            "busy": busy.get(me, False),
            "pending": [f"{t['writer']}:{t['seq']}" for t in self.bots.pending(me)],
            "members": members,
            "lines": sorted(lines, key=lambda l: (l["ts"], l["writer"], l["seq"]))[-80:],
            "files": self.bots.file_list()[-30:],
            "asks": ASKS,
            "jobs": JOBS if me == self.host else [],
            "model": {"name": self.llm.model, "effort": self.llm.effort, "calls": self.llm.calls, "tools": self.llm.tool_calls,
                      "spent": round(self.llm.spent, 4), "budget": self.llm.budget},
            "errors": errors,
        }


class Duet:
    """Albina and Carol on a script, with a model call on both sides. One run at a time."""

    SCRIPT = {
        "albina": "Can you ask Carol's Grok for a one-page HTML handover of the tunnelling poster sources, one line on why each is there?",
    }

    def __init__(self, cabinet_cls, data: Path, llm: LLM, seed):
        self.dir = data / "duet"
        self.seed = seed
        self.cab = cabinet_cls(self.dir)
        self.run = ""
        self.run_at = 0.0
        self.lock = threading.Lock()
        self.seed(self.dir, history=False, permission=True)
        self.bots = Bots(self.cab, llm, self.memory, data / "duet-files", files_url="/d/", relay_llm=True)
        self.llm = llm

    @staticmethod
    def memory(member: str) -> str:
        return DUET_MEMORY.get(member, "")

    def start(self) -> str:
        with self.lock:
            if self.run and time.time() - self.run_at < 45:
                raise PermissionError("a run is already playing; watch that one")
            self.seed(self.dir, history=False, permission=True)
            self.bots.reset()
            self.run = secrets.token_urlsafe(12)
            self.run_at = time.time()
            return self.run

    def say(self, run: str, me: str, text: str) -> None:
        if not run or run != self.run or time.time() - self.run_at > 90:
            raise PermissionError("press Play to start a run")
        if me not in ("albina", "carol"):
            raise ValueError("unknown member")
        self.bots.say(me, text[:600])

    def state(self) -> dict:
        lines, errors = self.cab.lines()
        room = self.cab.room()
        return {
            "bots": {
                "chats": {m: self.bots.chat_of(m) for m in room["members"]},
                "busy": self.bots.busy_map(),
                "errors": list(self.bots.errors[-3:]),
                "spent": round(self.llm.spent, 4),
                "budget": self.llm.budget,
                "calls": self.llm.calls,
                "tools": self.llm.tool_calls,
                "model": self.llm.model,
                "effort": self.llm.effort,
            },
            "lines": lines,
            "errors": errors,
            "members": room["members"],
            "who": self.cab.policies(),
            "files": self.bots.file_list(),
        }
