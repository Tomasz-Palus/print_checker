// Rozdział „Wymiar wydruku". Porównujemy wymiar pliku z wytycznymi; „Dopasuj wymiar" buduje
// nową stronę w docelowym formacie (obraz JPG/TIFF — nowy obraz, steps._raster_resize):
// projekt jako obiekt formy (wektor zostaje wektorem), w skali
// i położeniu z suwaków, margines pusty albo wypełniony tłem z krawędzi / odbiciem lustrzanym.
// Póki rozdział jest otwarty, podgląd pokazuje FORMAT (zielona ramka), a projekt skaluje się
// i przesuwa pod nim — to, co poza ramką, jest przyciemnione (zostanie odcięte).
import { $, fmtMm, chapter } from "./util.js";
import { S, changed, pageMm, targetMm, scaleK, hasStep, beforeStep, trimSettled, sizeMatches, isPdf } from "./state.js";
import { applyStep, undoStep, stepControls, rotateFile } from "./steps.js";

// Skala projektu w dwóch poziomach (ustalenie Tomasza): PRZESKALOWANIE PLIKU (÷10 … bez zmian … ×10,
// rzadko ruszane, schowane) × WIELKOŚĆ w procentach. Do 0.5.4 pisało się to „Skala projektu 1:1” —
// przy wytycznych 1:10 laik czytał to jako „drukuję w skali 1:1” (Tomasz 28.09).
const RATIOS = [1/50, 1/40, 1/30, 1/25, 1/20, 1/16, 1/12, 1/10, 1/8, 1/6, 1/5, 1/4, 1/3, 1/2,
                1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 30, 40, 50];
const R11 = 14;
const ratioLabel = (m) => Math.abs(m - 1) < 1e-9 ? "bez zmian" : m > 1 ? `×${Math.round(m)}` : `÷${Math.round(1 / m)}`;
const EDGE_TRIM_PX = 3, EDGE_FILL_PPI = 120;     // jak w steps.py

const fileMm = () => pageMm(beforeStep("resize"));

function sz() {
  const f = fileMm(), t = targetMm();
  const key = f && t ? `${S.job.job_id}|${S.page}|${f.w}x${f.h}|${t.w}x${t.h}` : "";
  if (!S.sz || S.sz.key !== key)            // nowy format — start ZAWSZE od 100 % (plik w swoim rozmiarze)
    S.sz = { key, ratio: R11, pct: 100, dx: 0, dy: 0, edge: false, mode: "stretch", hintShown: false };
  return S.sz;
}
const scale = () => RATIOS[sz().ratio] * sz().pct / 100;       // mnożnik względem pliku
const touched = () => Math.abs(scale() - 1) > 1e-4 || sz().dx || sz().dy || sz().edge;

// Gdzie na formacie ląduje projekt — ta sama arytmetyka co steps.place_rect. Przesunięcie
// dx/dy (mm pliku) liczone od środka; zakres: aż krawędź projektu dotknie PRZECIWNEJ krawędzi
// formatu (Tomasz 24.09 — wcześniej ruch był ograniczony do wolnego miejsca i przy projekcie
// prawie tej szerokości co format suwak „zacinał się", a przy większym jeździł odwrotnie).
const span = (pos, size, total) => {       // [przycięte, puste] w jednej osi
  const vis = Math.max(0, Math.min(pos + size, total) - Math.max(pos, 0));
  return [size - vis, total - vis];
};
export function cover() {
  const f = fileMm(), t = targetMm();
  if (!f || !t) return null;
  const z = scale(), pw = f.w * z, ph = f.h * z, s = sz();
  const rx = (t.w + pw) / 2, ry = (t.h + ph) / 2;
  s.dx = Math.max(-rx, Math.min(rx, s.dx)); s.dy = Math.max(-ry, Math.min(ry, s.dy));
  const left = (t.w - pw) / 2 + s.dx, top = (t.h - ph) / 2 + s.dy;
  const [cx, gx] = span(left, pw, t.w), [cy, gy] = span(top, ph, t.h);
  return { f, t, z, pw, ph, left, top, rx, ry,
           coverZ: Math.max(t.w / f.w, t.h / f.h), containZ: Math.min(t.w / f.w, t.h / f.h),
           cut: [cx, cy], gap: [gx, gy] };
}

