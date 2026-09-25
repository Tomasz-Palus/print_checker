// PODGLĄD. Pokazuje „scenę": ramkę (stronę, na którą patrzymy) i jedną albo dwie warstwy
// (wersje pliku) położone na niej w milimetrach. Dwie warstwy = porównanie przed/po:
// górna przenika się z dolną (`mix`).
//
// Każda warstwa ma swoją piramidę z serwera (render.py): najpierw podgląd całości
// (ov_q → ov), a przy powiększeniu — kafelki poziomu, który pasuje do powiększenia.
// Tu nic się nie renderuje: przeglądarka tylko czyta gotowe pliki, więc przewijanie
// i powiększanie nigdy nie czekają na Ghostscripta.
import { $, api } from "./util.js";
import { S } from "./state.js";

const PAD = 28;            // margines wokół sceny przy „Dopasuj"
const TILE = 1024;
const PAR = 6;             // ile kafelków ściągamy naraz

const stage = $("vStage");
const sizer = document.createElement("div");
const canvas = $("vCanvas");
stage.appendChild(sizer);
sizer.style.position = "relative";
sizer.appendChild(canvas);
canvas.style.position = "absolute";

let scene = null;          // {frame:{w,h}, k, layers:[spec], mix, overlay, frameLabel, dimOutside, clip}
let zoom = "fit";          // "fit" albo px ekranu na mm ramki
let bounds = { x: 0, y: 0, w: 1, h: 1 };   // obszar canvasu w mm ramki
let margin = { x: PAD, y: PAD };
let hilite = null, hiliteTimer = null;
let naviOn = true;
try { naviOn = localStorage.getItem("adcheck.navi") !== "0"; } catch (_) {}
const listeners = [];
export const onViewChange = (fn) => listeners.push(fn);

// ------------------------------------------------------------------ warstwa (jedna wersja pliku)
const live = new Map();    // klucz → Layer
const queue = [];
let inflight = 0;

const layerKey = (s) => `${s.vid}|${s.page}|${Math.round(s.pageMm.w * s.k * 10)}x${Math.round(s.pageMm.h * s.k * 10)}|${s.op ? 1 : 0}${s.pr ? 1 : 0}`;

