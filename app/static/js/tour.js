// Samouczek (wersja 0.2): dymki krok po kroku, jak w nowoczesnych aplikacjach.
// Część 1 — Ustawienia (kalibracja monitora, dokładność oceny jakości, indeks wymiarów).
// Część 2 — plik przykładowy (ma prawie każdy typowy błąd), rozdział po rozdziale.
//
// Ekran jest przyciemniony; widać i da się kliknąć tylko wskazane miejsca („dziury"). Krok
// z AKCJĄ czeka, aż użytkownik ją zrobi, i sam przechodzi dalej. Krok z OPISEM ma „Dalej".
// Gdy akcja była zrobiona już wcześniej (np. monitor skalibrowany, powrót „Wstecz") — też „Dalej".
// Kroki rozdziałów, które są już domknięte, idąc do przodu pomijamy.
import { $ } from "./util.js";
import { S, head, hasStep, isPdf, productOk, roleSettled, framesSettled, trimSettled, sizeSettled,
         colorSettled, overprintSettled, fontsSettled, flattenSettled } from "./state.js";
import { qualitySettled, acceptSettled } from "./quality.js";
import { cover } from "./size.js";
import { calCount, idxState } from "./settings.js";

const SAMPLE_URL = "/static/samples/przyklad_adChecker.pdf";
const SAMPLE_NAME = "przyklad_adChecker.pdf";
const DONE_KEY = "adcheck.tourDone";
const GRACE_MS = 1500;       // krok `grace`: stan dochodzi z serwera z opóźnieniem — spełniony tak szybko = był wcześniej

const vis = (id) => { const el = $(id); return !!el && el.getClientRects().length > 0; };
const settingsOpen = () => !$("settings").hidden;
const isSample = () => S.job?.file?.name === SAMPLE_NAME;
const btnText = (id, fb) => ($(id)?.textContent || fb).trim();

// ------------------------------------------------------------------ kroki
// target: id miejsc, które widać i da się kliknąć (pierwsze = kotwica dymka, chyba że `anchor`)
// wait(ctx): akcja zrobiona? (brak = krok z opisem)   when(): krok ma sens?   enter(ctx): stan na starcie
// skipDone: pomiń, gdy już zrobione   manual: po akcji pokaż „Dalej" zamiast iść samemu
// optional: napis linku „pomiń"   action: {label, run} — przycisk robi coś za użytkownika
const PART1 = "Ustawienia", PART2 = "Przykładowy projekt";
let loadSample = async () => {};

