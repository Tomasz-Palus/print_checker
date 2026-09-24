"""Poprawki pliku — każda to funkcja „plik wejściowy → NOWY plik wyjściowy".

Kolejność = kolejność rozdziałów (ustalenie Tomasza): szablon z wytycznych → spady →
wymiar → kolory → overprint → fonty → spłaszczenie. Wersje są niezmienne, więc żadna
poprawka niczego nie nadpisuje — zapisuje nowy plik pod nową nazwą (jobs.Job.apply).

Każda zwraca słownik: `text` (co zrobiła, po ludzku) i — gdy zmienia geometrię strony —
`map` = {s, dx, dy}: jak punkt poprzedniej strony (mm) przechodzi na nową: p' = s·p + d.
Podgląd kładzie dzięki temu wersje „przed" i „po" dokładnie na sobie.
"""
from __future__ import annotations

import math
import os

import pikepdf
import pymupdf

import frames
import gs

MM = 25.4 / 72.0
ORDER = ["frames", "trim", "resize", "cmyk", "overprint", "outline", "flatten"]


def run(name: str, src: str, dst: str, params: dict, job) -> dict:
    fn = STEPS.get(name)
    if not fn:
        raise ValueError(f"Nieznana poprawka: {name}")
    return fn(src, dst, params or {}, job)


def _fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")


# ----------------------------------------------------------------------------
# szablon z wytycznych
# ----------------------------------------------------------------------------
def step_frames(src, dst, p, job) -> dict:
    """Usuwa szablon z wytycznych — dokładnie te obiekty, które znalazł rozdział. Idzie jako
    PIERWSZA poprawka, na oryginale (inaczej po przycięciu spadów szablon wracał — Tomasz 24.09)."""
    page = int(p.get("page", 0))
    mm = job.original.pages_mm[page]
    r = frames.find(src, page, tuple(mm), p.get("gl_pdf"), p.get("gl_page"))
    if not r["found"]:
        raise ValueError("W pliku nie ma szablonu z wytycznych — nie ma czego usuwać.")
    n = frames.remove(src, dst, page, r["found"])
    return {"text": f"usunięty szablon z wytycznych ({n} {'element' if n == 1 else 'elementy' if n < 5 else 'elementów'})"}


# ----------------------------------------------------------------------------
# spady
# ----------------------------------------------------------------------------
def step_trim(src, dst, p, job) -> dict:
    """Przycięcie strony do formatu NETTO (bez spadów). Format netto z ramek PDF-a (TrimBox,
    potem ArtBox), a bez nich — docelowy wymiar wyśrodkowany na stronie. Zmieniamy tylko ramki
    strony: treść zostaje bit w bit ta sama, a to, co było na spadzie, wychodzi poza stronę."""
    page = int(p.get("page", 0))
    with pikepdf.open(src) as pdf:
        o = pdf.pages[page].obj
        mb = [float(v) for v in (o.get("/MediaBox") or [0, 0, 595, 842])]
        x0, y0, x1, y1 = min(mb[0], mb[2]), min(mb[1], mb[3]), max(mb[0], mb[2]), max(mb[1], mb[3])
        cut, source = None, ""
        for k in ("/TrimBox", "/ArtBox"):
            b = o.get(k)
            if b is not None:
                v = [float(x) for x in b]
                b0, b1, b2, b3 = min(v[0], v[2]), min(v[1], v[3]), max(v[0], v[2]), max(v[1], v[3])
                if (b2 - b0) < (x1 - x0) - 0.5 or (b3 - b1) < (y1 - y0) - 0.5:
                    cut, source = (b0, b1, b2, b3), k.lstrip("/")
                    break
        tw, th = float(p.get("w_mm") or 0) / MM, float(p.get("h_mm") or 0) / MM
        if cut is None and tw and th and (tw < (x1 - x0) - 0.5 or th < (y1 - y0) - 0.5):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            cut, source = (cx - tw / 2, cy - th / 2, cx + tw / 2, cy + th / 2), "wymiaru z wytycznych"
        if cut is None:
            raise ValueError("Ten plik nie ma spadów — nie ma czego przycinać.")
        box = pikepdf.Array([round(v, 4) for v in cut])
        o["/MediaBox"] = o["/CropBox"] = o["/TrimBox"] = box
        for k in ("/BleedBox", "/ArtBox"):
            if k in o:
                del o[k]
        pdf.save(dst)
    bleed = [(cut[0] - x0) * MM, (y1 - cut[3]) * MM, (x1 - cut[2]) * MM, (cut[1] - y0) * MM]   # L, G, P, D
    return {"text": f"spady przycięte: strona {_fmt((x1 - x0) * MM)} × {_fmt((y1 - y0) * MM)} → "
                    f"{_fmt((cut[2] - cut[0]) * MM)} × {_fmt((cut[3] - cut[1]) * MM)} mm (format netto z {source})",
            "map": {"s": 1.0, "dx": -bleed[0], "dy": -bleed[1]}}


# ----------------------------------------------------------------------------
# wymiar
# ----------------------------------------------------------------------------
# Tło na marginesach: KILKA OSTATNICH PIKSELI projektu powielonych na cały margines
# (decyzje Tomasza). Skrajne piksele bywają jaśniejsze (wygładzona krawędź z eksportu) —
# odcinamy je z projektu i tło wchodzi tyle samo POD projekt, żeby nie było jasnego pasa.
EDGE_FILL_PPI = 120.0      # rozdzielczość dołożonego tła NA WYDRUKU
EDGE_TRIM_PX = 3.0         # tyle pikseli wydruku odcinamy przy samej krawędzi
EDGE_FILL_MAX_PX = 30000   # sufit na bok bitmapy paska
MIRROR_SLACK_PT = 1.5      # zakładka komórek odbicia (bez jasnej kreski na styku)
MIRROR_MAX_CELLS = 9


