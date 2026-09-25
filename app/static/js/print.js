// Rozdziały „Kolory", „Overprint", „Fonty" i „Spłaszczenie" (etap 3).
// Każdy: fakty o stronie (analiza ostatniej wersji) → jedno zdanie → wybór. Kolory i overprint:
// wybór w rzędach, zawsze kończony „Pokaż, jak wydrukuje" (symulacja druku); fonty
// i spłaszczenie: przycisk poprawki i „zostaw jak jest", po poprawce suwak przed/po.
import { $, esc, chapter } from "./util.js";
import { S, changed, hasStep, isPdf, facts, colorNeed, fileProfile, transparencyKinds, flattenPlan, scaleK,
         sizeSettled, colorSettled, overprintSettled, fontsSettled } from "./state.js";
import { applyStep, undoStep } from "./steps.js";

const stepText = (name) => S.job.versions.find((v) => v.step === name)?.text || "";
const loading = (what) => `<span class="spin"></span>Sprawdzam ${what}…`;
const nf = (n) => n.toLocaleString("pl-PL");

// ------------------------------------------------------------------ wybór w rzędach
// Kolory, overprint, fonty i spłaszczenie (Tomasz 24.09): w każdym rzędzie wybiera się JEDEN przycisk (biały →
// niebieski), a rozdział zamyka się dopiero, gdy wybrano w każdym rzędzie. Ostatni rząd to
// zawsze „Pokaż, jak wydrukuje" — nikt nie przejdzie dalej, nie widząc wydruku.
const choice = (name) => (S.choice[name] ||= { act: null, profile: null, seen: false });
const pick = (id, v) => document.querySelectorAll(`#${id} button`).forEach((b) =>
  b.classList.toggle("on", b.dataset.v ? b.dataset.v === v : !!v));
const lockRows = (ids) => ids.forEach((id) => document.querySelectorAll(`#${id} button`).forEach((b) => { b.disabled = !!S.busy; }));

// Zmiana decyzji w pierwszym rzędzie: cofamy poprawkę (albo decyzję) — z pytaniem, gdy
// po niej zrobiono coś jeszcze. false = użytkownik zrezygnował.
async function reopen(name) {
  if (!hasStep(name) && !S.settle[name]) return true;
  return await undoStep(name);
}
async function setAct(name, act) {
  if (S.busy || choice(name).act === act) return;
  if (!(await reopen(name))) return;
  S.choice[name] = { act, profile: null, seen: false };
  S.sim = null; S.cmp = null;
  changed();
  if (act === "fix") await applyStep(name, name === "flatten" ? { k: scaleK() } : {});
}
// „Cofnij" w starszym rozdziale (klasa `past`, main.render): cofa do tego rozdziału — razem
// z krokami zrobionymi później (undoStep pyta, gdy jakieś są).
document.querySelectorAll(".ch-back button").forEach((b) => b.addEventListener("click", () => {
  if (!S.busy) undoStep(b.dataset.back);
}));
const SIM = { cmyk: "proof", overprint: "op", outline: "print", flatten: "print" };
const CH = { cmyk: "ch-color", overprint: "ch-op", outline: "ch-fonts", flatten: "ch-flat" };
function setSeen(name) {
  const c = choice(name);
  if (S.busy || c.seen || !c.act) return;
  if (c.act === "keep") {
    c.seen = true; S.settle[name] = "skip";
    S.sim = SIM[name]; S.simMix = 100;   // suwak ekran ↔ druk
  } else {
    if (!hasStep(name)) return;
    c.seen = true; S.settle[name] = "done";
  }
  S.cmp = null;
  // rozdział zostaje ROZWINIĘTY — właśnie kliknięto „Pokaż", więc suwak ma być widać — także
  // gdy zaraz pojawią się kolejne rozdziały zaliczone same (main.render, S.pin)
  S.pin = CH[name];
  $(CH[name]).classList.add("open");
  changed();
}

