"""
Mapa detalu wydruku — JEDEN system oceny jakości rastra niezależny od formatu.

Zasada: oceniamy to, co fizycznie pójdzie na drukarkę. Cała strona (PDF/AI/EPS/SVG
albo obraz JPG/TIFF/PNG/PSD — po spłaszczeniu, bo tylko to się drukuje) jest
renderowana PASAMI w „rozdzielczości analizy” i badana blok po bloku (BLOCK_PX px)
metodą krzywej strat (jak analyze.effective_factor): blok, który po zmniejszeniu f×
i powiększeniu z powrotem wygląda tak samo, nie ma detalu drobniejszego niż f px —
czyli realna rozdzielczość bloku = rozdzielczość analizy / f.

- PDF-podobne: rozdzielczość analizy = ANALYSIS_PPI_PRINT (240 ppi NA WYDRUKU) × k,
  gdzie k = 10 dla plików w skali 1:10 (strona 10× mniejsza, więc liczba pikseli ta
  sama). Wektory renderują się ostro (f = 1), obraz 72 ppi wklejony do PDF-a
  wychodzi jako f ≈ 4 tam, gdzie leży — niezależnie od tego, czy jest osobnym
  obiektem, czy został spłaszczony w tło. Strona bez obrazów (sam wektor) — mapa
  pomijana.
- rastry: analiza w natywnej rozdzielczości pliku (px = px); ppi na wydruku liczy UI
  (px / mm wydruku / f), bo rozmiar wydruku może być znany dopiero po wyborze produktu.

Bloki 64 px (≈ 6,8 mm przy 240 ppi) — logo ~15–20 mm zajmuje ≥ 3 bloki i nie ginie
w ostrym otoczeniu (kafelki 512 px uśredniały je ze zdjęciem obok). Bloki jednolite
(tło) są pomijane — nie potrzebują rozdzielczości.

Skale f: 2, 2,5, 3, 4, 6 względem E(8), z regułą „kolana” (_knee): obraz powiększany
f× ma krzywą strat PŁASKĄ do f i dopiero potem skok; naturalny detal rośnie gładko.
Samo „E(f) małe” (stara reguła z analyze.py) myliło miękką treść z powiększeniem.
Krzywe liczone są też na fragmencie zmniejszonym 2× (SCALES) — dla obszarów gładkich
(bez drobnego detalu, ale z treścią) sprawdzamy kolano w skali 2 (zakres do f = 12).

Wynik NIE jest listą bloków, tylko OBSZARÓW potwierdzonych krzywą całego obszaru
(średnia ważona krzywych bloków): pojedyncze bloki z f 2–3 to szum metody na natywnych
zdjęciach, więc obszar f < 4 musi mieć ≥ 3 bloki, f ≥ 4 — ≥ 2. Rodzaje obszarów:
  upscaled        — kolano w skali 1 (pewna sygnatura powiększenia, f ≤ 6) → decyduje
                    o werdykcie (UI: „Słabe obszary”),
  upscaled-coarse — kolano dopiero w skali 2 (brak nawet grubego detalu: mocne
                    powiększenie ALBO mocne rozmycie — nie do odróżnienia) → tylko do
                    obejrzenia (UI: razem z „gładkimi”),
  soft            — gładki w każdej skali (gradient, cień, bokeh) → tylko do obejrzenia.

Ograniczenia (świadome): powiększenie „najbliższym sąsiadem” (klocki bez wygładzenia)
wygląda dla metryki jak ostre krawędzie — nie jest wykrywane (renderer wymusza
wygładzanie obrazów z PDF-a, więc dotyczy tylko rastrów powiększonych tak PRZED
zapisem); elementy < ~15 mm na wydruku giną w statystyce bloku; rozmycie celowe
i mocne powiększenie są nie do odróżnienia (stąd kategoria „gładkie”, oceń na oko).

Wynik: siatka kodów bloków (base64 uint8, CODE_OF; 13 = gładki) do heatmapy w UI,
obszary (ułamki strony fx/fy/fw/fh, factor, kind), udziały powierzchni. Postęp pasami
(wątek w tle, chunki w procesach — numpy/PIL nie zwalniają GIL wystarczająco).
"""
from __future__ import annotations

import base64
import functools
import io
import math
import os
import threading
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pymupdf
from PIL import Image

import render

Image.MAX_IMAGE_PIXELS = None

ANALYSIS_PPI_PRINT = 240.0   # 240/f: f2→120, f3→80, f6→40 — progi ocen wypadają dokładnie na stopniach
BLOCK_PX = 128          # domyślnie 128 px ≈ 13,5 mm przy 240 ppi (Ustawienia: „wysoka dokładność” = 64 px ≈ 6,8 mm)
BLOCK_CHOICES = (64, 128)
FACTORS = (2.0, 2.5, 3.0, 4.0, 6.0, 8.0)   # 8 = odniesienie E(8); 1,5 pominięte (nic nie wnosi, kosztuje 15 %)
JUMP = 2.0                                    # „kolano”: skok E między kolejnymi f > JUMP × naturalny wzrost (next/f)²
CHUNK_THREADS = max(2, min(8, (os.cpu_count() or 4) - 1))
THRESHOLD = 0.045                            # jak analyze.EFF_THRESHOLD
MIN_REF = 12.0                               # jak analyze.TILE_MIN_REF (E(8) na piksel) — poniżej blok jednolity
BAND_MAX_PX = 150_000_000                    # piksele na jeden render pasa (gs/MuPDF)
CHUNK_ROWS = 512                             # wiersze przetwarzane naraz w numpy (4 wątki × ~0,3 GB przy szer. 47 kpx)
RASTER_FULL_DECODE_PX = 400_000_000          # rastry: Pillow dekoduje całość; powyżej — obraz jest zmniejszany 2× do analizy (mówimy o tym)
MAX_REGIONS = 60
REQUIRED_PPI = 120.0    # sztywny próg z wytycznych (decyzja Tomasza: bez uwzględniania odległości)
MAX_AREAS = 300         # ile pozycji listy oddajemy do UI
MIN_REGION_MM = 10.0    # minimalny bok/pole zgłaszanego fragmentu NA WYDRUKU (decyzja Tomasza)
BASELINE_PCT = 50       # baza elementu = MEDIANA współczynników bloków z detalem.
                        # Pomiar: adFrame_Smart (natywne 120 ppi) — 90 % bloków f=1, mediana 1 → 120 ppi (bez fałszywki);
                        # 1878 (tło powiększone 3×) — 50 % bloków f=3, mediana 3 → 33 ppi (zgodnie z niezależnym
                        # pomiarem obiektowym). 25. percentyl dawał na 1878 f=2 → 50 ppi, czyli zaniżał wadę.
