"""Otwieranie pliku i rysowanie go: metadane, miniatury, wycinki do analizy oraz
PIRAMIDA PODGLĄDU w pełnej jakości.

Piramida — zasada Tomasza: „ma być jak w Photoshopie: plik wczytuje się raz, a potem
nawigacja nie każe czekać". Jeden przebieg Ghostscripta na wersję pliku, w 120 ppi NA
WYDRUKU, pokrojony na kafelki i zapisany na dysku. Przeglądarka tylko czyta gotowe pliki.
  • ov_q.jpg — szybki podgląd całej strony (krótki przebieg w małej rozdzielczości),
  • L0_x_y.jpg … Ln — poziomy (0 = pełna rozdzielczość, każdy następny o połowę mniejszy),
  • ov.jpg — podgląd całej strony z gotowej piramidy (nie gubi cienkich linii).
"""
from __future__ import annotations

import io
import math
import os
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pikepdf
import pymupdf
from PIL import Image

import gs

Image.MAX_IMAGE_PIXELS = None
MM = 25.4 / 72.0

VECTOR_EXT = {".pdf", ".ai", ".svg", ".eps"}
RASTER_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
UNSUPPORTED_EXT = {".cdr": "CorelDRAW", ".indd": "InDesign", ".idml": "InDesign", ".psd": "Photoshop"}
ALLOWED_EXT = VECTOR_EXT | RASTER_EXT | set(UNSUPPORTED_EXT)


class UnsupportedFormat(Exception):
    pass


# ----------------------------------------------------------------------------
# otwieranie
# ----------------------------------------------------------------------------
def is_raster(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in RASTER_EXT


def open_doc(path: str) -> pymupdf.Document:
    """Plik jako dokument MuPDF. Raster = jednostronicowy PDF (jeden model „strony")."""
    ext = os.path.splitext(path)[1].lower()
    if ext in UNSUPPORTED_EXT:
        raise UnsupportedFormat(f"Plik {UNSUPPORTED_EXT[ext]} ({ext}) — wyeksportuj go do PDF i wgraj ponownie.")
    if ext in (".pdf", ".ai", ".eps", ".svg"):
        doc = pymupdf.open(path)
        if ext == ".ai" and not doc.is_pdf:
            raise UnsupportedFormat("Plik .ai bez zawartości PDF — zapisz go w Illustratorze z opcją "
                                    "„Create PDF Compatible File” albo wyeksportuj do PDF.")
        return doc
    try:
        img = pymupdf.open(path)
        data = img.convert_to_pdf()
        img.close()
        return pymupdf.open("pdf", data)
    except Exception:
        # CMYK / 16-bit / wielostronicowy TIFF — przez Pillow
        im = Image.open(path)
        pdf = pymupdf.open()
        for i in range(getattr(im, "n_frames", 1)):
            im.seek(i)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="PNG")
            page = pdf.new_page(width=im.width, height=im.height)
            page.insert_image(page.rect, stream=buf.getvalue())
        return pdf


def canonicalize(path: str) -> tuple[str, str | None]:
    """SVG i EPS → PDF (dalej wszystko działa na PDF-ie); reszta bez zmian."""
    ext = os.path.splitext(path)[1].lower()
    out = os.path.join(os.path.dirname(path), "canon.pdf")
    if ext == ".svg":
        doc = pymupdf.open(path)
        try:
            data = doc.convert_to_pdf()
        finally:
            doc.close()
        with open(out, "wb") as f:
            f.write(data)
        return out, "SVG → PDF"
    if ext == ".eps":
        r = gs.run(["-q", "-dSAFER", "-sDEVICE=pdfwrite", "-dEPSCrop", *gs.PDFWRITE_NO_ROTATE,
                    "-sOutputFile=" + gs.arg_path(out), path], 600)
        if r.returncode != 0:
            raise UnsupportedFormat("Nie udało się otworzyć EPS — wyeksportuj go do PDF.")
        return out, "EPS → PDF"
    return path, None


# ----------------------------------------------------------------------------
# geometria strony: obrót i CropBox wpisane w treść (przegląd kodu 27.09, A10)
# ----------------------------------------------------------------------------
def _box(o, key):
    v = o.get(key)
    return [float(x) for x in v] if v is not None else None


def _apply(m, x, y):
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def _map_box(m, b, W, H):
    """Prostokąt przez macierz (obroty o 90°) i przycięty do nowej strony."""
    pts = [_apply(m, x, y) for x in (b[0], b[2]) for y in (b[1], b[3])]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [max(0.0, min(xs)), max(0.0, min(ys)), min(W, max(xs)), min(H, max(ys))]


def _mat_mul(m, n):
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return [a * a2 + b * c2, a * b2 + b * d2, c * a2 + d * c2, c * b2 + d * d2,
            e * a2 + f * c2 + e2, e * b2 + f * d2 + f2]