const STEPS = [
  { part: PART1, title: "Witaj w adCheckerze!",
    text: `Pomogę Ci przygotować plik do druku — nie musisz znać się ani na grafice, ani na druku.<br><br>
      Najpierw raz ustawimy trzy rzeczy, a potem przejdziemy razem przez przykładowy projekt.
      Zajmie to około 10 minut.`,
    next: "Zaczynamy", cancel: "Nie teraz" },

  { part: PART1, target: ["btnSettings"], title: "Ustawienia", place: "bottom",
    text: `Kliknij <b>Ustawienia</b>.`,
    wait: settingsOpen, skipDone: true },

  { part: PART1, target: ["setCal"], title: "Kalibracja monitora",
    enter: (c) => { c.c0 = calCount(); c.was = S.calibrated; },
    text: (c) => `Dzięki niej przycisk <b>Rzeczywista wielkość</b> pokaże projekt dokładnie tak duży, jak na
      wydruku: 1 cm na ekranie = 1 cm wydruku.<br><br>`
      + (c.was ? `Monitor jest już skalibrowany. Możesz to poprawić albo iść dalej.`
               : `Wpisz <b>przekątną monitora</b> w calach (np. 24 albo 27 — jest w nazwie monitora albo na
                  naklejce z tyłu) i kliknij <b>Zastosuj</b>.`),
    wait: (c) => c.was || calCount() > c.c0, optional: "Pomiń — zrobię to później" },

  { part: PART1, target: ["calCheckWrap"], title: "Sprawdź linijką",
    text: `Przyłóż linijkę do ekranu: od czerwonej do czerwonej kreski powinno być dokładnie <b>100 mm</b>.<br><br>
      Jeśli jest inaczej — zmierz linijką górny pasek wzorcowy, wpisz wynik w polu
      <b>Zmierzona długość</b> i kliknij <b>Zastosuj</b> obok niego.` },

  { part: PART1, target: ["setAcc"], title: "Dokładność oceny jakości",
    text: `Program ogląda każdy obraz w projekcie i szuka miejsc, które na wydruku wyjdą rozmyte.<br><br>
      <b>Standardowa</b> wystarcza prawie zawsze. <b>Wysoka</b> znajdzie też mniejsze miejsca, ale liczy się
      dwa razy dłużej. Zaznacz jedną i kliknij Dalej.` },

  { part: PART1, target: ["setIdx"], title: "Indeks wymiarów",
    enter: (c) => { c.t0 = Date.now(); },
    text: () => idxComplete()
      ? `Program zna ponad 1000 produktów Adsystem i ma już pobrane wymiary wszystkich — dzięki temu po samym
         wymiarze pliku podpowie, co to za produkt. Nic nie trzeba robić.`
      : `Program zna ponad 1000 produktów Adsystem. Żeby po samym wymiarze pliku podpowiedzieć, co to za produkt,
         musi raz pobrać wymiary wszystkich.<br><br>Kliknij <b>Zbuduj / wznów indeks</b>. Potrwa to 2–4 minuty
         w tle — nie musisz czekać.`,
    wait: () => idxComplete() || !!idxState()?.running, grace: true, optional: "Pomiń — zrobię to później" },

  { part: PART1, target: ["setClose"], title: "Gotowe", place: "bottom",
    text: `Ustawienia zapamiętają się na stałe. Zamknij je.`,
    wait: () => !settingsOpen(), skipDone: true },

  // ---------------------------------------------------------------- część 2: plik przykładowy
  { part: PART2, target: ["ch-file"], title: "Plik do druku",
    text: `Tu zaczyna się każda praca: przeciągasz plik w to pole albo klikasz i wybierasz go z dysku.
      Najlepiej PDF.<br><br>Teraz wczytamy <b>plik przykładowy</b> — ma specjalnie prawie wszystkie typowe
      błędy, więc zobaczysz każdy rozdział.`,
    action: { label: "Wczytaj plik przykładowy", run: () => loadSample() },
    wait: () => isSample() && !!S.analysisFor },

  { part: PART2, target: ["side"], title: "Rozdziały",
    text: `Po lewej są <b>rozdziały</b>. Idziesz po kolei, z góry na dół — następny otwiera się, gdy skończysz
      poprzedni. Zielony ✓ znaczy „gotowe”.<br><br>Przy każdym rozdziale jest <b>?</b> — pod nim krótkie
      wyjaśnienie, gdy czegoś nie wiesz.` },

  { part: PART2, target: ["view"], title: "Podgląd",
    text: `Po prawej widzisz projekt. Kółkiem myszy przewijasz, lupkami powiększasz, a
      <b>Rzeczywista wielkość</b> pokazuje go dokładnie tak duży, jak na wydruku.` },

  { part: PART2, target: ["ch-page"], title: "Strona", when: () => S.job?.file.page_count > 1,
    text: `Ten plik ma kilka stron, a do druku idzie zawsze <b>jedna</b>. Zostaw stronę 1 i kliknij
      <b>Wybierz tę stronę</b>.`,
    wait: () => S.pageOk, skipDone: true },

  { part: PART2, target: ["ch-product", "pList"], title: "Produkt",
    text: () => S.candidate && !S.picking
      ? `Program sam zaproponował produkt. <b>Zawsze sprawdź</b>, czy to ten właściwy — od niego zależą wymiar
         i wytyczne.<br><br>Tu się zgadza: kliknij <b>Potwierdź</b>.`
      : `Wpisz nazwę albo kod produktu, kliknij go na liście, a potem <b>Potwierdź</b>.`,
    wait: productOk, skipDone: true },

  { part: PART2, target: ["ch-role"], title: "Rola pliku", when: () => !S.custom,
    text: () => S.glLoading ? `Pobieram wytyczne produktu…`
      : `Program pobrał <b>wytyczne</b> tego produktu. Produkt może mieć kilka elementów do druku (np. przód
         i tył) — tu wskazujesz, który jest w pliku.<br><br>Program już go wybrał: kliknij <b>Zatwierdź</b>.`,
    wait: roleSettled, skipDone: true },

  { part: PART2, target: ["vTpl", "vStage"], title: "Podgląd szablonu", place: "left",
    when: () => !$("vTpl").disabled,
    text: (c) => c.on
      ? `Widzisz linie? <b>Niebieska</b> to krawędź wydruku, <b>czerwona</b> — obszar bezpieczny: ważne napisy
         i logo muszą być w czerwonej ramce.<br><br>Kliknij jeszcze raz, żeby schować linie.`
      : `Ten przycisk nakłada na projekt linie z wytycznych produktu. Kliknij, żeby je zobaczyć.`,
    wait: (c) => { if (S.overlayOn) c.on = true; return !!c.on && !S.overlayOn; },
    optional: "Pomiń" },

  { part: PART2, target: ["ch-frames"], title: "Szablon z wytycznych",
    text: () => !S.fscan.data && !S.fscan.err ? `Program porównuje plik z szablonem z wytycznych…`
      : S.fscan.data?.found && !S.fscan.data.hidden
        ? `Projektant zostawił w pliku <b>szablon z wytycznych</b> — te ramki i napisy poszłyby do druku!<br><br>
           Kliknij <b>Usuń szablon</b>.`
        : `Przeczytaj, co znalazł program, i kliknij przycisk w rozdziale.`,
    wait: framesSettled, skipDone: true },

  { part: PART2, target: ["frMini", "vStage"], title: "Suwak przed / po", when: () => hasStep("frames"),
    text: `Po każdej poprawce pojawia się taki suwak. <b>Przeciągnij go w lewo</b> i patrz na podgląd:
      w lewo — przed poprawką, w prawo — po.`,
    wait: () => S.cmp?.step === "frames" && S.cmp.v < 50, manual: true, optional: "Pomiń" },

  { part: PART2, target: ["ch-trim"], title: "Spady",
    text: `Plik ma <b>spady</b> — zapas projektu poza formatem. W wielkim formacie się ich nie stosuje.<br><br>
      Kliknij <b>Przytnij spady</b>.`,
    wait: trimSettled, skipDone: true },

  { part: PART2, target: ["ch-size", "vStage"], title: "Wymiar wydruku", when: () => vis("szCtl"),
    text: `Plik jest trochę mniejszy niż format z wytycznych. <b>Zielona ramka</b> na podglądzie to format
      wydruku, a to, co przyciemnione, zostanie odcięte.<br><br>Kliknij <b>wypełnij format</b> — projekt
      powiększy się tak, żeby nie było pustych pasów.`,
    wait: () => { const c = cover(); return sizeSettled() || (!!c && c.gap[0] < 0.15 && c.gap[1] < 0.15); },
    skipDone: true },

  { part: PART2, target: ["ch-size", "vStage"], anchor: "szDo", title: "Zatwierdź wymiar",
    text: () => `Na podglądzie widać, jak projekt leży w formacie. Suwakami można go jeszcze przesunąć — tu nie
      trzeba.<br><br>Kliknij <b>${btnText("szDo", "Dopasuj wymiar")}</b>.`,
    wait: sizeSettled, skipDone: true },

  { part: PART2, target: ["ch-color"], title: "Kolory",
    text: `Maszyny drukują czterema farbami — to <b>CMYK</b>. W tym projekcie są też kolory z ekranu (RGB)
      i kolory specjalne (np. PANTONE, złoto) — trzeba je przeliczyć.<br><br>Kliknij <b>Zamień na CMYK</b>.`,
    wait: () => !!S.choice.cmyk?.act || colorSettled(), skipDone: true },

  { part: PART2, target: ["coProf"], title: "Profil kolorów", when: () => S.choice.cmyk?.act === "convert",
    text: `Profil mówi, pod jaką maszynę są przeliczone kolory. <b>FOGRA39</b> to standard drukarni —
      kliknij go.`,
    wait: () => hasStep("cmyk") || colorSettled(), skipDone: true },

  { part: PART2, target: ["coSeen"], title: "Pokaż, jak wydrukuje",
    text: `Rozdziały z kolorami i drukiem kończą się przyciskiem <b>Pokaż, jak wydrukuje</b> — żeby nikt nie
      szedł dalej, nie widząc wydruku. Kliknij go.`,
    wait: colorSettled, skipDone: true },

  { part: PART2, target: ["ch-color", "vStage"], anchor: () => vis("coMini") ? "coMini" : "coSimBar",
    title: "Podgląd = wydruk", when: () => colorSettled() && !!S.choice.cmyk?.seen,
    text: `Od teraz podgląd pokazuje <b>wydruk</b>, a nie ekran. Przesuń suwak: w lewo — tak było na ekranie,
      w prawo — tak wyjdzie z drukarki.<br><br>Jaskrawe kolory w druku bledną, bo farby nie mają tak nasyconych
      barw. To normalne.` },

  { part: PART2, target: ["ch-op"], title: "Overprint", when: isPdf,
    text: twoStep("overprint", `<b>Overprint</b> (nadruk) sprawia, że farba kładzie się na tło, zamiast je zakryć —
      w druku element wychodzi innym kolorem niż na ekranie. Wytyczne go nie dopuszczają.`, "Wyłącz overprint"),
    wait: overprintSettled, skipDone: true },

  { part: PART2, target: ["ch-fonts"], title: "Fonty", when: isPdf,
    text: twoStep("outline", `Tekst zapisany fontem drukarnia musi „złożyć” u siebie — gdy nie ma tego fontu,
      litery wyjdą inne. <b>Krzywe</b> to gotowe kształty liter: wyglądają identycznie.`, "Zamień na krzywe"),
    wait: fontsSettled, skipDone: true },

  { part: PART2, target: ["ch-flat"], title: "Spłaszczenie", when: isPdf,
    text: twoStep("flatten", `Cienie i półprzezroczyste elementy drukarnia i tak łączy w jedno — i czasem zostawia
      przy tym ślady. <b>Spłaszczenie</b> robi to tutaj: cała strona staje się jednym obrazem, dokładnie takim,
      jaki widzisz.`, "Spłaszcz projekt"),
    wait: flattenSettled, skipDone: true },

  { part: PART2, target: ["ch-qual"], title: "Jakość wydruku",
    text: () => !S.qual.data || S.qual.data.status === "running"
      ? `Program ogląda każdy obraz piksel po pikselu — czy na wydruku nie wyjdzie rozmyty. To chwilę potrwa…`
      : `Program znalazł miejsca, które na wydruku wyjdą <b>rozmyte</b>.<br><br>Kliknij
         <b>Pokaż na podglądzie</b>.`,
    wait: () => qualitySettled() || vis("qnav"), skipDone: true },

  { part: PART2, target: ["qnav", "vStage"], title: "Słabe miejsca", place: "left", when: () => vis("qnav"),
    text: `Każde słabe miejsce program pokazuje w <b>rzeczywistej wielkości wydruku</b> — tak, jak zobaczysz je
      z bliska. Strzałkami ‹ › (albo ← → na klawiaturze) przechodzisz do następnych.<br><br>Obrazy o za małej
      rozdzielczości trzeba wymienić na większe — poproś o nie klienta. Gdy obejrzysz, zamknij pasek <b>×</b>.`,
    wait: () => !vis("qnav"), skipDone: true },

  { part: PART2, target: ["ch-acc"], title: "Akceptacja pliku",
    text: `Ostatnie spojrzenie. Kliknij <b>Pokaż wydruk przed i po</b> — suwak porówna wydruk bez poprawek
      z wydrukiem po nich.`,
    wait: () => S.accShown === head()?.id || acceptSettled(), skipDone: true },

  { part: PART2, target: ["ch-acc", "vStage", "vFit"], anchor: "acSimBar", title: "Przed i po",
    text: `Przesuń suwak i porównaj: w lewo — wydruk bez poprawek, w prawo — po nich. <b>Dopasuj</b> u góry
      pokaże cały projekt.<br><br>Jeśli wszystko gra, kliknij <b>Akceptuję plik</b>.`,
    wait: acceptSettled, skipDone: true },

  { part: PART2, target: ["ch-dl"], title: "Pobierz plik do druku", when: acceptSettled,
    text: `Gotowe! Tu pobierasz plik do druku — ze wszystkimi poprawkami, zawsze jedną stronę. Oryginał zostaje
      nietknięty.<br><br>Pliku przykładowego nie musisz pobierać.` },

  { part: PART2, target: ["btnTour"], title: "To wszystko!", place: "bottom", next: "Zakończ",
    text: `Teraz wgraj swój plik i idź tak samo — rozdział po rozdziale. Gdy czegoś nie wiesz, kliknij
      <b>?</b> przy rozdziale.<br><br>Samouczek włączysz ponownie tym przyciskiem.` },
];

