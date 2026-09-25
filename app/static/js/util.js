// Drobne narzędzia wspólne dla wszystkich modułów.
export const $ = (id) => document.getElementById(id);

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const fmtMm = (v) => v == null ? "?" : (Math.round(v * 10) / 10).toString().replace(".", ",");
export const fmtBytes = (b) => b < 1048576 ? `${Math.round(b / 1024)} KB` : `${(b / 1048576).toFixed(1).replace(".", ",")} MB`;
export const fold = (s) => String(s || "").toLowerCase().replace(/ł/g, "l").normalize("NFKD").replace(/[̀-ͯ]/g, "");

export function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  return n === 1 ? one : (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) ? few : many;
}

export async function api(url, opts) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(data.error || `HTTP ${r.status}`); e.status = r.status; throw e; }
  return data;
}

export const post = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" },
                                              body: JSON.stringify(body || {}) });

// Pytanie „na pewno?" w oknie programu. Zwraca obietnicę: true = potwierdzone.
export function ask(title, html, yes = "Tak", no = "Anuluj") {
  return new Promise((resolve) => {
    const m = $("ask");
    $("askT").textContent = title; $("askX").innerHTML = html;
    $("askYes").textContent = yes; $("askNo").textContent = no;
    const done = (v) => { m.hidden = true; document.removeEventListener("keydown", key); resolve(v); };
    const key = (e) => { if (e.key === "Escape") done(false); if (e.key === "Enter") done(true); };
    $("askYes").onclick = () => done(true);
    $("askNo").onclick = () => done(false);
    m.onclick = (e) => { if (e.target === m) done(false); };
    document.addEventListener("keydown", key);
    m.hidden = false; $("askYes").focus();
  });
}

// Rozdział: stan (locked | open | todo | done), podsumowanie w nagłówku, pomoc pod „?".
export function chapter(id, st, summary) {
  const el = $(id);
  if (!el) return;
  if (el.dataset.st !== st) {
    el.dataset.st = st;
    if (st !== "done") el.classList.remove("open");
  }
  const sum = el.querySelector(".ch-sum");
  if (sum && summary !== undefined) { sum.innerHTML = summary; sum.title = sum.textContent; }
  const ico = el.querySelector(".ch-ico");
  if (ico) {
    if (!ico.dataset.n) ico.dataset.n = ico.textContent;
    ico.textContent = st === "done" ? "✓" : st === "todo" ? "!" : ico.dataset.n;
  }
}

// Rozdział zwinięty (zaliczony i niezrozwinięty albo zablokowany)?
export const collapsed = (ch) => ch.dataset.st === "locked" || (ch.dataset.st === "done" && !ch.classList.contains("open"));
// Element naprawdę widać: ma wymiary i nie siedzi w zwiniętym rozdziale (od 0.4.3 zwinięta treść
// nie znika z układu, tylko ma wysokość 0 — sam getClientRects już tego nie mówi).
export function shown(el) {
  if (!el || el.getClientRects().length === 0) return false;
  const b = el.closest(".ch-b");
  return !b || !collapsed(b.closest(".ch"));
}

// Zrobiony rozdział zwija się do jednej linii; kliknięcie w nagłówek go rozwija.
// Animacje (0.4.3, Tomasz 25.09): zwijanie i rozwijanie jest płynne (siatka 0fr ↔ 1fr w CSS), a na
// czas ruchu treść jest przycinana (klasa `anim`) — poza ruchem nie, bo lista produktów wystaje
// poza rozdział.
export function initChapters(HELP) {
  document.querySelectorAll(".ch-b").forEach((b) => {
    const inner = document.createElement("div");
    inner.className = "ch-in";
    while (b.firstChild) inner.appendChild(b.firstChild);
    b.appendChild(inner);
  });
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const state = new WeakMap();
  const mo = new MutationObserver((recs) => {
    for (const r of recs) {
      const ch = r.target, c = collapsed(ch);
      if (state.get(ch) === c) continue;
      state.set(ch, c);
      if (reduce) continue;
      ch.classList.add("anim");
      clearTimeout(ch._animT);
      ch._animT = setTimeout(() => ch.classList.remove("anim"), 420);
    }
  });
  document.querySelectorAll(".ch").forEach((ch) => {
    state.set(ch, collapsed(ch));
    mo.observe(ch, { attributes: true, attributeFilter: ["class", "data-st"] });
  });
  document.querySelectorAll(".ch").forEach((ch) => {
    const q = ch.querySelector(".ch-q"), help = ch.querySelector(".ch-help");
    const key = ch.id.replace("ch-", "");
    if (q && help) {
      q.onclick = (e) => {
        e.stopPropagation();
        if (help.hidden) help.innerHTML = HELP[key] || "";
        help.hidden = !help.hidden;
        q.classList.toggle("on", !help.hidden);
      };
    }
    ch.querySelector(".ch-h")?.addEventListener("click", () => {
      if (ch.dataset.st === "done") ch.classList.toggle("open");
    });
  });
}

// Rozdziały, które właśnie się pojawiły, wjeżdżają PO KOLEI (co 150 ms), a nie wszystkie naraz —
// widać, że program sprawdził je jeden po drugim (Tomasz 25.09).
const seen = new Set();
let lastEnter = 0, queued = 0;
export function revealChapters() {
  const now = performance.now();
  if (now - lastEnter > 1000) queued = 0;          // nowa seria — od zera
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  document.querySelectorAll(".ch").forEach((ch) => {
    const vis = !ch.hidden;
    if (vis && !seen.has(ch)) {
      seen.add(ch);
      if (reduce || !document.body.classList.contains("ready")) return;
      ch.style.animationDelay = `${queued++ * 150}ms`;   // po kolei co 1,5 s pilnuje main.gateChapters
      lastEnter = now;
      ch.classList.remove("enter"); void ch.offsetWidth; ch.classList.add("enter");
      ch.addEventListener("animationend", () => { ch.classList.remove("enter"); ch.style.animationDelay = ""; }, { once: true });
    } else if (!vis) seen.delete(ch);
  });
}
