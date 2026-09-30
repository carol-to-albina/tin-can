// Two Groks, one tin can: a scripted run with real model calls on both sides.
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const PEOPLE = ["albina", "carol"];
const COLORS = { albina: "#7c5cff", carol: "#e5484d" };

let B = null;
let playing = false;
let started = 0;
let clockTimer = 0;
const seenLines = new Set();
const openTraces = new Set();

async function api(path, body) {
  const init = body ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) } : {};
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const name = (id) => (id === "all" ? "everyone" : B?.members?.[id]?.display || id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const money = (n) => `$${Number(n || 0).toFixed(4)}`;
const GROK = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="9.5" cy="11" r="1.3" fill="currentColor"/><circle cx="14.5" cy="11" r="1.3" fill="currentColor"/><path d="M9 15h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';

function richText(s) {
  return esc(s)
    .replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/\n/g, "<br>");
}

function actionText(a) {
  if (a.kind === "error") return `Could not write: ${a.text}`;
  return { speech: `Message → ${name(a.to)}`, task: `Task → ${name(a.to)}'s Grok`, claim: `Took ${name(a.to)}'s task`, done: `Result → ${name(a.to)}`, fail: `Failed → ${name(a.to)}` }[a.kind] || a.kind;
}

function traceHTML(t, key) {
  if (!t) return "";
  const open = openTraces.has(key);
  const detail = open
    ? `<div class="trace-body"><dl>
        <dt>generation</dt><dd class="mono">${esc(t.id)}</dd>
        <dt>model</dt><dd>${esc(t.model)}${t.provider ? ` via ${esc(t.provider)}` : ""}</dd>
        <dt>tokens</dt><dd>${t.tokens_in} in · ${t.tokens_out} out · ${t.reasoning} reasoning</dd>
        <dt>cost</dt><dd>${money(t.cost)}</dd></dl>
        ${t.tool_calls.map((c) => `<div class="call"><span class="mono">${esc(c.name)}</span><pre>${esc(JSON.stringify(c.args, null, 2))}</pre></div>`).join("")}</div>`
    : "";
  return `<div class="trace"><button class="trace-chip" data-trace="${esc(key)}"><span class="dot"></span>${esc(t.via)} · ${t.took}s · ${esc(t.tool_calls.map((c) => c.name).join(" + ") || "no tools")} · ${money(t.cost)}<span class="chev">${open ? "▾" : "▸"}</span></button>${detail}</div>`;
}

function buildPanes() {
  for (const pane of document.querySelectorAll(".pane")) {
    pane.append($("#pane-tpl").content.cloneNode(true));
    const input = $("textarea", pane);
    input.readOnly = true;
    input.placeholder = "Press Play to run the script";
    pane._grow = () => {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 140) + "px";
    };
    $("form", pane).addEventListener("submit", (e) => e.preventDefault());
  }
}

