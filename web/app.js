// TinCan room UI. Polls /api/state, folds the outboxes the way docs/v3/SPEC.md does, renders a Grok-style chat.
"use strict";

const $ = (sel) => document.querySelector(sel);
const params = new URLSearchParams(location.search);
const ROOT_KINDS = new Set(["speech", "task", "grant_request"]);
const PALETTE = ["#7c5cff", "#e5484d", "#12a594", "#f76b15", "#0090ff", "#d6409f", "#8e8c99"];

let S = null;          // last /api/state payload
let D = null;          // derived view of S
let view = params.get("t") || "all";
let taskMode = false;
let lastRender = "";
let query = "";
const openForms = new Map(); // ref -> "done" | "fail"

// ---------- api ----------
async function api(path, body) {
  const url = new URL(path, location.href);
  if (params.get("me")) url.searchParams.set("me", params.get("me"));
  const init = body ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) } : {};
  const res = await fetch(url, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || res.statusText);
    Object.assign(err, { signin: !!data.signin, signout: !!data.signout });
    throw err;
  }
  return data;
}

// ---------- fold ----------
const refOf = (l) => `${l.writer}:${l.seq}`;
const byMerge = (a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : a.writer < b.writer ? -1 : a.writer > b.writer ? 1 : a.seq - b.seq);

function derive(S) {
  const me = S.me;
  const lines = S.lines.slice().sort(byMerge);
  const byRef = new Map(lines.map((l) => [refOf(l), l]));
  const autonomy = (id) => S.who[id]?.autonomy || "ask";
  const tasks = new Map();
  const grants = new Map();
  const cots = new Map();
  const now = Date.parse(S.now) || Date.now();

  for (const l of lines) {
    const id = refOf(l);
    if (l.kind === "task") {
      const initial = l.to === "all" ? "open" : { ask: "waiting_human", observe: "ignored" }[autonomy(l.to)] || "open";
      tasks.set(id, { status: initial, claimant: null, claimedAt: null, result: null });
    } else if (l.kind === "grant_request") {
      grants.set(id, { status: "requested", granter: l.to, decidedAt: null });
    } else if (l.ref) {
      const t = tasks.get(l.ref);
      if (t) {
        if (l.kind === "claim" && !t.claimant) Object.assign(t, { status: "claimed", claimant: l.writer, claimedAt: l.ts });
        else if ((l.kind === "done" || l.kind === "fail") && l.writer === t.claimant && t.status === "claimed")
          Object.assign(t, { status: l.kind === "done" ? "done" : "failed", result: l });
      }
      const g = grants.get(l.ref);
      if (g && l.writer === g.granter) {
        if (g.status === "requested" && (l.kind === "grant" || l.kind === "deny"))
          Object.assign(g, { status: l.kind === "grant" ? "live" : "denied", decidedAt: l.ts });
        else if (g.status === "live" && l.kind === "revoke") Object.assign(g, { status: "revoked", decidedAt: l.ts });
      }
      if (l.kind === "cot" || l.kind === "receipt") {
        if (!cots.has(l.ref)) cots.set(l.ref, []);
        cots.get(l.ref).push(l);
      }
    }
  }
  for (const [id, g] of grants) {
    const req = byRef.get(id);
    if (g.status === "live" && req.expires && Date.parse(req.expires) <= now) g.status = "expired";
  }

  const threadOf = (l) => {
    if (l.to === "all") return "all";
    if (l.writer === me) return l.to;
    if (l.to === me) return l.writer;
    return null; // between two other members: their bots, not yours
  };
  const seen = S.pos[me] || {};
  const isUnread = (l) => l.writer !== me && l.seq > (seen[l.writer] || 0);
  const threads = new Map([["all", { key: "all", roots: [], unread: false, last: "" }]]);
  for (const id of Object.keys(S.room.members)) {
    if (id !== me) threads.set(id, { key: id, roots: [], unread: false, last: "" });
  }
  const threadByRoot = new Map();
  for (const l of lines) {
    if (!ROOT_KINDS.has(l.kind)) continue;
    const key = threadOf(l);
    if (!key || !threads.has(key)) continue;
    const th = threads.get(key);
    th.roots.push(l);
    th.last = l.ts;
    threadByRoot.set(refOf(l), key);
  }
  for (const l of lines) {
    if (!isUnread(l)) continue;
    const key = ROOT_KINDS.has(l.kind) ? threadOf(l) : threadByRoot.get(l.ref);
    if (key && threads.has(key)) threads.get(key).unread = true;
  }

  const myTasks = [...tasks.entries()]
    .map(([id, t]) => ({ line: byRef.get(id), ...t }))
    .filter(({ line, claimant }) => line.writer === me || line.to === me || line.to === "all" || claimant === me);
  const todo = myTasks.filter((t) => t.claimant === me ? t.status === "claimed" : (t.line.to === me || (t.line.to === "all" && t.line.writer !== me)) && (t.status === "open" || t.status === "waiting_human"));

  return { me, lines, byRef, tasks, grants, cots, threads, threadByRoot, isUnread, myTasks, todo };
}