class Layer {
  constructor(spec) {
    this.spec = spec; this.key = layerKey(spec);
    this.el = document.createElement("div"); this.el.className = "layer shadow";
    this.ov = document.createElement("img"); this.ov.className = "ov"; this.ov.alt = ""; this.ov.draggable = false;
    this.tilesEl = document.createElement("div"); this.tilesEl.className = "tiles";
    this.el.append(this.ov, this.tilesEl);
    this.view = ""; this.plan = null; this.state = "wait"; this.done = 0; this.total = 0;
    this.quick = false; this.ovLevel = 0; this.tiles = new Map(); this.dead = false; this.tries = 0;
    this.poll(true);
  }
  url(extra = "") {
    const s = this.spec;
    return `/api/jobs/${S.job.job_id}/view?v=${s.vid}&page=${s.page}`
      + `&w_mm=${(s.pageMm.w * s.k).toFixed(2)}&h_mm=${(s.pageMm.h * s.k).toFixed(2)}`
      + `&op=${s.op ? 1 : 0}&pr=${s.pr ? 1 : 0}${extra}`;
  }
  async poll(start) {
    clearTimeout(this.timer);
    if (this.dead || !S.job) return;
    let r;
    try {
      r = await api(this.url(), start ? { method: "POST" } : undefined);
    } catch (_) {
      r = { state: "err" };
    }
    if (this.dead) return;
    if (r.state === "gone") { this.state = "gone"; progress(); return; }
    if (r.key) { this.view = r.key; this.plan = r.plan; }
    this.state = r.state; this.done = r.done || 0; this.total = r.total || 0;
    if (r.quick) this.quick = true;
    this.loadOverview();
    progress();
    draw();
    // przerwany / nieznany / chwilowy błąd — zamawiamy jeszcze raz (do 30 razy)
    if (["stale", "idle", "err"].includes(r.state)) {
      if (++this.tries <= 30) this.timer = setTimeout(() => this.poll(true), Math.min(4000, 400 * this.tries));
      return;
    }
    if (r.state !== "done") this.timer = setTimeout(() => this.poll(false), 600);
  }
  tileUrl(name) { return `/api/jobs/${S.job.job_id}/tile/${this.view}/${name}`; }
  loadOverview() {
    const want = this.state === "done" ? 2 : this.quick ? 1 : 0;
    if (want <= this.ovLevel || !this.view) return;
    const url = this.tileUrl(want === 2 ? "ov.jpg" : "ov_q.jpg");
    const img = new Image();
    img.onload = () => {
      if (this.dead || want <= this.ovLevel) return;
      this.ovLevel = want; this.ov.src = url; this.ready = true;
      wait(); draw();
    };
    img.src = url;
  }
  drawTiles(z, vp, lx, ly) {
    const p = this.plan;
    const w = this.spec.rect.w * z;
    const need = w * Math.min(window.devicePixelRatio || 1, 2);
    if (!p || !p.levels.length || need <= p.ov[0] * 1.15 || this.ovLevel === 0) { this.clearTiles(); return; }
    const full = this.state === "done";
    let lvl = 0;
    if (full) for (let i = p.levels.length - 1; i >= 0; i--) if (p.levels[i].w >= need) { lvl = i; break; }
    const L = p.levels[lvl], k = w / L.w;
    const rows = full ? L.rows : Math.max(0, this.done - 1);     // pasma, które już są policzone
    const x0 = Math.max(0, Math.floor((vp.x - lx) / k / TILE) - 1), x1 = Math.min(L.cols - 1, Math.floor((vp.x + vp.w - lx) / k / TILE) + 1);
    const y0 = Math.max(0, Math.floor((vp.y - ly) / k / TILE) - 1), y1 = Math.min(L.rows - 1, rows - 1, Math.floor((vp.y + vp.h - ly) / k / TILE) + 1);
    const keep = new Set();
    const cx = (vp.x + vp.w / 2 - lx) / k / TILE, cy = (vp.y + vp.h / 2 - ly) / k / TILE;
    for (let ty = y0; ty <= y1; ty++) for (let tx = x0; tx <= x1; tx++) {
      const key = `${lvl},${tx},${ty}`;
      keep.add(key);
      const t = this.tiles.get(key);
      if (t) { if (t.el) place(t.el, L, k, tx, ty); continue; }
      const rec = { lvl, tx, ty, L, k, d: Math.hypot(tx + .5 - cx, ty + .5 - cy), el: null };
      this.tiles.set(key, rec);
      queue.push({ layer: this, key, rec });
    }
    for (const [key, t] of this.tiles) {                // inne poziomy i to, co daleko poza widokiem
      if (!keep.has(key)) { t.el?.remove(); t.dead = true; this.tiles.delete(key); }
    }
    pump();
  }
  clearTiles() { for (const t of this.tiles.values()) { t.el?.remove(); t.dead = true; } this.tiles.clear(); }
  kill() {
    this.dead = true; clearTimeout(this.timer); this.clearTiles(); this.el.remove();
    if (this.view && this.state !== "done" && S.job)      // nikt już na to nie czeka — zwolnij kolejkę
      fetch(`/api/jobs/${S.job.job_id}/view/${this.view}/cancel`, { method: "POST" }).catch(() => {});
  }
}

function place(el, L, k, tx, ty) {
  const w = Math.min(TILE, L.w - tx * TILE), h = Math.min(TILE, L.h - ty * TILE);
  el.style.left = tx * TILE * k + "px"; el.style.top = ty * TILE * k + "px";
  el.style.width = w * k + 0.5 + "px"; el.style.height = h * k + 0.5 + "px";   // +0,5 px: bez szczelin
}

