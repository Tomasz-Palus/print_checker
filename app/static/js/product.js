// Rozdziały „Produkt", „Rola pliku" i „Strona".
import { $, esc, fmtMm, fold, api, chapter } from "./util.js";
import { S, changed, template, scaleK, productOk, roleSettled, pageSettled } from "./state.js";

// ------------------------------------------------------------------ lista produktów
export async function loadProducts(refresh = false) {
  try {
    const d = await api(refresh ? "/api/products/refresh" : "/api/products", refresh ? { method: "POST" } : undefined);
    S.products = d.products; S.productsStatus = d.status;
  } catch (e) {
    S.productsStatus = { count: S.products.length, source: "?", error: e.message };
  }
  changed();
}

function statusLine() {
  const st = S.productsStatus;
  if (!st) return "Wczytuję listę produktów…";
  const src = { remote: "aktualna ze strony", cache: "kopia z ostatnich 24 h", snapshot: "zapasowa kopia w programie" }[st.source] || "";
  return `${st.count} produktów (${src})` + (st.error ? ` · <span class="say warn">nie udało się pobrać aktualnej listy</span>` : "")
    + ` · <button class="link" type="button" id="pRefresh">odśwież</button>`;
}

// ------------------------------------------------------------------ wyszukiwarka
let visible = [], active = -1;
const search = $("pSearch"), list = $("pList");

function filter(q) {
  const terms = fold(q).split(/\s+/).filter(Boolean);
  if (!terms.length) return S.products.slice(0, 60);
  const out = [];
  for (const p of S.products) {
    const hay = fold(p.name) + " " + fold(p.code);
    let score = 0, ok = true;
    for (const t of terms) {
      const i = hay.indexOf(t);
      if (i < 0) { ok = false; break; }
      score += i === 0 || hay[i - 1] === " " ? 2 : 1;
    }
    if (ok) out.push([score, p]);
  }
  out.sort((a, b) => b[0] - a[0] || a[1].name.length - b[1].name.length);
  return out.slice(0, 80).map((x) => x[1]);
}
function openList() {
  visible = filter(search.value); active = -1;
  list.innerHTML = visible.length
    ? visible.map((p, i) => `<div class="combo-item" data-i="${i}">${esc(p.name)}<small>${esc(p.code)}</small></div>`).join("")
    : `<div class="combo-empty">Nie ma takiego produktu. Możesz podać wymiar ręcznie niżej.</div>`;
  list.hidden = false;
}
search.addEventListener("focus", openList);
search.addEventListener("input", openList);
search.addEventListener("keydown", (e) => {
  const items = list.querySelectorAll(".combo-item");
  if (e.key === "ArrowDown") active = Math.min(items.length - 1, active + 1);
  else if (e.key === "ArrowUp") active = Math.max(0, active - 1);
  else if (e.key === "Enter") { if (visible[active]) choose(visible[active]); return; }
  else if (e.key === "Escape") { list.hidden = true; return; }
  else return;
  e.preventDefault();
  items.forEach((el, i) => el.classList.toggle("active", i === active));
  items[active]?.scrollIntoView({ block: "nearest" });
});
list.addEventListener("mousedown", (e) => {
  const it = e.target.closest(".combo-item");
  if (it) { e.preventDefault(); choose(visible[+it.dataset.i]); }
});
document.addEventListener("mousedown", (e) => { if (!e.target.closest(".combo")) list.hidden = true; });

function choose(p) {                 // produkt na kartę do potwierdzenia
  S.candidate = p; S.picking = false; list.hidden = true; search.value = "";
  changed();
}

// ------------------------------------------------------------------ produkt
export function onNewFile() {
  S.candidate = null; S.product = null; S.custom = null; S.customOpen = false; S.picking = false;
  clearGuidelines();
  const best = S.job.suggestions[0];
  if (best && best.score >= 0.6) S.candidate = best;     // nic nie wybiera się samo — tylko propozycja
}

function clearGuidelines() {
  S.guidelines = null; S.glLoading = false; S.glError = ""; S.tplIndex = 0; S.tplDims = null;
  S.roleOk = false; S.overlayOn = false;
}

// Zmiana czegoś, od czego zależy format, zdejmuje poprawki (są robione pod ten format).
let resetSteps = async () => true;
export function setResetSteps(fn) { resetSteps = fn; }

