// Rozdziały „Szablon z wytycznych" i „Spady".
import { $, esc, fmtMm, api, chapter, plural } from "./util.js";
import { S, changed, template, hasStep, roleSettled, framesSettled, trimInfo, isPdf } from "./state.js";
import { applyStep, undoStep, stepControls } from "./steps.js";

// ------------------------------------------------------------------ szablon z wytycznych
// Program porównuje CAŁY szablon z wytycznych tego produktu (ramki, kolory, położenie) z tym,
// co jest w pliku. Szukamy raz, na oryginale — usuwanie szablonu jest pierwszą poprawką.
function scanKey() {
  const t = S.product ? template() : null;
  return [S.job.job_id, S.page, S.guidelines?.hash || "", t ? t.page : -1].join("|");
}
async function scan() {
  const key = scanKey();
  S.fscan = { key, data: null, err: "" };
  const t = S.product ? template() : null;
  try {
    const d = await api(`/api/jobs/${S.job.job_id}/frames?page=${S.page}`
      + (t && S.guidelines?.hash ? `&gl=${encodeURIComponent(S.guidelines.hash)}&glpage=${t.page}` : ""));
    if (S.fscan.key === key) S.fscan.data = d;
  } catch (e) {
    if (S.fscan.key === key) S.fscan.err = e.message;
  }
  changed();
}

$("frDo").onclick = () => {
  const t = template();
  applyStep("frames", { gl: S.guidelines?.hash || "", glpage: t ? t.page : -1 });
};
$("frUndo").onclick = () => undoStep("frames");
$("frSkip").onclick = () => { S.settle.frames = "skip"; changed(); };

export function renderFrames() {
  const el = $("ch-frames");
  el.hidden = !roleSettled();
  if (el.hidden) return;
  if (S.fscan.key !== scanKey()) scan();
  const d = S.fscan.data, on = hasStep("frames");
  let st = "open", sum = "", say = "", note = "", skip = "", hidden = false;
  if (on) {
    st = "done"; sum = "usunięty";
    say = `<span class="say ok">Szablon usunięty z projektu.</span> <span class="now-only">Suwakiem niżej porównasz przed i po.</span>`;
  } else if (S.fscan.err) {
    st = "done"; sum = "nie udało się sprawdzić";
    say = `<span class="say warn">Nie udało się przeszukać pliku.</span>`; note = esc(S.fscan.err);
  } else if (!d) {
    say = `<span class="spin"></span>Porównuję plik z szablonem z wytycznych…`;
  } else if (d.found && d.hidden) {
    // warstwa szablonu została w pliku, ale grafika ją całkowicie przykrywa
    st = "done"; sum = "przykryty — nie drukuje się"; hidden = true;
    say = `<span class="say ok">Szablon jest w pliku, ale całkowicie przykrywa go grafika</span> — `
      + `nie będzie go widać na wydruku. Nic nie trzeba robić.`;
  } else if (d.found) {
    const lines = d.lines >= d.lines_total ? "cały szablon" : `${d.lines} z ${d.lines_total} ramek szablonu`;
    st = S.settle.frames ? "done" : "todo"; sum = S.settle.frames ? "zostawiony" : "";
    say = `W projekcie został <b>szablon z wytycznych</b> — ramki${d.texts ? " i napisy" : ""} poszłyby do druku.`;
    note = `Znaleziono ${lines}${d.texts ? ` i ${d.texts} ${plural(d.texts, "napis", "napisy", "napisów")}` : ""}`
      + (d.err_mm > 0.5 ? `, krawędzie przesunięte najwyżej o ${fmtMm(d.err_mm)} mm` : "") + ".";
    skip = "zostaw jak jest";
  } else if (d.pixels) {
    st = S.settle.frames ? "done" : "todo"; sum = "wtopiony w obraz";
    say = `<span class="say warn">Linie w kolorach wytycznych są wtopione w obraz</span> — pikseli nie da się usunąć. `
      + `Poproś klienta o plik bez szablonu.`;
    skip = "rozumiem, idę dalej";
  } else if (d.foreign) {
    st = S.settle.frames ? "done" : "todo"; sum = "do obejrzenia";
    say = `W pliku są ramki w kolorach wytycznych, ale <b>nie pasują do szablonu tego produktu</b> — nie usuwam. `
      + `Obejrzyj je na podglądzie.`;
    skip = "rozumiem, idę dalej";
  } else {
    st = "done"; sum = d.known ? "czysto" : "nie dotyczy";
    say = d.known ? `<span class="say ok">W projekcie nie ma szablonu z wytycznych.</span>`
                  : `Bez wytycznych nie ma z czym porównać.`;
  }
  chapter("ch-frames", st, sum);
  $("frSay").innerHTML = say;
  $("frNote").innerHTML = note; $("frNote").hidden = !note;
  stepControls("fr", "frames", { canDo: !!d?.found, skip, doLabel: hidden ? "Usuń mimo to" : "Usuń szablon" });
  $("frDo").hidden = on || !d?.found || !!S.settle.frames;
  $("frDo").classList.toggle("primary", !hidden);
}

// ------------------------------------------------------------------ spady
// Plik ze spadami jest większy od formatu (treść wychodzi poza obszar cięcia). W wielkim
// formacie Adsystem spadów nie ma — taki plik trzeba przyciąć, i to PRZED wymiarem.
$("trDo").onclick = () => {
  const i = trimInfo();
  applyStep("trim", { w_mm: i ? i.net[0] : 0, h_mm: i ? i.net[1] : 0 });
};
$("trUndo").onclick = () => undoStep("trim");
$("trSkip").onclick = () => { S.settle.trim = "skip"; changed(); };

export function renderTrim() {
  const el = $("ch-trim");
  el.hidden = !framesSettled();
  if (el.hidden) return;
  const i = trimInfo(), on = hasStep("trim");
  let st, sum, say = "", note = "";
  if (on) {
    st = "done"; sum = "przycięte";
    say = `<span class="say ok">Spady przycięte</span>` + (i ? ` — strona ma format netto ${fmtMm(i.net[0])} × ${fmtMm(i.net[1])} mm.` : ".");
  } else if (!i) {
    st = "done"; sum = isPdf() ? "brak" : "nie dotyczy";
    say = isPdf() ? `<span class="say ok">Plik nie ma spadów.</span>` : "Obraz nie ma spadów do przycięcia.";
  } else {
    const even = i.bleed.every((v) => Math.abs(v - i.bleed[0]) < 0.3);
    const size = even ? `${fmtMm(i.bleed[0])} mm` : i.bleed.map(fmtMm).join(" / ") + " mm (lewo / góra / prawo / dół)";
    st = S.settle.trim ? "done" : "todo"; sum = S.settle.trim ? "zostawione" : "";
    say = `Plik ma <b>spady ${size}</b>. W wielkim formacie spadów nie ma — trzeba je przyciąć.`;
    note = `Po przycięciu strona będzie miała ${fmtMm(i.net[0])} × ${fmtMm(i.net[1])} mm`
      + (i.fits ? " — dokładnie tyle, ile wymagają wytyczne." : " (wymiar dopasujesz w następnym rozdziale).");
  }
  chapter("ch-trim", st, sum);
  $("trSay").innerHTML = say;
  $("trNote").innerHTML = note; $("trNote").hidden = !note;
  stepControls("tr", "trim", { canDo: !!i, skip: i ? "zostaw spady" : "" });
  $("trDo").hidden = on || !i || !!S.settle.trim;
}