function pump() {
  queue.sort((a, b) => a.rec.d - b.rec.d);
  while (inflight < PAR && queue.length) {
    const { layer, key, rec } = queue.shift();
    if (rec.dead || layer.dead || layer.tiles.get(key) !== rec) continue;
    inflight++;
    const img = new Image();
    img.alt = ""; img.draggable = false;
    const fin = () => { inflight--; pump(); };
    img.onload = () => {
      if (!rec.dead && !layer.dead) { rec.el = img; place(img, rec.L, rec.k, rec.tx, rec.ty); layer.tilesEl.appendChild(img); }
      fin();
    };
    img.onerror = () => { if (layer.tiles.get(key) === rec) layer.tiles.delete(key); fin(); };   // jeszcze nie ma — spróbujemy przy następnym rysowaniu
    img.src = layer.tileUrl(`L${rec.lvl}_${rec.tx}_${rec.ty}.jpg`);
  }
}

// ------------------------------------------------------------------ scena
export function setScene(sc) {
  scene = sc;
  if (!sc) {
    for (const l of live.values()) l.kill();
    live.clear(); canvas.innerHTML = ""; $("navi").hidden = true; progress(); wait();
    return;
  }
  // Dwie IDENTYCZNE warstwy (np. „Akceptacja" pliku bez poprawek: przed = po) to jedna warstwa.
  // Inaczej obie trafiały na ten sam element, a przezroczystość górnej (suwak na „przed" = 0)
  // chowała go całkiem — podgląd był biały (Tomasz 25.09).
  { const keys = sc.layers.map(layerKey); sc.layers = sc.layers.filter((_, i) => keys.indexOf(keys[i]) === i); }
  const want = sc.layers.map(layerKey);
  const old = [...live.values()];
  for (const [k, l] of live) if (!want.includes(k)) { l.kill(); live.delete(k); }
  sc.layers.forEach((spec, i) => {
    const k = want[i];
    let l = live.get(k);
    if (!l) {
      l = new Layer(spec);
      // Póki nowa wersja się nie wczyta, pokazujemy to, co leżało na tym miejscu (o ile ma
      // te same proporcje) — zamiast pustego miejsca na kilka sekund.
      const prev = old[i];
      if (prev && prev.ovLevel && prev.spec.page === spec.page && Math.abs(prev.spec.rect.w / prev.spec.rect.h - spec.rect.w / spec.rect.h) < 0.002) {
        l.ov.src = prev.ov.src;
      }
      live.set(k, l);
    }
    l.spec = spec;
    l.el.style.zIndex = String(2 * i + 1);
    if (l.el.parentNode !== canvas) canvas.appendChild(l.el);
  });
  // obszar canvasu = ramka + to, co z warstw wystaje poza nią (chyba że przycinamy)
  let x0 = 0, y0 = 0, x1 = sc.frame.w, y1 = sc.frame.h;
  if (!sc.clip) for (const s of sc.layers) {
    x0 = Math.min(x0, s.rect.x); y0 = Math.min(y0, s.rect.y);
    x1 = Math.max(x1, s.rect.x + s.rect.w); y1 = Math.max(y1, s.rect.y + s.rect.h);
  }
  bounds = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  canvas.style.overflow = sc.clip ? "hidden" : "";
  draw();
  progress(); wait();
}

export function setMix(v) { if (scene) { scene.mix = v; draw(); } }

function z100() { return scene ? scene.k * S.cssPxPerIn / 25.4 : 1; }
function zFit() {
  return Math.max(0.001, Math.min((stage.clientWidth - 2 * PAD) / bounds.w, (stage.clientHeight - 2 * PAD) / bounds.h));
}
export const currentZoom = () => (zoom === "fit" ? zFit() : zoom);
export const is100 = () => !!scene && Math.abs(currentZoom() / z100() - 1) < 0.01;