def place_rect(src_w, src_h, tw, th, scale, dx, dy):
    """Gdzie na docelowej stronie ląduje projekt. `scale` względem WŁASNEGO rozmiaru projektu
    (1 = bez zmiany), dx/dy = przesunięcie środka projektu od środka formatu (pt; w prawo /
    w dół dodatnie). Zakres: aż krawędź projektu dotknie PRZECIWNEJ krawędzi formatu (Tomasz
    24.09 — wcześniej ruch był ograniczony do wolnego miejsca). Proporcje się nie zmieniają."""
    z = max(1e-6, float(scale))
    pw, ph = src_w * z, src_h * z
    rx, ry = (tw + pw) / 2, (th + ph) / 2
    dx, dy = max(-rx, min(rx, float(dx))), max(-ry, min(ry, float(dy)))
    return (tw - pw) / 2 + dx, (th - ph) / 2 + dy, pw, ph


def _span(pos, size, total) -> tuple[float, float]:
    """Ile projektu wypada POZA format (przycięte) i ile formatu zostaje PUSTE — w jednej osi."""
    vis = max(0.0, min(pos + size, total) - max(pos, 0.0))
    return size - vis, total - vis


def _px_pt(n_px: float, k: float) -> float:
    """n pikseli wydruku (przy EDGE_FILL_PPI) w punktach PLIKU (plik 1:10 = k = 10)."""
    return n_px / EDGE_FILL_PPI * 25.4 / max(k, 0.01) / MM


def _strip(page, clip, w_px, h_px, keep_x, keep_y):
    """Pasek z krawędzi projektu jako bitmapa CMYK — zostawiamy JEDNĄ kolumnę/wiersz przy
    krawędzi i powielamy ją na margines („dilation" jak w Substance): linia dochodząca do
    krawędzi idzie dalej ostra i w pełnym kolorze.

    Bitmapa, a nie wektor: przy rozciągnięciu 3 mm na metr rasteryzator gubił przycięcie
    i na marginesie lądowała treść ze środka. CMYK z zarządzaniem kolorem: CMYK projektu
    przechodzi 1:1, a RGB przez profil (wcześniej pasek RGB miał inny odcień — Tomasz 24.09)."""
    import numpy as np
    zx, zy = max(w_px, 1) / max(clip.width, 1e-6), max(h_px, 1) / max(clip.height, 1e-6)
    pymupdf.TOOLS.set_icc(True)
    try:
        pix = page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(zx, zy), alpha=False, colorspace=pymupdf.csCMYK)
    finally:
        pymupdf.TOOLS.set_icc(False)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if keep_x:
        a = a[:, :1] if keep_x > 0 else a[:, -1:]
    if keep_y:
        a = a[:1] if keep_y > 0 else a[-1:]
    a = np.ascontiguousarray(a)
    return pymupdf.Pixmap(pymupdf.csCMYK, a.shape[1], a.shape[0], a.tobytes(), False)


def _fill_edges(pg, srcpage, sr, left, top, pw, ph, tw, th, k) -> int:
    """Tło na marginesach: pasy (4 boki + 4 narożniki) z krawędzi projektu, wchodzące o `ov`
    pod projekt. Pas jest ZWYKŁYM DeviceCMYK — PyMuPDF dołącza profil ICC, a z nim Ghostscript
    i RIP liczyły go inaczej niż DeviceCMYK obok (różnica koloru — Tomasz 24.09)."""
    L, T, R, B = left, top, left + pw, top + ph
    mL, mT, mR, mB = L > 0.01, T > 0.01, R < tw - 0.01, B < th - 0.01
    if not (mL or mT or mR or mB):
        return 0
    z = pw / max(sr.width, 1e-6)
    ov = min(_px_pt(EDGE_TRIM_PX, k), sr.width * 0.05, sr.height * 0.05) * z
    npx = int(EDGE_TRIM_PX) + 1
    e = min(_px_pt(npx, k), sr.width * 0.05, sr.height * 0.05)
    S = pymupdf.Rect
    cl, cr = S(sr.x0, sr.y0, sr.x0 + e, sr.y1), S(sr.x1 - e, sr.y0, sr.x1, sr.y1)
    ct, cb = S(sr.x0, sr.y0, sr.x1, sr.y0 + e), S(sr.x0, sr.y1 - e, sr.x1, sr.y1)
    co = lambda a, b: S(a.x0, b.y0, a.x1, b.y1)
    along = lambda pt: int(min(EDGE_FILL_MAX_PX, max(32, round(pt * MM * k / 25.4 * EDGE_FILL_PPI))))
    ny, nx = along(ph), along(pw)
    jobs = []
    if mL: jobs.append((S(0, T, L + ov, B), cl, npx, ny, -1, 0))
    if mR: jobs.append((S(R - ov, T, tw, B), cr, npx, ny, +1, 0))
    if mT: jobs.append((S(L, 0, R, T + ov), ct, nx, npx, 0, -1))
    if mB: jobs.append((S(L, B - ov, R, th), cb, nx, npx, 0, +1))
    if mL and mT: jobs.append((S(0, 0, L + ov, T + ov), co(cl, ct), npx, npx, -1, -1))
    if mR and mT: jobs.append((S(R - ov, 0, tw, T + ov), co(cr, ct), npx, npx, +1, -1))
    if mL and mB: jobs.append((S(0, B - ov, L + ov, th), co(cl, cb), npx, npx, -1, +1))
    if mR and mB: jobs.append((S(R - ov, B - ov, tw, th), co(cr, cb), npx, npx, +1, +1))
    n = 0
    for rect, clip, w_px, h_px, kx, ky in jobs:
        if rect.width <= 0.01 or rect.height <= 0.01:
            continue
        # który rząd pikseli paska powielamy: +1 = pierwszy, −1 = ostatni (dla lewego marginesu
        # to ten najgłębszy, tuż za odciętą krawędzią)
        xref = pg.insert_image(rect, pixmap=_strip(srcpage, clip, w_px, h_px, kx, ky), keep_proportion=False)
        if xref:
            pg.parent.xref_set_key(xref, "ColorSpace", "/DeviceCMYK")
        n += 1
    return n


