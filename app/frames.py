"""Szablon z wytycznych zostawiony w pliku klienta.

Częsty błąd: projektant robi projekt na stronie wytycznych i zapomina wyłączyć warstwę
z szablonem — na wydruk idzie cyjanowa ramka formatu, czerwona ramka obszaru bezpiecznego
i napisy. Mamy PDF wytycznych tego produktu, więc nie zgadujemy: porównujemy CAŁY szablon
(ramki, ich kolory i wzajemne położenie) z tym, co jest w pliku (ustalenie Tomasza 24.09).
Kilka mm różnicy (starsza wersja szablonu, pokrewny produkt) nie przeszkadza.
"""
from __future__ import annotations

import collections
import io
from decimal import Decimal
import math
import os

import pikepdf

MM = 25.4 / 72.0

# Kolory, którymi Adsystem rysuje wytyczne (100 % cyanu oraz 0/94,7/91,2/0), na ekranie:
TEMPLATE_COLORS = [(0.0, 1.0, 1.0), (1.0, 0.05, 0.09)]
COLOR_TOL = 0.10          # różnica składowej RGB (0–1), żeby uznać kolor za ten sam
MATCH_TOL = 0.006         # odchyłka krawędzi: 0,6 % większego boku szablonu (12 mm na 2 m)
MATCH_MIN = 0.6           # jaka część szablonu (ważona obwodem linii) musi się znaleźć w pliku


# ----------------------------------------------------------------------------
# odczyt kształtów i napisów ze strony
# ----------------------------------------------------------------------------
def _mul(m, n):
    return [m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3],
            m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3],
            m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5]]


def _apply(m, x, y):
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def _cmyk_rgb(c, m, y, k):
    return tuple(max(0.0, 1 - min(1.0, v + k)) for v in (c, m, y))