EXC_RATIO = 2.0         # wyjątek = fragment co najmniej 2× gorszy od BAZY swojego elementu
EXC_MIN_FACTOR = 3.0    # ...i nie mniej niż 3× w liczbach bezwzględnych. Przy f = 2 (60 ppi przy 120
                        # nominalnych) ŻADEN z dwóch sygnałów nie rozdziela: krzywa strat myli to
                        # z miękką treścią, a szum przy powiększeniu 2× jest jeszcze na poziomie
                        # tła (pomiar: 2× → 1,05–1,09 szumu elementu, 3× → 0,67, 4× → 0,51).
                        # To jest uczciwa granica metody dla plików SPŁASZCZONYCH; w PDF-ach
                        # z obiektami taki obraz i tak łapie nominalne ppi (fakt geometryczny).
STEP_MIN = 4.0          # SCHODEK: obraz powiększony f× drukuje się jako „grube piksele" f×f. Widać je
                        # tylko tam, gdzie SĄSIEDNIE grube piksele różnią się tonem. Miara: 95. percentyl
                        # różnicy sąsiednich grubych pikseli w bloku (0–255), dla fragmentu MAKSIMUM po
                        # blokach (żeby mały ostry element w dużym gładkim obszarze nie zginął). Poniżej
                        # ~1,2 % tonu (3/255) ani drukarka nie odda różnicy, ani oko jej nie zobaczy —
                        # niska rozdzielczość jest tam faktem, ale NIEWIDOCZNYM. Pomiar (strona 1878):
                        # jednolite niebo 1,0; ciemne gradienty Prosta_Light 2,4–4,9; bęben adFrame 50,9;
                        # pozostałe realne fragmenty 7,8–134.
NOISE_SUB = 16          # podkafelek do estymacji szumu
NOISE_RATIO = 0.70      # < 70 % szumu elementu -> powiększenie POTWIERDZONE drugim sygnałem
NOISE_MIN_RATIO = 0.15  # < 15 % -> treść syntetyczna (gradient/cień wektorowy wtopiony w obraz)
                        # UWAGA: szum NIE jest filtrem, tylko etykietą pewności. Decyzja Tomasza:
                        # wszystko podejrzane idzie na jedną listę, on przeklikuje i ocenia sam.
                        # Wcześniej szum działał jako twardy filtr i wyrzucał m.in. rozmyty bęben
                        # pralki z adFrame_Smart, który Tomasz uznał za realną wadę.
EXC_MAX_SHARE = 0.15    # gdy „wyjątki” to > 15 % bloków elementu, to nie wyjątek tylko charakter elementu
MIN_BLOCKS_MILD = {64: 3, 128: 2}     # obszar f 2–3 musi mieć tyle bloków (szum metody na natywnych zdjęciach), f ≥ 4 wystarczą 2
MIN_BLOCKS_SEVERE = 2
CODE_OF = {0.0: 0, 1.0: 1, 2.0: 2, 2.5: 3, 3.0: 4, 4.0: 5, 5.0: 9, 6.0: 6, 8.0: 7, 10.0: 10, 12.0: 8, 16.0: 11, 24.0: 12}   # 13 = gładki
FACTOR_OF = {v: k for k, v in CODE_OF.items()}


# ----------------------------------------------------------------------------
# metryka blokowa (wektorowo na całym fragmencie)
# ----------------------------------------------------------------------------
def _block_sums(err: np.ndarray, block: int, rows_idx, cols_idx) -> np.ndarray:
    s = np.add.reduceat(err, rows_idx, axis=0)
    return np.add.reduceat(s, cols_idx, axis=1)


def _knee(means: dict, ref: np.ndarray, flat: np.ndarray) -> np.ndarray:
    """Reguła „kolana” (wektorowo na tablicach bloków). Obraz powiększany f× ma krzywą strat
    PŁASKĄ do f i dopiero potem skok; obraz z naturalnym detalem rośnie gładko (~(next/f)²
    na stopień). Współczynnik = pierwsze f (≥ 2), przy którym E(f) < THRESHOLD·E(8) ORAZ
    następny stopień skacze > JUMP × naturalny wzrost (i jest zauważalny: > 1 % E(ref)).
    Samo „E(f) małe” (stara reguła) myliło miękką treść z powiększeniem."""
    out = np.ones_like(ref, dtype=np.float32)
    decided = flat.copy()
    e8 = means[8.0]
    for i, f in enumerate(FACTORS[:-1]):
        nxt = FACTORS[i + 1]
        small = means[f] < THRESHOLD * np.maximum(e8, 1e-6)
        jump = (means[nxt] > JUMP * (nxt / f) ** 2 * np.maximum(means[f], 1e-6)) & (means[nxt] > 0.01 * ref)
        hit = (~decided) & small & jump
        out[hit] = f if f >= 2.0 else 1.0
        decided |= hit
        decided |= (~small)          # krzywa rośnie monotonicznie — dalsze f już nie przejdą
    out[flat] = 0.0
    return out


def block_curves(gray: np.ndarray, block: int = BLOCK_PX, steps_out: dict | None = None):
    """Krzywe strat bloków: (means{f: [ny,nx]}, std[ny,nx], npix[ny,nx]). Bloki brzegowe
    (reszta < block) liczone jako mniejsze bloki, nic nie jest pomijane.
    steps_out (opcjonalnie): wypełniany {f: schodek per blok} z TEGO SAMEGO obrazu
    zmniejszonego f× — bez drugiego resize'u."""
    a = gray.astype(np.float32)
    H, W = a.shape
    rows_idx = np.arange(0, H, block); cols_idx = np.arange(0, W, block)
    rh = np.diff(np.append(rows_idx, H)); cw = np.diff(np.append(cols_idx, W))
    npix = np.outer(rh, cw).astype(np.float32)
    m1 = _block_sums(a, block, rows_idx, cols_idx) / npix
    m2 = _block_sums(a * a, block, rows_idx, cols_idx) / npix
    std = np.sqrt(np.maximum(m2 - m1 * m1, 0.0))
    im = Image.fromarray(a, mode="F")
    means = {}
    for f in FACTORS:
        nw, nh = max(1, round(W / f)), max(1, round(H / f))
        small = im.resize((nw, nh), Image.LANCZOS)
        if steps_out is not None and nw >= 2 and nh >= 2:
            steps_out[f] = _step_grid(np.asarray(small, dtype=np.float32), H, W, block)
        d = np.array(small.resize((W, H), Image.BICUBIC), dtype=np.float32)
        d -= a; d *= d
        means[f] = _block_sums(d, block, rows_idx, cols_idx) / npix
        del d
    return means, std, npix


