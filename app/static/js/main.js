// Start programu: wgrywanie pliku, jedna pętla rysowania rozdziałów i podglądu, ustawienia.
import { $, esc, fmtMm, fmtBytes, api, ask, chapter, initChapters, plural, shown, revealChapters } from "./util.js";
import { S, changed, onChange, resetJobState, head, template, scaleK, printMm, isPdf, colorSettled, factsKey, STEP_NAME, STEP_CH, stepIndex } from "./state.js";
import { HELP } from "./help.js";
import * as viewer from "./viewer.js";
import * as product from "./product.js";
import { initSettings } from "./settings.js";
import { resetSteps } from "./steps.js";
import { renderFrames, renderTrim } from "./chapters.js";
import { renderSize, sizeScene } from "./size.js";
import { renderColor, renderOverprint, renderFonts, renderFlatten, simLayers, CMP_WITH_OP } from "./print.js";
import { renderQuality, renderAccept, renderDownload } from "./quality.js";
import { initTour, autoStartTour } from "./tour.js";

product.setResetSteps(resetSteps);

initChapters(HELP);
initSettings();

// ------------------------------------------------------------------ wgrywanie
const drop = $("drop"), input = $("fileInput");
drop.addEventListener("click", () => input.click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
input.addEventListener("change", () => { if (input.files[0]) upload(input.files[0]); input.value = ""; });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) upload(f); });

// Co użytkownik już zrobił z obecnym plikiem — to przepadnie po wgraniu innego.
function progressMade() {
  if (!S.job) return [];
  const out = [];
  if (S.job.file.page_count > 1 && S.pageOk) out.push("wybór strony");
  if (S.product || S.custom) out.push("wybór produktu");
  if (S.product && S.roleOk) out.push("wybór roli");
  for (const v of S.job.versions.slice(1)) out.push(STEP_NAME[v.step]);
  if (Object.values(S.settle).some((v) => v !== "auto")) out.push("decyzje w rozdziałach");
  return out;
}

let xhr = null, upSeq = 0;
async function upload(file) {
  const lost = progressMade();
  if (lost.length && !(await ask("Wgrać inny plik?",
      `Wszystko, co zrobiłeś z obecnym plikiem, zostanie utracone: <b>${esc(lost.join(", "))}</b>.`,
      "Wgraj nowy plik", "Zostaw obecny"))) return;
  xhr?.abort();
  const seq = ++upSeq;
  if (S.job) fetch(`/api/jobs/${S.job.job_id}`, { method: "DELETE" }).catch(() => {});
  S.job = null; S.analysis = null; S.analysisFor = null; S.page = 0;
  resetJobState(); resetReveal();
  viewer.setScene(null);
  $("fileErr").hidden = true;
  $("dropIdle").hidden = true; $("dropFile").hidden = false;
  $("fileName").textContent = file.name;
  $("fileMeta").textContent = `${fmtBytes(file.size)} · wysyłam…`;
  const bar = $("upBar"); bar.hidden = false; bar.firstElementChild.style.width = "0%";
  changed();
  const fd = new FormData();
  fd.append("file", file, file.name);
  xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const pct = Math.round(e.loaded / e.total * 100);
    bar.firstElementChild.style.width = pct + "%";
    $("fileMeta").textContent = `${fmtBytes(file.size)} · ${pct < 100 ? `wysyłam ${pct} %` : "otwieram plik…"}`;
  };
  xhr.onload = () => {
    if (seq !== upSeq) return;
    bar.hidden = true;
    let d = {};
    try { d = JSON.parse(xhr.responseText); } catch (_) {}
    if (xhr.status >= 200 && xhr.status < 300) return onUploaded(d);
    $("fileMeta").textContent = fmtBytes(file.size);
    $("fileErr").textContent = d.error || `Błąd wysyłania (HTTP ${xhr.status})`;
    $("fileErr").hidden = false;
    changed();
  };
  xhr.onerror = () => {
    if (seq !== upSeq) return;
    bar.hidden = true;
    $("fileErr").textContent = "Brak połączenia z programem — czy okno serwera jest otwarte?";
    $("fileErr").hidden = false;
  };
  xhr.send(fd);
}