def _mirror(path_in, dst, page_index, left, top, pw, ph, tw, th, ov) -> int:
    """Margines wypełniony ODBICIEM LUSTRZANYM projektu. Projekt leży na stronie jako obiekt
    formy — rysujemy go jeszcze raz z ujemną skalą (pikepdf, bo PyMuPDF nie umie odbić).
    Zostaje wektor. Każda komórka trochę większa (zakładka `s`), inaczej na styku była jasna kreska."""
    L, T = left + ov, top + ov
    w, h = max(pw - 2 * ov, 1e-6), max(ph - 2 * ov, 1e-6)
    Y = th - T - h
    s = max(0.0, min(MIRROR_SLACK_PT, w * 0.02, h * 0.02))
    fx, fy = (w + 2 * s) / w, (h + 2 * s) / h
    with pikepdf.open(path_in) as pdf:
        page = pdf.pages[page_index]
        xo = page.obj.get("/Resources", {}).get("/XObject")
        forms = [k for k, v in dict(xo or {}).items() if str(v.get("/Subtype", "")) == "/Form"]
        if len(forms) != 1:
            pdf.save(dst)
            return 0
        name, ops = forms[0], []
        cl = lambda v: max(-MIRROR_MAX_CELLS, min(MIRROR_MAX_CELLS, v))
        for i in range(cl(-math.ceil(L / w)), cl(math.ceil((tw - L) / w) - 1) + 1):
            for j in range(cl(-math.ceil(T / h)), cl(math.ceil((th - T) / h) - 1) + 1):
                if i == 0 and j == 0:
                    continue
                a, e = (fx, L + i * w - s - fx * L) if i % 2 == 0 else (-fx, L + (i + 1) * w + s + fx * L)
                d, f = (fy, Y - j * h - s - fy * Y) if j % 2 == 0 else (-fy, Y - j * h + h + s + fy * Y)
                ops.append(f"q {L + i * w - s:.3f} {Y - j * h - s:.3f} {w + 2 * s:.3f} {h + 2 * s:.3f} re W n "
                           f"{a:.6f} 0 0 {d:.6f} {e:.3f} {f:.3f} cm {name} Do Q")
        if ops:
            page.contents_add(("\n".join(ops) + "\n").encode("latin-1"))
        pdf.save(dst)
    return len(ops)


def step_resize(src, dst, p, job) -> dict:
    """Nowa strona w formacie z wytycznych; projekt wstawiony jako obiekt formy (wektor zostaje
    wektorem, nic nie jest rasteryzowane), w skali i położeniu z suwaków. Margines można
    wypełnić tłem z krawędzi albo odbiciem lustrzanym."""
    page = int(p.get("page", 0))
    tw, th = float(p["w_mm"]) / MM, float(p["h_mm"]) / MM
    k = float(p.get("k", 1.0))
    scale = float(p.get("scale", 1.0))
    dx, dy = float(p.get("dx_mm", 0.0)) / MM, float(p.get("dy_mm", 0.0)) / MM   # mm pliku → pt
    fill, mode = bool(p.get("fill_edges")), ("mirror" if p.get("fill_mode") == "mirror" else "stretch")
    srcd = pymupdf.open(src)
    tmp = dst + ".r.pdf"
    try:
        sr = srcd[page].rect
        left, top, pw, ph = place_rect(sr.width, sr.height, tw, th, scale, dx, dy)
        # Przy dokładaniu tła skrajne piksele projektu są USUWANE (wstawiamy wycinek bez nich,
        # w to samo miejsce) — decyzja Tomasza: jasny pasek z eksportu nie może wejść w tło.
        crop = min(_px_pt(EDGE_TRIM_PX, k), sr.width * 0.02, sr.height * 0.02) if fill else 0.0
        src_rect = pymupdf.Rect(sr.x0 + crop, sr.y0 + crop, sr.x1 - crop, sr.y1 - crop)
        out = pymupdf.open()
        filled = 0
        for i in range(srcd.page_count):           # inne strony przepisujemy bez zmian
            if i != page:
                r = srcd[i].rect
                q = out.new_page(width=r.width, height=r.height)
                q.show_pdf_page(q.rect, srcd, i)
                continue
            pg = out.new_page(width=tw, height=th)
            # najpierw projekt, POTEM tło — pasy wchodzą pod krawędź projektu z wierzchu
            pg.show_pdf_page(pymupdf.Rect(left, top, left + pw, top + ph), srcd, page,
                             clip=src_rect if crop else None)
            if fill and mode == "stretch":
                filled = _fill_edges(pg, srcd[page], src_rect, left, top, pw, ph, tw, th, k)
        out.save(tmp, garbage=3, deflate=True)
        out.close()
    finally:
        srcd.close()
    if fill and mode == "mirror":
        filled = _mirror(tmp, dst, page, left, top, pw, ph, tw, th,
                         min(_px_pt(EDGE_TRIM_PX, k) * pw / max(sr.width, 1e-6), pw * 0.05, ph * 0.05))
        os.remove(tmp)
    else:
        os.replace(tmp, dst)
    (cx, gx), (cy, gy) = _span(left, pw, tw), _span(top, ph, th)
    gap, cut = [gx * MM, gy * MM], [cx * MM, cy * MM]
    parts = [f"wymiar {_fmt(sr.width * MM)} × {_fmt(sr.height * MM)} → {_fmt(tw * MM)} × {_fmt(th * MM)} mm, "
             f"projekt w skali {round(scale * 100)} %"]
    if max(cut) > 0.2:
        parts.append(f"przycięte {_fmt(cut[0])} × {_fmt(cut[1])} mm")
    if max(gap) > 0.2:
        parts.append((f"margines {_fmt(gap[0])} × {_fmt(gap[1])} mm wypełniony "
                      + ("odbiciem lustrzanym" if mode == "mirror" else "tłem z krawędzi"))
                     if fill and filled else f"PUSTE PASY {_fmt(gap[0])} × {_fmt(gap[1])} mm")
    return {"text": ", ".join(parts),
            "map": {"s": pw / sr.width, "dx": left * MM, "dy": top * MM}}


