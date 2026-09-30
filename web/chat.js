// Your Grok. Everything you say goes to your own Grok; it passes work to the host's Grok through the room.
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const SEAT = "tincan-seat";
const MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
const PALETTE = ["#7c5cff", "#e5484d", "#12a594", "#f76b15", "#0090ff", "#d6409f", "#8e8c99", "#3dbe7a"];

// The seat itself lives in an HttpOnly cookie. This copy is only a fallback for browsers that drop it.
let seat = "";
try { seat = localStorage.getItem(SEAT) || ""; } catch {}

let S = null;
let lastSig = "";
let shortcuts = [];
let jobTarget = "";
const openTraces = new Set();
const verified = new Map(); // gen id -> result or error

// ---------- api ----------
async function api(path, body) {
  const init = { headers: seat ? { "X-TinCan-Seat": seat } : {} };
  if (body) Object.assign(init, { method: "POST", body: JSON.stringify(body), headers: { ...init.headers, "content-type": "application/json" } });
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (res.status === 403 && /join the room/.test(data.error || "")) {
    try { localStorage.removeItem(SEAT); } catch {}
    location.replace("/");
  }
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

// ---------- helpers ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const member = (id) => S.members.find((m) => m.id === id);
const display = (id) => member(id)?.display || id;
const colorOf = (id) => PALETTE[Math.max(0, S.members.findIndex((m) => m.id === id)) % PALETTE.length];
const avatar = (id, cls = "sm") => `<span class="avatar ${cls}" style="background:${colorOf(id)}">${esc(display(id).slice(0, 1))}</span>`;
const GROK = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="9.5" cy="11" r="1.3" fill="currentColor"/><circle cx="14.5" cy="11" r="1.3" fill="currentColor"/><path d="M9 15h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
const money = (n) => `$${Number(n || 0).toFixed(n < 0.01 ? 4 : 3)}`;

function richText(s) {
  const safe = esc(s).trim();
  const inline = (t) =>
    t
      .replace(/`([^`\n]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
  return safe
    .split(/\n{2,}/)
    .map((p) => {
      const lines = p.split("\n");
      if (lines.every((l) => /^\s*([-*]|\d+[.)])\s+/.test(l))) {
        return `<ul>${lines.map((l) => `<li>${inline(l.replace(/^\s*([-*]|\d+[.)])\s+/, ""))}</li>`).join("")}</ul>`;
      }
      return `<p>${inline(p).replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 3200);
}

// ---------- render ----------
function traceHTML(t, key) {
  if (!t) return "";
  const calls = t.tool_calls.map((c) => c.name).join(", ") || "none";
  const open = openTraces.has(key);
  const v = verified.get(t.id);
  let check = `<button class="btn tiny" data-verify="${esc(t.id)}">Check with OpenRouter</button>`;
  if (v?.checking) check = `<span class="muted">Asking OpenRouter for its record of this call. It lists calls a few seconds after they finish…</span>`;
  else if (v?.error) check = `<span class="bad">${esc(v.error)}</span> <button class="btn tiny" data-verify="${esc(t.id)}">Retry</button>`;
  else if (v) {
    check = `<div class="verified"><b>OpenRouter's record</b><dl>${Object.entries(v)
      .map(([k, val]) => `<dt>${esc(k)}</dt><dd>${esc(typeof val === "number" && k.includes("cost") ? money(val) : val)}</dd>`)
      .join("")}</dl></div>`;
  }
  const detail = open
    ? `<div class="trace-body">
        <dl>
          <dt>generation</dt><dd class="mono">${esc(t.id)}</dd>
          <dt>model</dt><dd>${esc(t.model)}${t.provider ? ` via ${esc(t.provider)}` : ""}${t.route ? ` (route ${esc(t.route)})` : ""}</dd>
          <dt>reasoning</dt><dd>${esc(t.effort)} · ${t.reasoning} tokens</dd>
          <dt>tokens</dt><dd>${t.tokens_in} in · ${t.tokens_out} out</dd>
          <dt>time</dt><dd>${t.took}s${t.queued > 0.2 ? ` after ${t.queued}s in the queue` : ""} · ${esc(t.at)}</dd>
          <dt>cost</dt><dd>${money(t.cost)}${t.payer ? ` · paid by ${esc(display(t.payer))}` : ""}</dd>
          <dt>tools offered</dt><dd>${esc(t.tools_offered.join(", "))}</dd>
        </dl>
        ${t.tool_calls.map((c) => `<div class="call"><span class="mono">${esc(c.name)}</span><pre>${esc(JSON.stringify(c.args, null, 2))}</pre></div>`).join("")}
        ${check}
      </div>`
    : "";
  return `<div class="trace"><button class="trace-chip" data-trace="${esc(key)}" aria-expanded="${open}">
      <span class="dot live"></span>${esc(t.via)} · ${t.took}s · ${t.tool_calls.length} tool call${t.tool_calls.length === 1 ? "" : "s"} (${esc(calls)}) · ${money(t.cost)}
      <span class="chev">${open ? "▾" : "▸"}</span></button>${detail}</div>`;
}

function filesHTML(files) {
  return (files || [])
    .map((f) => `<button class="handover" data-file="${esc(f.name)}" data-base="/h/">
      <span class="handover-icon">&lt;/&gt;</span>
      <span class="handover-text"><b>${esc(f.title)}</b><span>${esc(display(f.by))}'s Grok · ${(f.bytes / 1024).toFixed(1)} KB HTML</span></span>
      <span class="handover-open">Open</span></button>`)
    .join("");
}

function messageHTML(m, i) {
  if (m.from === "human") {
    return `<div class="msg user"><div class="bubble">${esc(m.text)}</div></div>`;
  }
  const key = `m${i}`;
  if (m.task) {
    const waiting = S.pending.includes(m.task);
    const buttons = waiting
      ? `<div class="card-actions"><button class="btn primary" data-accept="${esc(m.task)}">Accept · my Grok does it</button><button class="btn" data-decline="${esc(m.task)}">Decline</button></div>`
      : "";
    return `<div class="msg bot"><div class="speaker"><span class="grok-face">${GROK}</span><b>Your Grok</b></div>
      <div class="card task-card"><div class="card-head">${avatar(m.asker)}<span class="who"><b>${esc(display(m.asker))}'s Grok</b> asks your Grok for this</span>
      <span class="state ${waiting ? "open" : "done"}">${waiting ? "waiting for you" : "answered"}</span></div>
      <div class="card-body text">${richText(m.body)}</div>${buttons}</div></div>`;
  }
  if (m.status) {
    const settled = S.chat.slice(i + 1).some((x) => x.relay);
    return `<div class="status-line ${settled ? "settled" : ""}"><span class="spinner"></span>${esc(m.text)}</div>`;
  }
  const acts = (m.actions || [])
    .map((a) => {
      if (a.kind === "error") return `<span class="act error">${esc(a.text)}</span>`;
      const label = { task: `Task → ${display(a.to)}'s Grok`, speech: `Message → ${display(a.to)}`, claim: `Took ${display(a.to)}'s task`, done: `Result → ${display(a.to)}`, fail: `Failed → ${display(a.to)}` }[a.kind] || a.kind;
      return `<span class="act ${a.kind}">${esc(label)}</span>`;
    })
    .join("");
  const room = m.room ? `<span class="act room">room only · no model call</span>` : "";
  const body = m.body ? `<blockquote class="relay text">${richText(m.body)}</blockquote>` : "";
  return `<div class="msg bot ${m.error ? "err" : ""}">
    <div class="speaker"><span class="grok-face">${GROK}</span><b>Your Grok</b></div>
    <div class="text">${richText(m.text)}</div>${body}
    ${m.files?.length ? `<div class="handovers">${filesHTML(m.files)}</div>` : ""}
    ${acts || room ? `<div class="acts">${acts}${room}</div>` : ""}
    ${traceHTML(m.trace, key)}</div>`;
}

function render() {
  const me = S.me;
  const host = S.host;
  $("#who").textContent = S.isHost ? `${S.name}'s Grok` : "Your Grok";
  $("#sub").textContent = S.isHost ? "You are the host. Jurors' requests land here." : `You are ${S.name}. ${S.hostName}'s Grok is in the room.`;
  document.title = `${S.isHost ? S.name + "'s" : "Your"} Grok · TinCan`;
  const credit = $("#credit");
  credit.hidden = !S.credit;
  if (S.credit) {
    credit.textContent = `${money(S.credit.left)} left`;
    credit.title = `Credit for model work you ask for (of ${money(S.credit.total)})`;
    credit.classList.toggle("low", S.credit.left < 0.03);
  }
  $("#people").textContent = S.members.length;
  $("#input").placeholder = S.isHost ? "Talk to your Grok, or tell it to ask someone's Grok for something" : `Ask ${S.hostName}'s Grok anything`;
  $("#route").textContent = S.isHost ? "Your Grok thinks with the model" : `Goes to ${S.hostName}'s Grok`;

  // one-tap asks
  const busyHost = member(host)?.busy;
  $("#asks").classList.toggle("grid", !S.chat.length);
  const asks = [...S.asks].sort((a, b) => (b.id === S.pick) - (a.id === S.pick));
  $("#asks").innerHTML = S.isHost
    ? ""
    : asks
        .map((a) => a.id === S.pick
          ? `<button class="ask pick" data-ask="${esc(a.id)}"><span class="pick-tag">Picked for you</span>${esc(a.label)}</button>`
          : `<button class="ask" data-ask="${esc(a.id)}">${esc(a.label)}</button>`)
        .join("");

  // host: hand a guest's Grok a job
  const guests = S.members.filter((m) => !m.host);
  $("#jobs").hidden = !S.isHost;
  if (S.isHost) {
    if (!guests.some((g) => g.id === jobTarget)) jobTarget = guests[guests.length - 1]?.id || "";
    $("#jobs").innerHTML = guests.length
      ? `<span class="jobs-label">Hand a job to</span>
         <select id="job-to" aria-label="Who gets the job">${guests.map((g) => `<option value="${esc(g.id)}" ${g.id === jobTarget ? "selected" : ""}>${esc(g.display)}</option>`).join("")}</select>
         ${S.jobs.map((j) => `<button class="ask" data-job="${esc(j.id)}">${esc(j.label)}</button>`).join("")}`
      : `<span class="jobs-label">When someone joins, you can hand their Grok a job from here.</span>`;
  }

  // messages
  let html = S.chat.map(messageHTML).join("");
  if (S.busy) html += `<div class="msg bot"><div class="speaker"><span class="grok-face">${GROK}</span><b>Your Grok</b></div><div class="thinking">Thinking</div></div>`;
  if (!S.chat.length) html = emptyHTML();
  const sig = html + [...openTraces].join() + [...verified.keys()].join();
  if (sig !== lastSig) {
    const box = $("#scroll");
    const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 160;
    $("#messages").innerHTML = html;
    lastSig = sig;
    if (stick) box.scrollTop = box.scrollHeight;
  }

  renderLive();

  // drawer
  $("#members").innerHTML = S.members
    .map((m) => `<div class="person">${avatar(m.id)}<span class="person-name">${esc(m.display)}${m.id === me ? " (you)" : ""}</span>
      <span class="person-state ${m.busy ? "busy" : ""}">${m.busy ? "working…" : m.host ? "Grok acts on its own" : m.autonomy === "auto" ? "Grok acts on its own" : "Grok asks first"}</span></div>`)
    .join("");
  $("#auto-row").hidden = S.isHost;
  $("#auto").checked = S.autonomy === "auto";
  $("#files").innerHTML = S.files.length ? filesHTML(S.files.slice().reverse()) : '<p class="muted">None yet.</p>';
  $("#model").textContent = `${S.model.name} · reasoning ${S.model.effort}. ${S.model.calls} OpenRouter calls and ${S.model.tools} tool calls so far, ${money(S.model.spent)} spent of the demo's ${money(S.model.budget)}.`;
  $("#log").innerHTML = S.lines
    .slice(-8)
    .map((l) => `<div class="log-line"><span class="dot" style="background:${colorOf(l.writer)}"></span><span>${esc(display(l.writer))} → ${esc(l.to === "all" ? "all" : display(l.to))}</span><span class="kind">${esc(l.kind)}</span></div>`)
    .join("") || '<p class="muted">Empty so far.</p>';
  $("#send").disabled = !$("#input").value.trim();
  void busyHost;
}

