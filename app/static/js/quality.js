// Rozdziały „Jakość wydruku" i „Pobierz plik do druku" (etap 4).
// Jakość liczy serwer (quality.py → detailmap.py) i oddaje gotowy werdykt; tu tylko pokazanie
// go po ludzku i nawigacja po słabych miejscach na podglądzie (w rzeczywistej wielkości wydruku).
import { $, esc, fmtMm, api, chapter, plural, brief } from "./util.js";
import { S, changed, head, scaleK, printMm, isPdf, flattenSettled, roleSettled, template, STEP_NAME, ROT_TXT, fontWarnings, inkNow, factsKey } from "./state.js";
import { detailBlock } from "./settings.js";
import * as viewer from "./viewer.js";

const REQ = 120;

// ------------------------------------------------------------------ jakość: liczenie
// Oceniana wersja: ostatnia po szablonie / spadach / wymiarze — przed zamianą kolorów (tak samo
// wybiera serwer — quality.version_for). Położenie obrazów jest już ostateczne, piksele oryginalne.
const GEOMETRY = ["frames", "trim", "resize"];
const qualVersion = () => [...S.job.versions].reverse().find((v, i, all) => i === all.length - 1 || GEOMETRY.includes(v.step));
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
  if (S.qual.err) return true;
  // także przy dobrej jakości rozdział czeka na „Rozumiem, dalej” — zostaje otwarty razem z lupkami
  // i nawigatorem, żeby można było obejrzeć projekt z bliska (Tomasz 29.09)
  const d = S.qual.data;
  return !!d && d.status === "done" && !!S.settle.quality;
}
const goodVerdict = (d) => !!d && d.status === "done" && (d.verdict === "ok" || d.verdict === "vector");
// ------------------------------------------------------------------ jakość: opis
const areaShort = (a) => {
  const mm = a.mm ? `${fmtMm(a.mm[0])} × ${fmtMm(a.mm[1])} mm` : "";
  if (a.reason === "jpeg") return `${a.whole ? "cały obraz" : "obraz"} ${mm} — mocna kompresja JPEG`;
  return a.reason === "lowres" ? `${a.whole ? "cały obraz" : "obraz"} ${mm} — ${Math.round(a.ppi)} ppi zamiast ${REQ}`
                               : `${a.whole ? "cały obraz" : "miejsce"} ${mm} — jak przy ${Math.round(a.ppi)} ppi`;
};
const areaPlain = (a) => a.reason === "jpeg"
  ? `Obraz zapisano z mocną kompresją JPEG (jakość ≈ ${Math.round(a.jpeg_q)} na 100) — na wydruku mogą być widoczne kwadraciki i „brudne” krawędzie.`
  : a.reason === "lowres"
  ? `Obraz${a.px ? ` ${a.px[0]} × ${a.px[1]} px` : ""} rozciągnięty na ${a.mm ? `${fmtMm(a.mm[0])} × ${fmtMm(a.mm[1])} mm` : "ten rozmiar"} — jeden piksel wychodzi ${a.ppi ? fmtMm(25.4 / a.ppi) : "?"} mm na wydruku.`
  : `${a.nominal_ppi != null ? `Obraz ma tu ${Math.round(a.nominal_ppi)} ppi, ale s` : "S"}zczegółu jest tyle, co przy ${Math.round(a.ppi)} ppi — jakby powiększono mniejszy kawałek.`;
const areaLabel = (a) => a.reason === "jpeg" ? "mocna kompresja JPEG — obejrzyj"
  : a.reason === "lowres"
  ? `≈ ${Math.round(a.ppi)} ppi na wydruku, wymagane ${REQ}`
  : `szczegół jak przy ≈ ${Math.round(a.ppi)} ppi — obejrzyj`;

// „Pokaż na podglądzie" to WŁĄCZNIK (Tomasz 24.09): drugi klik chowa ramki i pasek miejsc.
// Pierwszy klik domyka też rozdział (trzeba było obejrzeć).
$("quShow").querySelector("button").addEventListener("click", () => {
  S.settle.quality = "seen";
  if (nav === null) openNav(0); else closeNav();
  changed();
});

$("quRiskOk").querySelector("button").addEventListener("click", () => {
  S.settle.quality = "seen";
  changed();
});

