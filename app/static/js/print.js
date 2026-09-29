// Rozdziały „Symulacja wydruku", „Kolory", „Overprint", „Fonty" i „Spłaszczenie" (etap 3).
// Symulacja wydruku (Tomasz 28.09): od niej podgląd pokazuje WYDRUK, więc dalsze rozdziały nie
// potrzebują już „Pokaż, jak wydrukuje" — suwak przed/po każdej poprawki porównuje wydruk z wydrukiem.
// Każdy z dalszych: fakty o stronie → jedno zdanie → wybór (poprawka albo „Zostaw jak jest").
import { $, esc, chapter } from "./util.js";
import { S, changed, hasStep, isPdf, facts, colorNeed, fileProfile, transparencyKinds, flattenPlan, scaleK,
         sizeSettled, printSettled, colorSettled, overprintSettled, fontsSettled } from "./state.js";
import { applyStep, undoStep } from "./steps.js";

const stepText = (name) => S.job.versions.find((v) => v.step === name)?.text || "";
const loading = (what) => `<span class="spin"></span>Sprawdzam ${what}…`;
const nf = (n) => n.toLocaleString("pl-PL");

// ------------------------------------------------------------------ wybór w rzędach
// Kolory, overprint, fonty i spłaszczenie (Tomasz 24.09): w każdym rzędzie wybiera się JEDEN przycisk (biały →
// niebieski), a rozdział zamyka się dopiero, gdy wybrano w każdym rzędzie.
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
  if (!S.job || S.busy || choice(name).act === act) return;
  if (!(await reopen(name))) return;
  S.choice[name] = { act, profile: null, seen: false };
  S.sim = null; S.cmp = null;
  // „Zostaw jak jest" od razu zamyka rozdział — podgląd już pokazuje, jak to wyjdzie z drukarki
  if (act === "keep") S.settle[name] = "skip";
  changed();
  if (act === "fix") await applyStep(name, name === "flatten" ? { k: scaleK() } : {});
}
// „Cofnij" w starszym rozdziale (klasa `past`, main.render): cofa do tego rozdziału — razem
// z krokami zrobionymi później (undoStep pyta, gdy jakieś są).
document.querySelectorAll(".ch-back button").forEach((b) => b.addEventListener("click", () => {
  if (!S.busy) undoStep(b.dataset.back);
}));

// ------------------------------------------------------------------ symulacja wydruku
$("prOk").addEventListener("click", () => {
  if (!S.job || S.busy) return;
  S.settle.print = "seen"; S.sim = null;
  changed();
});

export function renderPrint() {
  const el = $("ch-print");
  el.hidden = !sizeSettled();
  if (el.hidden) return;
  const ok = printSettled();
  chapter("ch-print", ok ? "done" : "todo", ok ? "podgląd = wydruk" : "");
  $("prSay").innerHTML = ok
    ? `<b>Podgląd pokazuje wydruk.</b> <span class="now-only">Suwaki w kolejnych rozdziałach porównują wydruk przed poprawką z wydrukiem po niej.</span>`
    : `Od tego miejsca <b>podgląd pokazuje, jak projekt wyjdzie z drukarki</b>`
      + (isPdf() ? ` — z kolorami przeliczonymi przez drukarnię i z overprintem.` : ` — z kolorami przeliczonymi przez drukarnię.`)
      + ` Na wydruku kolory są zwykle <b>bledsze</b> niż na ekranie: monitor świeci, a farba tylko odbija`
      + ` światło. To normalne.<br>Przesuń suwak, żeby porównać ekran z wydrukiem.`;
  $("prOk").hidden = ok;
  $("prSimBar").hidden = false;           // chowa go main.render, gdy dalej jest świeższy suwak
  $("prOk").disabled = !!S.busy;
  if (S.sim !== "print") $("prSimBar").querySelector("input").value = 100;
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

export function renderColor() {
  const el = $("ch-color");
  el.hidden = !printSettled();
  if (el.hidden) return;
  const on = hasStep("cmyk"), a = facts("cmyk"), c = choice("cmyk");
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
    if (on) st = "done";
    if (c.act === "convert" || on) {
      sum = on ? "CMYK" : "";
      say = on ? `<span class="say ok">Kolory zamienione na CMYK.</span>`
                 + `<span class="now-only"> Suwakiem porównasz wydruk przed zamianą i po niej.</span>`
               : S.busy ? "Zamieniam kolory na CMYK…" : "Wybierz profil kolorów, który zostanie zapisany w pliku.";
      if (on) note = esc(stepText("cmyk"));
    } else if (c.act === "keep") {
      sum = "zostawione";
      say = "Kolory zostają jak są — drukarnia przeliczy je sama. Podgląd pokazuje, jak wyjdą z drukarki.";
    } else {
      const n = colorNeed(a);
      const what = [n.rgb && "<b>RGB</b>", n.lab && "<b>Lab</b>",
        n.spots.length && `<b>dodatkowe</b> (spot: ${esc(n.spots.slice(0, 3).join(", "))}${n.spots.length > 3 ? "…" : ""})`,
        n.other && "<b>inne</b>"].filter(Boolean);
      say = `W projekcie są kolory ${what.join(" i ")}. Drukujemy w CMYK — lepiej przeliczyć je tutaj `
        + `i zobaczyć wynik, niż zdać się na drukarnię. Podgląd pokazuje teraz, jak przeliczy je drukarnia.`;
    }
  }
  chapter("ch-color", st, sum);
  $("coSay").innerHTML = say;
  $("coNote").innerHTML = note; $("coNote").hidden = !note;
  $("coErr").hidden = !S.stepErr.cmyk; $("coErr").textContent = S.stepErr.cmyk || "";
  const rows = need.any || !!c.act;
  $("coAct").hidden = !rows;
  pick("coAct", on ? "convert" : c.act);
  // rząd 2 przy zamianie: profil („z pliku" — tylko gdy plik jakiś ma)
  const fp = isPdf() ? fileProfile(a) : "";
  $("coProf").hidden = !(rows && c.act === "convert");
  document.querySelectorAll("#coProf button").forEach((b) => {
    // po zamianie plik ma już NASZ profil — „z pliku" znaczy tylko profil sprzed zamiany
    if (b.dataset.v === "keep") { b.hidden = c.profile !== "keep" && (!fp || on); b.title = fp && !on ? `Zostaje profil zapisany w pliku: ${fp}` : ""; }
  });
  pick("coProf", c.profile);
  lockRows(["coAct", "coProf"]);
  // suwak po zamianie: wydruk przed ↔ wydruk po
  $("coMini").hidden = !on;
  if (S.cmp?.step !== "cmyk") $("coMini").querySelector("input").value = 100;
}