def normalize_geometry(path: str) -> tuple[str, list]:
    """Strona z /Rotate, z CropBoxem mniejszym od MediaBoxa albo z UserUnit → zwykła strona: MediaBox od (0, 0)
    równy temu, co widać, bez /Rotate. Wygląd strony (i wydruk) się nie zmienia.

    Po co: MuPDF liczy stronę z obrotem i CropBoxem, a pikepdf, Ghostscript i nasze obliczenia
    (spady, wymiar, szablon, maska widoczności w ocenie jakości) — w surowym MediaBoxie. Przy
    obróconej stronie „Dopasuj wymiar” dawał pół białej strony, szablon nie był znajdowany,
    a ocena jakości gubiła prawdziwe problemy.

    Jak: na początku treści strony `q <macierz> cm`, na końcu `Q`. Wzory (pattern) z zasobów strony
    liczą się w domyślnej przestrzeni strony, a nie w bieżącej macierzy — dostają kopię z przeliczoną
    /Matrix. Adnotacje: nowy /Rect i obrót ich wyglądu. TrimBox/BleedBox/ArtBox przeliczone.
    Zwraca (ścieżka, lista zmian); bez zmian — ta sama ścieżka."""
    try:
        pdf = pikepdf.open(path)
    except Exception:
        return path, []
    notes = []
    try:
        for i, page in enumerate(pdf.pages):
            o = page.obj
            mb = _box(o, "/MediaBox")
            if not mb or len(mb) != 4:
                continue
            mb = [min(mb[0], mb[2]), min(mb[1], mb[3]), max(mb[0], mb[2]), max(mb[1], mb[3])]
            cb = _box(o, "/CropBox") or mb
            cb = [min(cb[0], cb[2]), min(cb[1], cb[3]), max(cb[0], cb[2]), max(cb[1], cb[3])]
            v = [max(mb[0], cb[0]), max(mb[1], cb[1]), min(mb[2], cb[2]), min(mb[3], cb[3])]
            if v[2] - v[0] < 1 or v[3] - v[1] < 1:
                v = mb
            rot = int(o.get("/Rotate", 0) or 0) % 360
            if rot % 90:
                rot = 0
            cropped = any(abs(a - b) > 0.01 for a, b in zip(v, mb))
            # UserUnit (strony ponad 5 m z Illustratora / Acrobata): jednostka strony = U punktów.
            # MuPDF i Ghostscript ją uwzględniają, pikepdf i nasze obliczenia (spady, szablon,
            # przeskalowanie) — nie, więc wymiar wychodził U razy za mały. Wpisujemy ją w treść.
            try:
                uu = float(o.get("/UserUnit", 1) or 1)
            except Exception:
                uu = 1.0
            uu = uu if 0.01 < uu < 1000 and abs(uu - 1) > 1e-6 else 1.0
            if not rot and not cropped and uu == 1.0:
                continue
            x0, y0, x1, y1 = v
            w, h = x1 - x0, y1 - y0
            if rot == 90:
                m, W, H = [0, -1, 1, 0, -y0, x1], h, w
            elif rot == 180:
                m, W, H = [-1, 0, 0, -1, x1, y1], w, h
            elif rot == 270:
                m, W, H = [0, 1, -1, 0, y1, -x0], h, w
            else:
                m, W, H = [1, 0, 0, 1, -x0, -y0], w, h
            if uu != 1.0:
                m, W, H = _mat_mul(m, [uu, 0, 0, uu, 0, 0]), W * uu, H * uu
            cmd = ("q " + " ".join(f"{x:.6f}".rstrip("0").rstrip(".") or "0" for x in m) + " cm\n").encode()
            page.contents_add(pdf.make_stream(cmd), prepend=True)
            page.contents_add(pdf.make_stream(b"\nQ\n"), prepend=False)
            # wzory z zasobów STRONY — kopia z macierzą przeliczoną o nasz obrót/przesunięcie
            res = o.get("/Resources")
            pats = res.get("/Pattern") if res is not None else None
            if pats is not None:
                newp = pikepdf.Dictionary()
                for name, pat in pats.items():
                    pm = [float(x) for x in pat.get("/Matrix", [1, 0, 0, 1, 0, 0])]
                    if isinstance(pat, pikepdf.Stream):
                        cp = pikepdf.Stream(pdf, pat.read_raw_bytes())
                        for k2, v2 in pat.items():
                            if k2 not in ("/Length",):
                                cp[k2] = v2
                    else:
                        cp = pikepdf.Dictionary({k2: v2 for k2, v2 in pat.items()})
                    cp["/Matrix"] = pikepdf.Array(_mat_mul(pm, m))
                    newp[name] = pdf.make_indirect(cp)
                res = pikepdf.Dictionary({k2: v2 for k2, v2 in res.items()})
                res["/Pattern"] = newp
                o["/Resources"] = res
            # pola strony
            for key in ("/TrimBox", "/BleedBox", "/ArtBox"):
                b = _box(o, key)
                if b:
                    o[key] = pikepdf.Array(_map_box(m, b, W, H))
            o["/MediaBox"] = pikepdf.Array([0, 0, W, H])
            for key in ("/CropBox", "/Rotate", "/UserUnit"):
                if key in o:
                    del o[key]
            # adnotacje: nowe położenie; wygląd obrócony razem ze stroną
            rot_only = [m[0], m[1], m[2], m[3], 0, 0]
            for an in (o.get("/Annots") or []):
                try:
                    r = _box(an, "/Rect")
                    if r:
                        pts = [_apply(m, x, y) for x in (r[0], r[2]) for y in (r[1], r[3])]
                        an["/Rect"] = pikepdf.Array([min(p[0] for p in pts), min(p[1] for p in pts),
                                                     max(p[0] for p in pts), max(p[1] for p in pts)])
                    ap = an.get("/AP")
                    if rot and ap is not None and not (int(an.get("/F", 0)) & 16):   # 16 = NoRotate
                        for k2 in ("/N", "/R", "/D"):
                            st = ap.get(k2)
                            forms = [st] if isinstance(st, pikepdf.Stream) else \
                                    [x for x in (st.values() if st is not None else []) if isinstance(x, pikepdf.Stream)]
                            for f in forms:
                                fm = [float(x) for x in f.get("/Matrix", [1, 0, 0, 1, 0, 0])]
                                f["/Matrix"] = pikepdf.Array(_mat_mul(fm, rot_only))
                except Exception:
                    pass
            notes.append(f"str. {i + 1}: " + ", ".join(
                ([f"obrót {rot}° wpisany w stronę"] if rot else []) + (["przycięta do CropBox"] if cropped else [])
                + ([f"UserUnit {uu:g} wpisany w stronę"] if uu != 1.0 else [])))
        if not notes:
            return path, []
        out = os.path.splitext(path)[0] + "_geom.pdf"
        pdf.save(out)
    finally:
        pdf.close()
    return out, notes