function renderPane(me) {
  const pane = $(`.pane[data-me="${me}"]`);
  const who = B.members[me];
  $(".avatar", pane).textContent = who.display.slice(0, 1);
  $(".avatar", pane).style.background = COLORS[me] || "#888";
  $(".pane-who b", pane).textContent = who.display;
  $(".pane-sub", pane).textContent = `with ${who.display}'s Grok`;
  const chip = $(".pane-mode", pane);
  chip.textContent = "permission given";
  chip.className = "state pane-mode claimed";

  const chat = B.bots.chats[me] || [];
  let html = chat
    .map((m, i) => {
      if (m.from === "human") return `<div class="msg user"><div class="bubble">${esc(m.text)}</div></div>`;
      const acts = (m.actions || []).map((a) => `<span class="act ${a.kind}">${esc(actionText(a))}</span>`).join("");
      const tag = m.wake ? '<span class="woke">woke from the room</span>' : "";
      const files = (m.files || [])
        .map((f) => `<div class="duet-file"><div class="duet-file-head"><b>${esc(f.title)}</b><a href="/d/${encodeURIComponent(f.name)}" target="_blank" rel="noopener">open</a></div><iframe sandbox src="/d/${encodeURIComponent(f.name)}" title="${esc(f.title)}"></iframe></div>`)
        .join("");
      return `<div class="msg bot ${m.error ? "err" : ""}">
        <div class="speaker"><span class="grok-face">${GROK}</span><b>Grok</b>${tag}</div>
        <div class="text">${richText(m.text || "")}</div>${files}${acts ? `<div class="acts">${acts}</div>` : ""}${traceHTML(m.trace, `${me}${i}`)}</div>`;
    })
    .join("");
  if (B.bots.busy[me]) html += `<div class="msg bot"><div class="speaker"><span class="grok-face">${GROK}</span><b>Grok</b></div><div class="thinking">Thinking</div></div>`;
  if (!chat.length && !B.bots.busy[me]) html = `<p class="pane-empty">${esc(who.display)} and ${esc(who.display)}'s Grok. Nobody else is in this chat.</p>`;

  const msgs = $(".pane-msgs", pane);
  const sig = html + [...openTraces].join();
  if (msgs._sig === sig) return;
  const box = $(".pane-scroll", pane);
  const stick = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  msgs.innerHTML = html;
  msgs._sig = sig;
  if (stick || playing) box.scrollTop = box.scrollHeight;
}

function renderWire() {
  const lines = B.lines.slice().sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : a.writer < b.writer ? -1 : 1));
  const list = $("#wire-lines");
  if (!list.querySelector(".knot")) {
    list.innerHTML = `<div class="wire-card knot"><div class="wire-meta"><span class="dot" style="background:${COLORS.albina}"></span><span class="dot" style="background:${COLORS.carol}"></span>Knot tied when they joined</div><div class="wire-body">Albina's and Carol's Groks may take each other's tasks without asking first.</div></div>`;
    seenLines.clear();
  }
  for (const l of lines) {
    const id = `${l.writer}:${l.seq}`;
    if (seenLines.has(id)) continue;
    seenLines.add(id);
    const toRight = PEOPLE.indexOf(l.writer) < PEOPLE.indexOf(l.to === "all" ? PEOPLE.find((p) => p !== l.writer) : l.to);
    const card = document.createElement("div");
    card.className = `wire-card ${toRight ? "ltr" : "rtl"} k-${l.kind}`;
    const body = (l.body || "").split("\n\nHandover: ")[0];
    const handed = (l.body || "").includes("\n\nHandover: ") ? `<div class="wire-file">+ HTML handover</div>` : "";
    card.innerHTML = `<div class="wire-meta"><span class="dot" style="background:${COLORS[l.writer]}"></span>${esc(name(l.writer))}'s Grok <span class="arrow">${toRight ? "→" : "←"}</span> ${esc(name(l.to))}<span class="kind">${esc(l.kind)}</span></div>${body ? `<div class="wire-body">${esc(body)}</div>` : ""}${handed}`;
    list.append(card);
    spark(toRight);
    list.scrollTop = list.scrollHeight;
  }
}

function spark(toRight) {
  const s = $("#spark");
  s.classList.remove("go-ltr", "go-rtl");
  void s.offsetWidth;
  s.classList.add(toRight ? "go-ltr" : "go-rtl");
}

async function refresh() {
  try {
    B = await api("/api/duet");
  } catch (err) {
    $("#caption").textContent = err.message;
    return;
  }
  PEOPLE.forEach(renderPane);
  renderWire();
  $("#spend").textContent = `$${B.bots.spent.toFixed(3)}`;
  $("#spend").title = `${B.bots.calls} OpenRouter calls, ${B.bots.tools} tool calls this session`;
  $("#model").textContent = `${B.bots.model} · ${B.bots.effort}`;
}

function poll() {
  clearTimeout(poll.t);
  poll.t = setTimeout(async () => {
    await refresh();
    poll();
  }, playing ? 300 : 1500);
}