function onUploaded(job) {
  S.job = job; S.page = 0; S.pageOk = job.file.page_count < 2;
  product.onNewFile();
  const f = job.file;
  $("fileMeta").textContent = `${fmtBytes(f.size_bytes)} · ${f.page_count} ${plural(f.page_count, "strona", "strony", "stron")}`;
  thumbs();
  viewer.zoomFit();
  changed();
}

// ------------------------------------------------------------------ analiza (fakty o pliku)
let anSeq = 0, anBusy = null;
// Fakty zawsze o ostatniej wersji i o wybranej stronie (do druku idzie jedna strona).
async function loadAnalysis() {
  const v = head(), key = factsKey();
  if (!v || anBusy === key || S.analysisFor === key) return;
  const seq = ++anSeq;
  anBusy = key;
  try {
    const a = await api(`/api/jobs/${S.job.job_id}/analysis?v=${v.id}&page=${S.page}`);
    if (seq !== anSeq) return;
    S.analysis = a; S.analysisFor = key; S.factsCache[key] = a;
  } catch (e) {
    if (seq !== anSeq) return;
    S.analysis = { error: e.message }; S.analysisFor = key;
  }
  anBusy = null;
  changed();
}

// ------------------------------------------------------------------ miniatury stron
function thumbs() {
  const f = S.job.file, el = $("thumbs");
  el.hidden = f.page_count < 2;
  el.innerHTML = f.page_count < 2 ? "" : f.pages.map((p) =>
    `<div class="thumb" data-i="${p.index}"><img src="/api/jobs/${S.job.job_id}/thumb/${p.index}.png" alt="" loading="lazy">str. ${p.index + 1}</div>`).join("");
  el.querySelectorAll(".thumb").forEach((t) => { t.onclick = () => product.wantPage(+t.dataset.i); });
}

// ------------------------------------------------------------------ podgląd
// Wymiar strony (mm pliku) — raster bez DPI: umowne 72 dpi (i tak nie znamy rozmiaru).
function pageMmOf(v) {
  const p = v.pages_mm?.[S.page];
  if (p && p[0] > 0 && p[1] > 0) return { w: p[0], h: p[1] };
  const fp = S.job.file.pages[S.page];
  return { w: (fp.width_px || 595) * 25.4 / 72, h: (fp.height_px || 842) * 25.4 / 72 };
}

// Jak strona wersji `a` leży na stronie wersji `b` (b późniejsza): składamy przekształcenia
// kolejnych poprawek (spady przesuwają stronę, wymiar ją skaluje i przesuwa).
function rectIn(a, b) {
  const vs = S.job.versions;
  let s = 1, dx = 0, dy = 0;
  for (let i = a + 1; i <= b; i++) {
    const m = vs[i].map;
    if (m) { s *= m.s; dx = m.s * dx + m.dx; dy = m.s * dy + m.dy; }
  }
  const p = pageMmOf(vs[a]);
  return { x: dx, y: dy, w: p.w * s, h: p.h * s };
}

// Podgląd = WYDRUK od chwili, gdy rozdział „Kolory" jest domknięty (Tomasz 24.09). Wcześniej
// ekran pokazywał plik jak monitor, a to kłamie w dwóch miejscach, także gdy plik jest już
// w CMYK-u: przezroczystość bez zadeklarowanej przestrzeni mieszania drukarnia miesza w CMYK
// (zmierzone na PRINT_CHECKER_TEST: nałożenie 155/45/45 na ekranie, 166/55/55 w druku — tak
// samo przy „zostaw" i po zamianie), a czarny z samego K drukuje się grafitem, nie czernią.
// Zostawiony overprint → dochodzi symulacja overprintu.
function printFlags() {
  return { pr: colorSettled(), op: S.settle.overprint === "skip" && !S.job.versions.some((v) => v.step === "flatten") };
}

