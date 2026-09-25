// Stan programu w jednym miejscu. Każda zmiana woła `changed()` — to przerysowuje
// wszystkie rozdziały i podgląd naraz (jedna ścieżka rysowania zamiast dziesiątek „update…").
export const S = {
  // produkty
  products: [], productsStatus: null,
  // plik
  job: null,               // {job_id, file, suggestions, versions:[{id, step, text, pages_mm, map}]}
  analysis: null,          // analiza OSTATNIEJ wersji pliku
  analysisFor: null,       // id wersji, której dotyczy `analysis`
  // produkt
  candidate: null,         // produkt na karcie do potwierdzenia
  product: null,           // produkt POTWIERDZONY
  picking: false,          // użytkownik chce wybrać inny produkt z listy
  customOpen: false,       // formularz wymiaru dla produktu spoza listy
  custom: null,            // potwierdzony wymiar spoza listy {w, h} (mm wydruku)
  // wytyczne i rola
  guidelines: null, glLoading: false, glError: "",
  tplIndex: 0,             // wybrany szablon (rola)
  tplDims: null,           // wymiar podany dla szablonu „0 × 0" {w, h} (mm wydruku)
  roleOk: false,
  // strona
  page: 0, pageOk: false,
  // poprawki (etap 2+)
  busy: null,              // co się właśnie nakłada (napis na podglądzie) albo null
  stepErr: {},             // nazwa poprawki → komunikat błędu
  settle: {},              // rozdziały domknięte bez poprawki: {frames: "skip", trim: "skip", resize: "ok"}
  choice: {},              // wybór w rzędach (Kolory, Overprint): {act, profile, seen}
  fscan: { key: "", data: null, err: "" },   // wynik szukania szablonu z wytycznych
  qual: { key: "", data: null, err: "" },    // ocena jakości wydruku (etap 4)
  accShown: null,          // wersja, dla której w „Akceptacji" obejrzano wydruk przed i po
  sz: null,                // ustawienia rozdziału „Wymiar" (suwaki)
  sizeEdit: false,         // wymiar się zgadza, ale użytkownik chce poprawić kadr
  cmp: null,               // suwak w rozdziale: {step, v}
  sim: null,               // symulacja druku w rozdziale: "proof" (kolory) | "op" (overprint) | null
  simMix: 100,             // suwak symulacji: 0 = jak na ekranie, 100 = jak z drukarki
  cmykProfile: "fogra39",  // profil przy zamianie na CMYK: fogra39 | keep | none
  // podgląd
  overlayOn: false,
  cssPxPerIn: 96, calibrated: false,
};

try {
  const v = parseFloat(localStorage.getItem("adcheck.cssPxPerIn"));
  if (v > 20 && v < 1000) { S.cssPxPerIn = v; S.calibrated = true; }
} catch (_) {}

// Nowy plik = czysta kartka. BŁĄD do 0.4.1 (Tomasz 25.09): decyzje z rozdziałów (settle, choice)
// zostawały po poprzednim pliku — przy drugim wgraniu Kolory i Overprint były „domknięte”, choć na
// nowym pliku nic nie zrobiono („Nie udało się wyłączyć overprintu”, „…zamienić tekstu na krzywe”).
export function resetJobState() {
  Object.assign(S, {
    settle: {}, choice: {}, stepErr: {}, busy: null,
    fscan: { key: "", data: null, err: "" }, qual: { key: "", data: null, err: "" },
    accShown: null, sz: null, sizeEdit: false, cmp: null, sim: null, simMix: 100, cmykProfile: "fogra39",
  });
}

const subs = [];
let queued = false;
export function onChange(fn) { subs.push(fn); }
export function changed() {
  if (queued) return;
  queued = true;
  requestAnimationFrame(() => { queued = false; for (const f of subs) f(); });
}

// ---------------------------------------------------------------- pochodne
export const head = () => S.job ? S.job.versions[S.job.versions.length - 1] : null;
export const original = () => S.job ? S.job.versions[0] : null;
export const template = () => S.guidelines?.templates?.[S.tplIndex] || null;
export const scaleK = () => (S.guidelines?.scale === "1:10" ? 10 : 1);   // wydruk / plik
export const productOk = () => !!S.product || !!S.custom;
export const isPdf = () => !!S.job && S.job.file.kind !== "raster";
export const hasStep = (name) => !!S.job && S.job.versions.some((v) => v.step === name);