# ----------------------------------------------------------------------------
# wspólne dla poprawek przez Ghostscripta
# ----------------------------------------------------------------------------
def _gs_page(src: str, dst: str, page: int, args: list, what: str, timeout: int = 1800):
    """Ghostscript (pdfwrite) przepisuje TYLKO wybraną stronę; wynik wklejamy w kopię pliku
    na jej miejsce. Pozostałe strony i wszystko na poziomie dokumentu (profil kolorystyczny,
    metadane) zostają bit w bit — a Ghostscript nie mieli całego wielostronicowego PDF-a
    (i nie odmawia przez brakujący font na stronie, która i tak nie idzie do druku).
    Zwraca wynik Ghostscripta (log — do sprawdzania fontów zastępczych)."""
    out = dst + ".gs.pdf"
    try:
        r = gs.run(args + [f"-sPageList={page + 1}", "-o", gs.arg_path(out), gs.arg_path(src)], timeout)
        if r.returncode != 0 or not os.path.exists(out):
            # druga próba bez -dSAFER: pliki, które czyta, to nasze kopie profili — bywa,
            # że tylko tak Ghostscript je otwiera (Windows)
            if "-dSAFER" in args:
                r = gs.run([a for a in args if a != "-dSAFER"]
                           + [f"-sPageList={page + 1}", "-o", gs.arg_path(out), gs.arg_path(src)], timeout)
            if r.returncode != 0 or not os.path.exists(out):
                raise ValueError(f"Ghostscript nie dał rady ({what}). Komunikat: {gs.log_of(r)}")
        return r, out
    except Exception:
        _rm(out)
        raise


def _splice(base: str, page: int, new_page_pdf: str, dst: str, doc_fn=None) -> None:
    """Kopia `base` z podmienioną stroną `page` (pierwsza strona z `new_page_pdf`).
    `doc_fn(pdf)` — zmiana na poziomie dokumentu (np. profil kolorystyczny)."""
    with pikepdf.open(base) as pdf, pikepdf.open(new_page_pdf) as np_:
        pdf.pages[page] = np_.pages[0]
        if doc_fn:
            doc_fn(pdf)
        pdf.save(dst)


def _rm(*paths) -> None:
    for p in paths:
        if p:
            try:
                os.remove(p)
            except OSError:
                pass


def _page_facts(job, src: str, page: int) -> dict:
    """Fakty o stronie (analiza) — z pamięci, a gdy ich nie ma, liczymy."""
    import analyze
    v = next((v for v in job.versions if v.path == src), None)
    cache = job.analysis.get(v.id, {}) if v else {}
    if page in cache:
        return cache[page]
    return analyze.analyze(src, page)


# ----------------------------------------------------------------------------
# kolory: CMYK i profil kolorystyczny
# ----------------------------------------------------------------------------
PROFILE_KEEP, PROFILE_NONE, PROFILE_FOGRA = "keep", "none", "fogra39"


def file_icc(src: str) -> tuple[bytes | None, str]:
    """Profil CMYK zapisany W PLIKU: najpierw deklaracja (OutputIntent), potem pierwszy
    osadzony profil CMYK. Do wyboru „zostaw profil z pliku": plik bywa przygotowany pod
    konkretną maszynę (u nas najczęściej ISO Coated v2) — przestawianie go na inny profil
    tej samej normy to zmiana bez powodu (prośba Tomasza)."""
    try:
        with pikepdf.open(src) as pdf:
            for oi in pdf.Root.get("/OutputIntents") or []:
                p = oi.get("/DestOutputProfile")
                if p is not None and int(p.get("/N", 4)) == 4:
                    return bytes(p.read_bytes()), str(oi.get("/OutputConditionIdentifier") or oi.get("/Info") or "")
            for obj in pdf.objects:
                try:
                    if (isinstance(obj, pikepdf.Array) and len(obj) > 1 and str(obj[0]) == "/ICCBased"
                            and int(obj[1].get("/N", 0)) == 4):
                        return bytes(obj[1].read_bytes()), ""
                except Exception:
                    continue
    except Exception:
        pass
    return None, ""


def icc_name(data: bytes, fallback: str = "") -> str:
    try:
        import io
        from PIL import ImageCms
        return ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(data))).strip() or fallback
    except Exception:
        return fallback or "profil z pliku"