function emptyHTML() {
  if (S.isHost) {
    return `<div class="hello">${window.tincanLogo()}<h2>Hi ${esc(S.name)}.</h2><p>Jurors' Groks will ask yours for things, and it answers on its own. You'll see each request here as it happens.</p>
      <p>To give someone's Grok a job, pick them and a job below, or type something like "ask Petr's Grok to score the pitch".</p></div>`;
  }
  const pick = S.asks.find((a) => a.id === S.pick);
  return `<div class="hello">${window.tincanLogo()}<h2>Hi ${esc(S.name)}. This is your Grok.</h2>
    <p>${pick ? `Start with the question picked for you, "${esc(pick.label)}", or tap any other, or type your own.` : "Tap a question below, or type your own."} Your Grok passes it to ${esc(S.hostName)}'s Grok along the string, and you can watch the answer come back.</p>
    <p class="muted">If ${esc(S.hostName)} hands your Grok a job, it shows up here and waits for your yes.</p></div>`;
}

// ---------- live cards: work on the string ----------
// One card per task still in flight. Cards are built once and then updated in place,
// so the dot on the string keeps moving between polls instead of restarting.
const cards = new Map(); // ref -> { el, base, at }

function stageOf(p) {
  if (p.waiting) return "asked";
  if (p.writing) return "writing";
  if (p.started) return "thinking";
  return "sent";
}