// Wymiar strony (mm pliku) w danej wersji — dla wybranej strony.
export function pageMm(v = head()) {
  if (!v) return null;
  const p = v.pages_mm?.[S.page];
  return p && p[0] > 0 && p[1] > 0 ? { w: p[0], h: p[1] } : null;
}

// Docelowy wymiar W JEDNOSTKACH PLIKU (wytyczne podają wymiar pliku; skala 1:10 = wydruk 10×).
export function targetMm() {
  const t = template();
  if (S.product && t) {
    if (!t.dims_missing && t.width_mm > 0) return { w: t.width_mm, h: t.height_mm };
    return S.tplDims ? { w: S.tplDims.w / scaleK(), h: S.tplDims.h / scaleK() } : null;
  }
  return S.custom ? { w: S.custom.w, h: S.custom.h } : null;
}

// Rozmiar WYDRUKU (mm) — od niego zależy każde ppi.
export function printMm() {
  const t = targetMm();
  if (t) return { w: t.w * scaleK(), h: t.h * scaleK() };
  const p = pageMm();
  return p ? { w: p.w * scaleK(), h: p.h * scaleK() } : null;
}

// Rozdziały idą po kolei — każdy następny dopiero, gdy poprzedni jest domknięty:
// plik → strona (gdy jest ich kilka) → produkt → rola.
export function pageSettled() {
  return !!S.job && !!S.analysisFor && (S.job.file.page_count < 2 || S.pageOk);
}
export function roleSettled() {
  if (!pageSettled() || !productOk()) return false;
  if (S.custom) return true;
  return !!S.guidelines && S.roleOk && (!template()?.dims_missing || !!S.tplDims);
}

// ---------------------------------------------------------------- poprawki
export const STEP_ORDER = ["frames", "trim", "resize", "cmyk", "overprint", "outline", "flatten"];
export const STEP_NAME = { frames: "usunięcie szablonu", trim: "przycięcie spadów", resize: "dopasowanie wymiaru",
  cmyk: "przeliczenie kolorów na CMYK", overprint: "wyłączenie overprintu", outline: "przekształcenie tekstu w krzywe",
  flatten: "spłaszczenie" };      // rodzaj nijaki — pasuje też w pytaniu „Cofnąć …?"
export const stepIndex = (name) => S.job ? S.job.versions.findIndex((v) => v.step === name) : -1;
// Wersja tuż PRZED danym rozdziałem: gdy poprawka jest nałożona — poprzednia w łańcuchu,
// gdy nie — ostatnia (na niej zadziała).
export function beforeStep(name) {
  const i = stepIndex(name);
  return i > 0 ? S.job.versions[i - 1] : head();
}

// Spady: z ramek PDF-a (TrimBox/ArtBox), a bez nich — strona RÓWNOMIERNIE większa od formatu
// z wytycznych (spad dorobiony powiększeniem obszaru roboczego).
export function trimInfo() {
  if (!S.job || !isPdf()) return null;
  const p = S.job.file.pages[S.page], t = targetMm();
  if (p.trim_mm && p.trim_mm[0] > 0) {
    return { src: p.trim_src || "TrimBox", net: p.trim_mm, bleed: p.bleed_mm,
             fits: !!t && Math.abs(p.trim_mm[0] - t.w) < 0.5 && Math.abs(p.trim_mm[1] - t.h) < 0.5 };
  }
  if (t && p.width_mm) {
    const dx = (p.width_mm - t.w) / 2, dy = (p.height_mm - t.h) / 2;
    if (dx > 0.4 && dy > 0.4 && dx < 30 && dy < 30 && Math.abs(dx - dy) < 0.6)
      return { src: "wytyczne", net: [t.w, t.h], bleed: [dx, dy, dx, dy], fits: true };
  }
  return null;
}

// Szablon z wytycznych: domknięty, gdy usunięty, świadomie zostawiony, albo nic nie znaleziono.
export function framesSettled() {
  if (!roleSettled()) return false;
  if (hasStep("frames") || S.settle.frames) return true;
  const d = S.fscan.data;
  if (S.fscan.err) return true;                    // szukanie padło — nie blokujemy reszty
  return !!d && (!d.found || d.hidden) && !d.pixels && !d.foreign;
}
export function trimSettled() {
  return framesSettled() && (hasStep("trim") || !!S.settle.trim || !trimInfo());
}
export function sizeMatches() {
  const f = pageMm(beforeStep("resize")), t = targetMm();
  if (!f || !t || !isPdf()) return true;
  return Math.abs(f.w - t.w) < 0.5 && Math.abs(f.h - t.h) < 0.5;
}
export function sizeSettled() {
  return trimSettled() && (hasStep("resize") || S.settle.resize === "ok");
}