// Powiększenie wokół punktu (px w oknie podglądu) — punkt pod kursorem zostaje na miejscu.
export function zoomTo(z, ax = stage.clientWidth / 2, ay = stage.clientHeight / 2) {
  if (!scene) return;
  const z0 = currentZoom();
  const mx = (stage.scrollLeft + ax - margin.x) / z0, my = (stage.scrollTop + ay - margin.y) / z0;
  // największe przybliżenie = rzeczywista wielkość (dalej widać już tylko piksele ekranu)
  zoom = z === "fit" ? "fit" : Math.max(0.01, Math.min(z, z100()));
  drawNow();
  if (zoom !== "fit") {
    const z1 = currentZoom();
    stage.scrollLeft = mx * z1 + margin.x - ax;
    stage.scrollTop = my * z1 + margin.y - ay;
  }
  draw();
}
export const zoomFit = () => zoomTo("fit");
export const zoom100 = () => zoomTo(z100());
export const zoomBy = (f, ax, ay) => zoomTo(currentZoom() * f, ax, ay);

// Pokaż prostokąt (mm ramki): w rozmiarze rzeczywistym albo tak, żeby się zmieścił.
export const frameMm = () => (scene ? { ...scene.frame } : null);
export function clearHilite() { hilite = null; clearTimeout(hiliteTimer); if (scene) draw(); }
// `keep` — podświetlenie zostaje, aż ktoś je zdejmie (nawigacja po miejscach z „Jakości")
export function showRect(r, label, exact100 = false, keep = false) {
  if (!scene) return;
  const fit = Math.min(stage.clientWidth * 0.7 / r.w, stage.clientHeight * 0.7 / r.h);
  zoom = exact100 ? z100() : Math.min(fit, z100());
  drawNow();
  const z = currentZoom();
  stage.scrollLeft = (r.x + r.w / 2 - bounds.x) * z + margin.x - stage.clientWidth / 2;
  stage.scrollTop = (r.y + r.h / 2 - bounds.y) * z + margin.y - stage.clientHeight / 2;
  hilite = { r, label };
  clearTimeout(hiliteTimer);
  if (!keep) hiliteTimer = setTimeout(() => { hilite = null; draw(); }, 4000);
  draw();
}

// ------------------------------------------------------------------ rysowanie
let drawQueued = false;
export function draw() {
  if (drawQueued) return;
  drawQueued = true;
  requestAnimationFrame(() => { drawQueued = false; drawNow(); });
}

function drawNow() {
  if (!scene) return;
  const z = currentZoom();
  const cw = bounds.w * z, ch = bounds.h * z;
  // „Dopasuj" mieści wszystko w oknie — bez pasków przewijania (na ekranach 4K ułamki pikseli
  // potrafiły je włączyć)
  stage.style.overflow = zoom === "fit" ? "hidden" : "auto";
  margin = { x: Math.max(PAD, (stage.clientWidth - cw) / 2), y: Math.max(PAD, (stage.clientHeight - ch) / 2) };
  sizer.style.width = Math.floor(cw + 2 * margin.x) + "px"; sizer.style.height = Math.floor(ch + 2 * margin.y) + "px";
  canvas.style.left = margin.x + "px"; canvas.style.top = margin.y + "px";
  canvas.style.width = cw + "px"; canvas.style.height = ch + "px";
  stage.classList.toggle("pan", zoom !== "fit" && (cw > stage.clientWidth || ch > stage.clientHeight));
  const px = (x) => (x - bounds.x) * z, py = (y) => (y - bounds.y) * z;
  const vp = { x: stage.scrollLeft - margin.x, y: stage.scrollTop - margin.y, w: stage.clientWidth, h: stage.clientHeight };
  scene.layers.forEach((s, i) => {
    const l = live.get(layerKey(s));
    if (!l) return;
    const r = s.rect;
    Object.assign(l.el.style, { left: px(r.x) + "px", top: py(r.y) + "px", width: r.w * z + "px", height: r.h * z + "px" });
    l.el.style.opacity = i > 0 ? String(scene.mix ?? 1) : "1";
    l.el.style.zIndex = String(2 * i + 1);          // między warstwami jest zasłona (niżej)
    l.el.classList.toggle("shadow", i === 0 && !scene.frameLabel);
    l.drawTiles(z, vp, px(r.x), py(r.y));
  });
  drawVeil(z, px, py);
  drawDecor(z, px, py);
  drawNavi();
  for (const f of listeners) f();
}