function renderLive() {
  const live = $("#live");
  const box = $("#scroll");
  const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 200;
  const seen = new Set();
  for (const p of S.progress || []) {
    seen.add(p.ref);
    let card = cards.get(p.ref);
    if (!card) {
      const el = document.createElement("div");
      el.className = "tc-card";
      el.innerHTML = `<div class="tc-top"><b></b><span class="tc-timer">0.0s</span></div>
        <div class="tc-art">${window.tincanLogo({ dots: true })}</div>
        <div class="tc-names"><span class="tc-left"></span><span class="tc-right"></span></div>
        <ol class="tc-steps"><li></li><li></li><li></li><li></li></ol>
        <p class="tc-hint">Waiting for xAI's first token. In our tests that took 3 to 15 seconds.</p>
        <div class="tc-partial text"></div><div class="tc-bytes"></div>`;
      live.append(el);
      card = { el };
      cards.set(p.ref, card);
    }
    card.base = p.elapsed;
    card.at = performance.now();
    const el = card.el;
    const stage = stageOf(p);
    el.dataset.stage = stage;
    const worker = p.mine ? `${p.toName}'s Grok` : "Your Grok";
    const asker = p.mine ? "Your Grok" : `${p.fromName}'s Grok`;
    $(".tc-top b", el).textContent = p.mine ? `${p.job}` : `${p.fromName} asked: ${p.job}`;
    $(".tc-left", el).textContent = asker;
    $(".tc-right", el).textContent = worker;
    const steps = [
      [`${asker} put it in the can`, "done"],
      p.waiting
        ? [`Waiting for ${p.mine ? p.toName : "you"} to tap Accept`, "now"]
        : [`The string woke ${p.mine ? `${p.toName}'s Grok` : "your Grok"}`, p.started ? "done" : "now"],
      [`${worker} is thinking${p.queued ? " (waiting for a free model slot)" : " with x-ai/grok-4.7"}`, p.writing ? "done" : p.started ? "now" : ""],
      [`${worker} is writing${p.tools.includes("finish_task") ? " the answer" : ""}`, p.writing ? "now" : ""],
    ];
    el.querySelectorAll(".tc-steps li").forEach((li, i) => {
      li.textContent = steps[i][0];
      li.className = steps[i][1];
    });
    const partial = $(".tc-partial", el);
    if (partial.textContent !== p.partial) partial.textContent = p.partial;
    $(".tc-bytes", el).textContent = p.bytes ? `handover.html · ${(p.bytes / 1024).toFixed(1)} KB written` : "";
  }
  for (const [ref, card] of cards) {
    if (!seen.has(ref)) {
      card.el.remove();
      cards.delete(ref);
    }
  }
  if (stick && cards.size) box.scrollTop = box.scrollHeight;
}

setInterval(() => {
  for (const card of cards.values()) {
    const t = card.base + (performance.now() - card.at) / 1000;
    $(".tc-timer", card.el).textContent = `${t.toFixed(1)}s`;
  }
}, 100);

// ---------- loop ----------
async function refresh() {
  try {
    S = await api("/api/live");
    render();
  } catch (err) {
    toast(err.message);
  }
}
function poll() {
  clearTimeout(poll.t);
  poll.t = setTimeout(async () => {
    if (!document.hidden) await refresh();
    poll();
  }, S?.progress?.length ? 600 : 1300);
}

// ---------- actions ----------
async function say(text) {
  if (!text.trim()) return;
  try {
    await api("/api/say", { text });
    $("#input").value = "";
    grow();
    await refresh();
    $("#scroll").scrollTop = $("#scroll").scrollHeight;
  } catch (err) {
    toast(err.message);
  }
}

async function accept(ref) {
  try {
    await api("/api/accept", { ref });
    toast("Your Grok is on it");
    await refresh();
  } catch (err) {
    toast(err.message);
  }
}

async function decline(ref) {
  try {
    await api("/api/decline", { ref });
    await refresh();
  } catch (err) {
    toast(err.message);
  }
}

async function delegate(jobId) {
  const job = S.jobs.find((j) => j.id === jobId);
  const to = $("#job-to")?.value || jobTarget;
  if (!job || !to) return;
  try {
    await api("/api/delegate", { to, job: job.job });
    toast(`Sent to ${display(to)}'s Grok`);
    await refresh();
  } catch (err) {
    toast(err.message);
  }
}

function openFile(name) {
  const f = S.files.find((x) => x.name === name) || { name, title: "Handover", by: S.host };
  $("#viewer-title").textContent = f.title;
  $("#viewer-meta").textContent = `${display(f.by)}'s Grok${f.for ? ` for ${display(f.for)}` : ""}`;
  $("#viewer-frame").src = `/h/${encodeURIComponent(f.name)}`;
  $("#viewer-open").href = `/h/${encodeURIComponent(f.name)}`;
  $("#viewer").hidden = false;
}

async function verify(id) {
  verified.set(id, { checking: true });
  render();
  // OpenRouter lists a generation a little after it finishes, so wait and ask again a few times.
  for (let attempt = 0; attempt < 30; attempt++) {
    try {
      verified.set(id, await api(`/api/verify?id=${encodeURIComponent(id)}`));
      break;
    } catch (err) {
      const early = /not indexed/.test(err.message) && attempt < 29;
      verified.set(id, early ? { checking: true } : { error: err.message });
      lastSig = "";
      render();
      if (!early) break;
      await new Promise((r) => setTimeout(r, 4000));
    }
  }
  lastSig = "";
  render();
}

const grow = () => {
  const el = $("#input");
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 200) + "px";
  $("#send").disabled = !el.value.trim();
};

