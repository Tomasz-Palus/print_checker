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

// Zrobiony rozdział zwija się do jednej linii; kliknięcie w nagłówek go rozwija.
export function initChapters(HELP) {
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