function decor(cls) {
  let el = canvas.querySelector(":scope > ." + cls);
  if (!el) { el = document.createElement("div"); el.className = cls; canvas.appendChild(el); }
  return el;
}
function box(el, x, y, w, h) {
  Object.assign(el.style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
}

// Tło dołożone z krawędzi — podgląd tego, co zrobi steps._fill_edges / _mirror: pasy z krawędzi
// projektu (jeden rząd pikseli powielony na margines) albo odbicia lustrzane. Źródłem jest
// podgląd całości warstwy (ov). Elementy budujemy tylko przy zmianie, przy przewijaniu je przesuwamy.
let fillKey = "";
function drawFill(z, px, py) {
  const el = decor("fill");
  const f = scene.fill, l = f && live.get(layerKey(scene.layers[0]));
  const img = l && l.ov;
  if (!f || !img || !img.naturalWidth) { el.hidden = true; fillKey = ""; return; }
  el.hidden = false;
  const r = scene.layers[0].rect;
  const L = px(r.x), T = py(r.y), W = r.w * z, H = r.h * z;
  const fx = px(0), fy = py(0), fw = scene.frame.w * z, fh = scene.frame.h * z;
  const nw = img.naturalWidth, nh = img.naturalHeight;
  // odcięta krawędź projektu (jaśniejsze piksele z eksportu): co najmniej 1,5 piksela podglądu
  const ov = Math.min(0.05 * W, 0.05 * H, Math.max(1.5 * W / nw, f.trimMm * z));
  const mL = L - fx, mT = T - fy, mR = fx + fw - (L + W), mB = fy + fh - (T + H);
  const key = [img.src, f.mode, Math.round(ov * nw / W), mL > 0, mT > 0, mR > 0, mB > 0].join("|");
  if (key !== fillKey) {
    fillKey = key; el.innerHTML = "";
    if (f.mode === "mirror") {
      for (let i = -9; i <= 9; i++) for (let j = -9; j <= 9; j++) {
        if (!i && !j) continue;
        const d = document.createElement("div"), im = document.createElement("img");
        im.src = img.src; d.dataset.i = i; d.dataset.j = j; d.appendChild(im); el.appendChild(d);
      }
    } else {
      const cx = Math.min(nw - 2, Math.max(1, Math.round(ov * nw / W))), cy = Math.min(nh - 2, Math.max(1, Math.round(ov * nh / H)));
      const slice = (side, sx, sy, sw, sh) => {
        const d = document.createElement("div"), c = document.createElement("canvas");
        c.width = sw; c.height = sh;
        try { c.getContext("2d").drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh); } catch (_) {}
        d.dataset.side = side; d.appendChild(c); el.appendChild(d);
      };
      if (mL > 0) slice("L", cx, 0, 1, nh);
      if (mR > 0) slice("R", nw - 1 - cx, 0, 1, nh);
      if (mT > 0) slice("T", 0, cy, nw, 1);
      if (mB > 0) slice("B", 0, nh - 1 - cy, nw, 1);
      if (mL > 0 && mT > 0) slice("LT", cx, cy, 1, 1);
      if (mR > 0 && mT > 0) slice("RT", nw - 1 - cx, cy, 1, 1);
      if (mL > 0 && mB > 0) slice("LB", cx, nh - 1 - cy, 1, 1);
      if (mR > 0 && mB > 0) slice("RB", nw - 1 - cx, nh - 1 - cy, 1, 1);
    }
  }
  box(el, fx, fy, fw, fh);
  const O = 2;                                        // zakładka — bez włosowej szczeliny
  if (f.mode === "mirror") {
    const w = Math.max(1, W - 2 * ov), h = Math.max(1, H - 2 * ov), x0 = L + ov - fx, y0 = T + ov - fy;
    for (const d of el.children) {
      const i = +d.dataset.i, j = +d.dataset.j;
      const x = x0 + i * w, y = y0 + j * h;
      const vis = x < fw && y < fh && x + w > 0 && y + h > 0;
      d.hidden = !vis;
      if (!vis) continue;
      box(d, x, y, w + 1, h + 1);
      d.style.transform = `scale(${i % 2 ? -1 : 1},${j % 2 ? -1 : 1})`;
      box(d.firstChild, -ov, -ov, W, H);
    }
    return;
  }
  const lx = L - fx, ty = T - fy;
  const pos = { L: [0, ty, mL + ov + O, H], R: [lx + W - ov - O, ty, mR + ov + O, H],
                T: [lx, 0, W, mT + ov + O], B: [lx, ty + H - ov - O, W, mB + ov + O],
                LT: [0, 0, mL + ov + O, mT + ov + O], RT: [lx + W - ov - O, 0, mR + ov + O, mT + ov + O],
                LB: [0, ty + H - ov - O, mL + ov + O, mB + ov + O], RB: [lx + W - ov - O, ty + H - ov - O, mR + ov + O, mB + ov + O] };
  for (const d of el.children) box(d, ...pos[d.dataset.side]);
}