class _Walker:
    """Chodzi po treści strony jak rasteryzator (q/Q/cm, kolor) i zbiera narysowane kształty
    oraz napisy. Własny przebieg, bo `get_drawings()` z PyMuPDF nie wchodzi do obiektów formy —
    a tam siedzi szablon wstawiony jako osadzona strona. Zapamiętuje adres każdego kształtu
    (strumień + numery operatorów), żeby dało się go usunąć."""

    def __init__(self):
        self.shapes, self.texts = [], []

    def run(self, container, resources, ctm, depth=0, owner=None):
        if depth > 8:
            return
        try:
            ops = list(pikepdf.parse_content_stream(container))
        except Exception:
            return
        stack, fill, stroke, width = [], (0.0,) * 3, (0.0,) * 3, 1.0
        box, nseg, first = None, 0, None
        t_start, t_txt, t_pos, t_size, t_scale = None, [], None, 12.0, 1.0

        def add(x, y):
            nonlocal box
            px, py = _apply(ctm, x, y)
            box = [px, py, px, py] if box is None else [min(box[0], px), min(box[1], py), max(box[2], px), max(box[3], py)]

        def color(nums):
            return (tuple(nums[:3]) if len(nums) == 3 else _cmyk_rgb(*nums[:4]) if len(nums) == 4
                    else (1 - nums[0],) * 3 if len(nums) == 1 else None)

        for i, (operands, op) in enumerate(ops):
            o = str(op)
            try:
                if o == "q":
                    stack.append((ctm, fill, stroke, width))
                elif o == "Q":
                    if stack:
                        ctm, fill, stroke, width = stack.pop()
                elif o == "cm":
                    ctm = _mul([float(x) for x in operands], ctm)
                elif o == "w":
                    width = float(operands[0])
                elif o in ("g", "G", "rg", "RG", "k", "K", "sc", "scn", "SC", "SCN"):
                    nums = [float(x) for x in operands if isinstance(x, (int, float, Decimal))]
                    if o in ("g", "G"):
                        v = (float(operands[0]),) * 3
                    elif o in ("k", "K"):
                        v = _cmyk_rgb(*[float(x) for x in operands[:4]])
                    elif o in ("rg", "RG"):
                        v = tuple(float(x) for x in operands[:3])
                    else:
                        v = color(nums)
                    if v:
                        if o[0].islower():
                            fill = v
                        else:
                            stroke = v
                elif o == "re":
                    first = i if first is None else first
                    x, y, w, h = [float(v) for v in operands]
                    for cx, cy in ((x, y), (x + w, y), (x + w, y + h), (x, y + h)):
                        add(cx, cy)
                    nseg += 4
                elif o in ("m", "l"):
                    first = i if first is None else first
                    add(float(operands[0]), float(operands[1]))
                    nseg += 1
                elif o in ("c", "v", "y"):
                    first = i if first is None else first
                    vals = [float(v) for v in operands]
                    for j in range(0, len(vals) - 1, 2):
                        add(vals[j], vals[j + 1])
                    nseg += 1
                elif o in ("f", "F", "f*", "B", "B*", "b", "b*", "S", "s", "n"):
                    if box is not None and o != "n":
                        filled = o not in ("S", "s")
                        stroked = o in ("S", "s", "B", "B*", "b", "b*")
                        self.shapes.append({"x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3],
                                            "fill": fill if filled else None, "stroke": stroke if stroked else None,
                                            "segments": nseg, "owner": owner,
                                            "index": first if first is not None else i, "end": i})
                    box, nseg, first = None, 0, None
                elif o == "BT":
                    t_start, t_txt, t_pos = i, [], None
                elif o == "Tf":
                    t_size = float(operands[1])
                elif o in ("Tm", "Td", "TD"):
                    v = [float(x) for x in operands]
                    if o == "Tm" and len(v) >= 6:
                        p0 = _apply(ctm, v[4], v[5])
                        t_scale = math.hypot(v[0], v[1]) or 1.0
                    else:
                        p0 = _apply(ctm, v[0], v[1]) if len(v) >= 2 else None
                    t_pos = t_pos or p0
                elif o in ("Tj", "TJ", "'", '"'):
                    for x in operands:
                        _text(x, t_txt)
                elif o == "ET":
                    txt = "".join(t_txt).strip()
                    if t_start is not None and txt:
                        self.texts.append({"tekst": txt, "x": (t_pos or (0, 0))[0], "y": (t_pos or (0, 0))[1],
                                           "size_pt": t_size * t_scale * math.hypot(ctm[0], ctm[1]),
                                           "owner": owner, "index": t_start, "end": i})
                    t_start, t_txt, t_pos = None, [], None
                elif o == "Do":
                    xod = resources.get("/XObject") if resources is not None else None
                    if xod is None or operands[0] not in xod:
                        continue
                    xo = xod[operands[0]]
                    if str(xo.get("/Subtype", "")) != "/Form":
                        continue
                    m = xo.get("/Matrix")
                    c2 = _mul([float(v) for v in m], ctm) if m is not None else ctm
                    oid = list(xo.objgen) if tuple(xo.objgen) != (0, 0) else owner
                    self.run(xo, xo.get("/Resources") or resources, c2, depth + 1, owner=oid)
            except Exception:
                continue


def _text(x, out):
    """Tekst z Tj/TJ. Tablice (TJ) da się iterować, łańcuchy rzucają TypeError — i tylko tak
    da się je odróżnić (`bytes(tablica)` zwraca puste bajty zamiast błędu)."""
    try:
        for y in x:
            _text(y, out)
        return
    except TypeError:
        pass
    try:
        b = bytes(x)
        if b:
            out.append(b.decode("latin1", "replace"))
    except Exception:
        pass


