// Rozdziały „Jakość wydruku" i „Pobierz plik do druku" (etap 4).
// Jakość liczy serwer (quality.py → detailmap.py) i oddaje gotowy werdykt; tu tylko pokazanie
// go po ludzku i nawigacja po słabych miejscach na podglądzie (w rzeczywistej wielkości wydruku).
import { $, esc, fmtMm, api, chapter, plural } from "./util.js";
import { S, changed, head, scaleK, printMm, isPdf, flattenSettled, template, STEP_NAME } from "./state.js";
import { detailBlock } from "./settings.js";
import * as viewer from "./viewer.js";

const REQ = 120;

// ------------------------------------------------------------------ jakość: liczenie
// Oceniana wersja: ostatnia przed spłaszczeniem (tak samo wybiera serwer — quality.version_for).
const qualVersion = () => [...S.job.versions].reverse().find((v) => v.step !== "flatten");
function qualKey() {
  const pr = printMm();
  return [S.job.job_id, qualVersion().id, S.page, scaleK(), detailBlock(), pr ? `${pr.w.toFixed(1)}x${pr.h.toFixed(1)}` : ""].join("|");
}
let timer = null;
async function poll(key) {
  clearTimeout(timer);
  if (S.qual.key !== key) return;
  const pr = printMm();
  try {
    const d = await api(`/api/jobs/${S.job.job_id}/quality?page=${S.page}&k=${isPdf() ? scaleK() : 1}`
      + `&block=${detailBlock()}` + (pr ? `&w_mm=${pr.w}&h_mm=${pr.h}` : ""));
    if (S.qual.key !== key) return;
    S.qual.data = d; S.qual.err = d.status === "error" ? (d.error || "błąd") : "";
    if (d.status === "running") timer = setTimeout(() => poll(key), 1200);
  } catch (e) {
    if (S.qual.key !== key) return;
    S.qual.err = e.message;
  }
  changed();
}

export function qualitySettled() {
  if (!flattenSettled()) return false;
  if (S.settle.quality || S.qual.err) return true;
  const d = S.qual.data;
  return !!d && d.status === "done" && (d.verdict === "ok" || d.verdict === "vector");
}

// ------------------------------------------------------------------ jakość: opis
const areaShort = (a) => {
  const mm = a.mm ? `${fmtMm(a.mm[0])} × ${fmtMm(a.mm[1])} mm` : "";
  return a.reason === "lowres" ? `${a.whole ? "cały obraz" : "obraz"} ${mm} — ${Math.round(a.ppi)} ppi zamiast ${REQ}`
                               : `${a.whole ? "cały obraz" : "miejsce"} ${mm} — jak przy ${Math.round(a.ppi)} ppi`;
};
const areaPlain = (a) => a.reason === "lowres"
  ? `Obraz${a.px ? ` ${a.px[0]} × ${a.px[1]} px` : ""} rozciągnięty na ${a.mm ? `${fmtMm(a.mm[0])} × ${fmtMm(a.mm[1])} mm` : "ten rozmiar"} — jeden piksel wychodzi ${a.ppi ? fmtMm(25.4 / a.ppi) : "?"} mm na wydruku.`
  : `${a.nominal_ppi != null ? `Obraz ma tu ${Math.round(a.nominal_ppi)} ppi, ale s` : "S"}zczegółu jest tyle, co przy ${Math.round(a.ppi)} ppi — jakby powiększono mniejszy kawałek.`;
const areaLabel = (a) => a.reason === "lowres"
  ? `≈ ${Math.round(a.ppi)} ppi na wydruku, wymagane ${REQ}`
  : `szczegół jak przy ≈ ${Math.round(a.ppi)} ppi — obejrzyj`;

// „Pokaż na podglądzie" to WŁĄCZNIK (Tomasz 24.09): drugi klik chowa ramki i pasek miejsc.
// Pierwszy klik domyka też rozdział (trzeba było obejrzeć).
$("quShow").querySelector("button").addEventListener("click", () => {
  S.settle.quality = "seen";
  if (nav === null) openNav(0); else closeNav();
  changed();
});

