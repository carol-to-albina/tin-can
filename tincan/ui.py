"""Local chat for one room. Bind it to 127.0.0.1. Git does the rest."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .files import find_cabinet, load_all_events, load_members, load_room, local_me_path, room_path
from .reduce import merge_order
from .room import Room, github_login, init, join
from .types import (
    EventRef,
    MemberId,
    ProtocolError,
    SpeechDraft,
    TaskDraft,
    TaskState,
    TinCanError,
)

COLORS = ("#3dbe7a", "#f5a524", "#7c6af7", "#3b82f6", "#ec4899", "#2eb8b0")
HOST = "127.0.0.1"
MAX_BODY = 100_000

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TinCan</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #0c0c0e;
    --panel: #141416;
    --bubble: #2a2a2e;
    --line: #2c2c31;
    --text: #f4f4f5;
    --muted: #9b9ba4;
    --user: #f4f4f5;
    --ink: #141416;
    --green: #3dd68c;
    --danger: #ff8b8b;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; background: var(--bg); color: var(--text); }
  body { font: 15px/1.45 ui-sans-serif, system-ui, sans-serif; }
  button, textarea, input { font: inherit; color: inherit; }
  #app { height: 100%; display: grid; grid-template-columns: 280px minmax(0, 1fr) 300px; }
  aside { background: var(--panel); min-height: 0; display: flex; flex-direction: column; }
  #side { border-right: 1px solid var(--line); }
  #rail { border-left: 1px solid var(--line); }
  .brand, .chat-head, .block { padding: 16px; }
  .brand { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .brand strong { font-size: 18px; letter-spacing: -0.03em; }
  #find, #box, .done-body {
    width: 100%; border: 0; border-radius: 12px; background: #232328; padding: 10px 12px;
  }
  #find { margin: 0 16px 12px; width: auto; }
  #people { overflow: auto; padding: 0 8px 12px; }
  .person {
    width: 100%; text-align: left; border: 0; background: transparent; color: inherit;
    display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 10px;
    padding: 10px; border-radius: 12px; cursor: pointer;
  }
  .person.on { background: #222228; }
  .person small { color: var(--muted); display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .avatar {
    width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center;
    color: #111; font-weight: 700;
  }
  #seat { margin-top: auto; padding: 12px 16px 16px; display: flex; gap: 8px; }
  #seat button, #send, .act {
    border: 0; border-radius: 999px; padding: 8px 14px; background: #2a2a2e; cursor: pointer;
  }
  #seat button.on, #send { background: var(--user); color: var(--ink); }
  main { min-width: 0; min-height: 0; display: flex; flex-direction: column; }
  .chat-head { display: flex; gap: 10px; align-items: center; border-bottom: 1px solid var(--line); }
  .chat-head p, .sub { margin: 0; color: var(--muted); font-size: 13px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; background: var(--muted); margin-right: 6px; }
  .dot.on { background: var(--green); }
  #log { flex: 1; overflow: auto; padding: 20px 8vw 12px; display: flex; flex-direction: column; gap: 12px; }
  .msg { display: flex; gap: 10px; max-width: 680px; }
  .msg.mine { margin-left: auto; flex-direction: row-reverse; }
  .bubble { background: var(--bubble); border-radius: 18px; padding: 10px 14px; white-space: pre-wrap; }
  .msg.mine .bubble { background: var(--user); color: var(--ink); border-radius: 18px; }
  .meta { color: var(--muted); font-size: 12px; margin-top: 4px; }
  .msg.mine .meta { text-align: right; }
  .card { border: 1px solid var(--line); border-radius: 16px; padding: 12px; background: #1b1b1f; }
  .card h3 { margin: 0 0 6px; font-size: 13px; color: var(--muted); font-weight: 600; }
  .acts { display: flex; gap: 8px; margin-top: 8px; }
  .done-body { margin-top: 8px; }
  #composer { padding: 12px 8vw 18px; }
  #box { min-height: 52px; max-height: 160px; resize: vertical; background: #1c1c20; border-radius: 22px; }
  .compose-row { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
  .check { color: var(--muted); font-size: 13px; }
  #rail .block + .block { border-top: 1px solid var(--line); }
  .task { padding: 8px 0; }
  .task b { font-weight: 600; }
  #menu { display: none; }
  .empty { color: var(--muted); }
  .err { color: var(--danger); }
  @media (max-width: 860px) {
    #app { grid-template-columns: 1fr; }
    #side, #rail { display: none; }
    #app.nav #side { display: flex; position: absolute; inset: 0 auto 0 0; width: min(320px, 100%); z-index: 2; }
    #menu { display: inline-flex; }
    #log, #composer { padding-left: 16px; padding-right: 16px; }
  }
</style>
</head>
<body>
<div id="app">
  <aside id="side">
    <div class="brand"><strong>tincan</strong></div>
    <input id="find" placeholder="Search" aria-label="Search members">
    <div id="people"></div>
    <div id="seat"></div>
  </aside>
  <main>
    <header class="chat-head">
      <button id="menu" type="button">Room</button>
      <div id="who"></div>
    </header>
    <div id="log"></div>
    <form id="composer">
      <textarea id="box" rows="2" placeholder="Message" aria-label="Message"></textarea>
      <div class="compose-row">
        <label class="check"><input id="as-task" type="checkbox"> Send as a task</label>
        <button id="send" type="submit">Send</button>
      </div>
    </form>
  </main>
  <aside id="rail">
    <div class="block" id="link"></div>
    <div class="block" id="jobs"></div>
  </aside>
</div>
<script>
const params = new URLSearchParams(location.search);
let me = params.get("me") || "";
let latest = /*__BOOT__*/ null;

function el(tag, attrs, text) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  if (text != null) node.textContent = text;
  return node;
}

function initial(name) {
  return (name || "?").slice(0, 1).toUpperCase();
}

function paint() {
  const data = latest;
  if (!data || !data.ok) {
    document.querySelector("#log").replaceChildren(el("p", {class: "err"}, (data && data.error) || "The room did not load."));
    return;
  }
  const rest = data.members.filter((row) => row.id !== data.me);
  const talking = rest.length === 1 ? rest[0] : {id: "all", display: data.room, color: "#7c6af7"};
  const query = document.querySelector("#find").value.trim().toLowerCase();
  const people = document.querySelector("#people");
  people.replaceChildren();
  for (const row of data.members) {
    if (query && !row.display.toLowerCase().includes(query) && !row.id.includes(query)) continue;
    const button = el("button", {class: "person" + (row.id === talking.id ? " on" : ""), type: "button"});
    const face = el("span", {class: "avatar"});
    face.style.background = row.color;
    face.textContent = initial(row.display);
    const copy = el("span");
    copy.append(el("strong", null, row.display), el("small", null, row.preview || "No messages yet"));
    button.append(face, copy);
    people.append(button);
  }
  const who = document.querySelector("#who");
  who.replaceChildren();
  const face = el("span", {class: "avatar"});
  face.style.background = talking.color || "#7c6af7";
  face.textContent = initial(talking.display);
  const title = el("div");
  title.append(el("strong", null, talking.display));
  const status = el("p");
  const dot = el("span", {class: "dot" + (data.connection.ok ? " on" : "")});
  status.append(dot, document.createTextNode(data.connection.detail));
  title.append(status);
  who.append(face, title);

  const seat = document.querySelector("#seat");
  seat.replaceChildren();
  if ((data.seats || []).length > 1) {
    for (const id of data.seats) {
      const row = data.members.find((item) => item.id === id);
      const button = el("button", {type: "button", class: id === data.me ? "on" : ""}, row ? row.display : id);
      button.addEventListener("click", () => { me = id; tick(); });
      seat.append(button);
    }
  }

  const log = document.querySelector("#log");
  log.replaceChildren();
  if (!data.lines.length) log.append(el("p", {class: "empty"}, "No messages yet."));
  for (const line of data.lines) {
    const wrap = el("article", {class: "msg" + (line.mine ? " mine" : "")});
    const face = el("span", {class: "avatar"});
    const member = data.members.find((item) => item.id === line.writer);
    face.style.background = member ? member.color : "#444";
    face.textContent = initial(line.name);
    const body = el("div");
    if (line.kind === "task") {
      const card = el("div", {class: "card"});
      card.append(el("h3", null, "Task " + line.ref), el("div", null, line.body));
      const job = data.tasks.find((item) => item.ref === line.ref);
      if (job) {
        card.append(el("p", {class: "sub"}, job.state.replaceAll("_", " ") + (job.claimant ? " · " + job.claimant : "")));
        const acts = el("div", {class: "acts"});
        if (job.can_claim) {
          const claim = el("button", {class: "act", type: "button"}, "Claim");
          claim.addEventListener("click", () => run({op: "claim", ref: job.ref}));
          acts.append(claim);
        }
        if (job.can_finish) {
          const note = el("input", {class: "done-body", placeholder: "What happened"});
          const done = el("button", {class: "act", type: "button"}, "Done");
          done.addEventListener("click", () => run({op: "done", ref: job.ref, body: note.value}));
          card.append(note);
          acts.append(done);
        }
        if (acts.childNodes.length) card.append(acts);
      }
      body.append(card);
    } else if (line.kind === "speech") {
      body.append(el("div", {class: "bubble"}, line.body));
    } else {
      const label = line.kind + (line.pointer ? " " + line.pointer : "");
      body.append(el("div", {class: "bubble"}, (line.body ? label + "\\n" + line.body : label)));
    }
    body.append(el("div", {class: "meta"}, line.name + " · " + line.ts));
    wrap.append(face, body);
    log.append(wrap);
  }
  log.scrollTop = log.scrollHeight;

  const link = document.querySelector("#link");
  link.replaceChildren(el("h3", null, "This machine"), el("p", {class: "sub"}, data.connection.detail));
  const jobs = document.querySelector("#jobs");
  jobs.replaceChildren(el("h3", null, "Tasks"));
  if (!data.tasks.length) jobs.append(el("p", {class: "empty"}, "Nothing open."));
  for (const job of data.tasks) {
    const row = el("div", {class: "task"});
    row.append(el("b", null, job.ref), el("div", null, job.body), el("p", {class: "sub"}, job.state.replaceAll("_", " ")));
    jobs.append(row);
  }
}

async function tick() {
  const url = "/state" + (me ? "?me=" + encodeURIComponent(me) : "");
  const res = await fetch(url);
  latest = await res.json();
  if (latest.ok && !me) me = latest.me;
  paint();
}

async function run(payload) {
  payload.me = me;
  const res = await fetch("/act", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (!data.ok) {
    const log = document.querySelector("#log");
    log.prepend(el("p", {class: "err"}, data.error || "That did not send."));
    return;
  }
  await tick();
}

document.querySelector("#composer").addEventListener("submit", (event) => {
  event.preventDefault();
  const box = document.querySelector("#box");
  const body = box.value.trim();
  if (!body) return;
  const op = document.querySelector("#as-task").checked ? "task" : "speech";
  box.value = "";
  run({op, body});
});
document.querySelector("#box").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    document.querySelector("#composer").requestSubmit();
  }
});
document.querySelector("#find").addEventListener("input", paint);
document.querySelector("#menu").addEventListener("click", () => {
  document.querySelector("#app").classList.toggle("nav");
});
if (latest && latest.ok) {
  if (!me) me = latest.me;
  paint();
}
tick();
setInterval(tick, 2000);
</script>
</body>
</html>
"""