// Suwak przed/po, gdy „przed" wystaje poza „po" (spady, szablon, wymiar): to, czego w „po" już
// nie ma, znika razem z suwakiem. Wcześniej pas spadów z „przed" było widać także na „po" —
// suwak wyglądał, jakby pokazywał tylko „przed" (Tomasz 25.09). Zasłona w kolorze tła podglądu
// leży między warstwami: otwór = obszar „po", reszta przykryta w miarę przesuwania suwaka.
function drawVeil(z, px, py) {
  const veil = decor("veil");
  const [a, b] = scene.layers;
  const out = a && b && (a.rect.x < b.rect.x - 1e-6 || a.rect.y < b.rect.y - 1e-6
    || a.rect.x + a.rect.w > b.rect.x + b.rect.w + 1e-6 || a.rect.y + a.rect.h > b.rect.y + b.rect.h + 1e-6);
  veil.hidden = !out || !(scene.mix > 0);
  if (veil.hidden) return;
  box(veil, px(b.rect.x), py(b.rect.y), b.rect.w * z, b.rect.h * z);
  veil.style.boxShadow = `0 0 0 100000px rgba(233, 235, 239, ${scene.mix})`;
}

function drawDecor(z, px, py) {
  // biała „kartka" formatu pod warstwami — puste pasy wyglądają jak na wydruku
  const paper = decor("paper");
  box(paper, px(0), py(0), scene.frame.w * z, scene.frame.h * z);
  drawFill(z, px, py);
  // linie szablonu — wyśrodkowane na ramce, w skali 1:1
  const ov = decor("overlay");
  const o = scene.overlay;
  ov.hidden = !(o && S.overlayOn);
  if (!ov.hidden) {
    if (ov.dataset.svg !== o.key) { ov.innerHTML = o.svg; ov.dataset.svg = o.key; }
    box(ov, px((scene.frame.w - o.w) / 2), py((scene.frame.h - o.h) / 2), o.w * z, o.h * z);
  }
  // ramka formatu i przyciemnienie tego, co poza nią (rozdział „Wymiar")
  const fr = decor("frame"), dim = decor("dim");
  fr.hidden = !scene.frameLabel;
  dim.hidden = !scene.dimOutside;
  for (const el of [fr, dim]) box(el, px(0), py(0), scene.frame.w * z, scene.frame.h * z);
  if (!fr.hidden) fr.innerHTML = `<span>${scene.frameLabel}</span>`;
  // podświetlony obszar
  const hl = decor("hilite");
  hl.hidden = !hilite;
  if (hilite) {
    const r = hilite.r;
    box(hl, px(Math.max(0, r.x)) - 4, py(Math.max(0, r.y)) - 4,
        (Math.min(scene.frame.w, r.x + r.w) - Math.max(0, r.x)) * z + 8, (Math.min(scene.frame.h, r.y + r.h) - Math.max(0, r.y)) * z + 8);
    hl.innerHTML = hilite.label ? `<span>${hilite.label}</span>` : "";
  }
}

