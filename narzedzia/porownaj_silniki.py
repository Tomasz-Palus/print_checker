"""Porównanie podglądu: Ghostscript (dziś) ↔ MuPDF (kandydat na szybkie kafelki przy przybliżaniu).

Pytanie (doc 20, krok 1): czy kafelki z MuPDF wyglądają tak samo jak podgląd z Ghostscripta, którego
program używa dziś — w trybie „ekran” i „symulacja druku”. Overprint zostaje przy Ghostscripcie
(MuPDF w PyMuPDF go nie symuluje), więc tu tylko zaznaczamy strony, które go używają.

Uruchomienie (Windows, w katalogu repozytorium):
    py narzedzia\\porownaj_silniki.py "C:\\...\\przykladowe projekty" [--wyniki folder] [--tylko-pierwsza]

Dla każdej strony każdego PDF-a / AI:
  - plik przygotowany jak przy wgraniu (render.canonicalize, normalize_geometry, bake_print_state)
    i z tekstem na krzywych (render.text_as_curves — tak liczy podgląd);
  - podgląd całości (dłuższy bok 1600 px) i 3 kafelki 1024 px w 8× większym przybliżeniu;
  - Ghostscript dokładnie jak program (render._gs_args: profil pliku/FOGRA39, nadpróbkowanie 2×);
  - MuPDF w dwóch wariantach: RGB wprost („mu_rgb”) i CMYK → ekran naszym profilem („mu_cmyk”,
    render.proof_rgb — ta sama droga co symulacja druku).
Wynik: raport.md + raport.csv i obrazy porównań (GS | MuPDF | różnica×4) dla najgorszych miejsc.

Miary (0–255, największa różnica kanału w pikselu):
  - sr      — średnia różnica,
  - p99_kol — 99. percentyl po uśrednieniu bloków 4×4 px (kolor, bez wpływu wygładzania krawędzi),
  - kraw%   — % pikseli różniących się o > 32 (krawędzie, cienkie linie, detal).
Przyjęte progi „zgodne”: p99_kol ≤ 6 i kraw% ≤ 1 — różnica niewidoczna przy oglądaniu.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))

import numpy as np                      # noqa: E402
import pymupdf                          # noqa: E402
from PIL import Image                   # noqa: E402

import gs                               # noqa: E402
import prepare                          # noqa: E402
import render                           # noqa: E402

OV_PX = 1600
TILE = 1024
ZOOM = 8                                # kafelki: 8× gęściej niż podgląd całości
TILES = [(0.5, 0.5), (0.25, 0.3), (0.7, 0.72)]     # środki kafelków (ułamki strony)
OK_P99, OK_EDGE = 6, 1.0


def prepared(src: str, work: str) -> str:
    """Plik w postaci, w jakiej program go podgląda (jak jobs.create + text_as_curves)."""
    dst = os.path.join(work, "original" + os.path.splitext(src)[1].lower())
    shutil.copy(src, dst)
    path, _ = prepare.check_open(dst)
    path, _ = render.canonicalize(path)
    path, _ = render.normalize_geometry(path)
    path, _ = prepare.bake_print_state(path)
    return path


def gs_render(src: str, page: int, ppp: float, proof: bool, clip=None, page_rect=None) -> Image.Image:
    """Ghostscript jak podgląd programu (render._gs_args, nadpróbkowanie render.SS). `clip` — wycinek w pt
    (początek w lewym górnym rogu), inaczej cała strona."""
    ss = render.SS
    w = round((clip.width if clip else page_rect.width) * ppp)
    h = round((clip.height if clip else page_rect.height) * ppp)
    args = render._gs_args(src, page, ppp * 72 * ss, False, proof, w, h, ss)
    assert args[-5] == "-sOutputFile=-"
    tail = ["-sOutputFile=-", *gs.PREVIEW_PRE, args[-1]]
    if clip:
        tx, ty = -clip.x0, -(page_rect.height - clip.y1)
        tail = ["-dFIXEDMEDIA", f"-dDEVICEWIDTHPOINTS={clip.width:.4f}", f"-dDEVICEHEIGHTPOINTS={clip.height:.4f}",
                "-sOutputFile=-", "-c", f"<</Install {{{tx:.4f} {ty:.4f} translate}}>> setpagedevice 0 0 .setfilladjust2",
                "-f", args[-1]]
    p = gs.stream(args[:-5] + tail)
    try:
        W, H, ch = render._head(p)
        a = np.frombuffer(render._read(p, W * H * ch, "porównanie"), np.uint8).reshape(H, W, ch)
    finally:
        render._close(p)
    mode = "CMYK" if ch == 4 else "RGB"
    im = Image.frombuffer(mode, (W, H), np.ascontiguousarray(a).tobytes(), "raw", mode, 0, 1).reduce(ss)
    return render.proof_rgb(im, src) if ch == 4 else im


def mu_render(src: str, page: int, ppp: float, cmyk: bool, clip=None) -> tuple[Image.Image, str]:
    """MuPDF: (obraz na ekran, ostrzeżenia MuPDF)."""
    with render.MUPDF_LOCK:
        doc = render.open_doc(src)
        try:
            render._interpolate(doc)
            pymupdf.TOOLS.mupdf_warnings(reset=True)
            pix = doc[page].get_pixmap(matrix=pymupdf.Matrix(ppp, ppp), clip=clip, alpha=False,
                                       colorspace=pymupdf.csCMYK if cmyk else pymupdf.csRGB)
            warn = pymupdf.TOOLS.mupdf_warnings(reset=True) or ""
        finally:
            doc.close()
    if cmyk:
        im = Image.frombytes("CMYK", (pix.width, pix.height), pix.samples)
        return render.proof_rgb(im, src), warn
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples), warn


def measure(a: Image.Image, b: Image.Image) -> dict:
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    x, y = np.asarray(a, np.int16), np.asarray(b, np.int16)
    d = np.abs(x - y).max(axis=2)
    h, w = (d.shape[0] // 4) * 4, (d.shape[1] // 4) * 4
    blk = np.abs(x[:h, :w].reshape(h // 4, 4, w // 4, 4, 3).mean(axis=(1, 3))
                 - y[:h, :w].reshape(h // 4, 4, w // 4, 4, 3).mean(axis=(1, 3))).max(axis=2)
    return {"sr": round(float(d.mean()), 2), "p99_kol": round(float(np.percentile(blk, 99)), 1) if blk.size else 0.0,
            "kraw%": round(float((d > 32).mean() * 100), 2)}


def triptych(a: Image.Image, b: Image.Image, path: str) -> None:
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    d = np.clip(np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16)) * 4, 0, 255).astype(np.uint8)
    W, H = a.size
    out = Image.new("RGB", (W * 3 + 20, H), (255, 255, 255))
    out.paste(a, (0, 0)); out.paste(b, (W + 10, 0)); out.paste(Image.fromarray(d), (2 * W + 20, 0))
    out.thumbnail((3 * 900, 900))
    out.save(path, quality=88)


def facts(src: str, page: int) -> dict:
    try:
        import analyze
        a = analyze.analyze(src, page)
        fam = set((a.get("color") or {}).get("families") or {})
        # „czysty CMYK”: nic do przeliczenia na CMYK (RGB, Lab, inne) — wtedy MuPDF nie przelicza kolorów
        # własnym profilem i powinien zgadzać się z Ghostscriptem
        clean = not any("RGB" in f or f in ("Lab", "Unknown", "Indexed") for f in fam)
        return {"czysty_cmyk": clean, "przestrzeń_mieszania": not a.get("blend_space_missing") and not a.get("group_rgb"),
                "overprint": (a.get("overprint_uses") or 0) > 0,
                "spot": len((a.get("color") or {}).get("spots") or []),
                "transp": ", ".join(k for k in (a.get("transparency") or {}) if "grupa" not in k)}
    except Exception as e:
        return {"overprint": None, "spot": None, "transp": f"analiza: {e}"}


def run(folder: str, outdir: str, first_only: bool) -> None:
    os.makedirs(outdir, exist_ok=True)
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".pdf", ".ai")))
    rows = []
    for fi, name in enumerate(files, 1):
        print(f"[{fi}/{len(files)}] {name}", flush=True)
        with tempfile.TemporaryDirectory() as work:
            try:
                path = prepared(os.path.join(folder, name), work)
                with render.MUPDF_LOCK:
                    d = render.open_doc(path)
                    n = 1 if first_only else d.page_count
                    rects = [d[i].rect for i in range(n)]
                    d.close()
            except Exception as e:
                rows.append({"plik": name, "strona": "-", "błąd": f"przygotowanie: {type(e).__name__}: {e}"})
                continue
            for page in range(n):
                pr = rects[page]
                try:
                    cur, pg = render.text_as_curves(path, page)     # kopia JEDNEJ strony — inny numer
                except Exception:
                    cur, pg = path, page
                fx = facts(path, page)
                ppp = OV_PX / max(pr.width, pr.height)
                regions = [("całość", None)]
                tp = TILE / (ppp * ZOOM)                     # bok kafelka w pt
                for cx, cy in TILES:
                    x0 = min(max(0, cx * pr.width - tp / 2), max(0, pr.width - tp))
                    y0 = min(max(0, cy * pr.height - tp / 2), max(0, pr.height - tp))
                    regions.append((f"kafel {cx:.2f},{cy:.2f}",
                                    pymupdf.Rect(x0, y0, min(pr.width, x0 + tp), min(pr.height, y0 + tp))))
                for label, clip in regions:
                    z = ppp * (ZOOM if clip else 1)
                    for mode, proof in (("ekran", False), ("druk", True)):
                        row = {"plik": name, "strona": page + 1, "miejsce": label, "tryb": mode, **fx}
                        try:
                            t = time.time()
                            ref = gs_render(cur, pg, z, proof, clip, pr)
                            row["t_gs"] = round(time.time() - t, 2)
                            for var, cm in (("mu_rgb", False), ("mu_cmyk", True)):
                                t = time.time()
                                im, warn = mu_render(cur, pg, z, cm, clip)
                                row[f"t_{var}"] = round(time.time() - t, 2)
                                m = measure(ref, im)
                                for k, v in m.items():
                                    row[f"{var}_{k}"] = v
                                row[f"{var}_ok"] = m["p99_kol"] <= OK_P99 and m["kraw%"] <= OK_EDGE
                                if warn:
                                    row["ostrzeżenia_mupdf"] = warn[:200].replace("\n", " ")
                                if not row[f"{var}_ok"]:
                                    safe = "".join(c if c.isalnum() else "_" for c in f"{name}_{page + 1}_{label}_{mode}_{var}")
                                    triptych(ref, im, os.path.join(outdir, safe[:150] + ".jpg"))
                        except Exception as e:
                            row["błąd"] = f"{type(e).__name__}: {e}"[:300]
                        rows.append(row)
                        print("   ", label, mode, {k: row.get(k) for k in ("mu_rgb_p99_kol", "mu_cmyk_p99_kol",
                                                                        "mu_cmyk_kraw%", "t_gs", "t_mu_cmyk")}, flush=True)
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(os.path.join(outdir, "raport.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, keys, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    write_md(rows, os.path.join(outdir, "raport.md"))
    print("raport:", os.path.join(outdir, "raport.md"))


def write_md(rows: list, path: str) -> None:
    good = [r for r in rows if "błąd" not in r]
    lines = ["# Porównanie podglądu: Ghostscript ↔ MuPDF", "",
             f"Próg „zgodne”: p99 koloru ≤ {OK_P99}/255 i ≤ {OK_EDGE} % pikseli różnych o > 32.", ""]
    for var in ("mu_rgb", "mu_cmyk"):
        for mode in ("ekran", "druk"):
            sel = [r for r in good if r["tryb"] == mode and f"{var}_ok" in r]
            ok = sum(1 for r in sel if r[f"{var}_ok"])
            lines.append(f"- **{var} vs Ghostscript „{mode}”**: zgodne {ok} z {len(sel)} miejsc")
    tg = [r["t_gs"] for r in good if "t_gs" in r and r["miejsce"] != "całość"]
    tm = [r["t_mu_cmyk"] for r in good if "t_mu_cmyk" in r and r["miejsce"] != "całość"]
    if tg and tm:
        lines += ["", f"Kafel 1024 px: Ghostscript średnio {sum(tg) / len(tg):.2f} s (najdłużej {max(tg):.2f}), "
                      f"MuPDF CMYK średnio {sum(tm) / len(tm):.2f} s (najdłużej {max(tm):.2f})."]
    for mode in ("ekran", "druk"):
        sel = [r for r in good if r["tryb"] == mode and r.get("czysty_cmyk") and r.get("przestrzeń_mieszania")
               and "mu_cmyk_ok" in r]
        ok = sum(1 for r in sel if r["mu_cmyk_ok"])
        lines.append(f"- **mu_cmyk, strony „czysty CMYK” z zadeklarowaną przestrzenią mieszania, „{mode}”**: "
                     f"zgodne {ok} z {len(sel)}")
    lines += ["", "| plik | str. | miejsce | tryb | czysty CMYK | mieszanie OK | overprint | spot | przezroczystość | "
                  "mu_rgb p99 / kraw% | mu_cmyk p99 / kraw% | t GS | t MuPDF |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "błąd" in r:
            lines.append(f"| {r['plik']} | {r.get('strona', '')} | {r.get('miejsce', '')} | {r.get('tryb', '')} | "
                         f"**błąd:** {r['błąd']} ||||||||")
            continue
        f = lambda v: f"{r[v + '_p99_kol']} / {r[v + '_kraw%']}" + ("" if r[v + "_ok"] else " ✗")
        lines.append(f"| {r['plik']} | {r['strona']} | {r['miejsce']} | {r['tryb']} | {r.get('czysty_cmyk')} | "
                     f"{r.get('przestrzeń_mieszania')} | {r.get('overprint')} | "
                     f"{r.get('spot')} | {r.get('transp')} | {f('mu_rgb')} | {f('mu_cmyk')} | {r['t_gs']} | "
                     f"{r['t_mu_cmyk']} |")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder")
    ap.add_argument("--wyniki", default=None, help="folder na raport (domyślnie <folder>/porownanie_silnikow)")
    ap.add_argument("--tylko-pierwsza", action="store_true", help="tylko pierwsza strona każdego pliku")
    a = ap.parse_args()
    run(a.folder, a.wyniki or os.path.join(a.folder, "porownanie_silnikow"), a.tylko_pierwsza)