def color_for(member: str) -> str:
    total = sum(ord(char) for char in member)
    return COLORS[total % len(COLORS)]


def _other(me: str, members) -> MemberId | str:
    rest = [item for item in members if str(item) != me]
    if len(rest) == 1:
        return rest[0]
    return "all"


def _clock(stamp: str) -> str:
    if len(stamp) >= 16 and stamp[10] == "T":
        return stamp[11:16]
    return stamp


def connection(root: Path, me: str) -> dict:
    remote = ""
    try:
        from . import git

        remote = git.remote_url(root)
    except TinCanError:
        remote = ""
    on_github = "github.com" in remote
    login = github_login() if on_github else ""
    expected = ""
    try:
        expected = load_members(root)[MemberId(me)].github
    except (TinCanError, KeyError):
        expected = ""
    if on_github and login and expected and login != expected:
        detail = f"gh is {login}. This seat pushes as {expected}."
        ok = False
    elif on_github and login:
        detail = f"GitHub connected as {login}"
        ok = True
    elif on_github:
        detail = "GitHub is not connected on this machine"
        ok = False
    else:
        detail = "Local room. A GitHub remote uses the login already on this machine."
        ok = True
    return {"ok": ok, "github": on_github, "login": login, "remote": remote, "detail": detail}


def snapshot(root: Path, me: str, seats: list[str]) -> dict:
    room = Room(root, MemberId(me))
    try:
        room.sync()
        members = load_members(root)
        events = sorted(load_all_events(root, members), key=merge_order)
        tasks = list(room.tasks())
        cfg = load_room(root)
    except TinCanError as exc:
        return {"ok": False, "me": me, "error": str(exc), "seats": seats}
    last: dict[str, tuple[str, str]] = {}
    lines = []
    for event in events:
        writer = str(event.meta.writer)
        body = getattr(event, "body", "") or ""
        last[writer] = (body or event.kind.value, _clock(event.meta.ts))
        pointer = str(getattr(event, "ref", "") or "")
        lines.append(
            {
                "ref": str(event.meta.ref()),
                "writer": writer,
                "name": members[event.meta.writer].display,
                "kind": event.kind.value,
                "body": body,
                "ts": _clock(event.meta.ts),
                "mine": writer == me,
                "pointer": pointer,
            }
        )
    job_rows = []
    for task in tasks:
        job_rows.append(
            {
                "ref": str(task.ref),
                "body": task.body,
                "state": task.state.value,
                "claimant": str(task.claimant or ""),
                "can_claim": task.state in (TaskState.OPEN, TaskState.WAITING_HUMAN)
                and task.to in (MemberId(me), "all"),
                "can_finish": task.state is TaskState.CLAIMED and task.claimant == MemberId(me),
            }
        )
    roster = []
    for member_id, member in members.items():
        preview, when = last.get(str(member_id), ("", ""))
        roster.append(
            {
                "id": str(member_id),
                "display": member.display,
                "github": member.github,
                "color": color_for(str(member_id)),
                "preview": preview,
                "when": when,
            }
        )
    return {
        "ok": True,
        "me": me,
        "room": cfg.room,
        "seats": seats,
        "members": roster,
        "lines": lines,
        "tasks": job_rows,
        "connection": connection(root, me),
    }