// Overprint, fonty, spłaszczenie: najpierw poprawka (albo „zostaw"), potem „Pokaż, jak wydrukuje".
function twoStep(name, intro, fix) {
  return () => S.choice[name]?.act
    ? `${intro}<br><br>${S.busy ? "Program pracuje — chwileczkę." : "Teraz kliknij <b>Pokaż, jak wydrukuje</b>."}`
    : `${intro}<br><br>Kliknij <b>${fix}</b>, a potem <b>Pokaż, jak wydrukuje</b>.`;
}

function idxComplete() {
  const st = idxState();
  return !!st && !st.running && st.total_products > 0 && st.indexed >= st.total_products * 0.97;
}

// ------------------------------------------------------------------ silnik
let idx = -1, ctx = {}, doneAtEntry = false, enteredAt = 0, advancing = false, timer = null, lastScroll = 0;
let root, svg, dimPath, rings, bub, mask, shade;

export const tourActive = () => idx >= 0;

export function initTour({ upload }) {
  loadSample = async () => {
    try {
      const r = await fetch(SAMPLE_URL);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      upload(new File([blob], SAMPLE_NAME, { type: "application/pdf" }));
    } catch (e) {
      setWaitLine(`Nie udało się wczytać pliku przykładowego (${e.message}).`);
    }
  };
  $("btnTour").onclick = () => startTour();
}