function scene() {
  if (!S.job) return null;
  const vs = S.job.versions, hi = vs.length - 1;
  const t = template();
  const overlay = S.product && t && !t.dims_missing
    ? { svg: t.svg, key: `${S.guidelines.hash}:${S.tplIndex}`, w: t.page_width_pt * 25.4 / 72, h: t.page_height_pt * 25.4 / 72 }
    : null;
  const pf = printFlags();
  const layer = (v, rect, extra) => ({ vid: v.id, page: S.page, pageMm: pageMmOf(v), k: kOf(v), op: pf.op, pr: pf.pr, rect, ...extra });
  const label = (pm) => hasResize() ? `format z wytycznych ${fmtMm(pm.w * scaleK())} × ${fmtMm(pm.h * scaleK())} mm` : "";
  // rozdział „Wymiar" w edycji: ramka = format z wytycznych, projekt pod nią
  const fit = S.cmp ? null : sizeScene();       // suwak porównania ma pierwszeństwo
  if (fit) {
    return { frame: fit.frame, k: scaleK(), mix: 1, overlay, frameLabel: fit.label, dimOutside: !fit.clip,
             clip: fit.clip, fill: fit.fill, layers: [layer(vs[hi], fit.rect)] };
  }
  // „Akceptacja": wydruk BEZ poprawek od rozdziału Kolory ↔ wydruk PO nich (oba jako druk:
  // kolory z drukarki + overprint). „Bez poprawek" = ostatnia wersja po szablonie/spadach/wymiarze.
  if (S.sim === "final" && !S.cmp) {
    let base = 0;
    vs.forEach((v, i) => { if (["frames", "trim", "resize"].includes(v.step)) base = i; });
    const pm = pageMmOf(vs[hi]), P = { pr: true, op: true };
    return { frame: pm, k: kOf(vs[hi]), mix: S.simMix / 100, overlay, frameLabel: label(pm),
             layers: [layer(vs[base], rectIn(base, hi), P), layer(vs[hi], { x: 0, y: 0, w: pm.w, h: pm.h }, P)] };
  }
  // symulacja druku (rozdział Kolory / Overprint): ta sama wersja — na ekranie ↔ z drukarki
  const sim = simLayers();
  if (sim) {
    const pm = pageMmOf(vs[hi]), r = { x: 0, y: 0, w: pm.w, h: pm.h };
    // overprint: druk BEZ overprintu ↔ druk Z overprintem — zmienia się tylko to, co robi
    // overprint (ekran od druku różni się też gdzie indziej: czerń K100, mieszanie przezroczystości)
    return { frame: pm, k: kOf(vs[hi]), mix: sim.mix, overlay, frameLabel: label(pm),
             layers: [layer(vs[hi], r, sim.bottom), layer(vs[hi], r, sim.top)] };
  }
  // suwak w rozdziale: tuż przed ↔ tuż po tym kroku. (Główny suwak „przed / po wszystkich
  // poprawkach" usunięty — Tomasz 24.09: pokazywał plik, a nie wydruk. Wróci na końcu jako
  // symulacja wydruku przed i po, z overprintem i kolorami z drukarki.)
  const ci = S.cmp ? vs.findIndex((v) => v.step === S.cmp.step) : -1;
  if (ci > 0) {
    const pm = pageMmOf(vs[ci]);
    // kolory: przed = jak na ekranie, po = wydruk; overprint i spłaszczenie: obie strony z overprintem
    const [exA, exB] = S.cmp.step === "cmyk" ? [{ op: false, pr: false }, { op: false, pr: true }]
      : CMP_WITH_OP.includes(S.cmp.step) ? [{ op: true, pr: true }, { op: true, pr: true }] : [{}, {}];
    return { frame: pm, k: kOf(vs[ci]), mix: S.cmp.v / 100, overlay, frameLabel: label(pm),
             layers: [layer(vs[ci - 1], rectIn(ci - 1, ci), exA), layer(vs[ci], { x: 0, y: 0, w: pm.w, h: pm.h }, exB)] };
  }
  const pm = pageMmOf(vs[hi]);
  return { frame: pm, k: kOf(vs[hi]), mix: 1, overlay, frameLabel: label(pm),
           layers: [layer(vs[hi], { x: 0, y: 0, w: pm.w, h: pm.h })] };
}
const hasResize = () => S.job.versions.some((v) => v.step === "resize");