def act(root: Path, me: str, payload: dict) -> dict:
    room = Room(root, MemberId(me))
    op = str(payload.get("op") or "")
    if op in ("speech", "task"):
        body = str(payload.get("body") or "").strip()
        if not body:
            raise ProtocolError("message is empty")
        target = payload.get("to") or _other(me, load_members(root))
        if target != "all":
            target = MemberId(str(target))
        draft = SpeechDraft(target, body) if op == "speech" else TaskDraft(target, body)
        event = room.post(draft)
        room.publish()
        return {"ok": True, "ref": str(event.meta.ref())}
    if op == "claim":
        event = room.claim(EventRef.parse(str(payload.get("ref") or "")))
        return {"ok": True, "won": event is not None, "ref": None if event is None else str(event.meta.ref())}
    if op in ("done", "fail"):
        ref = EventRef.parse(str(payload.get("ref") or ""))
        body = str(payload.get("body") or "").strip() or "done"
        event = room.done(ref, body) if op == "done" else room.fail(ref, body)
        room.publish()
        return {"ok": True, "ref": str(event.meta.ref())}
    raise ProtocolError(f"unknown action {op!r}")


def _git(cwd: Path, *args: str, identity: tuple[str, str] | None = None) -> None:
    command = ["git"]
    env = None
    if identity:
        command += ["-c", f"user.name={identity[0]}", "-c", f"user.email={identity[1]}"]
        env = os.environ.copy()
        for key in (
            "GIT_AUTHOR_NAME",
            "GIT_AUTHOR_EMAIL",
            "GIT_AUTHOR_DATE",
            "GIT_COMMITTER_NAME",
            "GIT_COMMITTER_EMAIL",
            "GIT_COMMITTER_DATE",
        ):
            env.pop(key, None)
    command += list(args)
    run = subprocess.run(command, cwd=cwd, capture_output=True, text=True, env=env)
    if run.returncode != 0:
        detail = run.stderr.strip() or run.stdout.strip() or "git failed"
        raise RuntimeError(detail)