// Pierwsze uruchomienie programu: samouczek sam (da się go od razu wyłączyć „Nie teraz").
export function autoStartTour() {
  let done = false;
  try { done = !!localStorage.getItem(DONE_KEY); } catch (_) {}
  if (!done) setTimeout(() => { if (!tourActive()) startTour(); }, 700);
}

export function startTour() {
  endTour(false);
  build();
  go(0, 1);
  timer = setInterval(tick, 120);
  window.addEventListener("resize", layout);
}

function endTour(markDone = true) {
  if (markDone) { try { localStorage.setItem(DONE_KEY, "1"); } catch (_) {} }
  clearInterval(timer); timer = null;
  window.removeEventListener("resize", layout);
  root?.remove(); root = null;
  idx = -1;
}

function go(i, dir) {
  while (i >= 0 && i < STEPS.length) {
    const s = STEPS[i];
    if (s.when && !s.when()) { i += dir; continue; }
    const c = {};
    s.enter?.(c);
    const done = !!s.wait?.(c);
    if (done && s.skipDone && dir > 0) { i += dir; continue; }
    idx = i; ctx = c; doneAtEntry = done; enteredAt = Date.now(); advancing = false; lastScroll = 0;
    draw(true);
    return;
  }
  if (i >= STEPS.length) endTour(true); else go(0, 1);
}
const next = () => go(idx + 1, 1);
const back = () => { for (let i = idx - 1; i >= 0; i--) if (!STEPS[i].when || STEPS[i].when()) return go(i, -1); };