// Ile razy wydruk jest większy od strony tej wersji. PDF: skala wytycznych. Raster (wymiar
// z DPI bywa umowny): stosunek wymiaru wydruku do strony — tak liczy się „rzeczywista wielkość".
function kOf(v) {
  if (isPdf()) return scaleK();
  const pr = printMm(), pm = pageMmOf(v);
  return pr ? Math.max(pr.w, pr.h) / Math.max(pm.w, pm.h) : scaleK();
}

function fileLine() {
  const f = S.job.file, a = S.analysis;
  let typ = "";
  if (a && !a.error) {
    const r = a.resolution || {};
    typ = a.kind === "raster" ? `obraz ${a.meta?.format || ""}` : r.has_images ? "wektor + obrazy" : "sam wektor";
  }
  const who = a && a.meta ? [a.meta.creator, a.meta.producer].filter(Boolean).join(" · ") : "";
  $("vName").innerHTML = `<b>${esc(f.name)}</b>${typ ? ` <small>· ${esc(typ)}</small>` : ""}`;
  $("vName").title = [f.name, typ, who].filter(Boolean).join(" · ");
}

$("vFit").onclick = viewer.zoomFit;
$("v100").onclick = viewer.zoom100;
$("vIn").onclick = () => viewer.setTool("in");
$("vOut").onclick = () => viewer.setTool("out");
$("vNavi").onclick = () => viewer.setNavi(!viewer.naviIsOn());
$("vTpl").onclick = () => { S.overlayOn = !S.overlayOn; changed(); };
viewer.onViewChange(() => {
  $("v100").classList.toggle("on", viewer.is100());
  $("vIn").classList.toggle("on", viewer.currentTool() === "in");
  $("vOut").classList.toggle("on", viewer.currentTool() === "out");
  $("v100").title = (S.calibrated ? "Rzeczywista wielkość wydruku: 1 mm wydruku = 1 mm na ekranie"
    : "Rzeczywista wielkość wydruku — monitor nieskalibrowany (Ustawienia), więc to przybliżenie")
    + ". Bardziej przybliżyć się nie da — dalej widać już tylko piksele ekranu.";
});

// ------------------------------------------------------------------ rozdziały po kolei
// Rozdziały, które pojawiają się naraz (zaliczone same: fonty „brak tekstu", spłaszczenie
// „niepotrzebne"…), wychodzą PO KOLEI, co REVEAL_GAP ms — widać, że program sprawdza je jeden po
// drugim (Tomasz 25.09: „najpierw fonty, po kilku sekundach spłaszczenie, potem jakość").
// Czekający rozdział jest schowany (hidden); jego logika (np. liczenie jakości) już działa.
const REVEAL_GAP = 1500;
let logical = new Set(), revealQ = [], lastReveal = -1e9, revealTimer = null;
function gateChapters() {
  const vis = [...document.querySelectorAll(".ch")].filter((ch) => !ch.hidden);
  const now = performance.now();
  const animate = document.body.classList.contains("ready")
    && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const ids = new Set(vis.map((ch) => ch.id));
  revealQ = revealQ.filter((id) => ids.has(id));
  for (const ch of vis) {
    if (logical.has(ch.id)) continue;                       // już był widoczny
    if (animate && (revealQ.length || now - lastReveal < REVEAL_GAP)) revealQ.push(ch.id);
    else revealed(ch, animate ? now : lastReveal);
  }
  logical = ids;
  revealQ.forEach((id) => { $(id).hidden = true; });
  if (revealQ.length && !revealTimer) {
    revealTimer = setTimeout(() => {
      revealTimer = null;
      const id = revealQ.shift();
      if (id) revealed($(id), performance.now());
      changed();
    }, Math.max(0, REVEAL_GAP - (now - lastReveal)));
  }
}
const everShown = new Set();                                // rozdziały tego pliku widziane choć raz
function revealed(ch, now) {
  lastReveal = now;
  // pojawił się PIERWSZY RAZ rozdział dalej niż ten z przypiętym suwakiem — praca poszła naprzód,
  // więc przypięty rozdział może się już zwinąć (S.pin, niżej). Rozdział, który tylko wraca po
  // poprawce we wcześniejszym (jakość, akceptacja), przypięcia nie zdejmuje.
  const pin = S.pin && $(S.pin);
  if (pin && pin !== ch && !everShown.has(ch.id) && pin.compareDocumentPosition(ch) & Node.DOCUMENT_POSITION_FOLLOWING) S.pin = null;
  everShown.add(ch.id);
}
function resetReveal() {                                   // nowy plik: nic nie czeka
  revealQ = []; everShown.clear();
  if (revealTimer) { clearTimeout(revealTimer); revealTimer = null; }
}