// ------------------------------------------------------------------ kolory
document.querySelectorAll("#coAct button").forEach((b) => b.addEventListener("click", () => setAct("cmyk", b.dataset.v)));
document.querySelectorAll("#coProf button").forEach((b) => b.addEventListener("click", async () => {
  const c = choice("cmyk"), p = b.dataset.v;
  if (S.busy || (c.profile === p && hasStep("cmyk"))) return;
  if (hasStep("cmyk")) {                        // inny profil = zamiana od nowa
    if (!(await undoStep("cmyk"))) return;
    S.choice.cmyk = { act: "convert", profile: null, seen: false };
  }
  S.choice.cmyk.profile = p; S.cmykProfile = p;
  changed();
  await applyStep("cmyk", { profile: p });
  if (!hasStep("cmyk")) { S.choice.cmyk.profile = null; changed(); }   // błąd — wybór wraca
}));
$("coSeen").querySelector("button").addEventListener("click", () => setSeen("cmyk"));

export function renderColor() {
  const el = $("ch-color");
  el.hidden = !sizeSettled();
  if (el.hidden) return;
  const on = hasStep("cmyk"), a = facts(), c = choice("cmyk");
  // fakty o kolorach bierzemy z wersji PRZED zamianą (po niej wszystko jest już w CMYK-u)
  const need = on ? { any: true } : (colorNeed(a) || { any: false });
  let st = "todo", sum = "", say = "", note = "";
  if (!on && !c.act && !a) {
    st = "open"; say = loading("kolory");
  } else if (!on && !c.act && a.error) {
    st = "done"; sum = "nie udało się sprawdzić";
    say = `<span class="say warn">Nie udało się sprawdzić kolorów.</span>`; note = esc(a.error);
  } else if (!on && !c.act && !need.any) {
    st = "done"; sum = "CMYK";
    say = `<span class="say ok">Kolory są w CMYK — w porządku.</span>`;
  } else {
    if (S.settle.cmyk) st = "done";
    if (c.act === "convert") {
      sum = S.settle.cmyk ? "CMYK" : "";
      say = on ? `<span class="say ok">Kolory zamienione na CMYK.</span> `
                 + (c.seen ? "<b>Podgląd pokazuje teraz wydruk</b><span class=\"now-only\">; suwakiem porównasz go z ekranem sprzed zamiany</span>." : "Zobacz, jak to wydrukuje.")
               : S.busy ? "Zamieniam kolory na CMYK…" : "Wybierz profil kolorów, który zostanie zapisany w pliku.";
      if (on) note = esc(stepText("cmyk"));
    } else if (c.act === "keep") {
      sum = S.settle.cmyk ? "zostawione" : "";
      say = c.seen ? "Kolory zostają jak są — drukarnia przeliczy je sama. <b>Podgląd pokazuje teraz, jak wyjdą z drukarki.</b>"
                   : "Kolory zostają jak są. Zobacz, jak wyjdą z drukarki.";
    } else {
      const n = colorNeed(a);
      const what = [n.rgb && "<b>RGB</b>", n.lab && "<b>Lab</b>",
        n.spots.length && `<b>dodatkowe</b> (${esc(n.spots.slice(0, 3).join(", "))}${n.spots.length > 3 ? "…" : ""})`,
        n.other && "<b>inne</b>"].filter(Boolean);
      say = `W projekcie są kolory ${what.join(" i ")}. Drukujemy w CMYK — lepiej przeliczyć je tutaj `
        + `i zobaczyć wynik, niż zdać się na drukarnię.`;
    }
  }
  chapter("ch-color", st, sum);
  $("coSay").innerHTML = say;
  $("coNote").innerHTML = note; $("coNote").hidden = !note;
  $("coErr").hidden = !S.stepErr.cmyk; $("coErr").textContent = S.stepErr.cmyk || "";
  const rows = need.any || !!c.act;
  $("coAct").hidden = !rows;
  pick("coAct", c.act);
  // rząd 2 przy zamianie: profil („z pliku" — tylko gdy plik jakiś ma)
  const fp = isPdf() ? fileProfile(a) : "";
  $("coProf").hidden = !(rows && c.act === "convert");
  document.querySelectorAll("#coProf button").forEach((b) => {
    // po zamianie plik ma już NASZ profil — „z pliku" znaczy tylko profil sprzed zamiany
    if (b.dataset.v === "keep") { b.hidden = c.profile !== "keep" && (!fp || on); b.title = fp && !on ? `Zostaje profil zapisany w pliku: ${fp}` : ""; }
  });
  pick("coProf", c.profile);
  // ostatni rząd: „Pokaż, jak wydrukuje" — przy zamianie dopiero, gdy zamiana gotowa
  $("coSeen").hidden = !(rows && (c.act === "keep" || (c.act === "convert" && on)));
  pick("coSeen", c.seen);
  lockRows(["coAct", "coProf", "coSeen"]);
  // suwaki: zostawione → ekran ↔ druk (symulacja), zamienione → przed ↔ po
  $("coSimBar").hidden = !(c.act === "keep" && c.seen);
  if (S.sim !== "proof") $("coSimBar").querySelector("input").value = 100;
  $("coMini").hidden = !(on && c.seen);
  if (S.cmp?.step !== "cmyk") $("coMini").querySelector("input").value = 100;
}

