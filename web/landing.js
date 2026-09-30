// Landing: take a seat (no account), or pick up the one this browser already has.
"use strict";

const $ = (sel) => document.querySelector(sel);
const SEAT = "tincan-seat";
const NAMES = ["Daniel", "Petr", "Ben", "Kate"];

const store = {
  get() { try { return localStorage.getItem(SEAT) || ""; } catch { return ""; } },
  set(v) { try { localStorage.setItem(SEAT, v); } catch {} },
  drop() { try { localStorage.removeItem(SEAT); } catch {} },
};

// The presenter opens /host#<token>. The fragment never reaches a log or a referrer; the page
// trades it once for the same HttpOnly seat cookie guests get.
if (location.pathname === "/host" && location.hash.length > 10) {
  const token = location.hash.slice(1);
  history.replaceState(null, "", "/host");
  fetch("/api/host", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token }) })
    .then((res) => {
      if (!res.ok) throw new Error("that is not the host link");
      store.set(token);
      location.replace("/chat");
    })
    .catch((err) => alert(err.message));
}

async function hello() {
  const seat = store.get();
  const res = await fetch("/api/hello", { headers: seat ? { "X-TinCan-Seat": seat } : {} });
  return res.json();
}

async function join(name) {
  $("#join-err").textContent = "";
  $("#join-btn").disabled = true;
  try {
    const res = await fetch("/api/join", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "could not join");
    store.set(data.seat);
    location.href = "/chat";
  } catch (err) {
    $("#join-err").textContent = err.message;
    $("#join-btn").disabled = false;
  }
}

$("#names").innerHTML = NAMES.map((n) => `<button class="chip" data-name="${n}">${n}</button>`).join("");
$("#names").addEventListener("click", (e) => {
  const b = e.target.closest("[data-name]");
  if (b) join(b.dataset.name);
});
$("#join-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = $("#name").value.trim();
  if (name) join(name);
  else $("#name").focus();
});
$("#forget").addEventListener("click", () => {
  store.drop();
  fetch("/api/leave", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" }).catch(() => {});
  $("#again").hidden = true;
  $("#join").hidden = false;
});

hello()
  .then((h) => {
    $("#url").textContent = h.url.replace(/^https?:\/\//, "").replace(/\/$/, "");
    $("#lead").textContent = `Tap your name and ask ${h.host}'s Grok for something.`;
    $("#meta").textContent = h.people > 1 ? `${h.people} people in the room` : "";
    if (h.me) {
      $("#join").hidden = true;
      $("#again").hidden = false;
    }
  })
  .catch(() => {});

// The film: v2 of the demo video, from demo-video/.
const film = $("#film");
const video = $("#film-video");
function closeFilm() {
  video.pause();
  film.hidden = true;
}
$("#film-btn").addEventListener("click", () => {
  film.hidden = false;
  video.currentTime = 0;
  video.play().catch(() => {});
});
$("#film-close").addEventListener("click", closeFilm);
film.addEventListener("click", (e) => { if (e.target === film) closeFilm(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !film.hidden) closeFilm(); });