def inspect(path: str, original_name: str) -> dict:
    """Metadane pliku: strony, wymiary, spady (TrimBox/ArtBox), dla rastra — piksele i DPI."""
    raster = is_raster(original_name)
    dpi = None
    if raster:
        try:
            with Image.open(path) as im:
                d = im.info.get("dpi")
                dpi = (float(d[0]), float(d[1])) if d and d[0] and d[1] else None
        except Exception:
            pass
    doc = open_doc(path)
    try:
        pages = []
        for i, page in enumerate(doc):
            r = page.rect
            p = {"index": i, "width_mm": round(r.width * MM, 2), "height_mm": round(r.height * MM, 2)}
            # spad: TrimBox (a bez niego ArtBox) mniejszy od strony — osobno z każdej strony
            try:
                mb = page.mediabox
                for name, attr in (("TrimBox", "trimbox"), ("ArtBox", "artbox")):
                    tb = getattr(page, attr, None)
                    if tb is None or tb.is_empty or (tb.width >= mb.width - 0.5 and tb.height >= mb.height - 0.5):
                        continue
                    p["trim_mm"] = [round(tb.width * MM, 2), round(tb.height * MM, 2)]
                    p["trim_src"] = name
                    p["bleed_mm"] = [round((tb.x0 - mb.x0) * MM, 2), round((mb.y1 - tb.y1) * MM, 2),
                                     round((mb.x1 - tb.x1) * MM, 2), round((tb.y0 - mb.y0) * MM, 2)]
                    break
            except Exception:
                pass
            if raster:
                p["width_px"], p["height_px"] = int(round(r.width)), int(round(r.height))
                p["dpi"] = [round(dpi[0], 1), round(dpi[1], 1)] if dpi else None
                p["width_mm"] = round(r.width / dpi[0] * 25.4, 2) if dpi else None
                p["height_mm"] = round(r.height / dpi[1] * 25.4, 2) if dpi else None
            pages.append(p)
        return {"name": original_name, "kind": "raster" if raster else "pdf",
                "size_bytes": os.path.getsize(path), "page_count": len(pages), "pages": pages}
    finally:
        doc.close()


# ----------------------------------------------------------------------------
# miniatury i wycinki (MuPDF; Ghostscript, gdy MuPDF odmawia)
# ----------------------------------------------------------------------------
MUPDF_IMAGE_LIMIT = 400_000_000      # MuPDF odmawia obrazów > ~0,5 Gpx („Overly large image")


def _mupdf_can(page) -> bool:
    try:
        return all(int(i[2]) * int(i[3]) <= MUPDF_IMAGE_LIMIT for i in page.get_images(full=True))
    except Exception:
        return True