def shapes(path: str, page_index: int, page_mm: tuple | None = None) -> tuple[list, list]:
    """Kształty i napisy strony w mm WYDRUKU (od lewego górnego rogu). `page_mm` mówi, ile
    mm wydruku przypada na stronę (skala 1:10 przelicza się sama); bez niego — mm pliku."""
    with pikepdf.open(path) as pdf:
        page = pdf.pages[page_index]
        mb = [float(v) for v in (page.obj.get("/MediaBox") or [0, 0, 595, 842])]
        w_pt, h_pt = abs(mb[2] - mb[0]), abs(mb[3] - mb[1])
        wk = _Walker()
        wk.run(page, page.obj.get("/Resources"), [1, 0, 0, 1, -min(mb[0], mb[2]), -min(mb[1], mb[3])])
    sx = page_mm[0] / w_pt if page_mm else MM
    sy = page_mm[1] / h_pt if page_mm else MM
    out = []
    for r in wk.shapes:
        w, h = (r["x1"] - r["x0"]) * sx, (r["y1"] - r["y0"]) * sy
        if w >= 1 and h >= 1:
            out.append({**r, "x": r["x0"] * sx, "y": (h_pt - r["y1"]) * sy, "w": w, "h": h})
    txt = [{**t, "x": t["x"] * sx, "y": (h_pt - t["y"]) * sy, "size_mm": t["size_pt"] * sx} for t in wk.texts]
    return out, txt


def _same_color(a, b) -> bool:
    return bool(a and b) and all(abs(x - y) <= COLOR_TOL for x, y in zip(a, b))


def color_class(z: dict):
    """Który kolor wytycznych (0 = cyjan, 1 = czerwień) — albo None."""
    for i, c in enumerate(TEMPLATE_COLORS):
        if _same_color(z.get("stroke"), c) or _same_color(z.get("fill"), c):
            return i
    return None


def _edges(z):
    return z["x"], z["y"], z["x"] + z["w"], z["y"] + z["h"]


# ----------------------------------------------------------------------------
# porównanie z szablonem
# ----------------------------------------------------------------------------
def match_template(mine, mine_txt, tpl, tpl_txt) -> dict:
    """Szuka szablonu z wytycznych jako CAŁOŚCI (wszystko w mm wydruku).

    Każda para (linia w pliku, linia w szablonie) tego samego koloru i proporcji wyznacza,
    gdzie cały szablon musiałby leżeć (przesunięcie, ewentualnie skala). Dla każdego ułożenia
    liczymy, ile linii szablonu faktycznie stoi w pliku — i bierzemy najlepsze."""
    T = [t for t in tpl if color_class(t) is not None and t["w"] >= 5 and t["h"] >= 5]
    if not T:
        return {"known": False}
    F = [f for f in mine if color_class(f) is not None and f["w"] >= 5 and f["h"] >= 5]
    ext = max(max(t["x"] + t["w"] for t in T) - min(t["x"] for t in T),
              max(t["y"] + t["h"] for t in T) - min(t["y"] for t in T))
    perim = lambda z: z["w"] + z["h"]
    total = sum(perim(t) for t in T)
    place = lambda t, s, ox, oy: {"x": s * t["x"] + ox, "y": s * t["y"] + oy, "w": s * t["w"], "h": s * t["h"]}
    best = None
    for f in F:
        for t in T:
            if color_class(f) != color_class(t):
                continue
            sx, sy = f["w"] / t["w"], f["h"] / t["h"]
            s = (sx + sy) / 2
            if abs(sx - sy) > 0.02 * s:
                continue                                   # inne proporcje — to nie ta ramka
            s = 1.0 if abs(s - 1) <= 0.02 else s          # kilka mm różnicy to nie skala
            ox = f["x"] + f["w"] / 2 - s * (t["x"] + t["w"] / 2)
            oy = f["y"] + f["h"] / 2 - s * (t["y"] + t["h"] / 2)
            tol = MATCH_TOL * ext * s
            hits, err, used = [], 0.0, set()
            for t2 in T:
                pe = _edges(place(t2, s, ox, oy))
                cand = None
                for j, f2 in enumerate(F):
                    if j in used or color_class(f2) != color_class(t2):
                        continue
                    d = max(abs(a - b) for a, b in zip(_edges(f2), pe))
                    if d <= tol and (cand is None or d < cand[1]):
                        cand = (j, d)
                if cand:
                    used.add(cand[0]); hits.append((t2, cand[0])); err = max(err, cand[1])
            score = sum(perim(t2) for t2, _ in hits) / total
            if best is None or (score, -err) > (best["score"], -best["err"]):
                best = {"score": score, "err": err, "s": s, "ox": ox, "oy": oy, "tol": tol, "hits": hits}
    if best is None or not best["hits"]:
        return {"known": True, "match": False, "score": 0.0}
    s, ox, oy, tol = best["s"], best["ox"], best["oy"], best["tol"]
    targets = [F[j] for _, j in best["hits"]]
    for f in F:                                            # ta sama linia narysowana dwa razy
        if f not in targets and any(color_class(f) == color_class(t2) and
                                    max(abs(a - b) for a, b in zip(_edges(f), _edges(place(t2, s, ox, oy)))) <= tol
                                    for t2, _ in best["hits"]):
            targets.append(f)
    # Napisy z szablonu: treść bywa inna albo nieczytelna, więc porównujemy wysokość na
    # stronie i wielkość liter; w poziomie wystarczy, że leżą w obrębie szablonu.
    x0 = min(z["x"] for z in targets)
    x1 = max(z["x"] + z["w"] for z in targets)
    norm = lambda t: " ".join(t.split()).lower()
    for t in mine_txt:
        for c in tpl_txt:
            same = len(norm(c["tekst"])) >= 3 and norm(c["tekst"]) == norm(t["tekst"])
            at_h = abs(s * c["y"] + oy - t["y"]) <= max(tol, 2 * s * c["size_mm"])
            alike = abs(s * c["size_mm"] - t["size_mm"]) <= s * c["size_mm"] * 0.25
            if same or (at_h and alike and x0 - tol <= t["x"] <= x1):
                targets.append({**t, "w": 0, "h": 0})
                break
    return {"known": True, "match": best["score"] >= MATCH_MIN, "score": round(best["score"], 3),
            "err_mm": round(best["err"], 1), "scale": round(s, 3),
            "lines": len(best["hits"]), "lines_total": len(T), "targets": targets}