$("pConfirm").onclick = () => {
  if (!S.candidate) return;
  S.product = S.candidate; S.custom = null;
  loadGuidelines();
};
$("pOther").onclick = () => { S.picking = true; changed(); };
$("pChange").onclick = async () => {
  if (!(await resetSteps("Zmienić produkt?"))) return;
  S.product = null; S.custom = null; S.picking = !S.candidate; clearGuidelines(); changed();
};
$("pCustom").onclick = () => { S.customOpen = true; changed(); setTimeout(() => $("cW").focus(), 0); };
$("cBack").onclick = () => { S.customOpen = false; changed(); };
const customDims = () => {
  const w = parseFloat($("cW").value), h = parseFloat($("cH").value);
  return w > 0 && h > 0 ? { w, h } : null;
};
["cW", "cH"].forEach((id) => $(id).addEventListener("input", () => { $("cConfirm").disabled = !customDims(); }));
$("cConfirm").onclick = () => {
  const d = customDims(); if (!d) return;
  S.custom = d; S.product = null; S.customOpen = false; clearGuidelines(); changed();
};

function candidateLabel(c) {
  const s = S.job?.suggestions.find((x) => x.hash === c.hash);
  if (!s) return { label: "Wybrany produkt", warn: "" };
  const basis = { name: "z nazwy pliku", size: "z wymiaru pliku", content: "z szablonu w pliku" }[s.basis] || "";
  return { label: `Propozycja ${basis} · ${Math.round(s.score * 100)} %`,
           warn: s.scale_hint === "scale" ? s.note : "" };
}

export function renderProduct() {
  if (!pageSettled()) { chapter("ch-product", "locked", ""); return; }   // najpierw plik i strona
  const done = productOk();
  const name = S.product ? S.product.name : S.custom ? `Wydruk spoza listy ${fmtMm(S.custom.w)} × ${fmtMm(S.custom.h)} mm` : "";
  chapter("ch-product", done ? "done" : "todo", done ? esc(name) : "");
  const showCand = !done && !!S.candidate && !S.picking && !S.customOpen;
  const showCustom = !done && S.customOpen;
  $("pCand").hidden = !showCand;
  $("pPick").hidden = done || showCand || showCustom;
  $("pCustomBox").hidden = !showCustom;
  $("pDone").hidden = !done;
  if (showCand) {
    const { label, warn } = candidateLabel(S.candidate);
    $("pCandLabel").textContent = label;
    $("pCandName").textContent = S.candidate.name;
    $("pCandCode").textContent = S.candidate.code;
    $("pCandWarn").hidden = !warn; $("pCandWarn").textContent = warn ? "⚠ " + warn : "";
  }
  if (!$("pPick").hidden) {
    const sugs = S.job.suggestions.filter((s) => !S.candidate || s.hash !== S.candidate.hash).slice(0, 3);
    $("pSugs").innerHTML = sugs.map((s, i) =>
      `<button class="sug" type="button" data-i="${i}">${esc(s.name)}<small>${esc(s.code)} · ${Math.round(s.score * 100)} %</small></button>`).join("");
    $("pSugs").querySelectorAll(".sug").forEach((b) => { b.onclick = () => choose(sugs[+b.dataset.i]); });
    $("pStatus").innerHTML = statusLine();
    const r = $("pRefresh"); if (r) r.onclick = () => loadProducts(true);
  }
  if (done) {
    $("pDoneName").textContent = name;
    $("pDoneCode").textContent = S.product ? S.product.code : "";
  }
}

// ------------------------------------------------------------------ wytyczne i rola
let glSeq = 0;
async function loadGuidelines() {
  const seq = ++glSeq, p = S.product;
  S.glLoading = true; S.glError = ""; S.guidelines = null; S.roleOk = false;
  changed();
  try {
    const d = await api(`/api/guidelines/${encodeURIComponent(p.hash)}`);
    if (seq !== glSeq) return;
    S.guidelines = d; S.tplIndex = guessTemplate(d.templates);
  } catch (e) {
    if (seq !== glSeq) return;
    S.glError = e.message;
  }
  S.glLoading = false;
  changed();
}