$("#input").addEventListener("input", grow);
$("#input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing && !(e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    $("#composer").requestSubmit();
  }
});
$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  say($("#input").value);
});
$("#asks").addEventListener("click", (e) => {
  const b = e.target.closest("[data-ask]");
  if (b) say(S.asks.find((a) => a.id === b.dataset.ask).job);
});
$("#jobs").addEventListener("click", (e) => {
  const b = e.target.closest("[data-job]");
  if (b) delegate(b.dataset.job);
});
$("#jobs").addEventListener("change", (e) => {
  if (e.target.id === "job-to") jobTarget = e.target.value;
});
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-trace],[data-verify],[data-accept],[data-decline],[data-file]");
  if (!t) return;
  if (t.dataset.trace) {
    openTraces.has(t.dataset.trace) ? openTraces.delete(t.dataset.trace) : openTraces.add(t.dataset.trace);
    lastSig = "";
    render();
  } else if (t.dataset.verify) verify(t.dataset.verify);
  else if (t.dataset.accept) accept(t.dataset.accept);
  else if (t.dataset.decline) decline(t.dataset.decline);
  else if (t.dataset.file) openFile(t.dataset.file);
});
$("#auto").addEventListener("change", async (e) => {
  try {
    await api("/api/autonomy", { mode: e.target.checked ? "auto" : "ask" });
    toast(e.target.checked ? "Your Grok will take jobs without asking" : "Your Grok will ask you first");
    refresh();
  } catch (err) {
    toast(err.message);
  }
});