// po błędzie oceny — nowa próba (serwer zaczyna od nowa, gdy poprzednia skończyła się błędem)
$("quRetry").querySelector("button").addEventListener("click", () => {
  S.qual = { key: "", data: null, err: "" };
  changed();
});

// Ocena jakości startuje W TLE zaraz po wyborze roli (znamy już stronę i skalę) — zanim użytkownik
// przejdzie przez Szablon…Spłaszczenie, obrazy są zwykle policzone. Rozdział „Jakość” pyta potem
// o wersję po poprawkach, a serwer bierze wyniki obrazów z pamięci (detailmap._img_cache).
let prefetched = "";
function prefetch() {
  if (!S.job || !roleSettled() || S.busy) return;
  const key = [S.job.job_id, S.page, isPdf() ? scaleK() : 1].join("|");
  if (key === prefetched) return;
  prefetched = key;
  const pr = printMm();
  api(`/api/jobs/${S.job.job_id}/quality?page=${S.page}&k=${isPdf() ? scaleK() : 1}`
    + `&block=${detailBlock()}` + (pr ? `&w_mm=${pr.w}&h_mm=${pr.h}` : "")).catch(() => {});
}

const LOOK = `Projekt możesz obejrzeć z bliska: lupki, rzeczywista wielkość wydruku i nawigator są w panelu nad podglądem.`;