function tick() {
  const s = STEPS[idx];
  if (!s || !root) return;
  // pytanie „na pewno?" ma pierwszeństwo — samouczek chowa się, aż ktoś odpowie
  root.hidden = !$("ask").hidden;
  if (root.hidden) return;
  if (s.wait && !doneAtEntry && !advancing && s.wait(ctx)) {
    if (s.grace && Date.now() - enteredAt < GRACE_MS) doneAtEntry = true;   // było zrobione wcześniej
    else if (s.manual) doneAtEntry = true;                          // np. suwak — pokaż „Dalej"
    else {
      advancing = true;
      setTimeout(() => { if (STEPS[idx] === s && root) next(); }, 450);
    }
  }
  draw(false);
}

// ------------------------------------------------------------------ rysowanie
function build() {
  root = document.createElement("div");
  root.className = "tour";
  // przyciemnienie = maska (dziury łączą się, gdy na siebie zachodzą); klikanie blokuje osobna,
  // niewidoczna ścieżka z prostokątów, które NIE leżą w żadnej dziurze
  root.innerHTML = `<svg aria-hidden="true"><defs><mask id="trMask" maskUnits="userSpaceOnUse"></mask></defs>
    <rect class="tr-shade" x="0" y="0" mask="url(#trMask)"></rect><path class="tr-dim"></path><g class="tr-rings"></g></svg>
    <div class="tr-bub" role="dialog" aria-live="polite">
      <div class="tr-top"><span class="tr-part"></span><button class="tr-x" type="button" title="Zakończ samouczek">×</button></div>
      <div class="tr-prog"><i></i></div>
      <h3 class="tr-t"></h3>
      <div class="tr-txt"></div>
      <div class="tr-wait"></div>
      <div class="tr-foot">
        <button class="link tr-back" type="button">Wstecz</button>
        <button class="link tr-skip" type="button"></button>
        <span class="tr-sp"></span>
        <button class="btn primary tr-next" type="button"></button>
      </div>
      <span class="tr-arrow"></span>
    </div>`;
  document.body.appendChild(root);
  svg = root.querySelector("svg"); dimPath = root.querySelector(".tr-dim"); rings = root.querySelector(".tr-rings");
  mask = root.querySelector("#trMask"); shade = root.querySelector(".tr-shade");
  bub = root.querySelector(".tr-bub");
  root.querySelector(".tr-x").onclick = () => endTour(true);
  root.querySelector(".tr-back").onclick = back;
  root.querySelector(".tr-skip").onclick = () => {
    const s = STEPS[idx];
    if (s.cancel) endTour(true); else next();
  };
  root.querySelector(".tr-next").onclick = () => {
    const s = STEPS[idx];
    if (s.action && !doneAtEntry) s.action.run(); else next();
  };
  // klik w przyciemnienie: dymek „podskakuje", żeby było widać, gdzie patrzeć
  dimPath.addEventListener("mousedown", (e) => {
    e.preventDefault();
    bub.classList.remove("nudge"); void bub.offsetWidth; bub.classList.add("nudge");
  });
  // kółko myszy nad przyciemnieniem przewija to, co pod nim (panel rozdziałów, okno ustawień)
  dimPath.addEventListener("wheel", (e) => {
    dimPath.style.pointerEvents = "none";
    let el = document.elementFromPoint(e.clientX, e.clientY);
    dimPath.style.pointerEvents = "";
    while (el && el !== document.body) {
      const oy = getComputedStyle(el).overflowY;
      if ((oy === "auto" || oy === "scroll") && el.scrollHeight > el.clientHeight) { el.scrollBy(0, e.deltaY); break; }
      el = el.parentElement;
    }
    e.preventDefault();
  }, { passive: false });
}