// ---------- drawer, viewer, sheet ----------
const toggleRoom = (force) => $("#cv").classList.toggle("room-open", force);
$("#room-btn").addEventListener("click", () => toggleRoom());
$("#drawer-close").addEventListener("click", () => toggleRoom(false));
$("#viewer-close").addEventListener("click", () => closeOverlays());
$("#sheet-close").addEventListener("click", () => closeOverlays());
for (const id of ["#viewer", "#sheet", "#palette"]) {
  $(id).addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeOverlays();
  });
}
function closeOverlays() {
  $("#viewer").hidden = true;
  $("#viewer-frame").src = "about:blank";
  $("#sheet").hidden = true;
  $("#palette").hidden = true;
}
function sheet(title, html) {
  $("#sheet-title").textContent = title;
  $("#sheet-body").innerHTML = html;
  $("#sheet").hidden = false;
}
const keyLabel = (k) => (k === "Mod" ? (MAC ? "⌘" : "Ctrl") : k);
function showShortcuts() {
  sheet("Shortcuts", `<div class="shortcuts">${shortcuts.map((s) => `<div class="sc-row"><span>${s.keys.map((k) => `<kbd>${esc(keyLabel(k))}</kbd>`).join("")}</span><span>${esc(s.does)}</span></div>`).join("")}</div>`);
}
function showQR() {
  sheet("Join from a phone", `<div class="qr-sheet"><img src="/qr.svg" alt="QR code for this room" width="260" height="260"><p class="muted">${esc(location.host)}</p></div>`);
}