// ------------------------------------------------------------------ jedna pętla rysowania
let lastAuto = "";
function render() {
  const has = !!S.job;
  $("vEmpty").hidden = has; $("vMain").hidden = !has;
  chapter("ch-file", has ? "done" : "open", has ? esc(S.job.file.name) : "");
  if (has) { loadAnalysis(); fileLine(); }
  product.renderPage();
  product.renderProduct();
  product.renderRole();
  if (has) {
    renderFrames(); renderTrim(); renderSize(); renderColor(); renderOverprint(); renderFonts(); renderFlatten();
    renderQuality(); renderAccept(); renderDownload();
  } else {
    $("ch-qual").hidden = $("ch-acc").hidden = $("ch-dl").hidden = true;
  }
  // Rozwinięte same (Tomasz 24.09): ZAWSZE dwa ostatnie widoczne rozdziały — bieżący i ten tuż
  // przed nim; reszta zwinięta. Tylko przy PRZEJŚCIU do innego rozdziału, więc ręcznie da się
  // rozwinąć każdy.
  // Wyjątek (Tomasz 25.09, „spłaszczenie nie ma suwaka"): rozdział, w którym właśnie zrobiono
  // poprawkę albo kliknięto „Pokaż, jak wydrukuje" (S.pin), zostaje rozwinięty, choć za nim
  // pojawiły się rozdziały zaliczone same (np. jakość „w porządku" i akceptacja) — inaczej zwijał
  // się razem ze swoim suwakiem. Puszcza, gdy suwak przejdzie do innego rozdziału.
  gateChapters();
  const chs = [...document.querySelectorAll(".ch:not([hidden])")];
  const lastTwo = chs.slice(-2);
  const pin = chs.find((ch) => ch.id === S.pin) || null;
  const autoKey = [...lastTwo, pin].map((ch) => ch?.id || "").join("|");
  if (autoKey !== lastAuto) {
    lastAuto = autoKey;
    chs.forEach((ch) => ch.classList.toggle("open", lastTwo.includes(ch) || ch === pin));
  }
  // Starszy rozdział z poprawką albo decyzją (nie jeden z dwóch ostatnich ani przypięty) pokazuje
  // tylko „Cofnij" — cofa do niego (Tomasz 25.09). Wybór, „Pokaż, jak wydrukuje" i suwaki są
  // tylko w rozdziałach, nad którymi się teraz pracuje.
  for (const [name, id] of Object.entries(STEP_CH)) {
    const ch = $(id), step = stepIndex(name) > 0;
    const decided = step || (!!S.settle[name] && S.settle[name] !== "auto");
    ch.classList.toggle("past", !ch.hidden && decided && !lastTwo.includes(ch) && ch !== pin);
    const back = ch.querySelector(".ch-back button");
    if (back) back.textContent = step ? "Cofnij" : "Zmień decyzję";
  }
  // Tylko JEDEN suwak w panelu — ostatni, czyli najświeższy (Tomasz 24.09: przy overprincie
  // suwak z kolorów tylko mylił). Rozdziały ustawiają swoje suwaki przy każdym rysowaniu,
  // więc tu wystarczy schować wszystkie poza ostatnim widocznym.
  const minis = [...document.querySelectorAll(".ch:not([hidden]) .mini")].filter((m) => !m.hidden && shown(m));
  const keep = minis[minis.length - 1];
  document.querySelectorAll(".ch .mini").forEach((m) => { if (m !== keep) m.hidden = true; });
  if (S.pin && keep && keep.closest(".ch")?.id !== S.pin) S.pin = null;
  // porównanie ze schowanego suwaka nie może zostać na podglądzie
  if (S.cmp && !keep?.querySelector(`input[data-step="${S.cmp.step}"]`)) S.cmp = null;
  revealChapters();
  // numery rozdziałów po kolei, licząc tylko widoczne
  let n = 0;
  document.querySelectorAll(".ch:not([hidden]) .ch-ico").forEach((ico) => {
    ico.dataset.n = String(++n);
    if (!["✓", "!"].includes(ico.textContent)) ico.textContent = ico.dataset.n;
  });
  // podgląd
  const sc = scene();
  viewer.setScene(sc);
  viewer.setBusy(S.busy);
  $("vTpl").disabled = !sc?.overlay;
  $("vTpl").classList.toggle("on", !!sc?.overlay && S.overlayOn);
  document.querySelectorAll("#thumbs .thumb").forEach((t) => t.classList.toggle("on", +t.dataset.i === S.page));
}
onChange(render);