// ------------------------------------------------------------------ nawigator
const navi = $("navi"), naviIn = $("naviIn");
function drawNavi() {
  $("vNavi").classList.toggle("on", naviOn);
  const big = sizer.offsetWidth > stage.clientWidth + 2 || sizer.offsetHeight > stage.clientHeight + 2;
  navi.hidden = !(scene && naviOn && big && zoom !== "fit");
  if (navi.hidden) return;
  const s = 200 / Math.max(bounds.w, bounds.h);
  naviIn.style.width = bounds.w * s + "px"; naviIn.style.height = bounds.h * s + "px";
  const l = live.get(layerKey(scene.layers[0]));
  let img = naviIn.querySelector("img");
  if (!img) { img = document.createElement("img"); naviIn.appendChild(img); }
  if (l && l.ov.src && img.src !== l.ov.src) img.src = l.ov.src;
  const r = scene.layers[0].rect;
  box(img, (r.x - bounds.x) * s, (r.y - bounds.y) * s, r.w * s, r.h * s);
  let b = naviIn.querySelector(".box");
  if (!b) { b = document.createElement("div"); b.className = "box"; naviIn.appendChild(b); }
  const z = currentZoom();
  box(b, (stage.scrollLeft - margin.x) / z * s, (stage.scrollTop - margin.y) / z * s, stage.clientWidth / z * s, stage.clientHeight / z * s);
}
function naviGo(e) {
  const r = naviIn.getBoundingClientRect(), z = currentZoom();
  const s = r.width / bounds.w;
  stage.scrollLeft = (e.clientX - r.left) / s * z + margin.x - stage.clientWidth / 2;
  stage.scrollTop = (e.clientY - r.top) / s * z + margin.y - stage.clientHeight / 2;
}
navi.addEventListener("pointerdown", (e) => { e.preventDefault(); e.stopPropagation(); navi.setPointerCapture(e.pointerId); navi.dataset.drag = "1"; naviGo(e); });
navi.addEventListener("pointermove", (e) => { if (navi.dataset.drag) naviGo(e); });
navi.addEventListener("pointerup", () => { navi.dataset.drag = ""; });
export function setNavi(on) {
  naviOn = on;
  try { localStorage.setItem("adcheck.navi", on ? "1" : "0"); } catch (_) {}
  draw();
}
export const naviIsOn = () => naviOn;

// ------------------------------------------------------------------ postęp i czekanie
function progress() {
  const el = $("vProg");
  const act = [...live.values()].filter((l) => ["wait", "queued", "run"].includes(l.state));
  el.hidden = !act.length;
  if (!act.length) return;
  const done = act.reduce((a, l) => a + l.done, 0), total = act.reduce((a, l) => a + l.total, 0);
  const pct = total ? Math.min(99, Math.round(done / total * 100)) : 0;
  el.querySelector("i").style.width = pct + "%";
  el.querySelector(".t").textContent = `pełna jakość ${pct} %`;
  el.title = "Liczę cały projekt w pełnej jakości (120 ppi na wydruku) — raz, potem powiększanie działa bez czekania";
}
let busyTxt = null;
export function setBusy(t) { if (t !== busyTxt) { busyTxt = t; wait(); } }
function wait() {
  const any = !!scene && [...live.values()].some((l) => l.ov.src);
  $("vWait").hidden = !busyTxt && (!scene || any);
  $("vWait").querySelector(".t").textContent = busyTxt || "wczytuję podgląd…";
}

// ------------------------------------------------------------------ mysz i lupki
// Lupki jak w Photoshopie: przycisk WYBIERA narzędzie; potem kliknięcie w podgląd powiększa
// (pomniejsza), a przeciągnięcie zaznacza obszar. Spacja trzymana = chwilowo „rączka".
let tool = null, space = false, drag = null, mq = null;
const marq = document.createElement("div");
marq.className = "marquee"; marq.hidden = true;