def _step_grid(small: np.ndarray, H: int, W: int, block: int) -> np.ndarray:
    """Schodek per blok: 95. percentyl |różnicy| między sąsiednimi „grubymi pikselami"
    (small = obraz zmniejszony f×, czyli to, co wydrukuje się po powiększeniu f×).
    Percentyl bez pętli: histogram 256 koszy na blok, pierwszy kosz osiągający 95 %."""
    nh, nw = small.shape
    ny, nx = math.ceil(H / block), math.ceil(W / block)
    dx = np.abs(np.diff(small, axis=1)); dy = np.abs(np.diff(small, axis=0))
    d = np.zeros_like(small)
    d[:, :-1] = np.maximum(d[:, :-1], dx); d[:, 1:] = np.maximum(d[:, 1:], dx)
    d[:-1, :] = np.maximum(d[:-1, :], dy); d[1:, :] = np.maximum(d[1:, :], dy)
    fy, fx = H / nh, W / nw                    # ile pikseli źródła na jeden gruby piksel
    by = np.minimum(ny - 1, (np.arange(nh) * fy / block).astype(np.int64))
    bx = np.minimum(nx - 1, (np.arange(nw) * fx / block).astype(np.int64))
    bid = by[:, None] * nx + bx[None, :]
    vals = np.clip(np.rint(d), 0, 255).astype(np.int64)
    hist = np.bincount((bid * 256 + vals).ravel(), minlength=ny * nx * 256).reshape(ny * nx, 256)
    cum = hist.cumsum(axis=1); tot = cum[:, -1:]
    p95 = (cum < 0.95 * np.maximum(tot, 1)).sum(axis=1)
    return p95.reshape(ny, nx).astype(np.float32)