def set_intent(pdf: pikepdf.Pdf, data: bytes | None, name: str = "") -> None:
    """Deklaracja profilu (OutputIntent). Nie zmienia ani jednego koloru — mówi tylko, na jaką
    maszynę plik jest przygotowany. `data=None` usuwa deklarację."""
    if data is None:
        if "/OutputIntents" in pdf.Root:
            del pdf.Root["/OutputIntents"]
        return
    st = pdf.make_stream(data)
    st["/N"] = 4
    oi = pdf.make_indirect(pikepdf.Dictionary(
        Type=pikepdf.Name.OutputIntent, S=pikepdf.Name("/GTS_PDFX"),
        OutputConditionIdentifier=pikepdf.String(name), OutputCondition=pikepdf.String(name),
        Info=pikepdf.String(name), RegistryName=pikepdf.String("http://www.color.org"),
        DestOutputProfile=pdf.make_indirect(st)))
    pdf.Root["/OutputIntents"] = pdf.make_indirect(pikepdf.Array([oi]))


def _rename_registration(src: str, dst: str) -> int:
    """Kolor „Registration" (separacja /All = 100 % wszystkich farb) dostaje zwykłą nazwę.

    BŁĄD GHOSTSCRIPTA (Tomasz 24.09): przy konwersji na CMYK zamienia /All na SAM CYJAN —
    czarne pole „Registration" robiło się błękitne. Pod inną nazwą Ghostscript liczy je jak
    każdy kolor dodatkowy, przez przestrzeń alternatywną: 100/100/100/100, czyli to, co
    wydrukuje maszyna. Zwraca liczbę zmian; 0 = pliku `dst` nie ma."""
    import pdfutil
    n = 0

    def fix(a):
        nonlocal n
        try:
            if not isinstance(a, pikepdf.Array) or len(a) < 4:
                return
            if str(a[0]) == "/Separation" and str(a[1]) == "/All":
                a[1] = pikepdf.Name("/Registration_All")
                n += 1
            elif str(a[0]) == "/DeviceN" and isinstance(a[1], pikepdf.Array):
                for i, nm in enumerate(list(a[1])):
                    if str(nm) == "/All":
                        a[1][i] = pikepdf.Name("/Registration_All")
                        n += 1
        except Exception:
            pass

    with pikepdf.open(src) as pdf:
        for o in pdf.objects:
            fix(o)
        for d in pdfutil.all_dicts(pdf):
            try:
                for k in list(d.keys()):
                    fix(d[k])
            except Exception:
                continue
        if n:
            pdf.save(dst)
    return n


def color_need(facts: dict) -> dict:
    """Co w kolorach strony trzeba przeliczyć: {rgb, lab, spots:[nazwy], other}. Gray obok
    CMYK nie jest problemem (drukuje się czarną farbą)."""
    c = facts.get("color") or {}
    fam = set(c.get("families") or {})
    spots = [s["name"] for s in c.get("spots") or []]
    return {"rgb": "RGB" in fam or any("RGB" in f for f in fam), "lab": "Lab" in fam,
            "spots": spots, "other": bool(fam & {"Unknown", "Indexed"}),
            "spot_alt_ok": all((s.get("alt") or "CMYK") in ("CMYK", "Gray") for s in c.get("spots") or [])}


def step_cmyk(src, dst, p, job) -> dict:
    """Wszystko na CMYK, przez profil ICC — tak, jak robi to Photoshop przy „Konwertuj do
    profilu": źródło sRGB, cel Coated FOGRA39 (albo profil z pliku), intencja relatywna
    kolorymetryczna z kompensacją punktu czerni. Bez jawnych profili Ghostscript bierze swój
    domyślny CMYK i kolory wychodzą inne, bardziej matowe.

    Kolory dodatkowe (PANTONE, Registration…) idą przez swoją przestrzeń alternatywną — tak jak
    „konwersja na farby procesowe" w Photoshopie."""
    page = int(p.get("page", 0))
    profile = p.get("profile") or PROFILE_FOGRA
    if __import__("render").is_raster(src):
        return _raster_cmyk(src, dst, profile)
    data, name = (file_icc(src) if profile == PROFILE_KEEP else (None, ""))
    if profile == PROFILE_KEEP and not data:
        profile = PROFILE_FOGRA                     # plik nie ma profilu — bierzemy nasz
    if data is None:
        with open(gs.fogra(), "rb") as fh:
            data = fh.read()
        name = gs.FOGRA_NAME
    else:
        name = name or icc_name(data)
    work = os.path.dirname(os.path.abspath(dst))
    icc_path = os.path.join(work, "icc_cel.icc")
    with open(icc_path, "wb") as fh:
        fh.write(data)

    need = color_need(_page_facts(job, src, page))
    # SZYBKA ŚCIEŻKA: strona jest już w CMYK-u, są tylko kolory dodatkowe z alternatywą CMYK.
    # Wartości CMYK zostawiamy w spokoju — przeliczanie CMYK-u na CMYK ODDALA plik od
    # Photoshopa (zmierzone: średnio 9/255 zamiast 1,3/255, bo Ghostscript przebudowuje
    # separacje) i trwa 40 s zamiast 3 s. Spoty liczy przez alternatywę (tint 1,0 dla
    # 0,15/0,35/0,85/0,05 daje 0,149/0,349/0,847/0,047 — jak Photoshop).
    fast = not need["rgb"] and not need["lab"] and not need["other"] and need["spot_alt_ok"]
    if fast and not need["spots"]:
        raise ValueError("Kolory na tej stronie są już w CMYK-u — nie ma czego zamieniać.")
    common = ["-dSAFER", "-sDEVICE=pdfwrite", "-dPreserveSeparation=false", "-dPreserveDeviceN=false",
              "-dProcessColorModel=/DeviceCMYK"]
    if fast:
        args = common + ["-dColorConversionStrategy=/LeaveColorUnchanged", *gs.PDFWRITE_KEEP_IMAGES]
    else:
        srgb = gs.safe_icc(gs.srgb(), work)
        args = ["--permit-file-read=" + srgb, *gs.cmyk_target_args(icc_path, work)] + common + [
            "-dColorConversionStrategy=/CMYK", "-sDefaultRGBProfile=" + srgb,
            "-dRenderIntent=1", "-dBlackPtComp=1",       # relatywna kolorymetryczna + BPC
            *gs.PDFWRITE_KEEP_IMAGES,
            "-dPassThroughJPEGImages=false"]             # obrazy też mają przejść na CMYK (bez strat)
    reg = dst + ".reg.pdf"
    gs_src = reg if _rename_registration(src, reg) else src
    try:
        r, out = _gs_page(gs_src, dst, page, args, "zamiana kolorów na CMYK", 900)
    finally:
        _rm(reg if gs_src != src else None)
    try:
        if profile == PROFILE_KEEP:
            doc_fn = None                              # deklaracja z pliku zostaje, jaka była
        elif profile == PROFILE_NONE:
            doc_fn = lambda pdf: set_intent(pdf, None)
        else:
            doc_fn = lambda pdf: set_intent(pdf, data, name)
        _splice(src, page, out, dst, doc_fn)
    finally:
        _rm(out)
    if fast:
        text = ("kolory dodatkowe (" + ", ".join(need["spots"][:4]) + ") przeliczone na CMYK; "
                "reszta była już w CMYK-u, więc wartości zostały nietknięte")
    else:
        text = f"kolory zamienione na CMYK przez profil {name}"
    text += {PROFILE_KEEP: "; profil kolorystyczny z pliku zostaje",
             PROFILE_NONE: "; plik bez deklaracji profilu"}.get(profile, f"; profil pliku: {name}")
    return {"text": text}