def _mupdf_failed(warnings: str) -> bool:
    w = warnings.lower()
    return "error" in w and ("overly large" in w or "limit" in w or "out of memory" in w)


def _interpolate(doc) -> None:
    """MuPDF skaluje obrazy bez interpolacji (widać piksele), chyba że mają /Interpolate —
    ustawiamy ją w pamięci (plik na dysku bez zmian). Podgląd jest zawsze wygładzony."""
    if not doc.is_pdf:
        return
    try:
        for page in doc:
            for img in page.get_images(full=True):
                doc.xref_set_key(img[0], "Interpolate", "true")
    except Exception:
        pass


def fix_edges(data: bytes, gray: bool = False) -> bytes:
    """Skrajny wiersz/kolumna renderu bywa pokryty częściowo (strona rzadko wypada okrągło
    w pikselach) i wychodzi jaśniejszy — na ciemnym projekcie jasna kreska. Zastępujemy go
    sąsiednim, jeśli wygląda dokładnie jak zmieszanie sąsiedniego z bielą."""
    try:
        a = np.asarray(Image.open(io.BytesIO(data))).astype(np.int16)
    except Exception:
        return data
    if a.ndim == 2:
        a = a[:, :, None]
    if a.shape[0] < 3 or a.shape[1] < 3:
        return data
    changed = False
    blend = lambda e, n: e.mean() > n.mean() + 4 and (e >= n - 3).all()
    for edge, near in ((0, 1), (-1, -2)):
        if blend(a[edge], a[near]):
            a[edge] = a[near]; changed = True
        if blend(a[:, edge], a[:, near]):
            a[:, edge] = a[:, near]; changed = True
    if not changed:
        return data
    arr = a.astype("uint8")
    buf = io.BytesIO()
    Image.fromarray(arr[:, :, 0] if arr.shape[2] == 1 else arr).save(buf, format="PPM" if gray else "PNG")
    return buf.getvalue()


def page_png(path: str, page_index: int, max_px: int) -> bytes:
    """Cała strona jako PNG (miniatura, skan ramek w pikselach)."""
    doc = open_doc(path)
    try:
        page = doc[page_index]
        zoom = max_px / (max(page.rect.width, page.rect.height) or 1)
        if not is_raster(path) and not _mupdf_can(page):
            return region_png(path, page_index, tuple(page.rect), zoom, max_px=max_px)
        _interpolate(doc)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False, colorspace=pymupdf.csRGB)
        return pix.tobytes("png")
    finally:
        doc.close()


def region_png(path: str, page_index: int, clip_pt: tuple, px_per_pt: float, smooth: bool = True,
               max_px: int = 3200, gray: bool = False) -> bytes:
    """Wycinek strony (x0,y0,x1,y1 w pt, początek w lewym górnym rogu) — narzędzie pomiarowe
    analizy i mapy detalu. `gray` = skala szarości (mniej pamięci)."""
    doc = open_doc(path)
    try:
        page = doc[page_index]
        pr = page.rect
        clip = pymupdf.Rect(*clip_pt) & pr
        if clip.is_empty:
            raise ValueError("Wycinek poza stroną.")
        big = max(clip.width, clip.height) * px_per_pt
        if big > max_px:
            px_per_pt *= max_px / big
        if is_raster(path) or _mupdf_can(page):
            if smooth:
                _interpolate(doc)
            pymupdf.TOOLS.mupdf_warnings(reset=True)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(px_per_pt, px_per_pt), clip=clip, alpha=False,
                                  colorspace=pymupdf.csGRAY if gray else pymupdf.csRGB)
            if not _mupdf_failed(pymupdf.TOOLS.mupdf_warnings(reset=True)):
                return pix.tobytes("png")
    finally:
        doc.close()
    return _gs_region(path, page_index, pr, clip, px_per_pt, smooth, gray)


def _gs_region(path, page_index, page_rect, clip, px_per_pt, smooth, gray) -> bytes:
    """Wycinek przez Ghostscripta: urządzenie o wymiarze wycinka + przesunięcie strony."""
    tx, ty = -clip.x0, -(page_rect.height - clip.y1)
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "r.pgm" if gray else "r.png")
        r = gs.run(["-q", "-dSAFER", *gs.color_args(path), "-sDEVICE=" + ("pgmraw" if gray else "png16m"),
                    f"-r{px_per_pt * 72:.4f}", f"-dFirstPage={page_index + 1}", f"-dLastPage={page_index + 1}",
                    "-dFIXEDMEDIA", f"-dDEVICEWIDTHPOINTS={clip.width:.3f}", f"-dDEVICEHEIGHTPOINTS={clip.height:.3f}",
                    *gs.SPEED, *gs.aa_args(False, 0, 0), "-dInterpolateControl=" + ("1" if smooth else "0"),
                    f"-sOutputFile={out}",
                    "-c", f"<</Install {{{tx:.3f} {ty:.3f} translate}}>> setpagedevice 0 0 .setfilladjust2",
                    "-f", path], 600)
        if r.returncode != 0 or not os.path.exists(out):
            raise RuntimeError("Ghostscript nie wyrenderował wycinka: " + gs.log_of(r, 200))
        with open(out, "rb") as fh:
            return fix_edges(fh.read(), gray)