def seed_pair(base: Path) -> dict[str, Path]:
    """Bare remote plus Carol and Albina clones. No GitHub account required."""
    base.mkdir(parents=True, exist_ok=True)
    remote = base / "remote.git"
    _git(base, "init", "--bare", "-b", "master", str(remote))
    carol = base / "carol"
    _git(base, "clone", str(remote), str(carol))
    init(
        "tincan",
        "local/tincan",
        MemberId("carol"),
        "rainbowpuffpuff",
        "Carol",
        root=carol,
    )
    path = room_path(carol)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["members"]["albina"] = {"github": "enjojoy", "display": "Albina"}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _git(carol, "add", "--", ".tincan")
    _git(
        carol,
        "commit",
        "-m",
        "room",
        identity=("rainbowpuffpuff", "rainbowpuffpuff@users.noreply.github.com"),
    )
    _git(carol, "push", "-u", "origin", "master")
    albina = base / "albina"
    _git(base, "clone", str(remote), str(albina))
    join(MemberId("carol"), root=carol)
    join(MemberId("albina"), root=albina)
    return {"carol": carol, "albina": albina}


def make_handler(clones: dict[str, Path]):
    seats = {me: Path(path) for me, path in clones.items()}
    locks = {me: threading.Lock() for me in seats}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

        def _me(self, raw: str) -> str:
            chosen = raw.strip() or next(iter(seats))
            if chosen not in seats:
                raise ProtocolError(f"unknown member {chosen}")
            return chosen

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                raw = parse_qs(parsed.query).get("me", [""])[0]
                try:
                    chosen = self._me(raw)
                except ProtocolError:
                    chosen = next(iter(seats))
                with locks[chosen]:
                    payload = snapshot(seats[chosen], chosen, list(seats))
                blob = json.dumps(payload).replace("<", "\\u003c")
                html = PAGE.replace("/*__BOOT__*/ null", blob)
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
                return
            if parsed.path != "/state":
                self._json(404, {"ok": False, "error": "not found"})
                return
            try:
                me = self._me(parse_qs(parsed.query).get("me", [""])[0])
            except ProtocolError as exc:
                self._json(404, {"ok": False, "error": str(exc)})
                return
            with locks[me]:
                self._json(200, snapshot(seats[me], me, list(seats)))

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/act":
                self._json(404, {"ok": False, "error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or "0")
            if length < 1 or length > MAX_BODY:
                self._json(400, {"ok": False, "error": "bad body"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                self._json(400, {"ok": False, "error": "bad json"})
                return
            if not isinstance(payload, dict):
                self._json(400, {"ok": False, "error": "bad json"})
                return
            try:
                me = self._me(str(payload.get("me") or ""))
                with locks[me]:
                    self._json(200, act(seats[me], me, payload))
            except TinCanError as exc:
                self._json(400, {"ok": False, "error": str(exc)})

    return Handler


def serve(clones: dict[str, Path], port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer((HOST, port), make_handler(clones))
    url = f"http://{HOST}:{httpd.server_address[1]}/"
    return httpd, url


def _me_from(root: Path, explicit: str) -> str:
    chosen = explicit.strip() or os.environ.get("TINCAN_ME", "").strip()
    if not chosen:
        path = local_me_path(root)
        if path.is_file():
            chosen = path.read_text(encoding="utf-8").strip()
    if not chosen:
        raise ProtocolError("set --me, TINCAN_ME, or .tincan/local/me")
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tincan.ui", description="TinCan chat on this computer")
    parser.add_argument("--demo", action="store_true", help="local Carol and Albina room")
    parser.add_argument("--root", default="")
    parser.add_argument("--me", default="")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    if args.demo:
        base = Path(tempfile.mkdtemp(prefix="tincan-demo-"))
        clones = seed_pair(base)
        print(f"demo files {base}")
    else:
        root = find_cabinet(Path(args.root) if args.root else Path.cwd())
        me = _me_from(root, args.me)
        clones = {me: root}
    httpd, url = serve(clones, args.port)
    print(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