// ---------------------------------------------------------------- etap 3: kolory → overprint → fonty → spłaszczenie
// Fakty o OSTATNIEJ wersji pliku, o wybranej stronie (analiza). null = jeszcze się liczą.
export const factsKey = () => (S.job && head() ? `${head().id}:${S.page}` : "");
export function facts() {
  if (!S.job || S.analysisFor !== factsKey() || !S.analysis) return null;
  return S.analysis;
}
const factsFailed = () => S.analysisFor === factsKey() && !!S.analysis?.error;

// Co w kolorach trzeba przeliczyć (tak samo liczy serwer: steps.color_need). Gray obok
// CMYK nie jest problemem — drukuje się czarną farbą.
export function colorNeed(a = facts()) {
  if (!a || a.error) return null;
  const c = a.color || {}, fam = Object.keys(c.families || {});
  const spots = (c.spots || []).map((s) => (s.name === "All" ? "Registration" : s.name));
  const rgb = fam.some((f) => f.startsWith("RGB")), lab = fam.includes("Lab");
  const other = fam.includes("Unknown") || fam.includes("Indexed");
  return { rgb, lab, spots, other, any: rgb || lab || other || spots.length > 0 };
}
// Profil CMYK zapisany w pliku (deklaracja albo osadzony) — do wyboru „zostaw profil z pliku".
export function fileProfile(a = facts()) {
  const c = a?.color || {};
  const oi = (c.output_intents || []).find((o) => o.profile_space === "CMYK" || o.profile);
  if (oi) return oi.identifier || oi.profile || "profil z pliku";
  const icc = (c.icc_profiles || []).find((p) => p.family === "CMYK");
  return icc ? icc.desc : "";
}
// Przezroczystość, która naprawdę coś robi. Sama „grupa przezroczystości" (Illustrator dodaje
// ją do każdej strony) niczego nie miesza — nie jest powodem do spłaszczania.
export function transparencyKinds(a = facts()) {
  const out = new Set();
  for (const k of Object.keys(a?.transparency || {})) {
    if (k.includes("grupa przezroczystości")) continue;
    out.add(k.startsWith("krycie") ? "półprzezroczystość" : k.startsWith("tryb mieszania") ? "tryby mieszania"
      : k.startsWith("obraz z maską") ? "obrazy z przezroczystym tłem" : k.startsWith("maska") ? "maski" : k);
  }
  return [...out];
}

// Kolory i overprint: domknięte dopiero, gdy w KAŻDYM rzędzie coś wybrano (Tomasz 24.09) —
// wtedy `settle` = "done" (poprawione) albo "skip" (zostawione). Bez problemu w pliku — od razu.
function settledByChoice(name, prev, clean) {
  if (!prev) return false;
  if (S.settle[name] || factsFailed()) return true;
  const a = facts();
  return !hasStep(name) && !S.choice[name]?.act && !!a && clean(a);
}
export const colorSettled = () => settledByChoice("cmyk", sizeSettled(), (a) => !colorNeed(a).any);
export const overprintSettled = () => settledByChoice("overprint", colorSettled(), (a) => !isPdf() || !(a.overprint_uses > 0));
export const fontsSettled = () => settledByChoice("outline", overprintSettled(), (a) => !isPdf() || !(a.fonts || []).length);
export const flattenSettled = () => settledByChoice("flatten", fontsSettled(), (a) => !isPdf() || !transparencyKinds(a).length);

// Ile pikseli wyjdzie po spłaszczeniu (to samo liczy serwer: steps.flatten_plan).
export function flattenPlan() {
  const p = pageMm(), k = scaleK();
  if (!p) return null;
  const long = Math.max(p.w, p.h) * k;
  const ppi = long <= 800 ? 300 : long <= 1500 ? 200 : long <= 3000 ? 150 : 120;
  let dpi = ppi * k;
  const px = (mm) => mm / 25.4 * dpi;
  const mpx = px(p.w) * px(p.h) / 1e6;
  const cut = mpx > 400;
  if (cut) dpi *= Math.sqrt(400 / mpx);
  return { ppi: Math.round(dpi / k), want: ppi, cut, px: [Math.round(p.w / 25.4 * dpi), Math.round(p.h / 25.4 * dpi)] };
}