# ----------------------------------------------------------------------------
# symulacja druku: CMYK (FOGRA39) → ekran
# ----------------------------------------------------------------------------
_tf: dict = {}
_tf_lock = threading.Lock()


def _transform(kind: str, icc: str | None = None):
    """Przekształcenia ImageCms (liczone raz na profil): cmyk→ekran, rgb→druk. `icc` — profil
    maszyny (gs.sim_profile), domyślnie FOGRA39."""
    from PIL import ImageCms
    icc = icc or gs.fogra()
    with _tf_lock:
        if (kind, icc) not in _tf:
            fog = ImageCms.getOpenProfile(icc)
            srgb = ImageCms.createProfile("sRGB")
            rel, bpc = ImageCms.Intent.RELATIVE_COLORIMETRIC, ImageCms.Flags.BLACKPOINTCOMPENSATION
            if kind == "cmyk":
                _tf[(kind, icc)] = ImageCms.buildTransform(fog, srgb, "CMYK", "RGB", renderingIntent=rel, flags=bpc)
            else:
                _tf[(kind, icc)] = ImageCms.buildTransform(srgb, fog, "RGB", "CMYK", renderingIntent=rel, flags=bpc)
        return _tf[(kind, icc)]


def proof_rgb(im: Image.Image, src: str | None = None) -> Image.Image:
    """CMYK z symulacji druku → ekran, profilem maszyny tego pliku (gs.sim_profile)."""
    from PIL import ImageCms
    return ImageCms.applyTransform(im, _transform("cmyk", gs.sim_profile(src) if src else None))


# ----------------------------------------------------------------------------
# PIRAMIDA
# ----------------------------------------------------------------------------
PPI = 120              # pikseli na cal WYDRUKU w poziomie 0 (ten sam próg co w ocenie jakości)
TILE = 1024
MAX_MPX = 400          # sufit poziomu 0 (większe strony schodzą z ppi — i mówimy o tym)
OVERVIEW_PX = 2048     # dłuższy bok podglądu całej strony
JPEG_Q = 90
SS = 2                 # nadpróbkowanie podglądu i spłaszczenia (_supersample)
RENDER_VER = 8         # zmiana sposobu renderu = nowe klucze = stare kafelki się nie mieszają