export function renderQuality() {
  const el = $("ch-qual");
  el.hidden = !flattenSettled();
  if (el.hidden) { closeNav(); return; }
  const key = qualKey();
  if (S.qual.key !== key) {
    S.qual = { key, data: null, err: "" };
    delete S.settle.quality;
    closeNav();
    poll(key);
  }
  const d = S.qual.data;
  let st = "open", sum = "", say = "", note = "";
  const bar = $("quBar");
  bar.hidden = true;
  if (S.qual.err) {
    st = "done"; sum = "nie udało się sprawdzić";
    say = `<span class="say warn">Nie udało się sprawdzić jakości.</span>`; note = esc(S.qual.err);
  } else if (!d || d.status === "running") {
    say = `<span class="spin"></span>Sprawdzam jakość obrazów — piksel po pikselu…`;
    if (d?.bands) { bar.hidden = false; bar.firstElementChild.style.width = `${Math.round(d.band / d.bands * 100)}%`; }
  } else if (d.verdict === "vector") {
    st = "done"; sum = "sam wektor";
    say = `<span class="say ok">Projekt jest w wektorze</span> — rozdzielczość nie ma tu znaczenia.`;
  } else if (d.verdict === "ok") {
    st = "done"; sum = "w porządku";
    say = `<span class="say ok">Jakość w porządku</span> — każdy obraz ma co najmniej ${REQ} ppi na wydruku.`;
  } else {
    st = S.settle.quality ? "done" : "todo";
    const g0 = d.areas[d.groups[0].i];
    if (d.verdict === "bad") {
      sum = "za mała rozdzielczość";
      say = `<b>${d.few}</b> ${plural(d.few, "obraz ma", "obrazy mają", "obrazów ma")} za mało pikseli na swój rozmiar. `
        + `Najsłabszy wychodzi <b>≈ ${Math.round(g0.ppi)} ppi</b>, a wymagane jest ${REQ} — na wydruku będzie rozmyty `
        + `i schodkowy. Takie obrazy trzeba wymienić na większe.`;
      if (d.look) note = `Do tego ${d.look} ${plural(d.look, "miejsce wygląda", "miejsca wyglądają", "miejsc wygląda")} na powiększone — do obejrzenia.`;
    } else {
      sum = "do obejrzenia";
      say = `Obrazy mają dość pikseli, ale w <b>${d.look}</b> ${plural(d.look, "miejscu", "miejscach", "miejscach")} `
        + `nie niosą szczegółu — jakby ktoś powiększył mniejszy kawałek (najgorzej ≈ ${Math.round(g0.ppi)} ppi). `
        + `Może to być zwykłe rozmycie ze zdjęcia — obejrzyj i zdecyduj.`;
    }
    if (scaleK() > 1) note += `${note ? " " : ""}Plik w skali 1:10 drukuje się 10× większy — żeby wyszło ${REQ} ppi, w pliku trzeba ${REQ * 10} ppi.`;
  }
  chapter("ch-qual", st, sum);
  $("quSay").innerHTML = say;
  $("quNote").innerHTML = note; $("quNote").hidden = !note;
  $("quErr").hidden = true;
  const bad = !!d && d.status === "done" && (d.verdict === "bad" || d.verdict === "look");
  $("quShow").hidden = !bad;
  if (bad) {
    const b = $("quShow").querySelector("button");
    b.textContent = `Pokaż na podglądzie (${d.areas.length})`;
    b.classList.toggle("on", nav !== null);
  }
  $("quListBox").hidden = !bad;
  if (bad) {
    const html = d.groups.map((g) => {
      const a = d.areas[g.i];
      const rep = g.count > 1 ? ` <small>${g.kind === "image" ? `ten sam obraz w ${g.count} miejscach` : `${g.count} takich samych miejsc`}</small>` : "";
      return `<li><button type="button" data-i="${g.i}">${esc(areaShort(a))}</button>${rep}<small>${esc(areaPlain(a))}</small></li>`;
    }).join("");
    const list = $("quList");
    if (list.dataset.html !== html) {
      list.innerHTML = html; list.dataset.html = html;
      list.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
        S.settle.quality = "seen"; openNav(+b.dataset.i); changed();
      }));
    }
  }
}

// ------------------------------------------------------------------ nawigacja po miejscach
let nav = null;               // numer pokazywanego miejsca albo null
function areas() { return S.qual.data?.areas || []; }
function openNav(i) {
  const as = areas();
  if (!as.length) return;
  nav = (i + as.length) % as.length;
  const a = as[nav], fr = viewer.frameMm();
  $("qnav").hidden = false;
  $("qnTxt").innerHTML = `Miejsce <b>${nav + 1}</b> z ${as.length} · ${esc(areaShort(a))}`;
  // ocena ZAWSZE w rzeczywistej wielkości wydruku (decyzja Tomasza) — inaczej piksele
  // wyglądają lepiej albo gorzej niż na druku
  if (fr) viewer.showRect({ x: a.fx * fr.w, y: a.fy * fr.h, w: a.fw * fr.w, h: a.fh * fr.h },
                          a.whole ? "" : areaLabel(a), true, true);
}
function closeNav() {
  if (nav === null) return;
  nav = null;
  $("qnav").hidden = true;
  viewer.clearHilite();
  changed();                 // przycisk „Pokaż na podglądzie" wraca do białego
}
$("qnPrev").onclick = () => openNav(nav - 1);
$("qnNext").onclick = () => openNav(nav + 1);
$("qnClose").onclick = closeNav;
document.addEventListener("keydown", (e) => {
  if (nav === null || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || "")) return;
  if (e.key === "ArrowLeft") { e.preventDefault(); openNav(nav - 1); }
  else if (e.key === "ArrowRight") { e.preventDefault(); openNav(nav + 1); }
  else if (e.key === "Escape") closeNav();
});

// ------------------------------------------------------------------ pobieranie
// Nazwa pliku: produkt + rola, bez wymiarów (ustalenie Tomasza).
function fileName() {
  const parts = [];
  if (S.product) parts.push(S.product.name);
  else if (S.custom) parts.push("Wydruk niestandardowy");
  const t = S.product ? template() : null;
  if (t?.role) parts.push(t.role);
  return parts.join(" - ") || "do_druku";
}