const val = (x) => (typeof x === "function" ? x(ctx) : x);

function draw(entered) {
  const s = STEPS[idx];
  if (!s || !root) return;
  // treść
  const inPart = STEPS.filter((x) => x.part === s.part), n = inPart.indexOf(s) + 1;
  setHtml(".tr-part", `${s.part} · ${n} z ${inPart.length}`);
  root.querySelector(".tr-prog i").style.width = `${Math.round((idx + 1) / STEPS.length * 100)}%`;
  setHtml(".tr-t", s.title);
  setHtml(".tr-txt", val(s.text));
  const waiting = !!s.wait && !doneAtEntry;
  const anchorMissing = !anchorRect(s);
  if (waiting && s.action) {
    setWaitLine(isSample() ? `<span class="spin"></span>Wczytuję plik przykładowy…` : "");
  } else if (waiting) {
    setWaitLine(S.busy ? `<span class="spin"></span>Program pracuje — chwileczkę…`
      : anchorMissing && s.target ? `<span class="spin"></span>Chwileczkę…`
      : `<i class="tr-dot"></i>Twój ruch — dalej przejdę sam`);
  } else setWaitLine("");
  const nb = root.querySelector(".tr-next");
  const showNext = !s.wait || doneAtEntry || (s.action && !isSample());
  nb.hidden = !showNext;
  nb.textContent = s.action && !doneAtEntry ? s.action.label : s.next || (idx === STEPS.length - 1 ? "Zakończ" : "Dalej");
  nb.disabled = !!(s.action && S.job && !S.analysisFor && !doneAtEntry);
  const sk = root.querySelector(".tr-skip");
  sk.hidden = !(s.cancel || (s.optional && waiting));
  sk.textContent = s.cancel || s.optional || "";
  root.querySelector(".tr-back").hidden = idx === 0 || !!s.cancel;
  if (entered) setTimeout(() => nb.hidden || nb.focus({ preventScroll: true }), 0);
  layout();
}