// ---------- helpers ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const display = (id) => (id === "all" ? "Room" : S.who[id]?.display || S.room.members[id]?.display || id);
const colorOf = (id) => {
  const ids = Object.keys(S.room.members).sort();
  return PALETTE[Math.max(0, ids.indexOf(id)) % PALETTE.length];
};
const avatar = (id, cls = "") => `<span class="avatar ${cls}" style="background:${colorOf(id)}">${esc(display(id).slice(0, 1))}</span>`;
const possessive = (id) => (id === S.me ? "your" : `${display(id)}'s`);

function richText(s) {
  const safe = esc(s).trim();
  const inline = (t) =>
    t
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
  return safe
    .split(/\n{2,}/)
    .map((p) => `<p>${inline(p).replace(/\n/g, "<br>")}</p>`)
    .join("");
}

function ago(ts) {
  const s = Math.max(0, (Date.now() - Date.parse(ts)) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
const clock = (ts) => new Date(ts).toLocaleString(undefined, { hour: "2-digit", minute: "2-digit", month: "short", day: "numeric" });
const until = (ts) => new Date(ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

const ICON = {
  copy: '<svg viewBox="0 0 24 24" width="16" height="16"><rect x="8.5" y="8.5" width="11" height="11" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
  reply: '<svg viewBox="0 0 24 24" width="16" height="16"><path d="M9 7 4 12l5 5M4 12h10a6 6 0 0 1 6 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  check: '<svg viewBox="0 0 24 24" width="16" height="16"><path d="m5 12.5 4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  checks: '<svg viewBox="0 0 24 24" width="16" height="16"><path d="m2.5 12.5 4.5 4.5 9.5-9.5M11.5 16.5l.5.5 9.5-9.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  task: '<svg viewBox="0 0 24 24" width="18" height="18"><rect x="4" y="4" width="16" height="16" rx="4" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="m8.5 12.5 2.3 2.3 4.7-5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  key: '<svg viewBox="0 0 24 24" width="18" height="18"><circle cx="8" cy="15" r="4" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="m11 12 8-8m-3 3 2.5 2.5M14 9l2 2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
  room: '<svg viewBox="0 0 24 24" width="16" height="16"><circle cx="9" cy="9" r="3.2" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="16.5" cy="10" r="2.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M3.5 19c.6-3 2.8-4.5 5.5-4.5s4.9 1.5 5.5 4.5M15 14.6c2.6-.3 4.8 1 5.4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  wave: '<svg viewBox="0 0 24 24" width="16" height="16"><path d="M7 11.5V6.8a1.3 1.3 0 0 1 2.6 0V11m0-1.5V5.3a1.3 1.3 0 0 1 2.6 0V11m0-4.2a1.3 1.3 0 0 1 2.6 0V12m0-2.7a1.3 1.3 0 0 1 2.6 0v4.4a6.3 6.3 0 0 1-11.3 3.8L4.3 14a1.4 1.4 0 0 1 2.2-1.7L7 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

// ---------- render: sidebar ----------
function renderSidebar() {
  const rows = [...D.threads.values()]
    .filter((th) => !query || display(th.key).toLowerCase().includes(query) || th.roots.some((l) => (l.body || "").toLowerCase().includes(query)))
    .sort((a, b) => (a.key === "all" ? -1 : b.key === "all" ? 1 : (b.last || "").localeCompare(a.last || "")));
  $("#threads").innerHTML = rows
    .map((th) => {
      const icon = th.key === "all" ? `<span class="avatar sm" style="background:var(--surface-3);color:var(--text-2)">${ICON.room}</span>` : avatar(th.key, "sm");
      return `<button class="thread-link ${view === th.key ? "active" : ""}" data-thread="${esc(th.key)}">${icon}<span class="t-name">${esc(display(th.key))}</span>${th.unread ? '<span class="dot" title="unread"></span>' : ""}</button>`;
    })
    .join("");
  $("#to-room").classList.toggle("active", view === "all");
  $("#to-tasks").classList.toggle("active", view === "tasks");
  const count = $("#task-count");
  count.hidden = !D.todo.length;
  count.textContent = D.todo.length;
  $("#me-avatar").outerHTML = `<span class="avatar" id="me-avatar" style="background:${colorOf(S.me)}">${esc(display(S.me).slice(0, 1))}</span>`;
  $("#me-name").textContent = display(S.me);
}

// ---------- render: messages ----------
function receipt(l) {
  const others = Object.keys(S.room.members).filter((id) => id !== S.me);
  const targets = l.to === "all" ? others : [l.to];
  const readBy = targets.filter((id) => (S.pos[id]?.[S.me] || 0) >= l.seq);
  if (l.to !== "all") {
    return readBy.length
      ? `<span class="meta read" title="${esc(possessive(l.to))} Grok told them">${ICON.checks}</span><span class="meta read">Read by ${esc(display(l.to))}</span>`
      : `<span class="meta" title="In the room. Their Grok wakes on the next push.">${ICON.check}</span><span class="meta">Delivered</span>`;
  }
  return `<span class="meta ${readBy.length ? "read" : ""}">${readBy.length === targets.length ? ICON.checks : ICON.check}</span><span class="meta ${readBy.length ? "read" : ""}">Read by ${readBy.length} of ${targets.length}</span>`;
}

function speechHTML(l, isLast) {
  const mine = l.writer === S.me;
  const copy = `<button class="icon-btn" data-copy="${esc(refOf(l))}" title="Copy">${ICON.copy}</button>`;
  if (mine) {
    return `<div class="msg user ${isLast ? "last" : ""}" title="${esc(clock(l.ts))}">
      <div class="bubble text">${esc(l.body)}</div>
      <div class="actions">${receipt(l)}${copy}</div></div>`;
  }
  const reply = view === "all" && l.to === "all" ? `<button class="icon-btn" data-reply="${esc(l.writer)}" title="Reply to ${esc(display(l.writer))} only">${ICON.reply}</button>` : "";
  return `<div class="msg bot ${isLast ? "last" : ""}" title="${esc(clock(l.ts))}">
    <div class="speaker">${avatar(l.writer, "sm")}<b>${esc(display(l.writer))}</b><span class="via">via ${esc(possessive(l.writer))} Grok · ${esc(ago(l.ts))}</span></div>
    <div class="text">${richText(l.body)}</div>
    <div class="actions">${copy}${reply}</div></div>`;
}

function taskHTML(l, isLast) {
  const id = refOf(l);
  const t = D.tasks.get(id);
  const mine = l.writer === S.me;
  const target = l.to === "all" ? "the room" : display(l.to);
  const label = { open: "open", waiting_human: l.to === S.me ? "waiting for you" : "waiting", claimed: `claimed by ${display(t.claimant)}`, done: "done", failed: "failed", ignored: "observe only" }[t.status];
  const head = mine
    ? `${ICON.task}<span class="who">Task for <b>${esc(target)}</b></span>`
    : `${avatar(l.writer, "sm")}<span class="who"><b>${esc(display(l.writer))}</b> asked ${l.to === "all" ? "the room" : "you"} to do this</span>`;
  let foot = "";
  const canClaim = !mine || l.to === "all";
  if ((t.status === "open" || t.status === "waiting_human") && canClaim && (l.to === S.me || l.to === "all")) {
    foot = `<div class="card-actions"><button class="btn primary" data-act="claim" data-ref="${id}">Claim</button></div>`;
  } else if (t.status === "claimed" && t.claimant === S.me) {
    const form = openForms.get(id);
    foot = form
      ? `<form class="inline-form" data-form="${form}" data-ref="${id}"><input name="body" placeholder="${form === "done" ? "Result or PR link" : "Why it failed"}" required autofocus><button class="btn primary">${form === "done" ? "Post" : "Fail"}</button><button type="button" class="btn" data-act="cancel" data-ref="${id}">Cancel</button></form>`
      : `<div class="card-actions"><button class="btn primary" data-act="open-done" data-ref="${id}">Mark done</button><button class="btn" data-act="open-fail" data-ref="${id}">Can't do it</button></div>`;
  }
  let sub = "";
  if (t.claimant && t.status === "claimed") sub = `<div class="card-sub">${esc(display(t.claimant))} claimed it ${esc(ago(t.claimedAt))}. ${t.claimant === S.me ? "It's yours now." : `${esc(possessive(t.claimant))} Grok is on it.`}</div>`;
  if (t.result) sub = `<div class="card-sub"><span class="label">${t.status === "done" ? "Result" : "Reason"} · ${esc(display(t.result.writer))} · ${esc(ago(t.result.ts))}</span><div class="text">${richText(t.result.body)}</div></div>`;
  const card = `<div class="card"><div class="card-head">${head}<span class="state ${t.status}">${esc(label)}</span></div><div class="card-body text">${richText(l.body)}</div>${sub}${foot}</div>`;
  return `<div class="msg ${mine ? "user" : "bot"} ${isLast ? "last" : ""}" title="${esc(clock(l.ts))}">${card}</div>`;
}

function grantHTML(l, isLast) {
  const id = refOf(l);
  const g = D.grants.get(id);
  const mine = l.writer === S.me;
  const caps = (l.capabilities || []).map((c) => `<code>${esc(c)}</code>`).join("");
  const head = mine
    ? `${ICON.key}<span class="who">You asked <b>${esc(display(l.to))}</b> for access</span>`
    : `${avatar(l.writer, "sm")}<span class="who"><b>${esc(display(l.writer))}</b> asks ${l.to === S.me ? "you" : esc(display(l.to))} for access</span>`;
  const label = { requested: "pending", live: l.expires ? `live until ${until(l.expires)}` : "live", denied: "denied", revoked: "revoked", expired: "expired" }[g.status];
  let foot = "";
  if (g.granter === S.me && g.status === "requested") {
    foot = `<div class="card-actions"><button class="btn primary" data-act="grant" data-ref="${id}">Approve</button><button class="btn" data-act="deny" data-ref="${id}">Deny</button></div>`;
  } else if (g.granter === S.me && g.status === "live") {
    foot = `<div class="card-actions"><button class="btn" data-act="revoke" data-ref="${id}">Revoke</button></div>`;
  }
  const thoughts = (D.cots.get(id) || [])
    .filter((c) => c.kind === "receipt" || g.status === "live")
    .map((c) => `<details class="cot"><summary>${c.kind === "cot" ? "Thoughts" : "Receipt"} from ${esc(display(c.writer))} · ${esc(ago(c.ts))}</summary><div class="text">${esc(c.body)}</div></details>`)
    .join("");
  const card = `<div class="card"><div class="card-head">${head}<span class="state ${g.status}">${esc(label)}</span></div><div class="card-body text">${richText(l.body)}</div>${caps ? `<div class="caps">${caps}</div>` : ""}${thoughts}${foot}</div>`;
  return `<div class="msg ${mine ? "user" : "bot"} ${isLast ? "last" : ""}" title="${esc(clock(l.ts))}">${card}</div>`;
}

function lineHTML(l, isLast) {
  if (l.kind === "task") return taskHTML(l, isLast);
  if (l.kind === "grant_request") return grantHTML(l, isLast);
  return speechHTML(l, isLast);
}

function renderMessages() {
  let roots;
  if (view === "tasks") roots = D.myTasks.map((t) => t.line);
  else roots = D.threads.get(view)?.roots || [];
  if (query) roots = roots.filter((l) => (l.body || "").toLowerCase().includes(query) || display(l.writer).toLowerCase().includes(query));

  const errors = S.errors.length ? `<div class="errors">${S.errors.map(esc).join("<br>")}</div>` : "";
  const html = errors + roots.map((l, i) => lineHTML(l, i === roots.length - 1)).join("");
  const empty = !roots.length && !query;
  $("#app").classList.toggle("empty", empty);
  $("#hero").hidden = !empty;
  $("#chips").hidden = !empty || view === "tasks";
  if (empty) renderChips();

  const sig = html + JSON.stringify([...openForms]);
  if (sig === lastRender) return;
  const first = !lastRender;
  const box = $("#scroll");
  const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 120;
  const focused = document.activeElement?.closest?.(".inline-form") ? document.activeElement.value : null;
  $("#messages").innerHTML = html || (query ? `<p class="fineprint">Nothing matches “${esc(query)}”.</p>` : "");
  lastRender = sig;
  const form = $("#messages .inline-form input");
  if (form) {
    if (focused !== null) form.value = focused;
    form.focus();
  }
  if (nearBottom || first) box.scrollTop = box.scrollHeight;
}

function renderChips() {
  const who = view === "all" ? "the room" : display(view);
  const chips = [
    { icon: ICON.wave, text: `Say hi to ${who}`, fill: "Hi! My Grok set up our tin can." },
    { icon: ICON.task, text: `Give ${who} a task`, fill: "", task: true },
  ];
  $("#chips").innerHTML = chips.map((c, i) => `<button class="chip" data-chip="${i}">${c.icon}<span>${esc(c.text)}</span></button>`).join("");
  $("#chips").onclick = (e) => {
    const c = chips[e.target.closest("[data-chip]")?.dataset.chip];
    if (!c) return;
    setTaskMode(!!c.task);
    $("#input").value = c.fill;
    $("#input").focus();
    onInput();
  };
}

function renderChrome() {
  const title = view === "tasks" ? "Tasks" : view === "all" ? `${S.room.room || "Room"} · everyone` : `${display(view)}`;
  $("#title").textContent = title;
  document.title = `${title} · TinCan`;
  const target = view === "tasks" ? "all" : view;
  $("#to-label").textContent = target === "all" ? "Room" : display(target);
  $("#input").placeholder = taskMode ? `Describe the job for ${target === "all" ? "the room" : display(target)}…` : target === "all" ? "Talk to the room…" : `Message ${display(target)}…`;
  const st = $("#status");
  st.className = "pill status " + (S.errors.length ? "err" : S.push ? "live" : "");
  st.innerHTML = `<span class="led"></span>${S.errors.length ? "Room has errors" : S.demo ? "Demo room" : S.live ? `Live · ${esc(S.repo)}` : S.push ? "Publishing" : "Local"}`;
  $("#fineprint").textContent = S.demo
    ? `Demo room in a scratch folder. You are ${display(S.me)}. Switch sides from your name in the sidebar.`
    : S.live
      ? `Signed in as ${S.login}. Each line is a commit to .tincan/out/${S.me}.ndjson, and the push wakes their Grok.`
      : `You write only .tincan/out/${S.me}.ndjson${S.push ? ", and each line is pushed" : ". Lines stay local until you publish"}.`;
}

function render() {
  D = derive(S);
  $("#dock").hidden = !!S.readonly;
  if (view !== "tasks" && !D.threads.has(view)) view = "all";
  renderSidebar();
  renderChrome();
  renderMessages();
  autoAck();
}

// ---------- ack ----------
let acking = false;
async function autoAck() {
  if (acking || document.hidden) return;
  const shown = view === "tasks" ? D.myTasks.map((t) => t.line) : D.threads.get(view)?.roots || [];
  const shownRefs = new Set(shown.map(refOf));
  const upto = {};
  for (const l of D.lines) {
    const inView = shownRefs.has(refOf(l)) || (l.ref && shownRefs.has(l.ref));
    if (inView && D.isUnread(l)) upto[l.writer] = Math.max(upto[l.writer] || 0, l.seq);
  }
  if (!Object.keys(upto).length) return;
  acking = true;
  try {
    await api("/api/ack", { upto });
    await refresh();
  } catch (err) {
    toast(err.message);
  } finally {
    acking = false;
  }
}

// ---------- actions ----------
async function refresh() {
  try {
    S = await api("/api/state");
    $("#gate").hidden = true;
    render();
  } catch (err) {
    if (err.signin || err.signout) return showGate(err);
    $("#status").className = "pill status err";
    $("#status").innerHTML = `<span class="led"></span>${esc(err.message)}`;
  }
}

// Hosted mode: nobody is in the room until GitHub says who they are.
function showGate(err) {
  $("#gate").hidden = false;
  $("#gate-msg").textContent = err.signin ? "Sign in with the GitHub account the host put in the room." : err.message;
  $("#gate-signin").hidden = !err.signin;
  $("#gate-signin").href = `/auth/login?next=${encodeURIComponent(location.pathname + location.search)}`;
  $("#gate-signout").hidden = !err.signout;
}

let pollTimer;
function schedule() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    if (!document.hidden && $("#gate").hidden) await refresh();
    schedule();
  }, S?.poll || 1500);
}

async function post(draft) {
  const res = await api("/api/post", draft);
  await refresh();
  return res;
}

function setTaskMode(on) {
  taskMode = on;
  $("#task-toggle").setAttribute("aria-pressed", String(on));
  if (S) renderChrome();
}

function onInput() {
  const el = $("#input");
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 240) + "px";
  $("#send").disabled = !el.value.trim();
}