// ---------- command menu ----------
let palItems = [];
let palIndex = 0;

function commands() {
  const list = [];
  if (!S) return list;
  if (!S.isHost) for (const a of S.asks) list.push({ label: `Ask ${S.hostName}'s Grok: ${a.label}`, run: () => say(a.job), group: "Ask" });
  if (S.isHost) {
    for (const g of S.members.filter((m) => !m.host)) for (const j of S.jobs) list.push({ label: `${g.display}'s Grok: ${j.label}`, run: () => { jobTarget = g.id; render(); delegate(j.id); }, group: "Hand a job" });
  }
  for (const ref of S.pending) list.push({ label: "Accept the job your Grok is holding", keys: ["Mod", "Enter"], run: () => accept(ref), group: "Jobs" });
  if (!S.isHost) {
    list.push(S.autonomy === "auto"
      ? { label: "Ask me before taking jobs", run: () => { $("#auto").checked = false; $("#auto").dispatchEvent(new Event("change")); }, group: "Settings" }
      : { label: "Let my Grok take jobs without asking", run: () => { $("#auto").checked = true; $("#auto").dispatchEvent(new Event("change")); }, group: "Settings" });
  }
  const last = S.files[S.files.length - 1];
  if (last) list.push({ label: `Open the latest handover: ${last.title}`, run: () => openFile(last.name), group: "View" });
  list.push({ label: "Show the room", keys: ["Mod", "J"], run: () => toggleRoom(true), group: "View" });
  list.push({ label: "Show the QR code", run: showQR, group: "View" });
  list.push({ label: "Keyboard shortcuts", run: showShortcuts, group: "View" });
  list.push({ label: "Play the film (30 s)", run: () => window.open("/media/tincan-film.mp4", "_blank", "noopener"), group: "View" });
  list.push({ label: "Watch the scripted run", run: () => window.open("/duet", "_blank", "noopener"), group: "View" });
  list.push({ label: "Open the room log", run: () => window.open("/log", "_blank", "noopener"), group: "View" });
  list.push({ label: "Switch theme", run: toggleTheme, group: "Settings" });
  if (S.isHost) list.push({ label: "Reset the room (everyone rejoins)", run: resetRoom, group: "Host" });
  list.push({ label: "Leave this seat", run: leave, group: "Settings" });
  return list;
}

function openPalette() {
  $("#palette").hidden = false;
  $("#pal-input").value = "";
  palIndex = 0;
  drawPalette();
  $("#pal-input").focus();
}