export function setTool(t) {
  tool = tool === t ? null : t;
  stage.classList.toggle("zin", tool === "in");
  stage.classList.toggle("zout", tool === "out");
  for (const f of listeners) f();
}
export const currentTool = () => tool;

function local(e) {
  const r = stage.getBoundingClientRect();
  return { x: e.clientX - r.left, y: e.clientY - r.top };
}
stage.addEventListener("mousedown", (e) => {
  if (e.button !== 0 || !scene) return;
  if (tool && !space) {
    const p = local(e);
    mq = { x0: p.x, y0: p.y, x1: p.x, y1: p.y };
    e.preventDefault();
    return;
  }
  if (!stage.classList.contains("pan") && !space) return;
  drag = { x: e.clientX, y: e.clientY, sl: stage.scrollLeft, st: stage.scrollTop };
  stage.classList.add("panning"); e.preventDefault();
});
window.addEventListener("mousemove", (e) => {
  if (mq) {
    const p = local(e);
    mq.x1 = p.x; mq.y1 = p.y;
    const host = $("view");
    if (marq.parentNode !== host) host.appendChild(marq);
    const r = stage.getBoundingClientRect(), pr = host.getBoundingClientRect();
    Object.assign(marq.style, { left: Math.min(mq.x0, mq.x1) + r.left - pr.left + "px", top: Math.min(mq.y0, mq.y1) + r.top - pr.top + "px",
                                width: Math.abs(mq.x1 - mq.x0) + "px", height: Math.abs(mq.y1 - mq.y0) + "px" });
    marq.hidden = Math.abs(mq.x1 - mq.x0) < 5 && Math.abs(mq.y1 - mq.y0) < 5;
    return;
  }
  if (!drag) return;
  stage.scrollLeft = drag.sl - (e.clientX - drag.x);
  stage.scrollTop = drag.st - (e.clientY - drag.y);
});
window.addEventListener("mouseup", () => {
  if (mq) {
    const x = Math.min(mq.x0, mq.x1), y = Math.min(mq.y0, mq.y1), w = Math.abs(mq.x1 - mq.x0), h = Math.abs(mq.y1 - mq.y0);
    marq.hidden = true; mq = null;
    const z = currentZoom(), vw = stage.clientWidth, vh = stage.clientHeight;
    if (w < 6 || h < 6) {                                  // kliknięcie — krok powiększenia
      zoomBy(tool === "out" ? 1 / 1.5 : 1.5, x, y);
      return;
    }
    // zaznaczenie: lupka + → obszar wypełnia okno; lupka − → całe okno mieści się w obszarze
    const f = tool === "out" ? Math.min(w / vw, h / vh) : Math.min(vw / w, vh / h);
    const mx = (stage.scrollLeft + x + w / 2 - margin.x) / z, my = (stage.scrollTop + y + h / 2 - margin.y) / z;
    zoom = Math.max(0.01, Math.min(z * f, z100()));
    drawNow();
    const z1 = currentZoom();
    stage.scrollLeft = mx * z1 + margin.x - vw / 2;
    stage.scrollTop = my * z1 + margin.y - vh / 2;
    draw();
    return;
  }
  drag = null; stage.classList.remove("panning");
});
window.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea")) return;
  if (e.code === "Space" && !space) { space = true; stage.classList.add("space"); if (scene) e.preventDefault(); }
  if (e.key === "Escape" && tool) setTool(tool);
  if (e.code === "KeyZ" && !e.ctrlKey && !e.metaKey) setTool(e.altKey ? "out" : "in");
});
window.addEventListener("keyup", (e) => { if (e.code === "Space") { space = false; stage.classList.remove("space"); } });
stage.addEventListener("wheel", (e) => {
  if (!e.ctrlKey || !scene) return;
  e.preventDefault();
  const p = local(e);
  zoomBy(e.deltaY < 0 ? 1.2 : 1 / 1.2, p.x, p.y);
}, { passive: false });
stage.addEventListener("scroll", draw);
window.addEventListener("resize", draw);