function setHtml(sel, html) {
  const el = root?.querySelector(sel);
  if (el && el.dataset.h !== html) { el.innerHTML = html; el.dataset.h = html; }
}
function setWaitLine(html) {
  const el = root?.querySelector(".tr-wait");
  if (!el) return;
  el.hidden = !html;
  if (el.dataset.h !== html) { el.innerHTML = html; el.dataset.h = html; }
}

// Prostokąt elementu, przycięty do widocznej części przewijanych rodziców (panel, okno).
function rectOf(id) {
  const el = typeof id === "string" ? $(id) : id;
  if (!el || el.getClientRects().length === 0) return null;
  const r = el.getBoundingClientRect();
  let x0 = r.left, y0 = r.top, x1 = r.right, y1 = r.bottom;
  for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    const cs = getComputedStyle(p);
    if (/(auto|scroll|hidden)/.test(cs.overflowY + cs.overflowX)) {
      const q = p.getBoundingClientRect();
      x0 = Math.max(x0, q.left); y0 = Math.max(y0, q.top); x1 = Math.min(x1, q.right); y1 = Math.min(y1, q.bottom);
    }
  }
  if (x1 - x0 < 2 || y1 - y0 < 2) return null;
  return { left: x0, top: y0, right: x1, bottom: y1, width: x1 - x0, height: y1 - y0, el };
}
const anchorId = (s) => val(s.anchor) || s.target?.[0];
function anchorRect(s) {
  const a = anchorId(s) ? rectOf(anchorId(s)) : null;
  const t = s.anchor && s.target ? rectOf(s.target[0]) : null;
  if (!a || !t) return a;
  return { ...a, left: Math.min(a.left, t.left), right: Math.max(a.right, t.right), width: Math.max(a.right, t.right) - Math.min(a.left, t.left) };
}