// ------------------------------------------------------------------ overprint
document.querySelectorAll("#opAct button").forEach((b) => b.addEventListener("click", () => setAct("overprint", b.dataset.v)));

export function renderOverprint() {
  const el = $("ch-op");
  el.hidden = !colorSettled() || !isPdf();
  if (el.hidden) return;
  const on = hasStep("overprint"), a = facts("overprint"), c = choice("overprint");
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
    if (S.settle.overprint || on) st = "done";
    if (c.act === "fix" || on) {
      sum = on ? "wyłączony" : "";
      say = on ? `<span class="say ok">Overprint wyłączony</span> — elementy nie przepuszczają już tła.`
                 + `<span class="now-only"> Suwak niżej pokazuje wydruk przed i po.</span>`
               : S.busy ? "Wyłączam overprint…" : "Nie udało się wyłączyć overprintu.";
    } else if (c.act === "keep") {
      sum = "zostawiony";
      say = "Overprint zostaje — podgląd pokazuje, jak to wyjdzie z drukarki.";
    } else {
      say = `W projekcie jest <b>overprint</b> (nadruk): farba kładzie się na tło zamiast je zakryć, `
        + `więc w druku część elementów wychodzi inaczej niż na ekranie — podgląd pokazuje już, jak. `
        + `Wytyczne go nie dopuszczają.`;
    }
  }
  chapter("ch-op", st, sum);
  $("opSay").innerHTML = say;
  $("opNote").innerHTML = note; $("opNote").hidden = !note;
  $("opErr").hidden = !S.stepErr.overprint; $("opErr").textContent = S.stepErr.overprint || "";
  const rows = !!uses || !!c.act;
  $("opAct").hidden = !rows;
  pick("opAct", on ? "fix" : c.act);
  lockRows(["opAct"]);
  $("opMini").hidden = !on;
  if (S.cmp?.step !== "overprint") $("opMini").querySelector("input").value = 100;
}

// ------------------------------------------------------------------ fonty
document.querySelectorAll("#foAct button").forEach((b) => b.addEventListener("click", () => setAct("outline", b.dataset.v)));