product.loadProducts();
changed();
// animacje dopiero po pierwszym rysowaniu — przy starcie programu nic nie ma wjeżdżać
setTimeout(() => document.body.classList.add("ready"), 400);

// Wersja programu i aktualizacja (updater.py). Zainstalowany program sam pobiera nową wersję
// w tle, a potem pokazuje przycisk „Zaktualizuj do X" (Tomasz 25.09). Uruchomiony z kodu
// (run.bat) albo gdy pobieranie się nie uda — zwykły link do strony wydania.
let upd = null;
async function checkVersion() {
  try { upd = await api("/api/version"); } catch (_) { return; }
  $("ver").textContent = "v" + upd.version;
  const a = $("upd");
  a.hidden = !upd.update;
  a.classList.toggle("wait", upd.status === "downloading");
  if (upd.update) {
    a.href = upd.update_url || "#";
    a.textContent = !upd.self_update || upd.status === "error" ? `Jest nowa wersja ${upd.update} — pobierz`
      : upd.status === "ready" ? `Zaktualizuj do wersji ${upd.update}`
      : `Pobieram wersję ${upd.update}… ${upd.progress} %`;
    a.title = upd.status === "error" ? `Automatyczne pobranie nie wyszło (${upd.error}). Kliknij, żeby pobrać ręcznie.` : "";
  }
  setTimeout(checkVersion, upd.status === "downloading" ? 3000 : 10 * 60 * 1000);
}
$("upd").addEventListener("click", async (e) => {
  if (!upd?.self_update || upd.status === "error") return;     // zwykły link do wydania
  e.preventDefault();
  if (upd.status !== "ready") return;
  if (!(await ask(`Zaktualizować do wersji ${upd.update}?`,
      `Program zamknie się na kilkanaście sekund i uruchomi ponownie już w nowej wersji.`
      + (S.job ? ` Otwarty plik trzeba będzie wgrać jeszcze raz.` : ""), "Zaktualizuj teraz", "Później"))) return;
  try {
    await api("/api/update/install", { method: "POST" });
    $("updating").hidden = false;
  } catch (err) {
    await ask("Aktualizacja się nie udała", esc(err.message), "OK", "Zamknij");
  }
});
checkVersion();
// „żyję" — program uruchomiony bez własnego okna kończy się sam, gdy zamkniesz kartę
setInterval(() => fetch("/api/alive", { method: "POST" }).catch(() => {}), 20000);
initTour({ upload });
autoStartTour();