// ------------------------------------------------------------------ akceptacja
// Ostatnie spojrzenie przed pobraniem (Tomasz 24.09): wydruk BEZ poprawek od rozdziału „Kolory"
// ↔ wydruk PO nich — oba jako druk (kolory z drukarki + overprint). Akceptacja dotyczy
// konkretnej wersji: każda zmiana pliku ją zdejmuje.
$("acShow").querySelector("button").addEventListener("click", () => {
  const on = S.sim === "final";
  S.sim = on ? null : "final"; S.simMix = 0; S.cmp = null;     // start od „przed" — różnicę widać od razu
  $("acSimBar").querySelector("input").value = 0;
  S.accShown = head().id;
  closeNav();
  if (!on) viewer.zoomFit();              // cały projekt w oknie, jak po „Dopasuj" (Tomasz 25.09)
  changed();
});
$("acOk").querySelector("button").addEventListener("click", () => {
  S.settle.accept = head().id;
  S.sim = null;
  changed();
});
export const acceptSettled = () => qualitySettled() && S.settle.accept === head()?.id;

export function renderAccept() {
  const el = $("ch-acc");
  el.hidden = !qualitySettled();
  if (el.hidden) return;
  const ok = acceptSettled();
  if (!ok && S.settle.accept) delete S.settle.accept;            // plik się zmienił
  chapter("ch-acc", ok ? "done" : "todo", ok ? "zaakceptowany" : "");
  const same = !S.job.versions.some((v, i) => i > 0 && !["frames", "trim", "resize"].includes(v.step));
  $("acSay").innerHTML = ok
    ? `<span class="say ok">Plik zaakceptowany.</span>`
    : same ? `Od rozdziału Kolory plik nie potrzebował poprawek, więc wydruk <b>przed</b> i <b>po</b> wygląda tak samo. `
      + `Obejrzyj go jeszcze raz — tak, jak zrobi to drukarnia — i jeśli wszystko gra, zaakceptuj plik.`
    : `Porównaj, jak plik wydrukowałby się <b>bez poprawek</b> i jak wydrukuje się <b>teraz</b> — `
      + `z kolorami i overprintem tak, jak zrobi to drukarnia. Jeśli wszystko gra, zaakceptuj plik.`;
  const b = $("acShow").querySelector("button");
  b.classList.toggle("on", S.sim === "final");
  $("acSimBar").hidden = S.sim !== "final";
  if (S.sim !== "final") $("acSimBar").querySelector("input").value = 100;
  $("acOk").hidden = S.accShown !== head().id;
  $("acOk").querySelector("button").classList.toggle("on", ok);
}

// W oknie programu (pywebview) pobieranie idzie przez systemowe „Zapisz jako" — okno nie ma
// paska pobierania przeglądarki. W przeglądarce działa zwykły link.
$("dlDo").addEventListener("click", async (e) => {
  const api = window.pywebview?.api;
  if (!api?.save_download || !S.job) return;
  e.preventDefault();
  const r = await api.save_download(S.job.job_id, S.page, fileName());
  if (r?.ok || r?.error) { saved = { v: head().id, txt: r.ok ? `Zapisano: ${r.path}` : r.error }; changed(); }
});
let saved = null;

export function renderDownload() {
  const el = $("ch-dl");
  el.hidden = !acceptSettled();
  if (el.hidden) return;
  chapter("ch-dl", "open", "");
  const vs = S.job.versions.slice(1);
  const done = vs.map((v) => STEP_NAME[v.step]);
  const left = [["cmyk", "kolory"], ["overprint", "overprint"], ["outline", "tekst w fontach"], ["flatten", "warstwy (bez spłaszczenia)"]]
    .filter(([n]) => S.settle[n] === "skip").map(([, t]) => t);
  const bad = S.qual.data?.verdict === "bad";
  $("dlSay").innerHTML = bad
    ? `<span class="say warn">Plik można pobrać, ale obrazy są za małe</span> — na wydruku będą rozmyte.`
    : `<span class="say ok">Plik gotowy do druku.</span>`;
  $("dlSum").innerHTML = (done.length ? `<li>Zrobione: ${esc(done.join(", "))}.</li>` : `<li>Bez poprawek.</li>`)
    + (left.length ? `<li>Zostawione jak były: ${esc(left.join(", "))}.</li>` : "")
    + (S.job.file.page_count > 1 ? `<li>Tylko strona ${S.page + 1} z ${S.job.file.page_count}.</li>` : "");
  const name = fileName();
  const ext = isPdf() ? "pdf" : "";           // obraz: rozszerzenie po ostatniej wersji (JPG / TIFF)
  const a = $("dlDo");
  a.href = `/api/jobs/${S.job.job_id}/download?v=${head().id}&page=${S.page}&name=${encodeURIComponent(name)}`;
  $("dlName").textContent = saved?.v === head().id ? saved.txt : `Nazwa pliku: ${name}${ext ? "." + ext : ""}`;
}