$("#composer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const el = $("#input");
  const body = el.value.trim();
  if (!body) return;
  const to = view === "tasks" ? "all" : view;
  $("#send").disabled = true;
  try {
    const res = await post({ kind: taskMode ? "task" : "speech", to, body });
    el.value = "";
    setTaskMode(false);
    onInput();
    if (res.published === "pushed") toast("Pushed. Their Grok will wake.");
    $("#scroll").scrollTop = $("#scroll").scrollHeight;
  } catch (err) {
    toast(err.message);
    onInput();
  }
});
$("#input").addEventListener("input", onInput);
$("#input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("#composer").requestSubmit();
  }
});
$("#task-toggle").addEventListener("click", () => setTaskMode(!taskMode));

$("#messages").addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  if (btn.dataset.copy) {
    const l = D.byRef.get(btn.dataset.copy);
    await navigator.clipboard?.writeText(l?.body || "").catch(() => {});
    return toast("Copied");
  }
  if (btn.dataset.reply) return go(btn.dataset.reply);
  const { act, ref } = btn.dataset;
  if (!act) return;
  if (act === "open-done" || act === "open-fail") {
    openForms.set(ref, act.slice(5));
    return renderMessages();
  }
  if (act === "cancel") {
    openForms.delete(ref);
    return renderMessages();
  }
  btn.disabled = true;
  try {
    await post({ kind: act, ref });
    if (act === "claim") toast("Claimed. It's yours.");
  } catch (err) {
    toast(err.message);
    btn.disabled = false;
  }
});
$("#messages").addEventListener("submit", async (e) => {
  const form = e.target.closest(".inline-form");
  if (!form) return;
  e.preventDefault();
  const body = form.body.value.trim();
  if (!body) return;
  try {
    await post({ kind: form.dataset.form, ref: form.dataset.ref, body });
    openForms.delete(form.dataset.ref);
    renderMessages();
  } catch (err) {
    toast(err.message);
  }
});