// ------------------------------------------------------------------ overprint
document.querySelectorAll("#opAct button").forEach((b) => b.addEventListener("click", () => setAct("overprint", b.dataset.v)));
$("opSeen").querySelector("button").addEventListener("click", () => setSeen("overprint"));

export function renderOverprint() {
  const el = $("ch-op");
  el.hidden = !colorSettled() || !isPdf();
  if (el.hidden) return;
  const on = hasStep("overprint"), a = facts(), c = choice("overprint");
  const uses = on || (a && !a.error ? a.overprint_uses || 0 : 0);
  let st = "todo", sum = "", say = "", note = "";
  if (!on && !c.act && !a) {
    st = "open"; say = loading("overprint");
  } else if (!on && !c.act && a.error) {
    st = "done"; sum = "nie udało się sprawdzić";
    say = `<span class="say warn">Nie udało się sprawdzić overprintu.</span>`;
  } else if (!on && !c.act && !uses) {
    st = "done"; sum = "brak";
    say = `<span class="say ok">Projekt nie używa overprintu.</span>`;
  } else {
    if (S.settle.overprint) st = "done";
    if (c.act === "fix") {
      sum = S.settle.overprint ? "wyłączony" : "";
      say = on ? `<span class="say ok">Overprint wyłączony</span> — wydrukuje się to, co widać na ekranie. `
                 + (c.seen ? "<span class=\"now-only\">Suwak niżej pokazuje wydruk przed i po.</span>" : "Zobacz, jak to wydrukuje.")
               : S.busy ? "Wyłączam overprint…" : "Nie udało się wyłączyć overprintu.";
    } else if (c.act === "keep") {
      sum = S.settle.overprint ? "zostawiony" : "";
      say = c.seen ? "Overprint zostaje. <b>Podgląd pokazuje teraz wydruk z overprintem</b> — tak to wyjdzie z drukarki."
                   : "Overprint zostaje. Zobacz, jak to wyjdzie z drukarki.";
    } else {
      say = `W projekcie jest <b>overprint</b> (nadruk): farba kładzie się na tło zamiast je zakryć, `
        + `więc w druku część elementów wyjdzie inaczej niż na ekranie. Wytyczne go nie dopuszczają.`;
    }
  }
  chapter("ch-op", st, sum);
  $("opSay").innerHTML = say;
  $("opNote").innerHTML = note; $("opNote").hidden = !note;
  $("opErr").hidden = !S.stepErr.overprint; $("opErr").textContent = S.stepErr.overprint || "";
  const rows = !!uses || !!c.act;
  $("opAct").hidden = !rows;
  pick("opAct", c.act);
  $("opSeen").hidden = !(rows && (c.act === "keep" || (c.act === "fix" && on)));
  pick("opSeen", c.seen);
  lockRows(["opAct", "opSeen"]);
  $("opSimBar").hidden = !(c.act === "keep" && c.seen);
  if (S.sim !== "op") $("opSimBar").querySelector("input").value = 100;
  $("opMini").hidden = !(on && c.seen);
  if (S.cmp?.step !== "overprint") $("opMini").querySelector("input").value = 100;
}