def block_noise(gray: np.ndarray, block: int, sub: int = NOISE_SUB):
    """Poziom szumu wysokiej częstotliwości w każdym bloku.

    Po co: rozmycie optyczne (bokeh, głębia ostrości) NIE usuwa szumu matrycy/JPEG-a, bo
    szum powstaje po rozmyciu — a interpolacja przy powiększaniu wygładza wszystko razem
    z szumem. To jedyny zmierzony sygnał, który rozdziela te dwa przypadki: na zdjęciu
    z adFrame_Smart miękkie fragmenty (bęben poza ostrością) mają szum 1,21–1,58, a ten sam
    fragment powiększony 3–4× — 0,53–0,70. Szerokość krawędzi i krzywa strat NIE rozdzielają
    (pomiary w dokumentacji 07).

    Liczymy |Laplace| uśredniony po podkafelkach `sub` px, a z bloku bierzemy średnią
    najspokojniejszej ćwiartki podkafelków — dzięki temu miara jest o treści niezależna
    (krawędzie i faktura nie zawyżają wyniku)."""
    a = gray.astype(np.float32)
    H, W = a.shape
    if H < 3 or W < 3 or H < sub or W < sub:
        return None
    L = np.zeros_like(a)
    L[1:-1, 1:-1] = np.abs(4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:])
    sh, sw = H // sub, W // sub
    t = L[:sh * sub, :sw * sub].reshape(sh, sub, sw, sub).mean(axis=(1, 3))
    per = max(1, block // sub)
    ny, nx = math.ceil(H / block), math.ceil(W / block)
    t = np.pad(t, ((0, max(0, ny * per - sh)), (0, max(0, nx * per - sw))), constant_values=np.nan)
    t = t[:ny * per, :nx * per].reshape(ny, per, nx, per).transpose(0, 2, 1, 3).reshape(ny, nx, per * per)
    t = np.sort(t, axis=-1)                       # NaN-y lądują na końcu
    kq = max(1, (per * per) // 4)
    sel = t[:, :, :kq]
    cnt = np.sum(~np.isnan(sel), axis=-1)
    tot = np.nansum(sel, axis=-1)
    return np.where(cnt > 0, tot / np.maximum(cnt, 1), 0.0).astype(np.float32)


SCALES = (1, 2, 4)   # krzywe liczone też na fragmencie zmniejszonym 2× i 4× (blok 64/32 px = ten sam blok oryginału)
STD_MIN = 3.0        # blok o std poniżej = naprawdę jednolity; powyżej, a „płaski” wg E(8) = gładki: gradient ALBO mocno powiększony


def chunk_curves(gray: np.ndarray, block: int = BLOCK_PX) -> dict:
    """Krzywe strat bloków fragmentu w skalach SCALES: {s: (means, std, npix)}; siatka bloków
    ta sama w każdej skali (blok/s px w obrazie zmniejszonym s×)."""
    out = {}
    H, W = gray.shape
    steps = {}
    for s_ in SCALES:
        if s_ == 1:
            g = gray
        else:
            if W // s_ < 8 or H // s_ < 8 or block // s_ < 32:
                break
            g = np.asarray(Image.fromarray(gray).resize((W // s_, H // s_), Image.LANCZOS))
        out[s_] = block_curves(g, block // s_, steps_out=(steps if s_ == 1 else None))
    n = block_noise(gray, block)
    if n is not None:
        out["noise"] = n
    out["step"] = steps
    return out


def _agg_curve(means: dict, npix: np.ndarray, mask: np.ndarray) -> tuple[dict, float]:
    """Krzywa strat obszaru = średnia ważona pikselami krzywych jego bloków."""
    w = npix[mask]; tot = float(w.sum()) or 1.0
    return {f: float((m[mask] * w).sum() / tot) for f, m in means.items()}, tot


def _knee_scalar(c: dict, ref_key: float = 8.0) -> float:
    ref = c[ref_key]
    if ref < MIN_REF:
        return 0.0
    keys = [f for f in FACTORS if f <= ref_key]
    for i, f in enumerate(keys[:-1]):
        nxt = keys[i + 1]
        small = c[f] < THRESHOLD * max(ref, 1e-6)
        if not small:
            return 1.0
        jump = c[nxt] > JUMP * (nxt / f) ** 2 * max(c[f], 1e-6) and c[nxt] > 0.01 * ref
        if jump:
            return f if f >= 2.0 else 1.0
    return 1.0


# ----------------------------------------------------------------------------
# źródła pasów: PDF-podobne (render) i rastry (Pillow)
# ----------------------------------------------------------------------------
def _raster_bands(path: str, page_index: int, progress):
    with Image.open(path) as im:
        try:
            im.seek(page_index)
        except Exception:
            pass
        W, H = im.size
        shrink = 1
        if W * H > RASTER_FULL_DECODE_PX:
            shrink = 2
        if shrink > 1:
            im = im.reduce(shrink)
            W, H = im.size
        band_h = max(CHUNK_ROWS, (BAND_MAX_PX // max(1, W)) // CHUNK_ROWS * CHUNK_ROWS)
        bands = [(y, min(band_h, H - y)) for y in range(0, H, band_h)]
        for i, (y, bh) in enumerate(bands):
            g = np.asarray(im.crop((0, y, W, y + bh)).convert("L"))
            progress(i + 1, len(bands))
            yield y, g, (W, H, shrink)


# ----------------------------------------------------------------------------
# złożenie mapy
# ----------------------------------------------------------------------------
def _cluster_mask(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    ny, nx = mask.shape
    seen = np.zeros_like(mask)
    clusters = []
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        stack = [(sy, sx)]; seen[sy, sx] = True; cells = []
        while stack:
            y, x = stack.pop(); cells.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < ny and 0 <= xx < nx and mask[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True; stack.append((yy, xx))
        clusters.append(cells)
    return clusters


def _bbox_frac(cells, block, W, H) -> dict:
    y0 = min(c[0] for c in cells); y1 = max(c[0] for c in cells) + 1
    x0 = min(c[1] for c in cells); x1 = max(c[1] for c in cells) + 1
    return {"fx": round(x0 * block / W, 5), "fy": round(y0 * block / H, 5),
            "fw": round(min(W, x1 * block) / W - x0 * block / W, 5), "fh": round(min(H, y1 * block) / H - y0 * block / H, 5),
            "blocks": len(cells)}


class _Acc:
    """Siatka bloków całej strony; chunki wstawiane pod (by, bx) w blokach — pozwala liczyć
    tylko fragmenty strony (wokół obrazów) i zostawić resztę jako „jednolite”."""
    def __init__(self, W: int, H: int, block: int):
        self.W, self.H, self.block = W, H, block
        self.ny, self.nx = math.ceil(H / block), math.ceil(W / block)
        self.means = {s_: {f: np.zeros((self.ny, self.nx), np.float32) for f in FACTORS} for s_ in SCALES}
        self.npix = {s_: np.zeros((self.ny, self.nx), np.float32) for s_ in SCALES}
        self.std = np.zeros((self.ny, self.nx), np.float32)
        self.noise = np.zeros((self.ny, self.nx), np.float32)
        self.step = {f: np.zeros((self.ny, self.nx), np.float32) for f in FACTORS}
        self.done = np.zeros((self.ny, self.nx), bool)
    def place(self, cc: dict, by: int, bx: int):
        n = cc.get("noise")
        if n is not None:
            h = min(n.shape[0], self.ny - by); w = min(n.shape[1], self.nx - bx)
            if h > 0 and w > 0:
                self.noise[by:by + h, bx:bx + w] = n[:h, :w]
        st = cc.get("step")
        if st:
            for f, g in st.items():
                h = min(g.shape[0], self.ny - by); w = min(g.shape[1], self.nx - bx)
                if h > 0 and w > 0:
                    self.step[f][by:by + h, bx:bx + w] = g[:h, :w]
        for s_, v in cc.items():
            if s_ in ("noise", "step"):
                continue
            means, std, npix = v
            h, w = npix.shape
            h = min(h, self.ny - by); w = min(w, self.nx - bx)
            if h <= 0 or w <= 0:
                continue
            for f in FACTORS:
                self.means[s_][f][by:by + h, bx:bx + w] = means[f][:h, :w]
            self.npix[s_][by:by + h, bx:bx + w] = npix[:h, :w]
            if s_ == 1:
                self.std[by:by + h, bx:bx + w] = std[:h, :w]
                self.done[by:by + h, bx:bx + w] = True
    def grids(self):
        return {s_: (self.means[s_], self.npix[s_]) for s_ in SCALES}, self.std


def _finish(acc: _Acc, W: int, H: int, block: int, mask: np.ndarray | None = None) -> dict:
    """Ocena JEDNEGO elementu (obrazu albo całej strony rastra).

    Zwraca bazę elementu (typowy poziom detalu) i WYJĄTKI — fragmenty wyraźnie gorsze od
    tej bazy. To jest sedno poprawki: wcześniej fragmenty były porównywane z progiem
    bezwzględnym, więc obraz powiększony w całości rozpadał się na kilkadziesiąt
    „losowych” prostokątów (1878: 59 sztuk wewnątrz jednego tła). Teraz taki obraz daje
    JEDNO zgłoszenie na poziomie elementu, a fragmenty pojawiają się tylko wtedy, gdy
    naprawdę odstają od reszty (wklejone powiększone logo w ostrym zdjęciu)."""
    grids, std = acc.grids()
    means1, npix1 = grids[1]
    ref = means1[8.0]
    flat = ref < MIN_REF
    fac = _knee(means1, ref, flat)
    ny, nx = fac.shape
    if mask is not None:                      # poza obrazami (wektor) nic nie oceniamy
        fac = np.where(mask, fac, 0.0); std = np.where(mask, std, 0.0); flat = flat | ~mask

    def fit(a):
        return np.pad(a, ((0, max(0, ny - a.shape[0])), (0, max(0, nx - a.shape[1]))))[:ny, :nx]
    stdf = fit(std)
    soft = flat & (stdf > STD_MIN)         # jest treść, ale bez drobnego detalu (gradient/bokeh ALBO mocne powiększenie)
    detail = fac > 0                           # bloki, które w ogóle niosą informację o rozdzielczości

    # --- baza elementu: typowy poziom detalu (25. percentyl po blokach z detalem) ---
    n_detail = int(detail.sum())
    if n_detail:
        vals = np.sort(fac[detail])
        baseline = float(vals[min(n_detail - 1, int(n_detail * BASELINE_PCT / 100))])
    else:
        baseline = None

    def _dilate(m):
        """Rozszerzenie maski o 1 blok — sąsiadujące (ale nie stykające się) kawałki tej samej
        wady mają dać JEDEN obszar, a nie kilkanaście osobnych prostokątów."""
        d = m.copy()
        d[1:, :] |= m[:-1, :]; d[:-1, :] |= m[1:, :]
        d[:, 1:] |= m[:, :-1]; d[:, :-1] |= m[:, 1:]
        return d

    # --- szum elementu: mediana po blokach z jakąkolwiek treścią (odniesienie dla fragmentów) ---
    noise = fit(acc.noise)
    content = detail | soft
    elem_noise = float(np.median(noise[content])) if content.any() else 0.0

    def noise_verdict(m):
        """Pewność, nie filtr. Zwraca (etykieta, ratio):
          confirmed — szum wyraźnie niższy niż w reszcie obrazu: interpolacja wygładziła szum,
                      czyli powiększenie potwierdzone drugim, niezależnym sygnałem,
          soft      — szum na poziomie reszty: brak drobnego detalu, ale przyczyna nieznana
                      (rozmycie z aparatu, głębia ostrości ALBO powiększenie) — do obejrzenia,
          synthetic — szum bliski zeru: treść syntetyczna (gradient/cień), miękkość celowa."""
        if elem_noise <= 0:
            return "unknown", None
        rr = float(np.median(noise[m])) / elem_noise
        if rr < NOISE_MIN_RATIO:
            return "synthetic", rr
        return ("confirmed" if rr <= NOISE_RATIO else "soft"), rr

    regions = []
    soft_skipped = 0
    invisible_skipped = 0
    conf_counts = {}
    stepg = {f: fit(g) for f, g in acc.step.items()}

    def region_step(m, factor):
        """Schodek fragmentu przy jego współczynniku: MAKSIMUM po blokach (konserwatywnie —
        jeden blok z widocznymi schodkami wystarcza, żeby fragment został na liście)."""
        fk = max((f for f in FACTORS if f <= factor + 1e-6), default=FACTORS[0])
        g = stepg.get(fk)
        return float(g[m].max()) if (g is not None and m.any()) else None

    # --- 1) wyjątki: bloki co najmniej EXC_RATIO× gorsze od bazy elementu ---
    if baseline is not None:
        thr = max(EXC_MIN_FACTOR, EXC_RATIO * baseline)
        exc = detail & (fac >= thr)
        if exc.sum() <= EXC_MAX_SHARE * max(1, n_detail):     # inaczej: to charakter elementu, nie wyjątek
            for cells in _cluster_mask(_dilate(exc)):
                m = np.zeros_like(fac, bool)
                for c in cells:
                    m[c] = True
                m &= exc                     # krzywą liczymy z bloków faktycznie słabych, bbox z rozszerzonych
                if not m.any():
                    continue
                c1, _ = _agg_curve(means1, npix1, m)
                f_reg = _knee_scalar(c1)
                if f_reg < thr * 0.75:
                    continue                   # krzywa całego fragmentu nie potwierdza
                if len(cells) < (MIN_BLOCKS_SEVERE if f_reg >= 4.0 else MIN_BLOCKS_MILD.get(block, 2)):
                    continue
                stp = region_step(m, f_reg)
                if stp is not None and stp < STEP_MIN:     # niska rozdzielczość, ale NIEWIDOCZNA (jednolity ton)
                    invisible_skipped += 1
                    continue
                conf, rr = noise_verdict(m)         # drugi, niezależny sygnał — etykieta pewności
                r = _bbox_frac(cells, block, W, H)
                r.update({"factor": f_reg, "reason": "upscaled", "confidence": conf,
                          "step": round(stp, 1) if stp is not None else None,
                          "noise_ratio": round(rr, 2) if rr is not None else None})
                regions.append(r)
                conf_counts[conf] = conf_counts.get(conf, 0) + 1

    # --- 2) fragmenty gładkie: zgłaszamy TYLKO gdy krzywa w skali 2/4 potwierdza mocne
    #        powiększenie; czysty gradient/bokeh nie niesie informacji i jest pomijany
    #        (liczony w soft_skipped, żeby nic nie znikało po cichu) ---
    for cells in _cluster_mask(_dilate(soft)):
        if len(cells) < 2:
            continue
        m = np.zeros_like(fac, bool)
        for c in cells:
            m[c] = True
        m &= soft
        if not m.any():
            continue
        found = None
        for s_ in SCALES[1:]:
            if s_ not in grids:
                break
            ms, nps = grids[s_]
            ms = {f: fit(a) for f, a in ms.items()}; nps = fit(nps)
            cs, _ = _agg_curve(ms, nps, m)
            fs = _knee_scalar(cs)
            if fs >= 2.0:
                found = fs * s_; break
        if found and (baseline is None or found >= max(EXC_MIN_FACTOR, EXC_RATIO * baseline)):
            stp = region_step(m, found)
            if stp is not None and stp < STEP_MIN:
                invisible_skipped += 1
                continue
            conf, rr = noise_verdict(m)
            r = _bbox_frac(cells, block, W, H)
            r.update({"factor": found, "reason": "coarse", "confidence": conf,
                      "step": round(stp, 1) if stp is not None else None,
                      "noise_ratio": round(rr, 2) if rr is not None else None})
            regions.append(r)
            conf_counts[conf] = conf_counts.get(conf, 0) + 1
        else:
            soft_skipped += 1
    # najpierw potwierdzone drugim sygnałem, potem reszta; w grupach od najgorszego
    _rank = {"confirmed": 0, "unknown": 1, "soft": 2, "synthetic": 3}
    regions.sort(key=lambda r: (_rank.get(r.get("confidence"), 1), -r["factor"], -r["blocks"]))

    # siatka kodów (heatmapa dla rastrów)
    grid = fac.copy()
    grid[soft & (grid == 0.0)] = -1.0
    codes = np.zeros(grid.shape, np.uint8)
    for f, c in CODE_OF.items():
        codes[grid == f] = c
    codes[grid == -1.0] = 13
    hist = Counter(float(v) for v in fac[detail].ravel())
    elem_step = region_step(detail, baseline) if (baseline is not None and detail.any()) else None
    return {
        "elem_step": round(elem_step, 1) if elem_step is not None else None,
        "invisible_skipped": invisible_skipped,
        "grid": {"rows": int(ny), "cols": int(nx), "codes_b64": base64.b64encode(codes.tobytes()).decode("ascii")},
        "blocks_total": int(grid.size), "blocks_detail": n_detail, "blocks_soft": int(soft.sum()),
        "blocks_uniform": int((~detail & ~soft).sum()),
        "share": {str(f): round(n / max(1, n_detail), 4) for f, n in sorted(hist.items())},
        "baseline": baseline, "elem_noise": round(elem_noise, 3),
        "regions": regions[:MAX_REGIONS], "regions_total": len(regions),
        "soft_skipped": soft_skipped, "confidence_counts": conf_counts,
        # zgodność wstecz (raster/heatmapa)
        "weak": regions[:MAX_REGIONS], "weak_total": len(regions), "soft": [], "soft_total": 0,
        "worst_factor": max([r["factor"] for r in regions], default=(baseline or 0.0)),
    }


def analyze_gray(gray: np.ndarray, block: int = BLOCK_PX) -> dict:
    """Cała mapa dla obrazu w pamięci (testy; małe pliki)."""
    H, W = gray.shape
    acc = _Acc(W, H, block)
    for cy in range(0, H, CHUNK_ROWS):
        acc.place(chunk_curves(gray[cy:cy + CHUNK_ROWS], block), cy // block, 0)
    return _finish(acc, W, H, block)


def build(path: str, kind: str, page_index: int = 0, k: int = 1, progress=lambda i, n: None,
          block: int = BLOCK_PX, boxes: list | None = None) -> dict:
    """Raster (JPG/PNG/TIFF): cały plik w natywnych pikselach, blok po bloku. PDF idzie przez
    build_pdf_objects (każdy obraz osobno, w natywnych pikselach) — tamta droga jest dokładniejsza
    niż render strony (wektor nie ma rozdzielczości i tylko myli metrykę)."""
    t0 = time.time()
    if kind != "raster":
        return {"ok": False, "error": "PDF oceniamy obraz po obrazie (build_pdf_objects)."}
    W = H = None; shrink = 1; acc = None; mask = None
    src = _raster_bands(path, page_index, progress)
    with ProcessPoolExecutor(max_workers=CHUNK_THREADS) as ex:
        for y, g, dims in src:
            if acc is None:
                W, H = dims[0], dims[1]; shrink = dims[2] if len(dims) > 2 else 1
                acc = _Acc(W, H, block)
            chunks = [(y + cy, g[cy:cy + CHUNK_ROWS]) for cy in range(0, g.shape[0], CHUNK_ROWS)]
            for (cy, cc) in zip([c[0] for c in chunks], ex.map(functools.partial(chunk_curves, block=block), [c[1] for c in chunks], chunksize=1)):
                acc.place(cc, cy // block, 0)
            del g, chunks
    if acc is None:
        return {"ok": False, "error": "pusta strona"}
    res = _finish(acc, W, H, block, mask)
    # ten sam kształt wyniku co w trybie obiektowym: jedna lista „potencjalnie słabej jakości".
    # Dla rastra ppi liczy UI (nominalne = px / mm wydruku, znane dopiero po wyborze produktu).
    areas = [dict(r, scope="fragment", ppi=None, nominal_ppi=None) for r in res.get("regions", [])]
    if res.get("baseline") and res["baseline"] >= 2.0:
        es = res.get("elem_step")
        if es is not None and es < STEP_MIN:          # cały plik bez detalu, ale i bez widocznych schodków
            res["invisible_skipped"] = res.get("invisible_skipped", 0) + 1
        else:
            areas.insert(0, {"fx": 0.0, "fy": 0.0, "fw": 1.0, "fh": 1.0, "blocks": res["blocks_total"],
                             "scope": "element", "reason": "upscaled", "factor": res["baseline"],
                             "ppi": None, "nominal_ppi": None, "step": es})
    res.update({"areas": areas, "areas_total": len(areas), "min_region_mm": MIN_REGION_MM,
                "small_skipped": 0, "confidence_counts": res.get("confidence_counts", {})})
    res.update({
        "ok": True, "kind": kind, "k": k, "page": page_index,
        "analysis_ppi_print": ANALYSIS_PPI_PRINT if kind != "raster" else None,
        "raster_shrink": shrink,
        "page_px": [int(W * shrink), int(H * shrink)], "block_px": block * shrink,
        "seconds": round(time.time() - t0, 1),
    })
    return res


# ----------------------------------------------------------------------------
# PDF: mapa z NATYWNYCH pikseli obrazów (obiekt po obiekcie, wszystkie użycia)
# ----------------------------------------------------------------------------
# Dlaczego nie z renderu strony: (1) wektor (miękkie krawędzie, gradienty, cienie) nie ma
# rozdzielczości, a metryka widzi w nim „miękkość” → fałszywe obszary; (2) MuPDF powiększa
# obrazy „klockami” (najbliższy sąsiad) mimo /Interpolate — logo 30 ppi po renderze wygląda
# jak ostre krawędzie i przechodzi jako dobre. Natywne piksele obrazu + znane umiejscowienia
# (analyze.py, CTM) dają wynik niezależny od renderera i automatycznie omijają wektor.
IMG_MAX_DECODE_PX = 120_000_000


def _image_bands(doc, path: str, rec: dict):
    """Generator (y0, gray) po pasach obrazu w natywnej rozdzielczości; małe obrazy — całość."""
    w, h = rec["width"], rec["height"]
    if w * h <= IMG_MAX_DECODE_PX and rec.get("xref"):
        pix = pymupdf.Pixmap(doc, rec["xref"])
        if pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)
        if pix.n != 1:
            pix = pymupdf.Pixmap(pymupdf.csGRAY, pix)
        g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        yield 0, g.copy()
        return
    # ogromny obraz: pasy renderowane ze strony w natywnej rozdzielczości obrazu (bez przepróbkowania)
    page = doc[rec["page"]]
    x0, y0, x1, y1 = rec["rect_pdf"]
    ph = page.mediabox.height if hasattr(page, "mediabox") else page.rect.height
    top = ph - y1
    px_per_pt = w / max(1e-6, (x1 - x0))
    band_h = max(CHUNK_ROWS, (BAND_MAX_PX // w) // CHUNK_ROWS * CHUNK_ROWS)
    for y in range(0, h, band_h):
        bh = min(band_h, h - y)
        clip = (x0, top + y / px_per_pt, x1, top + (y + bh) / px_per_pt)
        png = render.region_png(path, rec["page"], clip, px_per_pt, smooth=False, max_px=max(w, bh) + 8, gray=True)
        yield y, np.asarray(Image.open(io.BytesIO(png)).convert("L"))


# ----------------------------------------------------------------------------
# Widoczność na FINALNEJ stronie
#
# Obraz może być umieszczony na dużym obszarze, ale realnie zasłonięty: maska
# przezroczystości (SMask), ścieżka przycinająca (W n), alfa 0, przykrycie innym
# obiektem. Analiza pikseli obrazu tego nie widzi — mierzy cały obraz, także
# fragmenty, które nigdy nie trafią na wydruk (przypadek adWall_Vario_Prosta_Light_300:
# zdjęcie 7008x4672 px rozłożone na 2780x1885 mm, w druku widoczny tylko pas u góry).
#
# Rozstrzygamy to na tym, co faktycznie idzie na druk: jeden render strony z kanałem
# alfa. Gdzie nic nie jest namalowane, tam nie ma czego oceniać — i tylko takie
# obszary odpadają (nie „miękkie", nie „gładkie" — te zostają na liście z etykietą).
# ----------------------------------------------------------------------------
VIS_PX_PER_MM = 1.0        # 10 mm = 10 px — do testu „czy cokolwiek tu jest" w zupełności
VIS_MAX_PX = 4000
VIS_ALPHA = 16             # poniżej tego uznajemy piksel za niezamalowany
VIS_MIN_SHARE = 0.02       # < 2 % widocznych pikseli = obszar niewidoczny na wydruku
VIS_TRIM_SHARE = 0.90      # < 90 % widocznych = przycinamy prostokąt do widocznej części


def page_alpha_map(path: str, page_index: int):
    """Kanał alfa finalnej strony (True = coś jest namalowane). None, gdy render zawiedzie."""
    try:
        doc = pymupdf.open(path)
        try:
            page = doc[page_index]
            long_pt = max(page.rect.width, page.rect.height) or 1.0
            long_mm = long_pt * 25.4 / 72.0
            target = min(VIS_MAX_PX, max(400.0, long_mm * VIS_PX_PER_MM))
            z = target / long_pt
            pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=True)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            return arr[..., -1] >= VIS_ALPHA
        finally:
            doc.close()
    except Exception:
        return None      # w razie wątpliwości NIC nie odrzucamy


def region_on_placement(p: dict, r: dict) -> dict:
    """Fragment z WNĘTRZA obrazu (ułamki fx,fy,fw,fh w pikselach obrazu, y od góry) → ułamki
    prostokąta umiejscowienia NA STRONIE. Idzie przez pełną macierz CTM, więc odbicia
    (a<0, d<0) i obroty o 90° trafiają we właściwe miejsce. Bez CTM — jak dotąd (bez odbić)."""
    ctm = p.get("ctm"); rect = p.get("rect_pdf")
    if not ctm or not rect:
        return {"fx": r["fx"], "fy": r["fy"], "fw": r["fw"], "fh": r["fh"]}
    a, b, c, d, e, f = ctm
    u0, u1 = r["fx"], r["fx"] + r["fw"]
    v0, v1 = 1.0 - (r["fy"] + r["fh"]), 1.0 - r["fy"]      # PDF: pierwszy wiersz obrazu to v = 1
    pts = [(a * u + c * v + e, b * u + d * v + f) for u in (u0, u1) for v in (v0, v1)]
    X0 = min(x for x, _ in pts); X1 = max(x for x, _ in pts)
    Y0 = min(y for _, y in pts); Y1 = max(y for _, y in pts)
    rx0, ry0, rx1, ry1 = rect
    W = max(1e-9, rx1 - rx0); H = max(1e-9, ry1 - ry0)
    return {"fx": (X0 - rx0) / W, "fy": (ry1 - Y1) / H, "fw": (X1 - X0) / W, "fh": (Y1 - Y0) / H}


def clip_to_page(a) -> bool:
    """Przycina obszar do strony. False = leży całkowicie poza stroną (nie zostanie
    wydrukowany). Obraz często wystaje poza format — spad albo celowe kadrowanie."""
    x0 = max(0.0, float(a["fx"])); x1 = min(1.0, float(a["fx"]) + float(a["fw"]))
    y0 = max(0.0, float(a["fy"])); y1 = min(1.0, float(a["fy"]) + float(a["fh"]))
    if x1 - x0 <= 1e-4 or y1 - y0 <= 1e-4:
        return False
    sx = (x1 - x0) / max(1e-9, float(a["fw"])); sy = (y1 - y0) / max(1e-9, float(a["fh"]))
    if a.get("mm") and (sx < 0.999 or sy < 0.999):
        a["mm"] = [round(a["mm"][0] * sx, 1), round(a["mm"][1] * sy, 1)]
        a["clipped"] = True
    a["fx"] = round(x0, 5); a["fy"] = round(y0, 5)
    a["fw"] = round(x1 - x0, 5); a["fh"] = round(y1 - y0, 5)
    return True


def apply_visibility(areas: list, vis) -> int:
    """Najpierw przycina obszary do strony (co wystaje poza format, nie idzie na druk),
    potem — jeśli mamy render — usuwa te, w których na wydruku nic nie ma, a częściowo
    zasłonięte przycina do widocznej części. Zwraca liczbę usuniętych."""
    if not areas:
        return 0
    out = []; hidden = 0
    for a in areas:
        if not clip_to_page(a):
            hidden += 1
            continue
        out.append(a)
    areas[:] = out
    if vis is None:
        return hidden
    H, W = vis.shape
    out = []
    for a in areas:
        x0 = int(np.clip(np.floor(a["fx"] * W), 0, W - 1)); x1 = int(np.clip(np.ceil((a["fx"] + a["fw"]) * W), x0 + 1, W))
        y0 = int(np.clip(np.floor(a["fy"] * H), 0, H - 1)); y1 = int(np.clip(np.ceil((a["fy"] + a["fh"]) * H), y0 + 1, H))
        sub = vis[y0:y1, x0:x1]
        share = float(sub.mean()) if sub.size else 0.0
        if share < VIS_MIN_SHARE:
            hidden += 1
            continue
        if share < VIS_TRIM_SHARE:
            rows = np.flatnonzero(sub.any(axis=1)); cols = np.flatnonzero(sub.any(axis=0))
            if rows.size and cols.size:
                ny0, ny1 = y0 + int(rows[0]), y0 + int(rows[-1]) + 1
                nx0, nx1 = x0 + int(cols[0]), x0 + int(cols[-1]) + 1
                sx = (nx1 - nx0) / max(1, x1 - x0); sy = (ny1 - ny0) / max(1, y1 - y0)
                if a.get("mm"):
                    a["mm"] = [round(a["mm"][0] * sx, 1), round(a["mm"][1] * sy, 1)]
                a["fx"] = round(nx0 / W, 5); a["fy"] = round(ny0 / H, 5)
                a["fw"] = round((nx1 - nx0) / W, 5); a["fh"] = round((ny1 - ny0) / H, 5)
                a["clipped"] = True
        a["visible_share"] = round(share, 3)
        out.append(a)
    areas[:] = out
    return hidden


def build_pdf_objects(path: str, images: list, page_index: int, k: int, block: int, page_mm, progress=lambda i, n: None) -> dict:
    """Każdy obraz (poza maskami) zdekodowany w całości, bloki w jego natywnych pikselach,
    rozmiar bloku dobrany tak, by na wydruku odpowiadał `block` px przy 240 ppi (≈ 13,5 mm);
    obszary rzutowane na WSZYSTKIE umiejscowienia obrazu na stronie."""
    t0 = time.time()
    pw, ph = (page_mm or (None, None))
    recs = [r for r in images or [] if not r.get("mask") and r.get("xref") and any(p.get("page", 0) == page_index for p in r["placements"])]
    areas = []
    blocks_total = 0; n_place = 0; per_image = []; soft_skipped = 0; small_skipped = 0; conf_counts = {}
    invisible_skipped = 0
    doc = pymupdf.open(path)
    try:
        with ProcessPoolExecutor(max_workers=CHUNK_THREADS) as ex:
            for i, rec in enumerate(recs):
                w, h = rec["width"], rec["height"]
                pl = [p for p in rec["placements"] if p.get("page", 0) == page_index]
                ppi_print_min = min((p["ppi"] for p in pl if p.get("ppi")), default=None)
                ppi_print_min = ppi_print_min / k if ppi_print_min else None
                # blok w px obrazu ≈ `block` px przy 240 ppi na wydruku (ten sam rozmiar w mm)
                b = int(round(block * (ppi_print_min or 240.0) / ANALYSIS_PPI_PRINT))
                b = max(32, min(512, (b // 16) * 16))   # wielokrotność NOISE_SUB, żeby siatka szumu pasowała do bloków
                if w < 8 or h < 8:
                    continue
                acc = _Acc(w, h, b)
                try:
                    for y, g in _image_bands(doc, path, rec):
                        chunks = [(y + cy, g[cy:cy + CHUNK_ROWS]) for cy in range(0, g.shape[0], CHUNK_ROWS)]
                        for (cy, cc) in zip([c[0] for c in chunks], ex.map(functools.partial(chunk_curves, block=b), [c[1] for c in chunks], chunksize=1)):
                            acc.place(cc, cy // b, 0)
                        del g, chunks
                except Exception as e:
                    per_image.append({"xref": rec["xref"], "error": f"{type(e).__name__}: {e}"})
                    progress(i + 1, len(recs))
                    continue
                res = _finish(acc, w, h, b)
                blocks_total += res["blocks_total"]
                base = res.get("baseline")
                per_image.append({"xref": rec["xref"], "w": w, "h": h, "block": b, "baseline": base,
                                  "noise": res.get("elem_noise"), "regions": res["regions_total"],
                                  "soft_skipped": res["soft_skipped"], "conf": res.get("confidence_counts"), "invisible": res.get("invisible_skipped", 0),
                                  "placements": len(pl)})
                soft_skipped += res["soft_skipped"]
                invisible_skipped += res.get("invisible_skipped", 0)
                for kk, vv in (res.get("confidence_counts") or {}).items():
                    conf_counts[kk] = conf_counts.get(kk, 0) + vv
                for p in pl:
                    n_place += 1
                    if not (pw and ph and p.get("bw_mm") and p.get("bh_mm")):
                        continue
                    nominal = (p["ppi"] / k) if p.get("ppi") else None
                    real = round(nominal / base, 1) if (nominal and base) else nominal
                    box = {"fx": round(p["x_mm"] / pw, 5), "fy": round(p["y_mm"] / ph, 5),
                           "fw": round(p["bw_mm"] / pw, 5), "fh": round(p["bh_mm"] / ph, 5),
                           "xref": rec["xref"], "page": page_index, "px": [w, h], "uses": len(pl),
                           "mm": [round(p["bw_mm"] * k, 1), round(p["bh_mm"] * k, 1)]}   # wymiar NA WYDRUKU
                    # (a) CAŁY element: fakt geometryczny (za mało pikseli) i/lub baza detalu poniżej progu
                    if nominal is not None and nominal < REQUIRED_PPI:
                        areas.append(dict(box, blocks=res["blocks_total"], scope="element", reason="lowres",
                                          nominal_ppi=round(nominal, 1), factor=base or 1.0, ppi=real))
                    elif nominal is not None and real is not None and real < REQUIRED_PPI:
                        # cały obraz bez detalu — ale tylko gdy to W OGÓLE widać (gładki gradient
                        # powiększony 4× nadal jest gładkim gradientem)
                        es = res.get("elem_step")
                        if es is not None and es < STEP_MIN:
                            invisible_skipped += 1
                        else:
                            areas.append(dict(box, blocks=res["blocks_total"], scope="element", reason="upscaled",
                                              nominal_ppi=round(nominal, 1), factor=base or 1.0, ppi=real,
                                              step=es))
                    # (b) WYJĄTKI wewnątrz elementu — tylko wyraźnie gorsze od jego bazy i ≥ MIN_REGION_MM
                    for r0 in res["regions"][:MAX_REGIONS]:
                        r = dict(r0, **region_on_placement(p, r0))   # ułamki prostokąta umiejscowienia (po CTM)
                        wmm = r["fw"] * p["bw_mm"] * k; hmm = r["fh"] * p["bh_mm"] * k   # mm NA WYDRUKU
                        if wmm * hmm < MIN_REGION_MM ** 2 or min(wmm, hmm) < MIN_REGION_MM / 2:
                            small_skipped += 1
                            continue
                        rppi = round(nominal / r["factor"], 1) if nominal else None
                        if rppi is not None and rppi >= REQUIRED_PPI:
                            continue
                        areas.append({"fx": round((p["x_mm"] + r["fx"] * p["bw_mm"]) / pw, 5),
                                      "fy": round((p["y_mm"] + r["fy"] * p["bh_mm"]) / ph, 5),
                                      "fw": round(r["fw"] * p["bw_mm"] / pw, 5), "fh": round(r["fh"] * p["bh_mm"] / ph, 5),
                                      "xref": rec["xref"], "page": page_index, "blocks": r["blocks"],
                                      "scope": "fragment", "reason": r["reason"], "factor": r["factor"],
                                      "noise_ratio": r.get("noise_ratio"), "confidence": r.get("confidence"),
                                      "step": r.get("step"),
                                      "nominal_ppi": round(nominal, 1) if nominal else None, "ppi": rppi,
                                      "mm": [round(wmm, 1), round(hmm, 1)]})
                progress(i + 1, len(recs))
    finally:
        doc.close()
    # co z tego naprawdę widać na wydruku (maski, przycięcia, przykrycia)
    hidden_skipped = apply_visibility(areas, page_alpha_map(path, page_index))
    _rk = {"element": 0, "fragment": 1}
    _ck = {None: 0, "confirmed": 0, "unknown": 1, "soft": 2, "synthetic": 3}
    areas.sort(key=lambda r: (_ck.get(r.get("confidence"), 1), (r["ppi"] if r["ppi"] is not None else 1e9), -r["blocks"]))
    return {
        "ok": True, "kind": "pdf", "mode": "objects", "k": k, "page": page_index,
        "analysis_ppi_print": None, "raster_shrink": 1, "page_px": None, "block_px": None,
        "block_mm": round(block / ANALYSIS_PPI_PRINT * 25.4, 1), "min_region_mm": MIN_REGION_MM,
        "grid": None, "share": {},
        "blocks_total": blocks_total, "objects": len(recs), "placements": n_place, "per_image": per_image,
        "areas": areas[:MAX_AREAS], "areas_total": len(areas),
        "soft_skipped": soft_skipped, "small_skipped": small_skipped, "confidence_counts": conf_counts,
        "hidden_skipped": hidden_skipped, "invisible_skipped": invisible_skipped,
        "worst_ppi": min((r["ppi"] for r in areas if r["ppi"] is not None), default=None),
        "seconds": round(time.time() - t0, 1),
    }


# ----------------------------------------------------------------------------
# zadania w tle (per job, per k)
# ----------------------------------------------------------------------------
_tasks: dict = {}
_lock = threading.Lock()


def start(job_id: str, path: str, kind: str, page_index: int = 0, k: int = 1, block: int = BLOCK_PX, boxes: list | None = None,
          images: list | None = None, page_mm=None) -> dict:
    key = (job_id, page_index, k, block)
    with _lock:
        t = _tasks.get(key)
        if t and (t["status"] == "running" or t["status"] == "done"):
            return dict(t)
        t = {"status": "running", "band": 0, "bands": 0, "started": time.time(), "result": None, "error": None}
        _tasks[key] = t

    def progress(i, n):
        with _lock:
            t["band"] = i; t["bands"] = n

    def run():
        try:
            res = build_pdf_objects(path, images, page_index, k, block, page_mm, progress) if kind == "pdf" and images is not None else build(path, kind, page_index, k, progress, block, boxes)
            with _lock:
                t["result"] = res; t["status"] = "done" if res.get("ok") else "error"; t["error"] = res.get("error")
        except Exception as e:
            with _lock:
                t["status"] = "error"; t["error"] = f"{type(e).__name__}: {e}"
    threading.Thread(target=run, daemon=True).start()
    return dict(t)


def status(job_id: str, page_index: int = 0, k: int = 1, block: int = BLOCK_PX) -> dict | None:
    with _lock:
        t = _tasks.get((job_id, page_index, k, block))
        return dict(t) if t else None


def forget(job_id: str) -> None:
    with _lock:
        for key in [key for key in _tasks if key[0] == job_id]:
            _tasks.pop(key, None)