def _raster_cmyk(src: str, dst: str, profile: str) -> dict:
    """Obraz RGB → CMYK (ImageCms: profil osadzony albo sRGB → FOGRA39, relatywna + BPC).
    JPEG zostaje JPEG-iem (jakość 95), reszta idzie do TIFF-a bez strat. Przezroczystość
    kładziemy na białym — tak wyjdzie na papierze. DPI zostaje."""
    import io
    from PIL import Image, ImageCms
    im = Image.open(src)
    im.seek(0)
    info = dict(im.info)
    if im.mode == "CMYK":
        raise ValueError("Obraz jest już w CMYK-u.")
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in info:
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        rgb = bg
    else:
        rgb = im.convert("RGB")
    src_prof = ImageCms.createProfile("sRGB")
    if info.get("icc_profile"):
        try:
            p = ImageCms.ImageCmsProfile(io.BytesIO(info["icc_profile"]))
            if p.profile.xcolor_space.strip().upper() == "RGB":
                src_prof = p
        except Exception:
            pass
    with open(gs.fogra(), "rb") as fh:
        fog = fh.read()
    cmyk = ImageCms.profileToProfile(rgb, src_prof, ImageCms.ImageCmsProfile(io.BytesIO(fog)), outputMode="CMYK",
                                     renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
                                     flags=ImageCms.Flags.BLACKPOINTCOMPENSATION)
    kw = {"icc_profile": fog} if profile != PROFILE_NONE else {}
    if info.get("dpi"):
        kw["dpi"] = info["dpi"]
    ext = os.path.splitext(src)[1].lower()
    if ext in (".jpg", ".jpeg"):
        out = os.path.splitext(dst)[0] + ".jpg"
        cmyk.save(out, "JPEG", quality=95, subsampling=0, **kw)
    else:
        out = os.path.splitext(dst)[0] + ".tif"
        cmyk.save(out, "TIFF", compression="tiff_lzw", **kw)
    return {"text": f"obraz zamieniony na CMYK przez profil {gs.FOGRA_NAME}"
                    + (" (zapisany jako TIFF — bez strat)" if out.endswith(".tif") else ""),
            "path": out}


# ----------------------------------------------------------------------------
# overprint
# ----------------------------------------------------------------------------
def step_overprint(src, dst, p, job) -> dict:
    """Wyłącza overprint (/OP i /op = false) we wszystkich stanach graficznych.

    Overprint każe farbie kłaść się NA tle zamiast je wybijać — czerwone „D" na czarnym tle
    wychodzi prawie czarne, choć projektant widział czerwone. Wytyczne Adsystem overprintu
    zabraniają, więc naprawa = wydrukować to, co widać w projekcie. /OPM zostaje — przy
    OP = false nie ma znaczenia."""
    import pdfutil
    n = 0
    with pikepdf.open(src) as pdf:
        for d in pdfutil.all_dicts(pdf):
            try:
                if any(k in d and bool(d[k]) for k in ("/OP", "/op")):
                    d["/OP"] = False
                    d["/op"] = False
                    n += 1
            except Exception:
                continue
        if not n:
            raise ValueError("Plik nie używa overprintu — nie ma czego wyłączać.")
        pdf.save(dst)
    return {"text": f"overprint wyłączony ({n} {'miejsce' if n == 1 else 'miejsca' if n < 5 else 'miejsc'} w pliku)"}


# ----------------------------------------------------------------------------
# fonty (krzywe) — wspólne ze spłaszczeniem
# ----------------------------------------------------------------------------
def _prepare_fonts(src: str, dst: str) -> tuple[str, dict]:
    """Nieosadzone fonty PRZED Ghostscriptem (fontfix.py): tekst niewidoczny pomijamy,
    widoczny — pobieramy prawdziwy font z Google Fonts i osadzamy. Czego się nie da, Ghostscript
    poszuka jeszcze w fontach systemu. Kroju zastępczego nie dopuszczamy (decyzja Tomasza).
    Zwraca (plik dla Ghostscripta, raport)."""
    try:
        import fontfix
        if not fontfix.missing(src):
            return src, {}
        tmp = dst + ".fonts.pdf"
        r = fontfix.embed(src, tmp)
    except Exception as e:                      # np. brak fontTools — zostaje ścieżka systemowa
        print(f"[adChecker] fontfix: {type(e).__name__}: {e}")
        return src, {}
    return (tmp if r.get("osadzone") else src), r