// ------------------------------------------------------------------ fonty
document.querySelectorAll("#foAct button").forEach((b) => b.addEventListener("click", () => setAct("outline", b.dataset.v)));
$("foSeen").querySelector("button").addEventListener("click", () => setSeen("outline"));

export function renderFonts() {
  const el = $("ch-fonts");
  el.hidden = !overprintSettled() || !isPdf();
  if (el.hidden) return;
  const on = hasStep("outline"), a = facts(), c = choice("outline");
  const fonts = a && !a.error ? a.fonts || [] : [];
  const any = on || fonts.length > 0;
  let st = "todo", sum = "", say = "", note = "";
  if (!on && !c.act && !a) {
    st = "open"; say = loading("fonty");
  } else if (!on && !c.act && a.error) {
    st = "done"; sum = "nie udało się sprawdzić";
    say = `<span class="say warn">Nie udało się sprawdzić fontów.</span>`;
  } else if (!on && !c.act && !any) {
    st = "done"; sum = "brak tekstu";
    say = `<span class="say ok">W projekcie nie ma tekstu w fontach</span> — nie ma czego zamieniać.`;
  } else {
    if (S.settle.outline) st = "done";
    if (c.act === "fix") {
      sum = S.settle.outline ? "na krzywych" : "";
      say = on ? `<span class="say ok">Tekst zamieniony na krzywe.</span> `
                 + (c.seen ? "<span class=\"now-only\">Suwakiem niżej porównasz przed i po.</span>" : "Zobacz, jak to wydrukuje.")
               : S.busy ? "Zamieniam tekst na krzywe…" : "Nie udało się zamienić tekstu na krzywe.";
      if (on) note = esc(stepText("outline"));
    } else if (c.act === "keep") {
      sum = S.settle.outline ? "zostawione" : "";
      say = c.seen ? "Tekst zostaje w fontach — drukarnia złoży go swoim programem."
                   : "Tekst zostaje w fontach. Zobacz, jak to wydrukuje.";
    } else {
      say = `Tekst w projekcie jest zapisany fontami (${fonts.length}). Zamiana na krzywe gwarantuje, `
        + `że w drukarni wyjdzie dokładnie ten sam kształt liter.`;
      const miss = fonts.filter((f) => !f.embedded && !isBase14(f.name)).map((f) => f.name.split("+").pop());
      if (miss.length) note = `${miss.length === 1 ? "Font" : "Fonty"} ${esc(miss.join(", "))} `
        + `${miss.length === 1 ? "nie jest osadzony" : "nie są osadzone"} w pliku — program poszuka `
        + `${miss.length === 1 ? "go" : "ich"} w Google Fonts i w systemie. Kroju zastępczego nie użyje.`;
    }
  }
  chapter("ch-fonts", st, sum);
  $("foSay").innerHTML = say;
  $("foNote").innerHTML = note; $("foNote").hidden = !note;
  rowsFor("fo", "outline", any || !!c.act, on);
}
const BASE14 = new Set(["helvetica", "helvetica-bold", "helvetica-oblique", "helvetica-boldoblique", "times-roman",
  "times-bold", "times-italic", "times-bolditalic", "courier", "courier-bold", "courier-oblique",
  "courier-boldoblique", "symbol", "zapfdingbats"]);
const isBase14 = (n) => BASE14.has((n || "").split("+").pop().toLowerCase().replace(",", "-").replace(/ /g, ""));

// ------------------------------------------------------------------ spłaszczenie
document.querySelectorAll("#flAct button").forEach((b) => b.addEventListener("click", () => setAct("flatten", b.dataset.v)));
$("flSeen").querySelector("button").addEventListener("click", () => setSeen("flatten"));

