// Ustawienia: kalibracja monitora (dla „100 %"), dokładność oceny jakości, indeks wymiarów.
import { $, api } from "./util.js";
import { S, changed } from "./state.js";

const BAR_PX = 400;           // pasek wzorcowy ma stałą długość w px CSS

function ruler(svg, lenPx, label, end, mmPerPx) {
  const pad = 20, base = 42;
  let s = "";
  if (mmPerPx) {
    const pxmm = 1 / mmPerPx;
    for (let i = 0; i <= Math.floor(lenPx * mmPerPx); i++) {
      const x = (pad + i * pxmm).toFixed(2), l = i % 10 === 0 ? 20 : i % 5 === 0 ? 13 : 7;
      if (pxmm >= 1.6 || i % 5 === 0) s += `<line x1="${x}" y1="${base}" x2="${x}" y2="${base - l}" stroke="#111" stroke-width="${i % 10 ? .8 : 1.2}"/>`;
    }
  }
  const x0 = pad, x1 = pad + lenPx;
  s += `<line x1="${x0}" y1="${base}" x2="${x1}" y2="${base}" stroke="#111"/>`;
  for (const x of [x0, x1]) s += `<line x1="${x}" y1="6" x2="${x}" y2="${base + 4}" stroke="#e0322b" stroke-width="1.5"/>`;
  s += `<text x="${(x0 + x1) / 2}" y="12" font-size="9" text-anchor="middle" fill="#888">${label}</text>`;
  s += `<text x="${x1}" y="${base + 13}" font-size="9" text-anchor="middle" fill="#e0322b">${end}</text>`;
  svg.setAttribute("width", lenPx + 2 * pad);
  svg.setAttribute("height", 58);
  svg.innerHTML = s;
}

function renderCal() {
  const dpr = window.devicePixelRatio || 1;
  $("calRes").textContent = `ekran ${Math.round(screen.width * dpr)} × ${Math.round(screen.height * dpr)} px`;
  $("calNow").innerHTML = S.calibrated ? `Teraz: <b>${S.cssPxPerIn.toFixed(1)} px/cal</b>.`
                                       : `Brak kalibracji — przyjęte domyślne 96 px/cal.`;
  const mmpx = 25.4 / S.cssPxPerIn;
  ruler($("calRuler"), BAR_PX, "pasek wzorcowy", "koniec", S.calibrated ? mmpx : null);
  ruler($("calCheck"), 100 / mmpx, "od czerwonej do czerwonej = 100 mm", "100 mm", mmpx);
}
// dla samouczka: ile razy zapisano kalibrację i ostatni stan indeksu wymiarów
let calSaves = 0, idxLast = null;
export const calCount = () => calSaves;
export const idxState = () => idxLast;

function saveCal(v) {
  calSaves++;
  S.cssPxPerIn = v; S.calibrated = v !== 96;
  try { v === 96 ? localStorage.removeItem("adcheck.cssPxPerIn") : localStorage.setItem("adcheck.cssPxPerIn", String(v)); } catch (_) {}
  renderCal(); changed();
}

export const detailBlock = () => {
  try { const v = +localStorage.getItem("adcheck.dmBlock"); if (v === 64 || v === 128) return v; } catch (_) {}
  return 128;
};

// ---------------------------------------------------------------- indeks wymiarów szablonów
let idxTimer = null;
async function pollIdx(start, retry) {
  let st;
  try {
    st = start ? await api(`/api/sizeindex/build${retry ? "?retry=1" : ""}`, { method: "POST" })
               : await api("/api/sizeindex/status");
  } catch (e) { $("idxSt").textContent = e.message; return; }
  idxLast = st;
  const total = st.total_products || 0, pct = total ? Math.round(st.indexed / total * 100) : 0;
  $("idxSt").innerHTML = `Znane wymiary: <b>${st.indexed}</b> z ${total} produktów (${pct} %)`
    + (st.failed ? `, nieudanych ${st.failed}` : "") + (st.running ? ` — <b>pobieram</b> ${st.done}/${st.total}…` : "")
    + (st.last_error ? `<br>Ostatni błąd: ${st.last_error}` : "");
  $("idxBar").style.width = pct + "%";
  $("idxBuild").hidden = !!st.running; $("idxRetry").hidden = !!st.running || !st.failed; $("idxStop").hidden = !st.running;
  clearTimeout(idxTimer);
  if (st.running) idxTimer = setTimeout(() => pollIdx(false), 1500);
}

export function initSettings() {
  $("btnSettings").onclick = () => {
    renderCal();
    document.querySelectorAll('input[name="dmBlock"]').forEach((r) => { r.checked = +r.value === detailBlock(); });
    pollIdx(false);
    $("settings").hidden = false;
  };
  $("setClose").onclick = () => { $("settings").hidden = true; };
  $("settings").addEventListener("mousedown", (e) => { if (e.target === $("settings")) $("settings").hidden = true; });
  $("calDiagOk").onclick = () => {
    const d = parseFloat($("calDiag").value);
    if (!(d > 4)) return;
    const dpr = window.devicePixelRatio || 1;
    saveCal(Math.hypot(screen.width * dpr, screen.height * dpr) / d / dpr);
  };
  $("calMmOk").onclick = () => { const m = parseFloat($("calMm").value); if (m > 10) saveCal(BAR_PX / m * 25.4); };
  $("calReset").onclick = () => saveCal(96);
  document.querySelectorAll('input[name="dmBlock"]').forEach((r) => r.addEventListener("change", () => {
    try { localStorage.setItem("adcheck.dmBlock", r.value); } catch (_) {}
    changed();
  }));
  $("idxBuild").onclick = () => pollIdx(true, false);
  $("idxRetry").onclick = () => pollIdx(true, true);
  $("idxStop").onclick = async () => { try { await api("/api/sizeindex/stop", { method: "POST" }); } catch (_) {} setTimeout(() => pollIdx(false), 800); };
}