// Rozdział jest „w edycji": podgląd pokazuje format i projekt pod nim.
export function editing() {
  return !!S.job && trimSettled() && !hasStep("resize") && !S.settle.resize
         && (!sizeMatches() || S.sizeEdit) && !!cover();
}

export function sizeScene() {
  if (!editing()) return null;
  const c = cover(), s = sz(), k = scaleK();
  const gaps = c.gap[0] > 0.15 || c.gap[1] > 0.15;
  return {
    frame: { w: c.t.w, h: c.t.h },
    rect: { x: c.left, y: c.top, w: c.pw, h: c.ph },
    label: `format z wytycznych ${fmtMm(c.t.w * k)} × ${fmtMm(c.t.h * k)} mm`,
    clip: false,              // zawsze widać też to, co zostanie odcięte (przyciemnione)
    fill: s.edge && gaps ? { mode: s.mode, trimMm: EDGE_TRIM_PX / EDGE_FILL_PPI * 25.4 / k * c.z } : null,
  };
}

function setScale(z) {                      // skala górnego suwaka tak, żeby procent był blisko 100
  S.cmp = null;
  let best = R11, bd = Infinity;
  RATIOS.forEach((r, i) => { const d = Math.abs(Math.log(r / z)); if (d < bd) { bd = d; best = i; } });
  const s = sz();
  s.ratio = best; s.pct = Math.min(1000, Math.max(5, z / RATIOS[best] * 100));
  changed();
}

// ------------------------------------------------------------------ zdarzenia
// ruszenie czegokolwiek w rozdziale wraca z suwaka porównania do podglądu formatu
const on = (id, ev, fn) => $(id).addEventListener(ev, () => { S.cmp = null; fn(); });
on("szRange", "input", () => { sz().pct = +$("szRange").value; changed(); });
on("szPct", "input", () => { const v = parseFloat($("szPct").value); if (v >= 5 && v <= 1000) { sz().pct = v; changed(); } });
on("szRatio", "input", () => { sz().ratio = +$("szRatio").value; changed(); });
// Suwak = ±1000 promili zakresu. Przyciąganie (magnes) do środka i do położeń, w których
// krawędź projektu równa się z krawędzią formatu — tam się najczęściej celuje.
function slide(axis) {
  const c = cover();
  if (!c) return;
  const R = axis === "x" ? c.rx : c.ry, T = axis === "x" ? c.t.w : c.t.h, P = axis === "x" ? c.pw : c.ph;
  let d = +$(axis === "x" ? "szX" : "szY").value / 1000 * R;
  for (const m of [0, (T - P) / 2, (P - T) / 2]) if (Math.abs(d - m) < R * 0.015) { d = m; break; }
  sz()[axis === "x" ? "dx" : "dy"] = d;
  changed();
}
on("szX", "input", () => slide("x"));
on("szY", "input", () => slide("y"));
// Własna wartość w mm (Tomasz 28.09): mm NA WYDRUKU od środka, plus = w prawo / w dół. Poza zakresem
// (krawędź projektu dalej niż przeciwna krawędź formatu) — przycinamy do zakresu, jak suwak.
function typed(axis) {
  const v = parseFloat($(axis === "x" ? "szXmm" : "szYmm").value.replace(",", ".").replace(/\s/g, ""));
  if (!Number.isFinite(v)) return;
  sz()[axis === "x" ? "dx" : "dy"] = v / scaleK();
  changed();
}
on("szXmm", "input", () => typed("x"));
on("szYmm", "input", () => typed("y"));
for (const id of ["szXmm", "szYmm"]) {
  $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") e.target.blur(); });
  $(id).addEventListener("blur", () => changed());          // po wyjściu z pola — wartość po przycięciu do zakresu
}
on("szX", "dblclick", () => { sz().dx = 0; changed(); });
on("szY", "dblclick", () => { sz().dy = 0; changed(); });
// marginesy: puste / tło z krawędzi / odbicie lustrzane — przyciski zamiast pola i listy (Tomasz 24.09)
document.querySelectorAll("#szFillSeg button").forEach((b) => b.addEventListener("click", () => {
  S.cmp = null;
  const s = sz(), v = b.dataset.v;
  s.edge = v !== "none"; if (s.edge) s.mode = v;
  changed();
}));
$("szOrig").onclick = () => setScale(1);
$("szFill").onclick = () => { const c = cover(); if (c) setScale(c.coverZ); };
$("szWhole").onclick = () => { const c = cover(); if (c) setScale(c.containZ); };
const setRatio = (m) => { S.cmp = null; const s = sz(); s.ratio = RATIOS.indexOf(m); s.pct = 100; changed(); };
$("szD10").onclick = () => setRatio(1 / 10);
$("szR11").onclick = () => setRatio(1);
$("szX10").onclick = () => setRatio(10);
$("szEditBtn").onclick = () => { S.sizeEdit = true; changed(); };
$("szUndo").onclick = () => undoStep("resize");
$("szRot").addEventListener("click", (e) => {                 // „obróć” z podpowiedzi o pliku bokiem
  const b = e.target.closest("button[data-deg]");
  if (b) rotateFile(+b.dataset.deg);
});
$("szDo").onclick = () => {
  if (!S.job) return;
  if (sizeMatches() && !touched()) { S.settle.resize = "ok"; S.sizeEdit = false; changed(); return; }
  const t = targetMm(), s = sz();
  applyStep("resize", { w_mm: t.w, h_mm: t.h, scale: scale(), dx_mm: s.dx, dy_mm: s.dy,
                        fill_edges: s.edge, fill_mode: s.mode, k: scaleK() });
};