// ---------- navigation ----------
function go(key) {
  view = key;
  const url = new URL(location.href);
  url.searchParams.set("t", key);
  history.replaceState(null, "", url);
  lastRender = "";
  if (matchMedia("(max-width: 800px)").matches) $("#app").classList.add("sb-hidden");
  render();
  $("#scroll").scrollTop = $("#scroll").scrollHeight;
  $("#input").focus();
}
$("#threads").addEventListener("click", (e) => {
  const b = e.target.closest("[data-thread]");
  if (b) go(b.dataset.thread);
});
$("#to-room").addEventListener("click", () => go("all"));
$("#to-tasks").addEventListener("click", () => go("tasks"));
$("#search").addEventListener("input", (e) => {
  query = e.target.value.trim().toLowerCase();
  lastRender = "";
  render();
});
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    $("#app").classList.remove("sb-hidden");
    $("#search").focus();
  }
  if (e.key === "Escape") closeMenu();
});
$("#sb-close").addEventListener("click", () => $("#app").classList.add("sb-hidden"));
$("#sb-open").addEventListener("click", () => $("#app").classList.remove("sb-hidden"));
if (matchMedia("(max-width: 800px)").matches) $("#app").classList.add("sb-hidden");

// ---------- menus ----------
function openMenu(anchor, html, onPick) {
  const m = $("#menu");
  m.innerHTML = html;
  m.hidden = false;
  const r = anchor.getBoundingClientRect();
  const below = r.bottom + m.offsetHeight + 8 < innerHeight;
  m.style.left = Math.min(r.left, innerWidth - m.offsetWidth - 8) + "px";
  m.style.top = (below ? r.bottom + 6 : r.top - m.offsetHeight - 6) + "px";
  m.onclick = (e) => {
    const b = e.target.closest("[data-pick]");
    if (b) {
      closeMenu();
      onPick(b.dataset.pick);
    }
  };
  setTimeout(() => document.addEventListener("click", closeMenu, { once: true }));
}
function closeMenu() {
  $("#menu").hidden = true;
}
$("#to-picker").addEventListener("click", (e) => {
  e.stopPropagation();
  const current = view === "tasks" ? "all" : view;
  const ids = ["all", ...Object.keys(S.room.members).filter((id) => id !== S.me)];
  openMenu(
    e.currentTarget,
    `<div class="hint">Send to</div>` + ids.map((id) => `<button data-pick="${esc(id)}">${id === "all" ? `<span class="avatar sm" style="background:var(--surface-3);color:var(--text-2)">${ICON.room}</span>` : avatar(id, "sm")}${esc(display(id))}${id === current ? `<span class="check">${ICON.check}</span>` : ""}</button>`).join(""),
    go,
  );
});
$("#whoami").addEventListener("click", (e) => {
  e.stopPropagation();
  const ids = S.demo ? Object.keys(S.room.members) : [S.me];
  const hint = S.demo ? "Demo: see the room as" : S.live ? `Signed in to GitHub as ${esc(S.login)}` : "Signed in as (restart with --me to change)";
  const signout = S.live ? `<button data-pick="__signout">Sign out</button>` : "";
  openMenu(
    e.currentTarget,
    `<div class="hint">${hint}</div>` + ids.map((id) => `<button data-pick="${esc(id)}">${avatar(id, "sm")}${esc(display(id))}${id === S.me ? `<span class="check">${ICON.check}</span>` : ""}</button>`).join("") + signout,
    (id) => {
      if (id === "__signout") return (location.href = "/auth/logout");
      if (!S.demo || id === S.me) return;
      const url = new URL(location.href);
      url.searchParams.set("me", id);
      url.searchParams.set("t", view === id ? S.me : view); // your DM with them is their DM with you
      location.href = url;
    },
  );
});

// ---------- theme + toast ----------
const THEME_KEY = "tincan-theme";
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
}
try { applyTheme(localStorage.getItem(THEME_KEY)); } catch {}
$("#theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  const next = dark ? "light" : "dark";
  applyTheme(next);
  try { localStorage.setItem(THEME_KEY, next); } catch {}
});

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 2600);
}

document.addEventListener("visibilitychange", () => !document.hidden && refresh());
refresh().then(() => {
  $("#scroll").scrollTop = $("#scroll").scrollHeight;
  $("#input").focus();
  schedule();
});