def _font_refusal(what: str, names: list, info: dict) -> str:
    """Komunikat dla osoby nietechnicznej: czego brakuje i o co poprosić klienta."""
    why = {n.split("+")[-1]: p for n, p in (info or {}).get("brak", [])}
    det = "; ".join(f"{n}: {why[n]}" for n in (x.split("+")[-1] for x in names) if n in why)
    return (f"Nie {what}: w pliku brakuje fontu {', '.join(n.split('+')[-1] for n in names[:6])}. "
            "Nie ma go w pliku (nie jest osadzony), w systemie ani w Google Fonts, a krój zastępczy "
            "zmieniłby tekst." + (f" ({det})" if det else "")
            + " Poproś klienta o PDF z osadzonymi fontami — w Illustratorze / InDesignie: Zapisz jako / "
              "Eksportuj → Adobe PDF, ustawienie „Wysoka jakość druku”.")


def _page_fonts(path: str, page: int) -> list[str]:
    d = pymupdf.open(path)
    try:
        return sorted({f[3] for f in d[page].get_fonts(full=True)})
    finally:
        d.close()


def step_outline(src, dst, p, job) -> dict:
    """Tekst zamieniony na krzywe (Ghostscript, `-dNoOutputFonts`).

    Kształty liter biorą się z fontu OSADZONEGO W PLIKU, więc wynik jest identyczny z
    oryginałem także wtedy, gdy nikt nie ma tego fontu zainstalowanego (zmierzone: różnica
    0,002–0,07 % pikseli, tyle co wygładzanie krawędzi liter). Font NIEOSADZONY: najpierw
    Google Fonts, potem fonty systemu; krój zastępczy = odmowa (utrwalilibyśmy przypadkowy font)."""
    page = int(p.get("page", 0))
    before = _page_fonts(src, page)
    if not before:
        raise ValueError("Na tej stronie nie ma tekstu w fontach — nie ma czego zamieniać.")
    gs_src, finfo = _prepare_fonts(src, dst)
    args = ["-dSAFER", "-sDEVICE=pdfwrite", "-dNoOutputFonts", *gs.font_path_args(),
            *gs.PDFWRITE_KEEP_IMAGES,                   # obrazy zostają, jakie są
            "-dColorConversionStrategy=/LeaveColorUnchanged"]
    try:
        r, out = _gs_page(gs_src, dst, page, args, "zamiana fontów na krzywe")
    finally:
        _rm(gs_src if gs_src != src else None)
    try:
        subs = gs.substituted((r.stdout or "") + "\n" + (r.stderr or ""), finfo.get("niewidoczne", []))
        if subs:
            raise ValueError(_font_refusal("zamieniam na krzywe", subs, finfo))
        left = _page_fonts(out, 0)
        if left:
            raise ValueError("Po zamianie na stronie dalej są fonty (" + ", ".join(left[:4])
                             + ") — nie zapisuję, żeby nie zrobić gorzej.")
        _splice(src, page, out, dst)
    finally:
        _rm(out)
    names = [n.split("+")[-1] for n in before]
    text = f"tekst zamieniony na krzywe ({len(names)} {'font' if len(names) == 1 else 'fonty' if len(names) < 5 else 'fontów'}: {', '.join(names[:4])})"
    got = [n.split("+")[-1] for n, _ in finfo.get("osadzone", [])]
    if got:
        text += f"; {', '.join(got[:4])} nie był(y) osadzone — pobrane z Google Fonts"
    if finfo.get("niewidoczne"):
        text += f"; {', '.join(finfo['niewidoczne'][:4])} — tekst niewidoczny, nie drukuje się"
    return {"text": text}


# ----------------------------------------------------------------------------
# spłaszczenie
# ----------------------------------------------------------------------------
FLATTEN_MAX_MPX = 400      # sufit; adWall Vario Prosta 600 w 1:10 przy 120 ppi to 319 Mpx (8 s)
FLATTEN_JPEG_Q = 90        # zmierzone: q95/q98 poprawiają wygląd o 0,1/255, a plik rośnie o 40–90 %


def flatten_ppi_for(long_mm: float) -> int:
    """Rozdzielczość spłaszczenia wg WIELKOŚCI WYDRUKU. 120 ppi to próg dla wielkiego formatu
    oglądanego z kilku metrów, ale na tabliczce 60 cm robi schodki na literach (Tomasz:
    „po zripowaniu litery są poszarpane"). Zmierzone na wydruku 616 mm: 120 ppi — schodki,
    200 — ledwo widoczne, 300 — jak wektor."""
    return 300 if long_mm <= 800 else 200 if long_mm <= 1500 else 150 if long_mm <= 3000 else 120


def flatten_plan(w_pt: float, h_pt: float, k: float) -> dict:
    """Ile pikseli wyjdzie po spłaszczeniu: ppi na WYDRUKU (plik 1:10 → render 10× gęstszy)."""
    k = max(0.01, float(k))
    ppi = flatten_ppi_for(max(w_pt, h_pt) * MM * k)
    dpi = ppi * k
    mpx = (w_pt / 72 * dpi) * (h_pt / 72 * dpi) / 1e6
    cut = mpx > FLATTEN_MAX_MPX
    if cut:
        dpi *= (FLATTEN_MAX_MPX / mpx) ** 0.5
    return {"ppi": round(dpi / k), "want_ppi": ppi, "dpi": dpi, "cut": cut,
            "px": [round(w_pt / 72 * dpi), round(h_pt / 72 * dpi)]}