export function renderQuality() {
  prefetch();
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
  $("quRetry").hidden = !S.qual.err;
  if (S.qual.err) {
    st = "done"; sum = "nie udało się sprawdzić";
    say = `<span class="say warn">Nie udało się sprawdzić jakości.</span>`; note = esc(S.qual.err);
  } else if (!d || d.status === "running") {
    say = `<span class="spin"></span>Sprawdzam jakość obrazów — piksel po pikselu…`;
    if (d?.bands) { bar.hidden = false; bar.firstElementChild.style.width = `${Math.round(d.band / d.bands * 100)}%`; }
  } else if (d.verdict === "vector") {
    st = S.settle.quality ? "done" : "todo"; sum = "sam wektor";
    say = `<span class="say ok">Projekt jest w wektorze</span> — rozdzielczość nie ma tu znaczenia.`;
    note = LOOK;
  } else if (d.verdict === "ok") {
    st = S.settle.quality ? "done" : "todo"; sum = "w porządku";
    say = `<span class="say ok">Jakość w porządku</span> — każdy obraz ma co najmniej ${REQ} ppi na wydruku.`;
    note = LOOK;
  } else {
    st = S.settle.quality ? "done" : "todo";
    // najsłabsze miejsce z POMIARU (kompresja JPEG nie ma ppi)
    const g0 = d.groups.map((g) => d.areas[g.i]).find((a) => a.reason !== "jpeg") || {};
    const jp = d.jpeg ? `${d.jpeg} ${plural(d.jpeg, "obraz zapisano", "obrazy zapisano", "obrazów zapisano")} z mocną kompresją JPEG — `
      + `na wydruku mogą być widoczne kwadraciki. Obejrzyj ${d.jpeg === 1 ? "go" : "je"} na podglądzie.` : "";
    if (d.verdict === "bad") {
      sum = "za mała rozdzielczość";
      say = `<b>${d.few}</b> ${plural(d.few, "obraz ma", "obrazy mają", "obrazów ma")} za mało pikseli na swój rozmiar. `
        + `Najsłabszy wychodzi <b>≈ ${Math.round(g0.ppi)} ppi</b>, a wymagane jest ${REQ} — na wydruku będzie rozmyty `
        + `i schodkowy. Takie obrazy trzeba wymienić na większe.`;
      if (d.look) note = `Do tego ${d.look} ${plural(d.look, "miejsce wygląda", "miejsca wyglądają", "miejsc wygląda")} na powiększone — do obejrzenia.`;
      if (jp) note += `${note ? " " : ""}${jp}`;
    } else if (d.look) {
      sum = "do obejrzenia";
      say = `Obrazy mają dość pikseli, ale w <b>${d.look}</b> ${plural(d.look, "miejscu", "miejscach", "miejscach")} `
        + `nie niosą szczegółu — jakby ktoś powiększył mniejszy kawałek (najgorzej ≈ ${Math.round(g0.ppi)} ppi). `
        + `Może to być zwykłe rozmycie ze zdjęcia — obejrzyj i zdecyduj.`;
      if (jp) note = jp;
    } else {
      sum = "do obejrzenia";
      say = `Obrazy mają dość pikseli, ale ${jp}`;
    }
    if (scaleK() > 1) note += `${note ? " " : ""}Plik w skali 1:10 drukuje się 10× większy — żeby wyszło ${REQ} ppi, w pliku trzeba ${REQ * 10} ppi.`;
  }
  // „Rozumiem, dalej” przy dobrej jakości — rozdział zostaje otwarty z lupkami i nawigatorem (Tomasz 29.09)
  $("quRiskOk").hidden = !(goodVerdict(d) && !S.settle.quality);
  chapter("ch-qual", st, sum);
  {
    let b = "";
    if (!S.qual.err) {
      if (!d || d.status === "running") b = `<span class="spin"></span>Sprawdzam jakość obrazów…`;
      else if (d.verdict === "vector") b = `<span class="ok">Sam wektor</span> — rozdzielczość nie ma znaczenia.`;
      else if (d.verdict === "ok") b = `<span class="ok">Jakość w porządku</span> — obrazy mają co najmniej ${REQ} ppi.`;
      else {
        const g = d.groups.map((x) => d.areas[x.i]).find((x) => x.reason !== "jpeg");
        b = d.verdict === "bad" && g ? `<span class="warn">Za mała rozdzielczość</span>: najsłabszy obraz ≈ ${Math.round(g.ppi)} ppi (wymagane ${REQ}).`
          : d.look ? `Do obejrzenia: ${d.look} ${plural(d.look, "miejsce", "miejsca", "miejsc")} wyglądające na powiększone.` : "";
        if (d.jpeg) b += `${b ? "<br>" : ""}Mocna kompresja JPEG: ${d.jpeg} ${plural(d.jpeg, "obraz", "obrazy", "obrazów")}.`;
      }
    }
    brief("quBrief", b);
  }
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
export const navOpen = () => nav !== null;
function areas() { return S.qual.data?.areas || []; }
function openNav(i) {
  const as = areas();
  if (!as.length) return;
  nav = (i + as.length) % as.length;
  const a = as[nav], fr = viewer.frameMm();
  $("qnav").hidden = false;
  $("qnTxt").innerHTML = `Miejsce <b>${nav + 1}</b> z ${as.length} · ${esc(areaShort(a))}`;
  $("qnTxt").title = `Miejsce ${nav + 1} z ${as.length} · ${areaShort(a)}`;
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
  S.sim = on ? null : "final"; S.simMix = 100; S.cmp = null;   // start od „po” — plik taki, jaki pójdzie do druku (Tomasz 29.09)
  $("acSimBar").querySelector("input").value = 100;
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
// Opis zmian DLA KLIENTA (Tomasz 01.10: „opis, który można skopiować i wysłać do klienta, żeby wiedział,
// co zostało poprawione”). Zwykłym językiem, bez nazw technicznych tam, gdzie się da. Pole jest edytowalne:
// tekst nadpisujemy tylko wtedy, gdy zmieni się plik (inaczej poprawki użytkownika by znikały).
const cap = (t) => t ? t[0].toUpperCase() + t.slice(1) : t;
const mmTxt = (v) => {
  const p = v?.pages_mm?.[S.page], k = isPdf() ? scaleK() : 1;
  return p ? `${fmtMm(p[0] * k)} × ${fmtMm(p[1] * k)} mm` : "";
};
function stepLine(v) {
  const t = v.text || "";
  switch (v.step) {
    case "frames": return "usunęliśmy elementy szablonu z wytycznych, które zostały w projekcie (ramki i opisy)";
    case "trim": return `przycięliśmy spady — projekt ma wymiar netto ${mmTxt(v)}`;
    case "resize": {
      const z = +(t.match(/w skali (\d+) %/)?.[1] || 100);
      return `dopasowaliśmy projekt do formatu ${mmTxt(v)}` + (z !== 100 ? ` (projekt w skali ${z} %)` : "")
        + (/przycięte/.test(t) ? ", część projektu przy krawędziach została przycięta" : "")
        + (/odbiciem lustrzanym/.test(t) ? ", brakujący margines uzupełniliśmy lustrzanym odbiciem projektu"
          : /tłem z krawędzi/.test(t) ? ", brakujący margines uzupełniliśmy tłem z krawędzi projektu"
          : /PUSTE PASY/.test(t) ? ", na brzegach zostały puste (białe) pasy" : "");
    }
    case "cmyk": {
      const pf = t.match(/przez profil ([^;(]+)/)?.[1]?.trim();
      return /^kolory dodatkowe/.test(t) ? "przeliczyliśmy kolory dodatkowe (spot) na CMYK — reszta kolorów została bez zmian"
        : `przeliczyliśmy kolory do druku (CMYK${pf ? `, profil ${pf}` : ""})`;
    }
    case "black": return "czerń złożoną ze wszystkich farb zamieniliśmy na zalecaną do druku czerń C78 M85 Y90 K100 — przy zbyt dużej ilości farby wydruk mógłby się rozmazać";
    case "overprint": return "wyłączyliśmy nadruk (overprint) — elementy wydrukują się tak, jak widać je na ekranie";
    case "outline": {
      const m = t.match(/\(\d+ fon[^:]*: ([^)]*)\)/);
      return "zamieniliśmy tekst na krzywe" + (m ? ` (fonty: ${m[1]})` : "") + " — litery wydrukują się dokładnie tak, jak w projekcie";
    }
    case "flatten": return "spłaszczyliśmy projekt do jednego obrazu w rozdzielczości druku — cienie i przezroczystości wydrukują się tak jak na podglądzie";
    default: return t;
  }
}
function prepLine(t) {
  if (/^warstwy \(\d+\) — wszystkie się drukują/.test(t) || /UserUnit|zabezpieczenie pliku/.test(t)) return "";   // nic się nie zmieniło w wyglądzie
  if (/^warstwy, które się nie drukują/.test(t)) return "usunęliśmy warstwy oznaczone w pliku jako niedrukowane";
  if (/^warstwy ukryte na ekranie, ale drukowane/.test(t)) return "warstwy ukryte w pliku, ale ustawione do druku, zostały w projekcie (tak, jak wydrukowałaby je drukarnia)";
  const a = t.match(/^adnotacje, które się drukują: (.*?) — /);
  if (a) return `elementy Acrobata ustawione do druku (${a[1]}) wpisaliśmy na stałe w projekt`;
  const b = t.match(/^adnotacje, które się nie drukują: (.*?) — /);
  if (b) return `usunęliśmy komentarze Acrobata, które się nie drukują (${b[1]})`;
  if (/^plik był uszkodzony/.test(t)) return "plik był uszkodzony — naprawiliśmy go przy otwarciu; prosimy sprawdzić, czy niczego w nim nie brakuje";
  return t;
}
function clientText() {
  const f = S.job.file, rot = f.rot || 0, pr = printMm();
  const what = [S.product?.name, S.product ? template()?.role : "", pr ? `${fmtMm(pr.w)} × ${fmtMm(pr.h)} mm` : ""].filter(Boolean).join(", ");
  const done = [rot ? `obróciliśmy projekt ${ROT_TXT[rot]}` : "",
    ...(f.prepared || []).map(prepLine), ...S.job.versions.slice(1).map(stepLine)].filter(Boolean);
  // uwagi — to, czego program nie poprawił, a klient powinien wiedzieć
  const fw = fontWarnings(), fl = fw.filter((x) => !x.baked), fb = fw.filter((x) => x.baked);
  const ha = S.analysisFor === factsKey() && S.analysis && !S.analysis.error ? S.analysis : null;
  const wo = (ha?.white_overprint || []).length, ink = inkNow(), d = S.qual.data;
  const nm = (l) => l.map((x) => x.name).join(", ");
  const g0 = d?.status === "done" && d.groups ? d.groups.map((g) => d.areas[g.i]).find((a) => a.reason !== "jpeg") : null;
  const notes = [
    fl.length ? `w pliku brakuje fontu ${nm(fl)} — przy druku zostanie podstawiony inny krój` : "",
    fb.length ? `litery fontu ${nm(fb)} mają kształt kroju zastępczego (fontu nie było w pliku)` : "",
    wo ? `biały element z nadrukiem (overprint) może w druku zniknąć` : "",
    ink?.boxes?.length ? `w ${ink.boxes.length} ${plural(ink.boxes.length, "miejscu", "miejscach", "miejscach")} jest za dużo farby (do ${ink.max} %) — może się rozmazać` : "",
    d?.status === "done" && d.verdict === "bad" && g0 ? `część obrazów ma za małą rozdzielczość (ok. ${Math.round(g0.ppi)} ppi przy wymaganych ${REQ}) — na wydruku będą rozmyte` : "",
    d?.status === "done" && d.verdict !== "bad" && d.look ? `w ${d.look} ${plural(d.look, "miejscu", "miejscach", "miejscach")} obrazy mogą wyglądać na nieostre` : "",
  ].filter(Boolean);
  const li = (l) => l.map((x) => `- ${x}`).join("\n");
  return `Dzień dobry,\n\n`
    + (done.length ? `przygotowując plik „${f.name}” do druku${what ? ` (${what})` : ""}, `
        + `wprowadziliśmy następujące zmiany:\n${li(done)}\n`
      : `plik „${f.name}” sprawdziliśmy przed drukiem — nie wymagał zmian.\n`)
    + (notes.length ? `\nUwagi do projektu:\n${li(notes)}\n` : "");
}
$("acCopy").addEventListener("click", async () => {
  const ta = $("acClientTxt"), b = $("acCopy");
  try { await navigator.clipboard.writeText(ta.value); }
  catch (_) { ta.select(); document.execCommand("copy"); }
  b.textContent = "Skopiowano ✓";
  setTimeout(() => { b.textContent = "Kopiuj"; }, 1500);
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
  const txt = clientText(), ta = $("acClientTxt");
  if (ta.dataset.src !== txt) {                    // tylko gdy zmienił się plik — własne poprawki zostają
    ta.dataset.src = txt; ta.value = txt;
    ta.rows = Math.min(18, txt.split("\n").length + 1);
  }
  $("acClient").hidden = false;
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
  brief("dlBrief", bad ? `<span class="warn">Obrazy są za małe</span> — na wydruku będą rozmyte.` : `<span class="ok">Plik gotowy do druku.</span>`);
  $("dlSay").innerHTML = bad
    ? `<span class="say warn">Plik można pobrać, ale obrazy są za małe</span> — na wydruku będą rozmyte.`
    : `<span class="say ok">Plik gotowy do druku.</span>`;
  // brak fontu (Tomasz 29.09): można drukować, ale ma być o tym informacja
  const fw = fontWarnings(), fb = fw.filter((f) => f.baked), fl = fw.filter((f) => !f.baked);
  const ha = S.analysisFor === factsKey() && S.analysis && !S.analysis.error ? S.analysis : null;
  const wo = (ha?.white_overprint || []).length, ink = inkNow();
  const nm = (l) => esc(l.map((f) => f.name).join(", "));
  $("dlSum").innerHTML = (fl.length ? `<li class="warn">Brak fontu w pliku: <b>${nm(fl)}</b> — `
      + `drukarnia podstawi swój krój, litery wyjdą inne.</li>` : "")
    + (fb.length ? `<li class="warn">Krój zastępczy utrwalony (krzywe / spłaszczenie): <b>${nm(fb)}</b> — `
      + `te litery wyjdą innym krojem niż w projekcie.</li>` : "")
    + (wo ? `<li class="warn">Biel z overprintem (${wo} ${plural(wo, "miejsce", "miejsca", "miejsc")}) — może w druku zniknąć.</li>` : "")
    + (ink?.boxes?.length ? `<li class="warn">Za dużo farby: do ${ink.max} % (limit ${ink.limit} %) — może się rozmazać.</li>` : "")
    + (done.length ? `<li>Zrobione: ${esc(done.join(", "))}.</li>` : `<li>Bez poprawek.</li>`)
    + (left.length ? `<li>Zostawione jak były: ${esc(left.join(", "))}.</li>` : "")
    + (S.job.file.page_count > 1 ? `<li>Tylko strona ${S.page + 1} z ${S.job.file.page_count}.</li>` : "");
  const name = fileName();
  const ext = isPdf() ? "pdf" : "";           // obraz: rozszerzenie po ostatniej wersji (JPG / TIFF)
  const a = $("dlDo");
  a.href = `/api/jobs/${S.job.job_id}/download?v=${head().id}&page=${S.page}&name=${encodeURIComponent(name)}`;
  $("dlName").textContent = saved?.v === head().id ? saved.txt : `Nazwa pliku: ${name}${ext ? "." + ext : ""}`;
}