const ROLE_HINTS = [
  ["przod", ["przod", "front", "przed"]], ["tyl", ["tyl", "back", "rear"]], ["dach", ["dach", "roof"]],
  ["nogi", ["nogi", "noga", "leg"]], ["wrota", ["wrota", "sciana", "wall", "gate"]], ["owijka", ["owijka", "wrap"]],
  ["lewy", ["lewy", "left"]], ["prawy", ["prawy", "right"]], ["gora", ["gora", "top"]], ["dol", ["dol", "bottom"]],
  ["bok", ["bok", "side"]],
];

// Która rola: najpierw nazwa pliku, a gdy nic nie mówi — wymiar (ramka szablonu w pliku,
// format netto, strona). Wcześniej brana była pierwsza pozycja (Tomasz: „Base-a 1917×536").
function guessTemplate(tpls) {
  if (tpls.length < 2) return 0;
  const f = S.job.file;
  const ft = fold(f.name).replace(/[^a-z0-9]+/g, " ").split(" ").filter(Boolean);
  let best = 0, bestScore = 0;
  tpls.forEach((t, i) => {
    let sc = 0;
    for (const rt of fold(t.role).replace(/[^a-z0-9]+/g, " ").split(" ").filter(Boolean)) {
      if (ft.includes(rt)) sc += rt.length;
      for (const [key, alts] of ROLE_HINTS) if (rt.startsWith(key) && alts.some((a) => ft.some((x) => x.startsWith(a)))) sc += 3;
    }
    if (sc > bestScore) { bestScore = sc; best = i; }
  });
  if (bestScore > 0) return best;
  const p = f.pages[S.page] || f.pages[0];
  const cands = [...(f.template_frames || []), ...(p.trim_mm ? [p.trim_mm] : []), ...(p.width_mm ? [[p.width_mm, p.height_mm]] : [])];
  let bestErr = Infinity;
  tpls.forEach((t, i) => {
    if (t.dims_missing || !t.width_mm) return;
    const m = Math.max(t.width_mm, t.height_mm);
    for (const [w, h] of cands) {
      const e = Math.min(Math.max(Math.abs(w - t.width_mm), Math.abs(h - t.height_mm)) / m,
                         Math.max(Math.abs(w - t.height_mm), Math.abs(h - t.width_mm)) / m + 0.02);
      if (e < bestErr) { bestErr = e; best = i; }
    }
  });
  return bestErr <= 0.05 ? best : 0;
}

$("rSelect").addEventListener("change", (e) => { S.tplIndex = +e.target.value; changed(); });
const tplDims = () => {
  const w = parseFloat($("rW").value), h = parseFloat($("rH").value);
  return w > 0 && h > 0 ? { w, h } : null;
};
["rW", "rH"].forEach((id) => $(id).addEventListener("input", () => { S.tplDims = tplDims(); changed(); }));
$("rConfirm").onclick = async () => {
  if (S.roleOk) {
    if (!(await resetSteps("Zmienić rolę pliku?"))) return;
    S.roleOk = false;
  } else {
    S.roleOk = true;
  }
  changed();
};