// ------------------------------------------------------------------ rysowanie
const setVal = (id, v) => { const el = $(id); if (document.activeElement !== el) el.value = v; };

export function renderSize() {
  const el = $("ch-size");
  el.hidden = !trimSettled();
  if (el.hidden) return;
  const f = fileMm(), t = targetMm(), k = scaleK(), done = hasStep("resize"), ok = S.settle.resize === "ok";
  const match = sizeMatches(), edit = editing();
  const printT = t ? `${fmtMm(t.w * k)} × ${fmtMm(t.h * k)} mm` : "";
  let st, sum, say;
  if (done) {
    st = "done"; sum = `dopasowany — ${printT}`;
    say = `<span class="say ok">Wymiar dopasowany</span> — wydruk ${printT}.`;
  } else if (ok && !f) {                       // obraz bez DPI — „rozumiem" to nie „zgadza się"
    st = "done"; sum = "obraz bez zmian";
    say = `Obraz zostaje bez zmian; wytyczne: ${printT}.`;
  } else if (ok) {
    st = "done"; sum = `zgadza się — ${printT}`;
    say = `<span class="say ok">Wymiar się zgadza</span> — wydruk ${printT}.`;
  } else if (!f) {
    // obraz bez zapisanej rozdzielczości (DPI) — nie wiadomo, ile ma milimetrów
    st = "todo"; sum = "";
    say = `<span class="say warn">Obraz nie ma zapisanej rozdzielczości (DPI)</span>, więc nie wiadomo, ile ma `
      + `milimetrów — nie da się go porównać z wytycznymi (${printT}) ani dopasować. Ustaw DPI w programie graficznym.`;
  } else if (match) {
    st = "todo"; sum = "";
    say = `<span class="say ok">Wymiar się zgadza</span>: plik ${fmtMm(f.w)} × ${fmtMm(f.h)} mm`
      + (k > 1 ? `, na wydruku ${printT}` : "") + ".";
  } else {
    st = "todo"; sum = "";
    say = (k > 1
      ? `Na wydruku plik ma <b>${fmtMm(f.w * k)} × ${fmtMm(f.h * k)} mm</b>, a wytyczne wymagają <b>${printT}</b> `
        + `(plik w skali 1:${k}: ${fmtMm(f.w)} × ${fmtMm(f.h)} mm zamiast ${fmtMm(t.w)} × ${fmtMm(t.h)} mm)`
      : `${isPdf() ? "Plik" : "Obraz"} ma <b>${fmtMm(f.w)} × ${fmtMm(f.h)} mm</b>, a wytyczne wymagają <b>${fmtMm(t.w)} × ${fmtMm(t.h)} mm</b>`)
      + ". Ustaw, jak projekt ma się zmieścić w formacie.";
  }
  // plik leży bokiem względem formatu (poziomy zamiast pionowego) — obrót pasuje lepiej niż skalowanie
  let rot = "";
  if (!done && !ok && f && t && !match) {
    const land = (a) => a.w > a.h * 1.03, port = (a) => a.h > a.w * 1.03;
    const e = (w, h) => Math.abs(Math.log((w / h) / (t.w / t.h)));
    if (((land(f) && port(t)) || (port(f) && land(t))) && e(f.h, f.w) < e(f.w, f.h))
      rot = `Plik leży <b>bokiem</b> — obróć go:`
        + `<button class="btn small" type="button" data-deg="90">⟳ 90° w prawo</button>`
        + `<button class="btn small" type="button" data-deg="-90">⟲ 90° w lewo</button>`;
  }
  if ($("szRot").dataset.html !== rot) { $("szRot").innerHTML = rot; $("szRot").dataset.html = rot; }
  $("szRot").hidden = !rot;
  chapter("ch-size", st, sum);
  $("szSay").innerHTML = say;
  $("szCtl").hidden = !edit;
  $("szEditBtn").hidden = !(match && f && !edit && !done && !ok);
  const c = cover();
  if (edit && c) {
    const s = sz(), m = RATIOS[s.ratio];
    setVal("szRange", Math.round(Math.min(500, Math.max(10, s.pct))));
    setVal("szPct", s.pct >= 100 ? Math.round(s.pct) : Math.round(s.pct * 10) / 10);
    $("szRatio").value = s.ratio; $("szRatioVal").textContent = ratioLabel(m);
    $("szRatioNote").textContent = k > 1 ? `(wytyczne w skali 1:${k} — plik drukuje się ${k}× większy)` : "";
    const pc = (z) => { const p = z / m * 100; return p >= 10 ? Math.round(p) : Math.round(p * 10) / 10; };
    $("szOrig").textContent = `rozmiar pliku (${pc(1)} %)`;
    $("szFill").textContent = `wypełnij format (${pc(c.coverZ)} %)`;
    $("szWhole").textContent = `cały projekt (${pc(c.containZ)} %)`;
    // zła skala pliku: ×10 albo ÷10 trafia co do milimetra — mówimy wprost
    const fits = (q) => Math.abs(c.f.w * q - c.t.w) < 1 && Math.abs(c.f.h * q - c.t.h) < 1;
    const x10 = fits(10), d10 = fits(0.1);
    $("szX10").classList.toggle("on", x10); $("szD10").classList.toggle("on", d10);
    $("szHint").hidden = !(x10 || d10);
    $("szHint").innerHTML = x10
      ? `Plik wygląda na zapisany w skali <b>1:1</b>, a wytyczne są w <b>1:10</b> — po przeskalowaniu <b>×10</b> wymiar zgadza się co do milimetra. Rastry nie zyskają pikseli, więc ppi na wydruku spadnie 10×.`
      : `Plik wygląda na zapisany w skali <b>1:10</b>, a wytyczne są w <b>1:1</b> — po przeskalowaniu <b>÷10</b> wymiar zgadza się co do milimetra.`;
    if ((x10 || d10) && !s.hintShown) { s.hintShown = true; $("szRatioBox").open = true; }
    setVal("szX", Math.round(s.dx / c.rx * 1000)); setVal("szY", Math.round(s.dy / c.ry * 1000));
    // opis na WYDRUKU: ile mm od środka, a gdy krawędź projektu równa się z krawędzią formatu — to
    const where = (d, pos, T, P, neg, pos_, eA, eB) => {
      if (Math.abs(d) < 0.05) return "środek";
      if (Math.abs(T - P) > 0.1 && Math.abs(pos) < 0.05) return `równo z ${eA} krawędzią`;
      if (Math.abs(T - P) > 0.1 && Math.abs(pos + P - T) < 0.05) return `równo z ${eB} krawędzią`;
      return d < 0 ? neg : pos_;                   // ile mm — w polu obok
    };
    const mm = (d) => { const v = Math.round(d * k * 10) / 10; return String(Object.is(v, -0) ? 0 : v).replace(".", ","); };
    setVal("szXmm", mm(s.dx)); setVal("szYmm", mm(s.dy));
    $("szXVal").textContent = where(s.dx, c.left, c.t.w, c.pw, "w lewo", "w prawo", "lewą", "prawą");
    $("szYVal").textContent = where(s.dy, c.top, c.t.h, c.ph, "w górę", "w dół", "górną", "dolną");
    $("szFillBox").hidden = !(c.gap[0] > 0.15 || c.gap[1] > 0.15);        // bez pustych pasów nie ma czego wypełniać
    document.querySelectorAll("#szFillSeg button").forEach((b) =>
      b.classList.toggle("on", b.dataset.v === (s.edge ? s.mode : "none")));
    const parts = [];
    // opis w mm NA WYDRUKU (przy wytycznych 1:10 mm pliku ×10 — Tomasz 28.09: laik myśli wydrukiem)
    if (c.cut[0] > 0.2 || c.cut[1] > 0.2) parts.push(`przycięte ${fmtMm(c.cut[0] * k)} mm w poziomie i ${fmtMm(c.cut[1] * k)} mm w pionie`);
    if (c.gap[0] > 0.2 || c.gap[1] > 0.2) parts.push(s.edge
      ? `margines ${fmtMm(c.gap[0] * k)} × ${fmtMm(c.gap[1] * k)} mm wypełniony ${s.mode === "mirror" ? "odbiciem lustrzanym" : "tłem z krawędzi"}`
      : `<span class="say warn">puste pasy ${fmtMm(c.gap[0] * k)} × ${fmtMm(c.gap[1] * k)} mm</span>`);
    $("szDesc").innerHTML = `Przy wielkości <b>${Math.round(c.z * 100)} %</b> projekt ma na wydruku ${fmtMm(c.pw * k)} × ${fmtMm(c.ph * k)} mm — `
      + (parts.length ? parts.join(", ") : "wypełnia format dokładnie") + "."
      // obraz zostaje obrazem, zapisany na nowo (Tomasz 29.09: dopasowanie wymiaru dla każdego formatu)
      + (isPdf() ? "" : /\.jpe?g$/i.test(S.job.file.name || "")
        ? ` <span class="muted">Obraz zostanie zapisany na nowo jako JPG (jakość 95).</span>`
        : ` <span class="muted">Obraz zostanie zapisany jako TIFF — bez strat.</span>`);
    const lost = 1 - (c.t.w * c.t.h) / (c.f.w * c.coverZ * c.f.h * c.coverZ);
    $("szWarn").hidden = !(lost > 0.25);
    $("szWarn").innerHTML = `Proporcje pliku zupełnie nie pasują do formatu — wypełnienie formatu odcięłoby `
      + `${Math.round(lost * 100)} % projektu. Sprawdź, czy to na pewno plik do tego produktu.`;
  } else {
    $("szWarn").hidden = true;
  }
  stepControls("sz", "resize", {
    canDo: true,
    doLabel: !f ? "Rozumiem, idę dalej" : match && !touched() ? "Zatwierdź wymiar" : "Dopasuj wymiar",
  });
  $("szDo").hidden = done || ok;
}
