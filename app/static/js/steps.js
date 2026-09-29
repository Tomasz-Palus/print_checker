// Nakładanie i cofanie poprawek — wspólne dla wszystkich rozdziałów.
// Każda poprawka tworzy na serwerze NOWĄ wersję pliku (v1, v2…); cofnięcie ucina łańcuch
// przed nią, razem z krokami zrobionymi później.
import { $, esc, api, post, ask } from "./util.js";
import { S, changed, STEP_ORDER, STEP_NAME, STEP_CH, resetJobState } from "./state.js";

// Wyczyść decyzje rozdziałów od `name` w dół (po cofnięciu pliku są nieaktualne).
function forgetFrom(name) {
  const i = STEP_ORDER.indexOf(name);
  for (const n of STEP_ORDER.slice(Math.max(0, i))) { delete S.settle[n]; delete S.stepErr[n]; delete S.choice[n]; }
  if (i <= STEP_ORDER.indexOf("resize")) { S.sz = null; S.sizeEdit = false; delete S.settle.print; }
  S.cmp = null; S.sim = null;
}

// Odpowiedź dla zadania, którego już nie ma (w międzyczasie wgrano inny plik), nie może nadpisać
// S.job — program wracał do usuniętego zadania (przegląd kodu 27.09, A4).
const same = (jid) => S.job?.job_id === jid;

export async function applyStep(name, params) {
  if (!S.job || S.busy) return;
  const jid = S.job.job_id;
  S.busy = `Pracuję: ${STEP_NAME[name]}…`; delete S.stepErr[name];
  changed();
  try {
    const job = await post(`/api/jobs/${jid}/steps`, { name, params: { page: S.page, ...params } });
    if (!same(jid)) return;
    S.job = job;
    S.cmp = null; S.sim = null;
    S.pin = STEP_CH[name];            // rozdział z nową poprawką zostaje rozwinięty (main.render)
  } catch (e) {
    if (!same(jid)) return;
    S.stepErr[name] = e.message;
  }
  S.busy = null;
  changed();
}

// Cofnięcie poprawki (albo decyzji „zostaw jak jest") cofa też wszystko, co zrobiono później.
export async function undoStep(name) {
  if (!S.job || S.busy) return false;
  const vs = S.job.versions, oi = STEP_ORDER.indexOf(name);
  let i = vs.findIndex((v) => v.step === name);
  const own = i > 0;
  if (!own) i = vs.findIndex((v, j) => j > 0 && STEP_ORDER.indexOf(v.step) > oi);
  if (i > 0) {
    const later = vs.slice(own ? i + 1 : i).map((v) => STEP_NAME[v.step]);
    if (later.length && !(await ask(own ? `Cofnąć ${STEP_NAME[name]}?` : "Zmienić decyzję?",
        `Razem z tym cofną się kroki zrobione później: <b>${esc(later.join(", "))}</b>. Oryginał jest nietknięty.`,
        own ? "Cofnij" : "Tak, zmieniam", "Zostaw"))) return false;
    const jid = S.job.job_id;
    S.busy = "Cofam…"; changed();
    try {
      const job = await api(`/api/jobs/${jid}/steps/${vs[i].step}`, { method: "DELETE" });
      if (!same(jid)) return false;
      S.job = job;
    } catch (e) {
      if (!same(jid)) return false;
      S.stepErr[name] = e.message;
    }
  }
  forgetFrom(name);
  S.busy = null;
  changed();
  return true;
}

// Zmiana strony, produktu albo roli zmienia format docelowy — poprawki robione pod stary
// format przestają mieć sens. Pytamy (gdy jakieś są) i zdejmujemy wszystkie.
export async function resetSteps(title, why = "były robione pod obecny format") {
  if (!S.job) return true;
  const vs = S.job.versions;
  if (vs.length > 1) {
    const names = vs.slice(1).map((v) => STEP_NAME[v.step]).join(", ");
    if (!(await ask(title, `Nałożone poprawki (<b>${esc(names)}</b>) zostaną cofnięte — ${why}. `
        + `Oryginał jest nietknięty, nałożysz je na nowo.`, "Tak, zmieniam", "Zostaw jak jest"))) return false;
    const jid = S.job.job_id;
    S.busy = "Cofam poprawki…"; changed();
    try {
      const job = await api(`/api/jobs/${jid}/steps/${vs[1].step}`, { method: "DELETE" });
      if (!same(jid)) return false;
      S.job = job;
    } catch (_) {
      if (!same(jid)) return false;
    }
    S.busy = null;
  }
  forgetFrom(STEP_ORDER[0]);
  S.fscan = { key: "", data: null, err: "" };
  changed();
  return true;
}

// Obrót CAŁEGO pliku o 90° / 180° (Tomasz 29.09). Obrócony plik to nowy punkt wyjścia: poprawki
// (po pytaniu) i decyzje w rozdziałach przepadają, szablon, spady i wymiar liczą się od nowa.
// Produkt, rola i strona zostają.
export async function rotateFile(deg) {
  if (!S.job || S.busy) return;
  if (!(await resetSteps("Obrócić plik?", "były robione na pliku przed obrotem"))) return;
  const jid = S.job.job_id;
  S.busy = "Obracam plik…"; changed();
  try {
    const job = await post(`/api/jobs/${jid}/rotate`, { deg, page: S.page });
    if (!same(jid)) return;
    resetJobState();
    S.job = job; S.analysis = null; S.analysisFor = null; S.fitNext = true; S.rotErr = "";
  } catch (e) {
    if (!same(jid)) return;
    S.rotErr = e.message;
  }
  S.busy = null;
  changed();
}

// Suwaki w rozdziałach: porównanie stanu tuż przed i tuż po tym kroku.
document.querySelectorAll(".mini:not(.sim) input").forEach((sl) => sl.addEventListener("input", () => {
  S.cmp = { step: sl.dataset.step, v: +sl.value };
  changed();
}));
// suwaki symulacji (Symulacja wydruku: ekran ↔ druk; Akceptacja: wydruk przed ↔ po poprawkach)
document.querySelectorAll(".mini.sim input").forEach((sl) => sl.addEventListener("input", () => {
  S.cmp = null; S.sim = sl.closest(".mini").dataset.sim; S.simMix = +sl.value;
  changed();
}));

// Wspólny dół rozdziału z poprawką: przycisk, „Cofnij", pominięcie, suwak, błąd.
export function stepControls(pre, name, { canDo = true, doLabel, skip = "" } = {}) {
  const on = S.job.versions.some((v) => v.step === name);
  const busy = !!S.busy;
  const b = $(pre + "Do"), u = $(pre + "Undo"), sk = $(pre + "Skip"), mini = $(pre + "Mini"), er = $(pre + "Err");
  b.hidden = on; b.disabled = busy || !canDo;
  if (doLabel) b.textContent = doLabel;
  u.hidden = !on && !(S.settle[name] && S.settle[name] !== "auto"); u.disabled = busy;
  u.textContent = on ? "Cofnij" : "Zmień decyzję";
  if (sk) {                       // przycisk (uwaga Tomasza), więc wielką literą
    sk.hidden = on || !skip || !!S.settle[name]; sk.disabled = busy;
    sk.textContent = skip ? skip[0].toUpperCase() + skip.slice(1) : "";
  }
  if (mini) {
    mini.hidden = !on;
    const inp = mini.querySelector("input");
    if (!S.cmp || S.cmp.step !== name) inp.value = 100;
  }
  if (er) { er.hidden = !S.stepErr[name]; er.textContent = S.stepErr[name] || ""; }
}