export function renderRole() {
  const el = $("ch-role");
  el.hidden = !S.product;
  if (el.hidden) return;
  const t = template(), k = scaleK();
  $("rErr").hidden = !S.glError;
  $("rErr").innerHTML = S.glError ? `${esc(S.glError)}<br>Sprawdź połączenie z internetem i `
    + `<button class="link" type="button" id="rRetry">spróbuj ponownie</button> — albo zmień produkt.` : "";
  if (S.glError) $("rRetry").onclick = loadGuidelines;
  const g = S.guidelines;
  $("rStale").hidden = !(g && g.stale);
  if (g && g.stale) {
    const when = g.fetched_at ? new Date(g.fetched_at * 1000).toLocaleString("pl-PL", { dateStyle: "short", timeStyle: "short" }) : "?";
    $("rStale").innerHTML = `Nie udało się pobrać aktualnych wytycznych — używam kopii z ${esc(when)}.`;
  }
  $("rBody").hidden = !g;
  if (S.glLoading || !g) {
    chapter("ch-role", "open", "");
    $("rSay").innerHTML = S.glLoading ? `<span class="spin"></span>Pobieram wytyczne produktu…` : "";
    return;
  }
  const print = t && !t.dims_missing ? `${fmtMm(t.width_mm * k)} × ${fmtMm(t.height_mm * k)} mm` : "";
  chapter("ch-role", roleSettled() ? "done" : "todo",
    roleSettled() ? `${esc(t.role)}${print ? " — wydruk " + print : ""}` : "");
  $("rSay").textContent = g.templates.length > 1 ? "Który element produktu jest w tym pliku?" : "";
  const opts = g.templates.map((x, i) => {
    const dup = g.templates.filter((y) => y.role === x.role).length > 1;
    return `<option value="${i}">${esc(x.role)}${dup ? ` (str. ${x.page + 1})` : ""} — `
      + `${x.dims_missing ? "wymiar do podania" : `${fmtMm(x.width_mm * k)} × ${fmtMm(x.height_mm * k)} mm`}</option>`;
  }).join("");
  const sel = $("rSelect");
  if (sel.dataset.opts !== opts) { sel.innerHTML = opts; sel.dataset.opts = opts; }
  sel.value = String(S.tplIndex);
  sel.disabled = S.roleOk;
  $("rDims").hidden = !t?.dims_missing;
  $("rW").disabled = $("rH").disabled = S.roleOk;
  $("rInfo").innerHTML = `Skala wytycznych <b>${g.scale || "1:1"}</b>`
    + (k > 1 ? ` — plik jest 10× mniejszy niż wydruk` : "");
  const b = $("rConfirm");
  b.textContent = S.roleOk ? "Zmień rolę" : "Zatwierdź";
  b.classList.toggle("primary", !S.roleOk);
  b.disabled = !S.roleOk && !!t?.dims_missing && !S.tplDims;
  $("rPdf").hidden = !g.hash;
  if (g.hash) $("rPdf").href = `https://noname.tey.pl/file/requirements?type=product&hash=${encodeURIComponent(g.hash)}&lang=en`;
}

// ------------------------------------------------------------------ strona
// Strona idzie PRZED produktem: propozycje produktu i roli liczą się z wymiaru tej strony.
async function setPage(n, confirm) {
  if (S.job.versions.length > 1 && !(await resetSteps("Wybrać inną stronę?"))) return false;
  S.page = n; S.pageOk = !!confirm; S.roleOk = false;
  changed();
  if (confirm) await refreshSuggestions();
  return true;
}
async function refreshSuggestions() {
  if (productOk()) {                               // produkt już jest — zgadujemy tylko rolę
    if (S.guidelines) { S.tplIndex = guessTemplate(S.guidelines.templates); changed(); }
    return;
  }
  try {
    const job = S.job;
    const d = await api(`/api/jobs/${job.job_id}/suggest?page=${S.page}`);
    if (S.job !== job) return;
    job.suggestions = d.suggestions; job.file.template_frames = d.file.template_frames;
    const best = d.suggestions[0];
    S.candidate = best && best.score >= 0.6 ? best : null;
    S.picking = false;
  } catch (_) { /* zostają propozycje ze strony 1 */ }
  changed();
}
$("pgSelect").addEventListener("change", async (e) => {
  if (!(await setPage(+e.target.value, false))) e.target.value = String(S.page);
});
$("pgConfirm").onclick = () => setPage(S.page, !S.pageOk);
export async function wantPage(n) {                        // kliknięcie w miniaturę
  if (n === S.page) return;
  await setPage(n, false);
}

export function renderPage() {
  const f = S.job?.file;
  const el = $("ch-page");
  el.hidden = !f || f.page_count < 2;
  if (el.hidden) return;
  if (!S.analysisFor) { chapter("ch-page", "locked", ""); return; }
  chapter("ch-page", pageSettled() ? "done" : "todo", pageSettled() ? `strona ${S.page + 1} z ${f.page_count}` : "");
  const opts = f.pages.map((p) => `<option value="${p.index}">Strona ${p.index + 1}`
    + `${p.width_mm ? ` — ${fmtMm(p.width_mm)} × ${fmtMm(p.height_mm)} mm` : ""}</option>`).join("");
  const sel = $("pgSelect");
  if (sel.dataset.opts !== opts) { sel.innerHTML = opts; sel.dataset.opts = opts; }
  sel.value = String(S.page);
  sel.disabled = S.pageOk;
  $("pgConfirm").textContent = S.pageOk ? "Wybierz inną stronę" : "Wybierz tę stronę";
  $("pgConfirm").classList.toggle("primary", !S.pageOk);
}
