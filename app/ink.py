"""Suma farb (TAC — total area coverage): ile farby maszyna położy w jednym miejscu.

Za dużo farby (np. czerń 100/100/100/100 = 400 %, kolor „Registration”, ciemne tło złożone
ze wszystkich farb) nie schnie, rozmazuje się i odbija. Limit 360 % przepuszcza zalecaną czerń
Adsystem (C78 M85 Y90 K100 = 353 %) i czerń z RGB po zamianie (ok. 316 %), więc powyżej to
zawsze CMYK / kolor dodatkowy wpisany ręcznie w projekcie (Tomasz 29.09, „edge cases”).

Liczymy na wydruku (render CMYK FOGRA39 z symulacją overprintu — overprint dokłada farby),
w niskiej rozdzielczości: to pola, a nie pojedyncze kreski, są problemem.
"""
from __future__ import annotations

import os
import tempfile

import numpy as np

import gs

# % — powyżej zalecanej czerni Adsystem C78 M85 Y90 K100 (= 353 %, Tomasz 29.09), a czerń z RGB
# po zamianie na FOGRA39 daje ok. 316 %. Wyżej są już czernie 4 × 100 %, „Registration” i podobne.
TAC_LIMIT = 360
LONG_PX = 1500           # dłuższy bok renderu
CELL = 12                # kratka do wyznaczania ramek (px renderu)
CELL_MIN = 6             # tyle pikseli ponad limit, żeby kratka się liczyła
MIN_AREA_PX = 30         # mniejsze skupiska pomijamy (pojedyncze kreski, krawędzie)


def _read_pam(path: str) -> np.ndarray:
    raw = open(path, "rb").read()
    end = raw.index(b"ENDHDR\n") + 7
    hdr = raw[:end].decode("latin1").split()
    f = {hdr[i]: hdr[i + 1] for i in range(1, len(hdr) - 1) if hdr[i] in ("WIDTH", "HEIGHT", "DEPTH")}
    w, h, d = int(f["WIDTH"]), int(f["HEIGHT"]), int(f.get("DEPTH", 4))
    return np.frombuffer(raw[end:end + w * h * d], np.uint8).reshape(h, w, d)


def _components(mask: np.ndarray) -> list:
    """Spójne skupiska kratek (4-sąsiedztwo): [(y0, x0, y1, x1, liczba kratek)] — bez scipy."""
    h, w = mask.shape
    seen = np.zeros_like(mask, bool)
    out = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            st, seen[y, x] = [(y, x)], True
            y0 = y1 = y
            x0 = x1 = x
            n = 0
            while st:
                cy, cx = st.pop()
                n += 1
                y0, y1, x0, x1 = min(y0, cy), max(y1, cy), min(x0, cx), max(x1, cx)
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        st.append((ny, nx))
            out.append((y0, x0, y1 + 1, x1 + 1, n))
    return out


def measure(path: str, page: int, page_pt: tuple) -> dict:
    """{limit, max, over_pct, boxes:[[fx, fy, fw, fh, max %]]} dla strony `page`."""
    w_pt, h_pt = page_pt
    dpi = LONG_PX / (max(w_pt, h_pt) / 72.0)
    fd, tmp = tempfile.mkstemp(suffix=".pam")
    os.close(fd)
    try:
        r = gs.run(["-q", "-dSAFER", *gs.proof_args(), "-sDEVICE=pamcmyk32", f"-r{dpi:.4f}",
                    f"-dFirstPage={page + 1}", f"-dLastPage={page + 1}", *gs.overprint_args(True),
                    "-sOutputFile=" + gs.arg_path(tmp), gs.arg_path(path)], 600)
        if r.returncode != 0 or os.path.getsize(tmp) < 16:
            raise RuntimeError("Ghostscript: " + gs.log_of(r, 200))
        a = _read_pam(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    tac = a[:, :, :4].astype(np.uint16).sum(axis=2) * (100.0 / 255.0)
    over = tac > TAC_LIMIT + 0.5
    H, W = over.shape
    res = {"limit": TAC_LIMIT, "max": int(round(float(tac.max()))) if tac.size else 0,
           "over_pct": round(float(over.mean()) * 100, 3) if over.size else 0.0, "boxes": []}
    if not over.any():
        return res
    gh, gw = -(-H // CELL), -(-W // CELL)
    pad = np.zeros((gh * CELL, gw * CELL), bool)
    pad[:H, :W] = over
    cnt = pad.reshape(gh, CELL, gw, CELL).sum(axis=(1, 3))
    comps = _components(cnt >= CELL_MIN)
    boxes = []
    for y0, x0, y1, x1, n in comps:
        py0, px0, py1, px1 = y0 * CELL, x0 * CELL, min(H, y1 * CELL), min(W, x1 * CELL)
        area = int(over[py0:py1, px0:px1].sum())
        if area < MIN_AREA_PX:
            continue
        mx = int(round(float(tac[py0:py1, px0:px1].max())))
        boxes.append((area, [round(px0 / W, 5), round(py0 / H, 5), round((px1 - px0) / W, 5),
                             round((py1 - py0) / H, 5), mx]))
    boxes.sort(key=lambda b: -b[0])
    res["boxes"] = [b for _, b in boxes[:30]]
    return res