function caption(text) {
  const c = $("#caption");
  c.classList.remove("fresh");
  void c.offsetWidth;
  c.textContent = text;
  c.classList.add("fresh");
}

async function until(test, label, ms = 45000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    await refresh();
    if (test()) return;
    await sleep(250);
  }
  throw new Error(`timed out waiting for ${label}`);
}

async function typeInto(me, text) {
  const pane = $(`.pane[data-me="${me}"]`);
  const input = $("textarea", pane);
  for (let i = 1; i <= text.length; i += 3) {
    input.value = text.slice(0, i);
    pane._grow();
    await sleep(12);
  }
  input.value = text;
  pane._grow();
  await sleep(120);
  input.value = "";
  pane._grow();
}

const botMsgs = (me) => (B.bots.chats[me] || []).filter((m) => m.from === "bot");
const hasLine = (writer, kind) => B.lines.some((l) => l.writer === writer && l.kind === kind);

async function play() {
  if (playing) return;
  playing = true;
  $("#play").disabled = true;
  try {
    const { run, script } = await api("/api/duet/start", {});
    seenLines.clear();
    openTraces.clear();
    $("#wire-lines").innerHTML = "";
    await refresh();
    const base = { calls: B.bots.calls, spent: B.bots.spent, tools: B.bots.tools };
    started = performance.now();
    tick();

    caption("1 · Albina asks her own Grok for something only Carol has. The knot is already tied.");
    await typeInto("albina", script.albina);
    await api("/api/duet/say", { run, me: "albina", text: script.albina });
    await until(() => hasLine("albina", "task"), "Albina's Grok");
    caption("2 · Albina's Grok calls send_task. The line lands in the room and wakes Carol's Grok.");
    await until(() => B.bots.busy.carol || hasLine("carol", "claim"), "Carol's Grok");
    caption("3 · Permission was given up front, so Carol's Grok writes the HTML now and calls finish_task.");
    await until(() => hasLine("carol", "done") || hasLine("carol", "fail"), "Carol's Grok to finish");
    caption("4 · The handover goes back through the room. Albina's Grok wakes.");
    await until(() => botMsgs("albina").some((m) => m.wake), "Albina's Grok to wake");

    const secs = ((performance.now() - started) / 1000).toFixed(1);
    stopClock();
    await refresh();
    const calls = B.bots.calls - base.calls;
    const tools = B.bots.tools - base.tools;
    caption(`5 · Albina has the page. ${secs}s, ${calls} OpenRouter calls, ${tools} tool calls, $${(B.bots.spent - base.spent).toFixed(3)}. Tap any receipt to see the call.`);
  } catch (err) {
    stopClock();
    caption(`Stopped: ${err.message}`);
  } finally {
    playing = false;
    $("#play").disabled = false;
    poll();
  }
}

function tick() {
  cancelAnimationFrame(clockTimer);
  const step = () => {
    $("#clock").textContent = `${((performance.now() - started) / 1000).toFixed(1)}s`;
    clockTimer = requestAnimationFrame(step);
  };
  step();
}
function stopClock() {
  cancelAnimationFrame(clockTimer);
  $("#clock").textContent = `${((performance.now() - started) / 1000).toFixed(1)}s`;
}

$("#play").addEventListener("click", play);
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-trace]");
  if (!t) return;
  openTraces.has(t.dataset.trace) ? openTraces.delete(t.dataset.trace) : openTraces.add(t.dataset.trace);
  PEOPLE.forEach(renderPane);
});

const THEME_KEY = "tincan-theme";
try { const t = localStorage.getItem(THEME_KEY); if (t) document.documentElement.dataset.theme = t; } catch {}
$("#theme").addEventListener("click", () => {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem(THEME_KEY, root.dataset.theme); } catch {}
});

buildPanes();
refresh().then(() => {
  poll();
  if (new URLSearchParams(location.search).has("autoplay")) play();
});