export function renderFonts() {
  const el = $("ch-fonts");
  el.hidden = !overprintSettled() || !isPdf();
  if (el.hidden) return;
  const on = hasStep("outline"), a = facts("outline"), c = choice("outline");
  const fonts = a && !a.error ? a.fonts || [] : [];
  // nieosadzone fonty, którymi na tej stronie coś się DRUKUJE (analiza: fontfix.missing)
  const miss = a && !a.error ? (a.fonts_missing || []).filter((f) => f.visible).map((f) => f.name.split("+").pop()) : [];
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
    if (S.settle.outline || on) st = "done";
    if (c.act === "fix" || on) {
      sum = on ? "na krzywych" : "";
      say = on ? `<span class="say ok">Tekst zamieniony na krzywe.</span>`
                 + `<span class="now-only"> Suwakiem niżej porównasz przed i po.</span>`
               : S.busy ? "Zamieniam tekst na krzywe…" : "Nie udało się zamienić tekstu na krzywe.";
      if (on) note = esc(stepText("outline"));
    } else if (c.act === "keep") {
      sum = "zostawione";
      say = "Tekst zostaje w fontach — drukarnia złoży go swoim programem.";
    } else {
      say = `Tekst w projekcie jest zapisany fontami (${fonts.length}). Zamiana na krzywe gwarantuje, `
        + `że w drukarni wyjdzie dokładnie ten sam kształt liter.`;
      if (miss.length) note = `<span class="say warn">${miss.length === 1 ? "Font" : "Fonty"} ${esc(miss.join(", "))} `
        + `${miss.length === 1 ? "nie jest osadzony" : "nie są osadzone"} w pliku</span> — w pliku jest tylko nazwa, `
        + `bez kształtów liter. Zostawić tak się nie da: drukarnia podstawiłaby inny krój. Kliknij `
        + `<b>Zamień na krzywe</b> — program poszuka ${miss.length === 1 ? "go" : "ich"} w Google Fonts i w systemie `
        + `(kroju zastępczego nie użyje). Jeśli nie znajdzie — poproś klienta o PDF z osadzonymi fontami.`;
    }
  }
  chapter("ch-fonts", st, sum);
  $("foSay").innerHTML = say;
  $("foNote").innerHTML = note; $("foNote").hidden = !note;
  rowsFor("fo", "outline", any || !!c.act, on);
  // nieosadzony, WIDOCZNY font nie może zostać (Tomasz 29.09) — „Zostaw jak jest” nieaktywne
  const keep = $("foAct").querySelector('button[data-v="keep"]');
  keep.disabled = keep.disabled || (!on && miss.length > 0);
  keep.title = !on && miss.length ? "Nie da się zostawić — w pliku brakuje fontu, drukarnia podstawiłaby inny krój." : "";
}

// ------------------------------------------------------------------ spłaszczenie
document.querySelectorAll("#flAct button").forEach((b) => b.addEventListener("click", () => setAct("flatten", b.dataset.v)));

export function renderFlatten() {
  const el = $("ch-flat");
  el.hidden = !fontsSettled() || !isPdf();
  if (el.hidden) return;
  const on = hasStep("flatten"), a = facts("flatten"), c = choice("flatten");
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
    if (S.settle.flatten || on) st = "done";
    if (c.act === "fix" || on) {
      sum = on ? "spłaszczone" : "";
      say = on ? `<span class="say ok">Projekt spłaszczony</span> — na maszynę pójdzie dokładnie to, co widać.`
                 + `<span class="now-only"> Suwakiem niżej porównasz przed i po.</span>`
               : S.busy ? "Spłaszczam projekt…" : "Nie udało się spłaszczyć projektu.";
      note = on ? esc(stepText("flatten")) : plan;
    } else if (c.act === "keep" && !kinds.length) {
      sum = "zostawione";
      say = `<span class="say ok">Projekt zostaje jak jest</span> — bez przezroczystości nie ma czego spłaszczać.`;
    } else if (c.act === "keep") {
      sum = "zostawione";
      say = "Projekt zostaje warstwowy — przezroczystość spłaszczy drukarnia.";
    } else if (kinds.length) {
      // Tomasz 25.09: spłaszczać tylko, gdy to konieczne — lepiej, żeby plik spłaszczyła drukarnia
      say = `W projekcie jest <b>przezroczystość</b> (${esc(kinds.join(", "))}). Zwykle najlepiej `
        + `zostawić ją drukarni — spłaszczy ją przy druku, a tekst i linie zostaną wektorowe. `
        + `Spłaszcz tutaj tylko wtedy, gdy to konieczne: drukarnia o to prosi albo podgląd `
        + `pokazuje ślady (jasne obwódki, szwy).`;
      note = plan;
    } else {
      // bez przezroczystości też czekamy na wybór (Tomasz 25.09) — zwykle „Zostaw jak jest"
      say = `<span class="say ok">Projekt nie ma przezroczystości</span> — spłaszczać nie trzeba. `
        + `Kliknij <b>Zostaw jak jest</b>. Spłaszcz tylko wtedy, gdy drukarnia tego wymaga.`;
      note = plan;
    }
  }
  chapter("ch-flat", st, sum);
  $("flSay").innerHTML = say;
  $("flNote").innerHTML = note; $("flNote").hidden = !note;
  rowsFor("fl", "flatten", !!a && !a.error || on || !!c.act, on);
}

// Wspólne rzędy fontów i spłaszczenia: [poprawka | zostaw] → suwak przed/po.
function rowsFor(pre, name, show, on) {
  const c = choice(name);
  $(pre + "Err").hidden = !S.stepErr[name]; $(pre + "Err").textContent = S.stepErr[name] || "";
  $(pre + "Act").hidden = !show;
  pick(pre + "Act", on ? "fix" : c.act);
  lockRows([pre + "Act"]);
  $(pre + "Mini").hidden = !on;
  if (S.cmp?.step !== name) $(pre + "Mini").querySelector("input").value = 100;
}

// Warstwy podglądu przy suwaku „Symulacji wydruku”: ten sam plik — jak na ekranie ↔ jak z drukarki
// (kolory z drukarki i overprint). {mix, bottom, top} — flagi op/pr obu warstw.
export function simLayers() {
  if (S.sim !== "print" || S.cmp) return null;
  return { mix: S.simMix / 100, bottom: { op: false, pr: false }, top: { op: isPdf(), pr: true } };
}