function drawPalette() {
  const q = $("#pal-input").value.trim().toLowerCase();
  palItems = commands().filter((c) => !q || c.label.toLowerCase().includes(q));
  if (q && !S.isHost) palItems.push({ label: `Ask ${S.hostName}'s Grok: "${$("#pal-input").value.trim()}"`, run: () => say($("#pal-input").value.trim()), group: "Ask" });
  if (q && S.isHost) palItems.push({ label: `Tell your Grok: "${$("#pal-input").value.trim()}"`, run: () => say($("#pal-input").value.trim()), group: "Ask" });
  palIndex = Math.min(palIndex, Math.max(0, palItems.length - 1));
  let group = "";
  $("#pal-list").innerHTML = palItems
    .map((c, i) => {
      const head = c.group !== group ? `<div class="pal-group">${esc((group = c.group))}</div>` : "";
      const keys = c.keys ? `<span class="pal-keys">${c.keys.map((k) => `<kbd>${esc(keyLabel(k))}</kbd>`).join("")}</span>` : "";
      return `${head}<div class="pal-item ${i === palIndex ? "on" : ""}" role="option" data-i="${i}">${esc(c.label)}${keys}</div>`;
    })
    .join("") || '<p class="muted pal-empty">Nothing matches.</p>';
  $(`.pal-item.on`)?.scrollIntoView({ block: "nearest" });
}

function runPalette(i) {
  const c = palItems[i];
  if (!c) return;
  closeOverlays();
  c.run();
}

$("#pal-input").addEventListener("input", () => { palIndex = 0; drawPalette(); });
$("#pal-input").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { e.preventDefault(); palIndex = Math.min(palIndex + 1, palItems.length - 1); drawPalette(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); palIndex = Math.max(palIndex - 1, 0); drawPalette(); }
  else if (e.key === "Enter") { e.preventDefault(); runPalette(palIndex); }
});
$("#pal-list").addEventListener("click", (e) => {
  const it = e.target.closest("[data-i]");
  if (it) runPalette(Number(it.dataset.i));
});
$("#pal-list").addEventListener("mousemove", (e) => {
  const it = e.target.closest("[data-i]");
  if (it && Number(it.dataset.i) !== palIndex) { palIndex = Number(it.dataset.i); drawPalette(); }
});
$("#k-btn").addEventListener("click", openPalette);
$("#k-mod").textContent = MAC ? "⌘" : "Ctrl";

document.addEventListener("keydown", (e) => {
  const mod = e.metaKey || e.ctrlKey;
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "");
  if (mod && e.key.toLowerCase() === "k") {
    e.preventDefault();
    $("#palette").hidden ? openPalette() : closeOverlays();
  } else if (mod && e.key.toLowerCase() === "j") {
    e.preventDefault();
    toggleRoom();
  } else if (mod && e.key === "Enter" && S?.pending.length) {
    e.preventDefault();
    accept(S.pending[0]);
  } else if (e.key === "Escape") {
    closeOverlays();
  } else if (e.key === "/" && !typing && $("#palette").hidden) {
    e.preventDefault();
    $("#input").focus();
  }
});

// ---------- misc ----------
function toggleTheme() {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("tincan-theme", root.dataset.theme); } catch {}
}
try { const t = localStorage.getItem("tincan-theme"); if (t) document.documentElement.dataset.theme = t; } catch {}

async function resetRoom() {
  if (!confirm("Reset the room? Everyone's chat and seat is cleared.")) return;
  try {
    await api("/api/reset", {});
    toast("Room reset");
    refresh();
  } catch (err) {
    toast(err.message);
  }
}

async function leave() {
  try { localStorage.removeItem(SEAT); } catch {}
  await api("/api/leave", {}).catch(() => {});
  location.href = "/";
}

fetch("/shortcuts.json").then((r) => r.json()).then((s) => (shortcuts = s)).catch(() => {});
if (matchMedia("(min-width: 1100px)").matches) toggleRoom(true);
refresh().then(() => {
  $("#scroll").scrollTop = $("#scroll").scrollHeight;
  poll();
});
document.addEventListener("visibilitychange", () => !document.hidden && refresh());