def _edge_frame(z, W, H) -> bool:
    """Ramka/pas przy krawędzi: prawie cała szerokość albo wysokość, przy brzegu."""
    if not (z["w"] >= W * 0.8 or z["h"] >= H * 0.8):
        return False
    return min(z["x"], z["y"], W - z["x"] - z["w"], H - z["y"] - z["h"]) <= max(60.0, 0.06 * max(W, H))


def find(path: str, page_index: int, page_mm: tuple, gl_pdf: str | None, gl_page: int | None) -> dict:
    """Czy w pliku został szablon z wytycznych. Zwraca:
        found   — obiekty do usunięcia (gdy szablon pasuje),
        match   — opis dopasowania,
        foreign — liczba ramek w kolorach wytycznych, które NIE układają się w ten szablon."""
    mine, mine_txt = shapes(path, page_index, page_mm)
    tpl, tpl_txt = [], []
    if gl_pdf and gl_page is not None and os.path.exists(gl_pdf):
        with pikepdf.open(path) as pdf:
            mb = [float(v) for v in (pdf.pages[page_index].obj.get("/MediaBox") or [0, 0, 595, 842])]
        k = page_mm[0] / (abs(mb[2] - mb[0]) * MM)          # mm wydruku na mm pliku
        try:
            tpl, tpl_txt = shapes(gl_pdf, gl_page)
            for z in tpl:
                z.update(x=z["x"] * k, y=z["y"] * k, w=z["w"] * k, h=z["h"] * k)
            for z in tpl_txt:
                z.update(x=z["x"] * k, y=z["y"] * k, size_mm=z["size_mm"] * k)
        except Exception:
            tpl, tpl_txt = [], []
    m = match_template(mine, mine_txt, tpl, tpl_txt)
    found = m.pop("targets", []) if m.get("match") else []
    ids = {(tuple(z["owner"]) if z.get("owner") else None, z["index"]) for z in found}
    foreign = [z for z in mine if color_class(z) is not None and _edge_frame(z, *page_mm)
               and ((tuple(z["owner"]) if z.get("owner") else None, z["index"]) not in ids)]
    m.pop("targets", None)
    return {"found": found, "match": m, "foreign": len(foreign)}