export function renderFlatten() {
  const el = $("ch-flat");
  el.hidden = !fontsSettled() || !isPdf();
  if (el.hidden) return;
  const on = hasStep("flatten"), a = facts(), c = choice("flatten");
  const kinds = a && !a.error ? transparencyKinds(a) : [];
  const pl = flattenPlan();
  const plan = pl ? `Strona stanie się jednym obrazem CMYK ${nf(pl.px[0])} × ${nf(pl.px[1])} px `
    + `(${pl.ppi} ppi na wydruku). Tekst i linie przestaną być wektorowe.` : "";
  let st = "todo", sum = "", say = "", note = "";
  if (!on && !c.act && !a) {
    st = "open"; say = loading("przezroczystość");
  } else if (!on && !c.act && a.error) {
    st = "done"; sum = "nie udało się sprawdzić";
    say = `<span class="say warn">Nie udało się sprawdzić przezroczystości.</span>`;
  } else {
    if (S.settle.flatten) st = "done";
    if (c.act === "fix") {
      sum = S.settle.flatten ? "spłaszczone" : "";
      say = on ? `<span class="say ok">Projekt spłaszczony</span> — na maszynę pójdzie dokładnie to, co widać. `
                 + (c.seen ? "" : "Zobacz, jak to wydrukuje.")
               : S.busy ? "Spłaszczam projekt…" : "Nie udało się spłaszczyć projektu.";
      note = on ? esc(stepText("flatten")) : plan;
    } else if (c.act === "keep") {
      sum = S.settle.flatten ? "zostawione" : "";
      say = c.seen ? "Projekt zostaje warstwowy — przezroczystość spłaszczy drukarnia."
                   : "Projekt zostaje warstwowy. Zobacz, jak to wydrukuje.";
    } else if (kinds.length) {
      say = `W projekcie jest <b>przezroczystość</b> (${esc(kinds.join(", "))}). Drukarnia spłaszcza ją `
        + `sama i czasem zostawia ślady — jasne obwódki, szwy. Bezpieczniej spłaszczyć tutaj.`;
      note = plan;
    } else {
      // bez przezroczystości rozdział jest od razu zamknięty; spłaszczyć można i tak
      st = "done"; sum = "niepotrzebne";
      say = `<span class="say ok">Projekt nie ma przezroczystości</span> — spłaszczać nie trzeba.`;
      note = plan;
    }
  }
  chapter("ch-flat", st, sum);
  $("flSay").innerHTML = say;
  $("flNote").innerHTML = note; $("flNote").hidden = !note;
  rowsFor("fl", "flatten", !!a && !a.error || on || !!c.act, on);
}

// Wspólne rzędy fontów i spłaszczenia: [poprawka | zostaw] → [Pokaż, jak wydrukuje] → suwak.
function rowsFor(pre, name, show, on) {
  const c = choice(name);
  $(pre + "Err").hidden = !S.stepErr[name]; $(pre + "Err").textContent = S.stepErr[name] || "";
  $(pre + "Act").hidden = !show;
  pick(pre + "Act", c.act);
  $(pre + "Seen").hidden = !(show && (c.act === "keep" || (c.act === "fix" && on)));
  pick(pre + "Seen", c.seen);
  lockRows([pre + "Act", pre + "Seen"]);
  $(pre + "SimBar").hidden = !(c.act === "keep" && c.seen);
  if (S.sim !== $(pre + "SimBar").dataset.sim) $(pre + "SimBar").querySelector("input").value = 100;
  $(pre + "Mini").hidden = !(on && c.seen);
  if (S.cmp?.step !== name) $(pre + "Mini").querySelector("input").value = 100;
}

// Warstwy podglądu w trakcie symulacji (suwak ekran ↔ druk): {mix, bottom, top} — flagi
// op/pr obu warstw. proof = same kolory, op = druk bez ↔ z overprintem, print = ekran ↔ pełny druk.
export function simLayers() {
  if (!S.sim || S.cmp) return null;
  const F = { proof: [{ op: false, pr: false }, { op: false, pr: true }],
              op: [{ op: false, pr: true }, { op: true, pr: true }],
              print: [{ op: false, pr: false }, { op: true, pr: true }] }[S.sim];
  return F ? { mix: S.simMix / 100, bottom: F[0], top: F[1] } : null;
}
// Porównanie przed/po dla overprintu i spłaszczenia ma sens tylko Z symulacją overprintu —
// bez niej obie strony suwaka wyglądają tak samo (tak pracuje maszyna).
export const CMP_WITH_OP = ["overprint", "flatten"];