function layout() {
  const s = STEPS[idx];
  if (!s || !root) return;
  const W = window.innerWidth, H = window.innerHeight, P = 6;
  svg.setAttribute("width", W); svg.setAttribute("height", H);
  // wskazany element poza widokiem panelu → przewiń do niego
  const aEl = anchorId(s) ? $(anchorId(s)) : null;
  if (aEl && aEl.getClientRects().length && Date.now() - lastScroll > 900) {
    const full = aEl.getBoundingClientRect(), vis_ = rectOf(aEl);
    if (!vis_ || vis_.height < Math.min(full.height, H * 0.5) - 4) {
      lastScroll = Date.now();
      aEl.scrollIntoView({ block: full.height > H * 0.8 ? "start" : "nearest", behavior: "smooth" });
    }
  }
  const holes = (s.target || []).map(rectOf).filter(Boolean)
    .map((r) => ({ x: r.left - P, y: r.top - P, w: r.width + 2 * P, h: r.height + 2 * P }));
  shade.setAttribute("width", W); shade.setAttribute("height", H);
  mask.innerHTML = `<rect x="0" y="0" width="${W}" height="${H}" fill="#fff"/>`
    + holes.map((h) => `<rect x="${h.x}" y="${h.y}" width="${h.w}" height="${h.h}" rx="10" fill="#000"/>`).join("");
  dimPath.setAttribute("d", blockedCells(holes, W, H));
  root.classList.toggle("nohole", !s.target);
  rings.innerHTML = holes.map((h) => `<rect class="tr-ring" x="${h.x}" y="${h.y}" width="${h.w}" height="${h.h}" rx="10"/>`).join("");
  placeBubble(s, anchorRect(s), W, H);
}

// Obszar blokujący kliknięcia: siatka z krawędzi dziur; bierzemy komórki poza wszystkimi dziurami.
function blockedCells(holes, W, H) {
  const xs = [...new Set([0, W, ...holes.flatMap((h) => [h.x, h.x + h.w])])].filter((v) => v >= 0 && v <= W).sort((a, b) => a - b);
  const ys = [...new Set([0, H, ...holes.flatMap((h) => [h.y, h.y + h.h])])].filter((v) => v >= 0 && v <= H).sort((a, b) => a - b);
  let d = "";
  for (let j = 0; j < ys.length - 1; j++) {
    for (let i = 0; i < xs.length - 1; i++) {
      const cx = (xs[i] + xs[i + 1]) / 2, cy = (ys[j] + ys[j + 1]) / 2;
      if (holes.some((h) => cx > h.x && cx < h.x + h.w && cy > h.y && cy < h.y + h.h)) continue;
      d += `M${xs[i]} ${ys[j]}H${xs[i + 1]}V${ys[j + 1]}H${xs[i]}Z`;
    }
  }
  return d;
}

function placeBubble(s, a, W, H) {
  const bw = bub.offsetWidth, bh = bub.offsetHeight, G = 16, M = 10;
  const arrow = root.querySelector(".tr-arrow");
  let x, y, side = null;
  if (a) {
    const fits = {
      right: a.right + G + bw <= W - M, left: a.left - G - bw >= M,
      bottom: a.bottom + G + bh <= H - M, top: a.top - G - bh >= M,
    };
    const order = [s.place, "right", "left", "bottom", "top"].filter(Boolean);
    side = order.find((o) => fits[o]) || null;
    const cy = Math.max(M, Math.min(H - bh - M, a.top + Math.min(a.height, 160) / 2 - bh / 2));
    const cx = Math.max(M, Math.min(W - bw - M, a.left + a.width / 2 - bw / 2));
    if (side === "right") { x = a.right + G; y = cy; }
    else if (side === "left") { x = a.left - G - bw; y = cy; }
    else if (side === "bottom") { x = cx; y = a.bottom + G; }
    else if (side === "top") { x = cx; y = a.top - G - bh; }
    else { x = W - bw - 24; y = H - bh - 24; }        // nigdzie się nie mieści — róg ekranu
  } else {
    x = (W - bw) / 2; y = (H - bh) / 2;
  }
  bub.style.left = `${Math.round(x)}px`; bub.style.top = `${Math.round(y)}px`;
  arrow.hidden = !side;
  if (side) {
    arrow.dataset.side = side;
    if (side === "right" || side === "left") {
      const ay = Math.max(14, Math.min(bh - 14, a.top + Math.min(a.height, 160) / 2 - y));
      arrow.style.top = `${ay - 7}px`; arrow.style.left = side === "right" ? "-7px" : `${bw - 7}px`;
    } else {
      const ax = Math.max(14, Math.min(bw - 14, a.left + a.width / 2 - x));
      arrow.style.left = `${ax - 7}px`; arrow.style.top = side === "bottom" ? "-7px" : `${bh - 7}px`;
    }
  }
}