def remove(src: str, dst: str, page_index: int, targets: list) -> int:
    """Wycina wskazane kształty — dokładnie te operatory, które je rysują. Reszta pliku
    zostaje bit w bit taka sama."""
    groups = collections.defaultdict(list)
    for t in targets:
        groups[tuple(t["owner"]) if t.get("owner") else None].append((int(t["index"]), int(t["end"])))
    n = 0
    with pikepdf.open(src) as pdf:
        page = pdf.pages[page_index]
        for owner, spans in groups.items():
            container = page if owner is None else pdf.get_object(*owner)
            try:
                ops = list(pikepdf.parse_content_stream(container))
            except Exception:
                continue
            drop = {i for a, b in spans for i in range(a, b + 1)}
            data = pikepdf.unparse_content_stream([op for i, op in enumerate(ops) if i not in drop])
            n += len(spans)
            if owner is None:
                page.Contents = pdf.make_stream(data)
            else:
                container.write(data)
        pdf.save(dst)
    return n


VIS_PX = 2000             # rozdzielczość porównania (dłuższy bok)
VIS_DIFF = 24             # różnica koloru, którą uznajemy za widoczną (0–255)
VIS_MIN = 40              # tyle pikseli musi się zmienić, żeby szablon był „widoczny"


def visible(path: str, page_index: int, targets: list) -> bool:
    """Czy znaleziony szablon w ogóle WIDAĆ. Bywa, że projektant zostawił warstwę szablonu
    pod grafiką — jest w pliku, ale nic z niej nie wychodzi na wierzch. Renderujemy stronę
    z szablonem i bez niego; brak różnicy = szablon przykryty, nie drukuje się."""
    import tempfile
    import numpy as np
    from PIL import Image
    import render
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        remove(path, tmp, page_index, targets)
        a, b = (np.asarray(Image.open(io.BytesIO(render.page_png(p, page_index, VIS_PX))).convert("RGB")).astype(np.int16)
                for p in (path, tmp))
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if a.shape != b.shape:
        return True
    return int((np.abs(a - b).max(axis=2) > VIS_DIFF).sum()) >= VIS_MIN


# ----------------------------------------------------------------------------
# ramki WTOPIONE W OBRAZ — tylko do powiedzenia, że są (pikseli nie da się usunąć)
# ----------------------------------------------------------------------------
RASTER_COLORS = [(0, 174, 239), (237, 28, 36)]
RASTER_TOL = 70           # druk i JPEG rozmywają kolor
RASTER_MIN_COVER = 0.5    # jaka część wiersza/kolumny ma mieć ten kolor


def in_pixels(path: str, page_index: int, page_mm: tuple) -> bool:
    """Czy w obrazie strony biegnie linia w kolorze wytycznych przez (prawie) całą szerokość
    albo wysokość. Pas grubszy niż 14 mm to już pole, nie linia — pomijamy."""
    import numpy as np
    from PIL import Image
    import render
    try:
        a = np.asarray(Image.open(io.BytesIO(render.page_png(path, page_index, 2400))).convert("RGB")).astype(np.int16)
    except Exception:
        return False
    H, W, _ = a.shape
    for rgb in RASTER_COLORS:
        m = np.abs(a - np.array(rgb, dtype=np.int16)).max(axis=2) <= RASTER_TOL
        for vals, mm_px in ((m.mean(axis=1), page_mm[1] / H), (m.mean(axis=0), page_mm[0] / W)):
            run = 0
            for v in list(vals) + [0.0]:
                if v >= RASTER_MIN_COVER:
                    run += 1
                elif run:
                    if run * mm_px <= 14:
                        return True
                    run = 0
    return False