def plan(page_w_pt: float, page_h_pt: float, print_w_mm: float, print_h_mm: float,
         native_px: tuple | None = None) -> dict:
    """Rozdzielczość i poziomy. `print_*_mm` = wymiar NA WYDRUKU (strona × skala).
    `native_px` — raster: więcej pikseli, niż ma obraz, nic nie da."""
    if min(print_w_mm, print_h_mm, page_w_pt, page_h_pt) <= 0:
        raise ValueError("Nie znam wymiaru wydruku.")
    W = int(round(print_w_mm / 25.4 * PPI))
    H = int(round(print_h_mm / 25.4 * PPI))
    if native_px:
        W, H = int(native_px[0]), int(native_px[1])
    note = ""
    if W * H > MAX_MPX * 1e6:
        f = math.sqrt(MAX_MPX * 1e6 / (W * H))
        W, H = int(W * f), int(H * f)
        note = f"strona jest tak duża, że podgląd liczę w {round(W / (print_w_mm / 25.4))} ppi"
    levels, lw, lh = [], W, H
    if max(W, H) > OVERVIEW_PX:
        while True:
            levels.append({"w": lw, "h": lh, "cols": math.ceil(lw / TILE), "rows": math.ceil(lh / TILE)})
            if max(lw, lh) // 2 <= OVERVIEW_PX * 1.25:     # niżej wystarcza podgląd całości
                break
            lw, lh = max(1, lw // 2), max(1, lh // 2)
    f = min(1.0, OVERVIEW_PX / max(W, H))
    return {"w": W, "h": H, "px_per_pt": W / page_w_pt, "tile": TILE, "levels": levels,
            "ov": [max(1, round(W * f)), max(1, round(H * f))], "note": note}


def _gs_args(src, page, dpi, op, proof, w_px, h_px, ss=1) -> list:
    # Obie symulacje (druku i overprintu) liczymy na urządzeniu CMYK FOGRA39, jak maszyna.
    # Overprint symulowany na urządzeniu RGB przesuwał kolory CAŁEJ strony (szare tło,
    # czerwień) — Ghostscript mieszał je wtedy w swojej przestrzeni CMYK (Tomasz 24.09).
    cmyk = proof or op
    # na urządzeniu CMYK zawsze ścieżka bezpieczna przy overprincie — obie strony suwaka
    # symulacji (bez i z overprintem) mają wtedy identyczne wygładzanie krawędzi
    # wygładzanie Ghostscripta liczone dla renderu ss× (gdy przy overprincie niebezpieczne — samo
    # nadpróbkowanie)
    aa = gs.aa_args(cmyk, w_px * ss, h_px * ss, 4 if cmyk else 3)
    return ["-dSAFER", *(gs.proof_args(src) if cmyk else gs.color_args(src)),
            "-sDEVICE=" + ("pamcmyk32" if cmyk else "ppmraw"), f"-r{dpi:.4f}",
            f"-dFirstPage={page + 1}", f"-dLastPage={page + 1}", *gs.SPEED, *aa,
            "-dInterpolateControl=1", *gs.overprint_args(op),
            "-sOutputFile=-", *gs.PREVIEW_PRE, gs.arg_path(src)]


def _supersample(op: bool, w: int, h: int) -> int:
    """Podgląd liczymy ZAWSZE 2× gęściej i uśredniamy sami (Pillow reduce).

    - Przy overprincie za dużym na render w całości (gs.aa_args zwraca []) to jedyne wygładzanie
      — inaczej tekst był postrzępiony.
    - Tekst wypełniony gradientem (gradient przycięty kształtem liter) Ghostscript rysuje BEZ
      wygładzania nawet z AlphaBits — przycięcia nie wygładza (Tomasz 25.09, `spady.pdf`: litery
      „PACHNĄCE” poszarpane). Nadpróbkowanie wygładza każdą krawędź.
    Koszt zmierzony na spady.pdf: render 2× z wygładzaniem 1,9 s wobec 2,5 s dla 1× — czas idzie
    głównie na wczytanie obrazów, nie na piksele."""
    return SS


def _head(p) -> tuple:
    """Nagłówek PPM (P6) albo PAM (P7, CMYK) ze strumienia: (szer., wys., kanały)."""
    def tok():
        out = b""
        while True:
            c = p.stdout.read(1)
            if not c:
                try:
                    p.wait(timeout=5)
                except Exception:
                    pass
                raise RuntimeError("Ghostscript nie zwrócił obrazu. "
                                   + p.err_tail[-300:].decode("latin1", "replace"))
            if c.isspace():
                if out:
                    return out
                continue
            if c == b"#":
                while p.stdout.read(1) not in (b"\n", b""):
                    pass
                continue
            out += c
    magic = tok()
    if magic == b"P7":
        f = {}
        while (k := tok()) != b"ENDHDR":
            f[k] = tok()
        return int(f[b"WIDTH"]), int(f[b"HEIGHT"]), int(f.get(b"DEPTH", b"4"))
    if magic != b"P6":
        raise RuntimeError("Nieoczekiwany format renderu.")
    W, H = int(tok()), int(tok())
    tok()
    return W, H, 3


def _read(p, n: int, what: str) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = p.stdout.read(min(1 << 22, n - len(buf)))
        if not chunk:
            try:
                p.wait(timeout=5)
            except Exception:
                pass
            raise RuntimeError(f"Render urwał się ({what}, kod {p.returncode}): "
                               + p.err_tail[-400:].decode("utf-8", "replace").strip())
        buf += chunk
    return bytes(buf)


def _close(p) -> None:
    try:
        p.stdout.close()
    except Exception:
        pass
    try:
        p.wait(timeout=5)
    except Exception:
        p.kill()


def _img(a: np.ndarray, src: str | None = None) -> Image.Image:
    """Tablica pikseli → obraz na ekran (CMYK z symulacji druku przez profil maszyny)."""
    a = np.ascontiguousarray(a)
    if a.shape[2] == 4:
        return proof_rgb(Image.frombuffer("CMYK", (a.shape[1], a.shape[0]), a.tobytes(), "raw", "CMYK", 0, 1), src)
    return Image.frombuffer("RGB", (a.shape[1], a.shape[0]), a.tobytes(), "raw", "RGB", 0, 1)


def _save(path: str, im: Image.Image) -> None:
    """Zapis przez plik tymczasowy — równoległe żądanie nie dostanie obciętego JPEG-a."""
    tmp = f"{path}.{threading.get_ident()}.part"
    im.save(tmp, "JPEG", quality=JPEG_Q, subsampling=0)
    os.replace(tmp, path)


def _render_whole(src, page, pl, W, H, op, proof, stop) -> Image.Image | None:
    """Cała strona naraz w rozdzielczości W×H (podgląd całości)."""
    dpi = pl["px_per_pt"] * 72 * W / pl["w"]
    ss = _supersample(op or proof, W, H)
    p = gs.stream(_gs_args(src, page, dpi * ss, op, proof, W, H, ss))
    try:
        w, h, ch = _head(p)
        a = np.frombuffer(_read(p, w * h * ch, "podgląd całości"), np.uint8).reshape(h, w, ch)
        if stop():
            return None
        mode = "CMYK" if ch == 4 else "RGB"
        im = Image.frombuffer(mode, (w, h), np.ascontiguousarray(a).tobytes(), "raw", mode, 0, 1).reduce(ss)
        im = proof_rgb(im, src) if ch == 4 else im
    finally:
        _close(p)
    return im if im.size == (W, H) else im.resize((W, H), Image.LANCZOS)


def _level0(src, page, pl, out, op, proof, on_band, stop) -> bool:
    """Poziom 0 JEDNYM przebiegiem, krojony w locie pasmami po TILE wierszy."""
    L0 = pl["levels"][0]
    ss = _supersample(op or proof, L0["w"], L0["h"])
    p = gs.stream(_gs_args(src, page, pl["px_per_pt"] * 72 * ss, op, proof, L0["w"], L0["h"], ss))
    try:
        W2, H2, ch = _head(p)
        W, H = math.ceil(W2 / ss), math.ceil(H2 / ss)
        rows = math.ceil(H / TILE)
        for ty in range(rows):
            if stop():
                p.kill()
                return False
            hgt = min(TILE, H - ty * TILE)
            src_rows = min(hgt * ss, H2 - ty * TILE * ss)
            band = np.frombuffer(_read(p, W2 * ch * src_rows, f"pasmo {ty + 1}"), np.uint8).reshape(src_rows, W2, ch)
            if ss > 1:                                   # uśrednianie ss×ss (Pillow reduce)
                band = np.pad(band, ((0, hgt * ss - src_rows), (0, W * ss - W2), (0, 0)), mode="edge")
                im = Image.frombuffer("CMYK" if ch == 4 else "RGB", (W * ss, hgt * ss),
                                      np.ascontiguousarray(band).tobytes(), "raw", "CMYK" if ch == 4 else "RGB", 0, 1).reduce(ss)
                im = proof_rgb(im, src) if ch == 4 else im
            else:
                im = _img(band, src)
            for tx in range(math.ceil(W / TILE)):
                _save(os.path.join(out, f"L0_{tx}_{ty}.jpg"), im.crop((tx * TILE, 0, min(W, tx * TILE + TILE), hgt)))
            on_band(ty + 1)
        return True
    finally:
        _close(p)


def _levels(pl, out, stop) -> None:
    """Poziomy 1..n z kafelków poziomu niżej: cztery → jeden (kilka sekund, nie przebieg gs)."""
    def one(lvl, L, tx, ty):
        if stop():
            return
        tile = Image.new("RGB", (min(TILE, L["w"] - tx * TILE), min(TILE, L["h"] - ty * TILE)), "white")
        for dy in (0, 1):
            for dx in (0, 1):
                f = os.path.join(out, f"L{lvl - 1}_{tx * 2 + dx}_{ty * 2 + dy}.jpg")
                if os.path.exists(f):
                    im = Image.open(f).convert("RGB")
                    tile.paste(im.resize((max(1, im.width // 2), max(1, im.height // 2)), Image.LANCZOS),
                               (dx * TILE // 2, dy * TILE // 2))
        _save(os.path.join(out, f"L{lvl}_{tx}_{ty}.jpg"), tile)

    with ThreadPoolExecutor(max_workers=gs.THREADS) as pool:
        for lvl in range(1, len(pl["levels"])):
            L = pl["levels"][lvl]
            list(pool.map(lambda t: one(lvl, L, *t), [(x, y) for y in range(L["rows"]) for x in range(L["cols"])]))


def _stitch(pl, out, lvl) -> Image.Image:
    L = pl["levels"][lvl]
    im = Image.new("RGB", (L["w"], L["h"]), "white")
    for ty in range(L["rows"]):
        for tx in range(L["cols"]):
            f = os.path.join(out, f"L{lvl}_{tx}_{ty}.jpg")
            if os.path.exists(f):
                im.paste(Image.open(f).convert("RGB"), (tx * TILE, ty * TILE))
    return im


def text_as_curves(src: str, page: int) -> tuple[str, int]:
    """Kopia strony z tekstem zamienionym na krzywe — TYLKO do podglądu.

    Ghostscript w rozdzielczości podglądu rysuje litery z fontu niedokładnie: zmierzone na
    PRINT_CHECKER_TEST (Arial) — przy 120 ppi o 11 % za cienko, przy 300 ppi o 6 % za grubo,
    a te same litery jako krzywe wychodzą co do 0,5 % (prawda = render 2400 dpi, gdzie font
    i krzywe są identyczne). Przez to „fonty na krzywe" wyglądało, jakby pogrubiało litery
    (Tomasz 24.09), a symulacja overprintu zmieniała ich grubość. Drukarnia rysuje w
    ~1200 dpi, gdzie problemu nie ma — więc podgląd pokazuje kształt z krzywych.
    Strona bez fontów idzie bez zmian. Plik liczony raz na wersję i stronę."""
    out = f"{os.path.splitext(src)[0]}_p{page}_krzywe.pdf"
    if os.path.exists(out):
        return out, 0
    try:
        doc = pymupdf.open(src)
        try:
            has = bool(doc[page].get_fonts())
        finally:
            doc.close()
    except Exception:
        return src, page
    if not has:
        return src, page
    tmp = out + ".part"
    r = gs.run(["-dSAFER", "-sDEVICE=pdfwrite", "-dNoOutputFonts", *gs.PDFWRITE_NO_ROTATE, *gs.font_path_args(),
                *gs.PDFWRITE_KEEP_IMAGES, "-dColorConversionStrategy=/LeaveColorUnchanged",
                f"-sPageList={page + 1}", "-o", gs.arg_path(tmp), gs.arg_path(src)], 900)
    if r.returncode != 0 or not os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
        return src, page                       # podgląd i tak ma się pokazać — z fontami
    os.replace(tmp, out)
    return out, 0


def build(src: str, page: int, pl: dict, out: str, op: bool, proof: bool, progress, stop) -> None:
    """Liczy piramidę do katalogu `out`. `progress(done, quick)` — postęp; `stop()` — przerwij."""
    os.makedirs(out, exist_ok=True)
    ow, oh = pl["ov"]
    if is_raster(src):
        _build_raster(src, pl, out, proof, progress, stop)
        return
    src, page = text_as_curves(src, page)
    if not pl["levels"]:                               # mała strona: sam podgląd całości
        im = _render_whole(src, page, pl, ow, oh, op, proof, stop)
        if im is not None:
            _save(os.path.join(out, "ov.jpg"), im)
        return
    # Szybki podgląd całości RÓWNOLEGLE z poziomem 0: jego koszt to głównie wczytanie PDF-a,
    # więc po kolei dołożyłby ten czas do całości. Dzięki niemu projekt widać od razu.
    def quick():
        try:
            im = _render_whole(src, page, pl, ow, oh, op, proof, stop)
            if im is not None and not stop():
                _save(os.path.join(out, "ov_q.jpg"), im)
                progress(None, True)
        except Exception:
            pass                                       # to wygoda, nie warunek
    t = threading.Thread(target=quick, daemon=True)
    t.start()
    if not _level0(src, page, pl, out, op, proof, lambda n: progress(n, None), stop):
        return
    t.join()
    _levels(pl, out, stop)
    if stop():
        return
    last = len(pl["levels"]) - 1
    _save(os.path.join(out, "ov.jpg"), _stitch(pl, out, last).resize((ow, oh), Image.LANCZOS))


def raster_rgb(src: str, proof: bool = False) -> Image.Image:
    """Raster na ekran: CMYK przez profil (osadzony albo FOGRA39); przy symulacji druku RGB
    idzie przez FOGRA39 i z powrotem — tak, jak zobaczy go drukarka."""
    from PIL import ImageCms
    im = Image.open(src)
    im.seek(0)
    if im.mode == "CMYK":
        icc = im.info.get("icc_profile")
        if icc:
            try:
                # z kompensacją punktu czerni — tak samo jak proof_rgb (bez niej obraz CMYK po
                # konwersji wychodził na ekranie jaśniejszy niż symulacja druku tego samego obrazu)
                return ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                                 ImageCms.createProfile("sRGB"), outputMode="RGB",
                                                 renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                                                 flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
            except Exception:
                pass
        return proof_rgb(im)
    rgb = im.convert("RGB")
    if proof:
        rgb = proof_rgb(ImageCms.applyTransform(rgb, _transform("rgb")))
    return rgb


def _build_raster(src, pl, out, proof, progress, stop) -> None:
    im = raster_rgb(src, proof)
    if (im.width, im.height) != (pl["w"], pl["h"]):
        im = im.resize((pl["w"], pl["h"]), Image.LANCZOS)
    for lvl, L in enumerate(pl["levels"]):
        if stop():
            return
        if lvl:
            im = im.resize((L["w"], L["h"]), Image.LANCZOS)
        for ty in range(L["rows"]):
            for tx in range(L["cols"]):
                _save(os.path.join(out, f"L{lvl}_{tx}_{ty}.jpg"),
                      im.crop((tx * TILE, ty * TILE, min(L["w"], tx * TILE + TILE), min(L["h"], ty * TILE + TILE))))
            if lvl == 0:
                progress(ty + 1, None)
    _save(os.path.join(out, "ov.jpg"), im.resize(tuple(pl["ov"]), Image.LANCZOS))