def step_flatten(src, dst, p, job) -> dict:
    """Cała strona zamieniona na JEDEN obraz CMYK — „spłaszczenie" jak w Photoshopie.

    Żywa przezroczystość (maski, cienie, tryby mieszania) bywa spłaszczana dopiero w RIP-ie
    i tam, gdzie spotyka kolor dodatkowy albo overprint, potrafi zostawić szew, jasną obwódkę
    albo przesunięcie koloru. Spłaszczona u nas — wiemy dokładnie, co pójdzie na maszynę.
    Rysuje Ghostscript prosto do CMYK-owego JPEG-a (overprint policzony jak na maszynie),
    profilem z pliku albo FOGRA39. Tekst i wektory dostają rozdzielczość rastra."""
    import io
    import pdfutil
    from PIL import Image
    page = int(p.get("page", 0))
    d = pymupdf.open(src)
    try:
        rect = d[page].rect
    finally:
        d.close()
    w_pt, h_pt = float(rect.width), float(rect.height)
    plan = flatten_plan(w_pt, h_pt, float(p.get("k", 1.0)))
    data, name = file_icc(src)
    work = os.path.dirname(os.path.abspath(dst))
    if data:
        icc_path = os.path.join(work, "icc_splaszcz.icc")
        with open(icc_path, "wb") as fh:
            fh.write(data)
        icc, name = gs.arg_path(icc_path), (name or icc_name(data))
    else:
        icc, name = gs.safe_icc(gs.fogra(), work), gs.FOGRA_NAME
        with open(gs.fogra(), "rb") as fh:
            data = fh.read()
    op = pdfutil.uses_overprint(src)
    gs_src, finfo = _prepare_fonts(src, dst)
    jpg = dst + ".jpg"
    args = ["-dSAFER", "--permit-file-read=" + icc, *gs.font_path_args(),
            "-sOutputICCProfile=" + icc, "-sDefaultCMYKProfile=" + icc,
            "-sDEVICE=jpegcmyk", f"-r{plan['dpi']:.4f}", f"-dJPEGQ={FLATTEN_JPEG_Q}", "-dUseCropBox",
            f"-dFirstPage={page + 1}", f"-dLastPage={page + 1}", *gs.SPEED[:1],
            # wygładzanie bezpieczne przy overprincie (błąd Ghostscripta — gs.aa_args)
            *gs.aa_args(op, plan["px"][0], plan["px"][1], 4),
            "-dOverprint=/simulate",                  # na urządzeniu CMYK to nie symulacja, tylko druk
            "-sOutputFile=" + gs.arg_path(jpg),
            # bez „fill adjust": Ghostscript domyślnie pogrubia każdy kształt o ułamek piksela —
            # przy 150 ppi to było widać: tekst o 3,6 % grubszy, krawędzie 2× dalej od ideału
            # (Tomasz 24.09: „napisy robią się grubsze i mniej wyraźne"). Bez niego 99,9 %.
            *gs.PREVIEW_PRE, gs.arg_path(gs_src)]
    try:
        r = gs.run(args, 1800)
    finally:
        _rm(gs_src if gs_src != src else None)
    try:
        if r.returncode != 0 or not os.path.exists(jpg):
            raise ValueError("Ghostscript nie dał rady spłaszczyć strony. Komunikat: " + gs.log_of(r))
        subs = gs.substituted((r.stdout or "") + "\n" + (r.stderr or ""), finfo.get("niewidoczne", []))
        if subs:
            raise ValueError(_font_refusal("spłaszczam", subs, finfo))
        with open(jpg, "rb") as fh:
            raw = fh.read()
        px = Image.open(io.BytesIO(raw)).size
        with pikepdf.open(src) as pdf:
            ic = pdf.make_stream(data)
            ic["/N"] = 4
            img = pikepdf.Stream(pdf, raw)
            img["/Type"], img["/Subtype"] = pikepdf.Name("/XObject"), pikepdf.Name("/Image")
            img["/Width"], img["/Height"], img["/BitsPerComponent"] = px[0], px[1], 8
            img["/ColorSpace"] = pikepdf.Array([pikepdf.Name("/ICCBased"), pdf.make_indirect(ic)])
            img["/Filter"] = pikepdf.Name("/DCTDecode")
            # CMYK-owy JPEG z Ghostscripta jest w konwencji Adobe (wartości odwrócone) —
            # bez /Decode strona wychodzi jak negatyw
            img["/Decode"] = pikepdf.Array([1, 0, 1, 0, 1, 0, 1, 0])
            new = pikepdf.Dictionary(
                Type=pikepdf.Name("/Page"), MediaBox=[0, 0, w_pt, h_pt],
                Resources=pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=img)),
                Contents=pdf.make_stream(f"q {w_pt:.3f} 0 0 {h_pt:.3f} 0 0 cm /Im0 Do Q".encode()))
            pdf.pages[page] = pikepdf.Page(pdf.make_indirect(new))
            pdf.save(dst)
    finally:
        _rm(jpg)
    text = (f"strona spłaszczona do jednego obrazu CMYK {px[0]} × {px[1]} px "
            f"({plan['ppi']} ppi na wydruku), profil {name}")
    if plan["cut"]:
        text += (f" — strona jest tak duża, że zamiast {plan['want_ppi']} ppi wyszło {plan['ppi']} ppi "
                 f"(sufit {FLATTEN_MAX_MPX} megapikseli)")
    return {"text": text}


STEPS = {"frames": step_frames, "trim": step_trim, "resize": step_resize, "cmyk": step_cmyk,
         "overprint": step_overprint, "outline": step_outline, "flatten": step_flatten}

