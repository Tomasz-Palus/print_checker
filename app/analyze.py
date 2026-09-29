"""
Analiza pliku do druku: liczba stron, kolory, profile ICC, rozdzielczość.

PDF (także .ai zgodny z PDF): pikepdf — przechodzimy strumienie treści KAŻDEJ
strony rekurencyjnie (Form XObject, wzorki kafelkowe), śledząc CTM (q/Q/cm),
i liczymy faktyczne UŻYCIA przestrzeni barw:
    g/G rg/RG k/K            -> DeviceGray / DeviceRGB / DeviceCMYK
    cs/CS + sc/scn/SC/SCN    -> przestrzeń z zasobów (/ICCBased, /Indexed,
                                /Separation, /DeviceN, /Lab, /Cal*, /Pattern)
    sh, wzorki cieniowane    -> /ColorSpace cieniowania
    Do (Image), BI (inline)  -> przestrzeń obrazu (+ /SMask), rozmiar w px,
                                a z CTM wielkość na stronie -> efektywne ppi
    gs (ExtGState)           -> overprint (/OP /op), przezroczystość (/ca /CA /SMask /BM)
Deklaracja w zasobach bez użycia NIE jest liczona. Profile ICC: opis z tagu
'desc'/'mluc' strumienia ICC. Output intent z /OutputIntents.

Rastry (JPG/PNG/TIFF/…): Pillow — tryb (RGB/CMYK/L/P/…), bity, ICC, DPI, klatki.
(SVG i EPS są wcześniej zamieniane na PDF — render.canonicalize.)

Wynik = fakty. Ocenę jakości obrazów (realny detal) liczy detailmap.py, werdykt — quality.py.
"""
from __future__ import annotations

import math
import struct
from collections import Counter, defaultdict

import pikepdf
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

MM_PER_PT = 25.4 / 72.0
MAX_IMAGE_RECORDS = 400          # ile rekordów obrazów zwracamy do UI
def icc_info(data: bytes) -> dict:
    """Nazwa profilu (tag desc/mluc), przestrzeń (RGB/CMYK/GRAY/Lab) i klasa."""
    out = {"desc": None, "space": None, "class": None}
    try:
        if len(data) < 132:
            return out
        out["class"] = data[12:16].decode("latin-1").strip()
        out["space"] = data[16:20].decode("latin-1").strip()
        count = struct.unpack(">I", data[128:132])[0]
        for i in range(min(count, 200)):
            off = 132 + i * 12
            sig, toff, tsize = struct.unpack(">4sII", data[off:off + 12])
            if sig != b"desc":
                continue
            tag = data[toff:toff + tsize]
            typ = tag[:4]
            if typ == b"desc":
                n = struct.unpack(">I", tag[8:12])[0]
                out["desc"] = tag[12:12 + n].split(b"\x00")[0].decode("latin-1", "replace").strip()
            elif typ == b"mluc":
                n = struct.unpack(">I", tag[8:12])[0]
                recsize = struct.unpack(">I", tag[12:16])[0]
                best = None
                for r in range(n):
                    ro = 16 + r * recsize
                    lang = tag[ro:ro + 2]
                    ln, so = struct.unpack(">II", tag[ro + 4:ro + 12])
                    s = tag[so:so + ln].decode("utf-16-be", "replace").strip("\x00 ")
                    if best is None or lang == b"en":
                        best = s
                out["desc"] = best
            break
    except Exception:
        pass
    return out


# ----------------------------------------------------------------------------
# Klasyfikacja przestrzeni barw
# ----------------------------------------------------------------------------
_ICC_N_FAMILY = {1: "Gray", 3: "RGB", 4: "CMYK"}


class Analyzer:
    def __init__(self, pdf: pikepdf.Pdf):
        self.pdf = pdf
        self._icc_cache: dict[int, dict] = {}
        self.usage = Counter()          # (family, kind) -> count; kind: fill|stroke|image|shading|inline
        self.spots = Counter()          # nazwa spotu -> użycia
        self.spot_alt = {}              # nazwa spotu -> rodzina alternatywna
        self.devicen = Counter()        # tuple nazw -> użycia
        self.icc_profiles = Counter()   # (desc, family) -> użycia
        self.images = []                # dicty obrazów (po xref, z listą umiejscowień)
        self._img_by_xref: dict[int, dict] = {}
        self.overprint_uses = 0
        self.white_op = []              # biały z overprintem — w druku znika: [x0,y0,x1,y1] w pt strony
        self._ov_in = {}                # stan overprintu przekazywany do formy
        self.heavy_black = 0            # jednolite czernie ponad limit farby (CMYK / Registration) — da się poprawić
        self.thin = []                  # cienkie kreski: [x0,y0,x1,y1, grubość w mm PLIKU] (0 = hairline)
        self._lw_in = 1.0               # grubość linii przekazywana do formy
        self.transparency = Counter()   # rodzaj -> liczba
        self.inline_images = 0
        self.unknown_ops = 0
        self.fonts = Counter()          # (basefont, embedded) -> użycia Tf
        self.visited_forms = set()
        self._active_forms = set()      # formy w toku (ochrona przed cyklem: forma rysuje samą siebie)
        self._budget = OPS_BUDGET       # ile operatorów wolno przejść (formy wielokrotnie zagnieżdżone)
        self.truncated = False          # budżet się skończył — analiza niepełna
        self.page_index = 0
        self.page_box = (0.0, 0.0, 0.0, 0.0)   # MediaBox bieżącej strony (x0, y0, x1, y1) w pt

    # --- ICC
    def _icc(self, stream) -> dict:
        try:
            key = stream.objgen
        except Exception:
            key = id(stream)
        if key not in self._icc_cache:
            info = {"desc": None, "space": None, "class": None, "N": None}
            try:
                info["N"] = int(stream.get("/N", 0)) or None
                info.update(icc_info(stream.read_bytes()))
            except Exception:
                pass
            self._icc_cache[key] = info
        return self._icc_cache[key]

    # --- klasyfikacja
    def classify(self, cs, resources, depth=0) -> dict:
        """Zwraca {'family','icc','spot','names','indexed'} dla obiektu przestrzeni barw."""
        res = {"family": "Unknown", "icc": None, "spot": None, "names": None, "indexed": False}
        if cs is None or depth > 6:
            return res
        try:
            if isinstance(cs, pikepdf.Name):
                n = str(cs)
                simple = {"/DeviceGray": "Gray", "/G": "Gray", "/CalGray": "Gray",
                          "/DeviceRGB": "RGB", "/RGB": "RGB", "/CalRGB": "RGB",
                          "/DeviceCMYK": "CMYK", "/CMYK": "CMYK",
                          "/Pattern": "Pattern", "/Lab": "Lab", "/Indexed": "Indexed", "/I": "Indexed"}
                if n in simple:
                    res["family"] = simple[n]
                    return res
                # nazwa z zasobów
                csd = (resources or {}).get("/ColorSpace") if resources is not None else None
                if csd is not None and n in csd:
                    return self.classify(csd[n], resources, depth + 1)
                return res
            if isinstance(cs, pikepdf.Array) and len(cs) > 0:
                fam = str(cs[0])
                if fam == "/ICCBased":
                    info = self._icc(cs[1])
                    n = info.get("N")
                    space = (info.get("space") or "").upper()
                    family = _ICC_N_FAMILY.get(n) or {"RGB": "RGB", "CMYK": "CMYK", "GRAY": "Gray", "LAB": "Lab"}.get(space, "Unknown")
                    res["family"] = family
                    res["icc"] = info.get("desc") or f"(profil ICC bez nazwy, N={n})"
                    return res
                if fam in ("/Indexed", "/I"):
                    base = self.classify(cs[1], resources, depth + 1)
                    base["indexed"] = True
                    return base
                if fam == "/Separation":
                    name = str(cs[1]).lstrip("/")
                    alt = self.classify(cs[2], resources, depth + 1) if len(cs) > 2 else res
                    return {"family": "Spot", "icc": alt.get("icc"), "spot": name, "names": [name],
                            "indexed": False, "alt": alt.get("family")}
                if fam == "/DeviceN":
                    names = [str(x).lstrip("/") for x in cs[1]]
                    alt = self.classify(cs[2], resources, depth + 1) if len(cs) > 2 else res
                    return {"family": "DeviceN", "icc": alt.get("icc"), "spot": None, "names": names,
                            "indexed": False, "alt": alt.get("family")}
                if fam == "/Pattern":
                    return {"family": "Pattern", "icc": None, "spot": None, "names": None, "indexed": False,
                            "base": self.classify(cs[1], resources, depth + 1) if len(cs) > 1 else None}
                if fam in ("/CalRGB",):
                    res["family"] = "RGB"; return res
                if fam in ("/CalGray",):
                    res["family"] = "Gray"; return res
                if fam == "/Lab":
                    res["family"] = "Lab"; return res
                if fam in ("/DeviceRGB", "/DeviceCMYK", "/DeviceGray"):
                    return self.classify(cs[0], resources, depth + 1)
        except Exception:
            pass
        return res

    def _record(self, c: dict, kind: str):
        fam = c.get("family", "Unknown")
        if fam == "Spot":
            self.spots[c["spot"]] += 1
            self.spot_alt[c["spot"]] = c.get("alt")
            self.usage[("Spot", kind)] += 1
        elif fam == "DeviceN":
            names = tuple(c.get("names") or [])
            self.devicen[names] += 1
            self.usage[("DeviceN", kind)] += 1
            # DeviceN z nazwami procesowymi to w praktyce CMYK; inne nazwy to spoty
            for nme in names:
                if nme.lower() not in ("cyan", "magenta", "yellow", "black", "none", "all"):
                    self.spots[nme] += 1
                    self.spot_alt.setdefault(nme, c.get("alt"))
        elif fam == "Pattern":
            base = c.get("base")
            if base:
                self._record(base, kind)
        else:
            self.usage[(fam, kind)] += 1
        if c.get("icc"):
            self.icc_profiles[(c["icc"], fam if fam not in ("Spot", "DeviceN") else c.get("alt"))] += 1

    # --- ExtGState
    def _extgstate(self, name, resources):
        try:
            gsd = resources.get("/ExtGState")
            if gsd is None or name not in gsd:
                return
            g = gsd[name]
            if bool(g.get("/OP", False)) or bool(g.get("/op", False)):
                self.overprint_uses += 1
            ov = {}
            if "/OP" in g:
                ov["OP"] = bool(g.get("/OP"))
                ov["op"] = bool(g.get("/OP"))           # bez /op obowiązuje /OP (PDF 1.7, 8.4.5)
            if "/op" in g:
                ov["op"] = bool(g.get("/op"))
            if "/OPM" in g:
                try:
                    ov["OPM"] = int(g.get("/OPM"))
                except Exception:
                    pass
            ca, CA = g.get("/ca", 1), g.get("/CA", 1)
            try:
                if float(ca) < 1 or float(CA) < 1:
                    self.transparency["krycie < 100 %"] += 1
            except Exception:
                pass
            bm = g.get("/BM")
            if bm is not None and str(bm) not in ("/Normal", "/Compatible"):
                self.transparency[f"tryb mieszania {str(bm).lstrip('/')}"] += 1
            sm = g.get("/SMask")
            if sm is not None and not (isinstance(sm, pikepdf.Name) and str(sm) == "/None"):
                self.transparency["maska miękka (ExtGState)"] += 1
            return ov
        except Exception:
            pass
        return {}

    # --- biały z overprintem
    def _white_hit(self, box):
        if box and len(self.white_op) < 200:
            self.white_op.append([round(v, 2) for v in box])

    @staticmethod
    def _text_box(operands, ctm, tm, size):
        """Przybliżony prostokąt napisu (wystarczy do ramki na podglądzie)."""
        n = 0
        for x in operands:
            try:
                for y in x:
                    try:
                        n += len(bytes(y))
                    except Exception:
                        pass
            except TypeError:
                try:
                    n += len(bytes(x))
                except Exception:
                    pass
        w, h = max(n, 1) * size * 0.55, size
        m = _mul(tm, ctm)
        pts = [(0, -0.2 * h), (w, -0.2 * h), (0, h), (w, h)]
        xs = [m[0] * x + m[2] * y + m[4] for x, y in pts]
        ys = [m[1] * x + m[3] * y + m[5] for x, y in pts]
        return [min(xs), min(ys), max(xs), max(ys)]

    # --- obrazy
    def _image(self, xobj, ctm, resources, name, inline=False):
        try:
            key = xobj.objgen if not inline else ("inline", id(xobj))
        except Exception:
            key = (id(xobj), 0)
        w = int(xobj.get("/Width", 0)); h = int(xobj.get("/Height", 0))
        # rozmiar na stronie z CTM (jednostkowy kwadrat obrazu -> CTM)
        a, b, c, d = ctm[0], ctm[1], ctm[2], ctm[3]
        w_pt = math.hypot(a, b); h_pt = math.hypot(c, d)
        ppi_x = w / (w_pt / 72.0) if w_pt > 1e-6 else None
        ppi_y = h / (h_pt / 72.0) if h_pt > 1e-6 else None
        ppi = min(x for x in (ppi_x, ppi_y) if x) if (ppi_x or ppi_y) else None
        # prostokąt umiejscowienia w układzie PDF (origin lewy-dolny)
        xs = [ctm[4], ctm[0] + ctm[4], ctm[2] + ctm[4], ctm[0] + ctm[2] + ctm[4]]
        ys = [ctm[5], ctm[1] + ctm[5], ctm[3] + ctm[5], ctm[1] + ctm[3] + ctm[5]]
        rect_pdf = (min(xs), min(ys), max(xs), max(ys))
        rec = self._img_by_xref.get(key)
        if rec is None:
            cs = xobj.get("/ColorSpace")
            mask = bool(xobj.get("/ImageMask", False))
            c = self.classify(cs, resources) if not mask else {"family": "Mask", "icc": None, "spot": None, "names": None, "indexed": False}
            rec = {
                "name": str(name), "width": w, "height": h,
                "bpc": int(xobj.get("/BitsPerComponent", 0) or 0),
                "family": c.get("family"), "icc": c.get("icc"), "spot": c.get("spot"), "names": c.get("names"),
                "indexed": c.get("indexed", False), "mask": mask,
                "smask": "/SMask" in xobj or ("/Mask" in xobj),
                "filter": str(xobj.get("/Filter", "")).replace("/", ""),
                "placements": [], "min_ppi": None,
                # obraz inline nie ma numeru obiektu — detailmap go nie dekoduje, sprawdza tylko
                # liczbę pikseli (przegląd kodu 27.09, A6)
                "xref": None if inline else (key[0] if isinstance(key, tuple) else None), "inline": inline,
                "page": self.page_index, "rect_pdf": rect_pdf,
            }
            self._img_by_xref[key] = rec
            self.images.append(rec)
            if not mask:
                self._record(c, "image")
            if rec["smask"]:
                self.transparency["obraz z maską (SMask)"] += 1
        bx0, by0, bx1, by1 = self.page_box
        rec["placements"].append({"w_mm": round(w_pt * MM_PER_PT, 2), "h_mm": round(h_pt * MM_PER_PT, 2),
                                  "ppi": round(ppi, 1) if ppi else None,
                                  # położenie od lewego-górnego rogu strony (mm) — do „pokaż na podglądzie”
                                  "x_mm": round((rect_pdf[0] - bx0) * MM_PER_PT, 2),
                                  "y_mm": round((by1 - rect_pdf[3]) * MM_PER_PT, 2),
                                  "bw_mm": round((rect_pdf[2] - rect_pdf[0]) * MM_PER_PT, 2),
                                  "bh_mm": round((rect_pdf[3] - rect_pdf[1]) * MM_PER_PT, 2),
                                  # pełna macierz — obraz może być odbity (a<0 / d<0) albo obrócony
                                  # (b,c≠0); bez niej fragment z wnętrza obrazu trafia na stronę
                                  # w lustrzanym miejscu (1878: ramka na niebie, liście w analizie)
                                  "ctm": [round(float(v), 4) for v in ctm[:6]],
                                  "rect_pdf": [round(float(v), 3) for v in rect_pdf],
                                  "page": self.page_index})
        if ppi and (rec["min_ppi"] is None or ppi < rec["min_ppi"]):
            rec["min_ppi"] = round(ppi, 1)

    # --- strumień treści
    def walk(self, container, resources, ctm, depth=0):
        if depth > 12 or self._budget <= 0:
            if self._budget <= 0:
                self.truncated = True
            return
        try:
            ops = pikepdf.parse_content_stream(container)
        except Exception:
            self.unknown_ops += 1
            return
        self._budget -= len(ops)
        # przestrzeń WZORU (pattern) = domyślna przestrzeń tego strumienia (strony albo formy),
        # a nie macierz w chwili `scn` (przegląd kodu 27.09, A9: ppi obrazu we wzorze zawyżone 10×)
        base_ctm = ctm
        stack = []
        fill_cs = {"family": "Gray"}   # domyślnie DeviceGray
        stroke_cs = {"family": "Gray"}
        fill_pattern_cs = None
        # biały z overprintem (Tomasz 29.09 — „edge cases”): stan overprintu, kolor i obrys ścieżki
        ov = dict(self._ov_in)
        fill_v, stroke_v, tr = [0.0], [0.0], 0
        lw = self._lw_in
        tm, tsize = [1, 0, 0, 1, 0, 0], 12.0
        pbox = None
        for operands, op in ops:
            o = str(op)
            try:
                if o in ("m", "l", "c", "v", "y", "re"):
                    vals = [float(x) for x in operands]
                    if o == "re":
                        x, y, w, h = vals
                        vals = [x, y, x + w, y + h]
                    for j in range(0, len(vals) - 1, 2):
                        px, py = ctm[0] * vals[j] + ctm[2] * vals[j + 1] + ctm[4], ctm[1] * vals[j] + ctm[3] * vals[j + 1] + ctm[5]
                        pbox = [px, py, px, py] if pbox is None else [min(pbox[0], px), min(pbox[1], py),
                                                                      max(pbox[2], px), max(pbox[3], py)]
                    continue
                if o == "w":
                    lw = float(operands[0])
                    continue
                if o in ("f", "F", "f*", "B", "B*", "b", "b*", "S", "s", "n"):
                    if pbox is not None and o in ("S", "s", "B", "B*", "b", "b*"):
                        # grubość kreski na stronie: w × skala macierzy (pierwiastek z wyznacznika)
                        wmm = lw * abs(ctm[0] * ctm[3] - ctm[1] * ctm[2]) ** 0.5 * MM_PER_PT
                        if wmm < THIN_FILE_MM and len(self.thin) < 400 and not _template_color(stroke_cs, stroke_v):
                            self.thin.append([round(v, 2) for v in pbox] + [round(wmm, 4)])
                    if pbox is not None and o != "n":
                        if (o not in ("S", "s") and _heavy(fill_cs, fill_v)) or \
                                (o not in ("f", "F", "f*") and _heavy(stroke_cs, stroke_v)):
                            self.heavy_black += 1
                        if o not in ("S", "s") and ov.get("op") and _white(fill_cs, fill_v, ov.get("OPM", 0)):
                            self._white_hit(pbox)
                        elif o not in ("f", "F", "f*") and ov.get("OP") and _white(stroke_cs, stroke_v, ov.get("OPM", 0)):
                            self._white_hit(pbox)
                    pbox = None
                    continue
                if o in ("Tj", "TJ", "'", '"') and tr not in (3, 7) and \
                        _heavy(*((fill_cs, fill_v) if tr in (0, 2, 4, 6) else (stroke_cs, stroke_v))):
                    self.heavy_black += 1
                if o in ("Tj", "TJ", "'", '"') and tr not in (3, 7) and ov.get("op" if tr in (0, 2, 4, 6) else "OP"):
                    cs_, v_ = (fill_cs, fill_v) if tr in (0, 2, 4, 6) else (stroke_cs, stroke_v)
                    if _white(cs_, v_, ov.get("OPM", 0)):
                        self._white_hit(self._text_box(operands, ctm, tm, tsize))
                if o == "Tr":
                    tr = int(operands[0])
                elif o == "BT":
                    tm = [1, 0, 0, 1, 0, 0]
                elif o == "Tm":
                    tm = [float(x) for x in operands]
                elif o in ("Td", "TD"):
                    tm = [tm[0], tm[1], tm[2], tm[3], tm[4] + float(operands[0]) * tm[0] + float(operands[1]) * tm[2],
                          tm[5] + float(operands[0]) * tm[1] + float(operands[1]) * tm[3]]
                if o == "q":
                    stack.append((ctm, fill_cs, stroke_cs, dict(ov), fill_v, stroke_v, lw))
                elif o == "Q":
                    if stack:
                        ctm, fill_cs, stroke_cs, ov, fill_v, stroke_v, lw = stack.pop()
                elif o == "cm":
                    m = [float(x) for x in operands]
                    ctm = _mul(m, ctm)
                elif o == "g":
                    fill_cs = {"family": "Gray"}; self._record(fill_cs, "fill"); fill_v = _nums(operands)
                elif o == "G":
                    stroke_cs = {"family": "Gray"}; self._record(stroke_cs, "stroke"); stroke_v = _nums(operands)
                elif o == "rg":
                    fill_cs = {"family": "RGB"}; self._record(fill_cs, "fill"); fill_v = _nums(operands)
                elif o == "RG":
                    stroke_cs = {"family": "RGB"}; self._record(stroke_cs, "stroke"); stroke_v = _nums(operands)
                elif o == "k":
                    fill_cs = {"family": "CMYK"}; self._record(fill_cs, "fill"); fill_v = _nums(operands)
                elif o == "K":
                    stroke_cs = {"family": "CMYK"}; self._record(stroke_cs, "stroke"); stroke_v = _nums(operands)
                elif o == "cs":
                    fill_cs = self.classify(operands[0], resources); fill_v = [0.0]
                elif o == "CS":
                    stroke_cs = self.classify(operands[0], resources); stroke_v = [0.0]
                elif o in ("sc", "scn"):
                    fill_v = _nums(operands)
                    if fill_cs.get("family") == "Pattern":
                        self._pattern(operands, resources, base_ctm, "fill", depth)
                    else:
                        self._record(fill_cs, "fill")
                elif o in ("SC", "SCN"):
                    stroke_v = _nums(operands)
                    if stroke_cs.get("family") == "Pattern":
                        self._pattern(operands, resources, base_ctm, "stroke", depth)
                    else:
                        self._record(stroke_cs, "stroke")
                elif o == "sh":
                    shd = resources.get("/Shading") if resources is not None else None
                    if shd is not None and operands[0] in shd:
                        self._record(self.classify(shd[operands[0]].get("/ColorSpace"), resources), "shading")
                elif o == "gs":
                    ov.update(self._extgstate(operands[0], resources))
                elif o == "Tf":
                    tsize = float(operands[1])
                    self._font(operands[0], resources)
                elif o in ("BI", "INLINE IMAGE"):   # pikepdf: „INLINE IMAGE” (przegląd kodu 27.09, A6)
                    self.inline_images += 1
                    if operands and isinstance(operands[0], pikepdf.PdfInlineImage):
                        try:
                            self._image(_InlineDict(operands[0].obj), ctm, resources, "inline", inline=True)
                        except Exception:
                            self.unknown_ops += 1
                elif o == "Do":
                    xod = resources.get("/XObject") if resources is not None else None
                    if xod is None or operands[0] not in xod:
                        continue
                    xo = xod[operands[0]]
                    st = str(xo.get("/Subtype", ""))
                    if st == "/Image":
                        self._image(xo, ctm, resources, operands[0])
                    elif st == "/Form":
                        self._ov_in = dict(ov)          # forma dziedziczy stan overprintu i grubość linii
                        self._lw_in = lw
                        try:
                            self._form(xo, ctm, resources, depth)
                        finally:
                            self._ov_in = {}
                            self._lw_in = 1.0
            except Exception:
                self.unknown_ops += 1

    def _form(self, xo, ctm, parent_res, depth):
        try:
            key = xo.objgen
        except Exception:
            key = id(xo)
        mtx = xo.get("/Matrix")
        m = [float(x) for x in mtx] if mtx is not None else [1, 0, 0, 1, 0, 0]
        res = xo.get("/Resources")
        if res is None:
            res = parent_res
        grp = xo.get("/Group")
        if grp is not None and str(grp.get("/S", "")) == "/Transparency" and key not in self.visited_forms:
            self.transparency["grupa przezroczystości"] += 1
        self.visited_forms.add(key)
        if key in self._active_forms:                # forma rysuje samą siebie (cykl) — koniec
            self.unknown_ops += 1
            return
        self._active_forms.add(key)
        try:
            self.walk(xo, res, _mul(m, ctm), depth + 1)
        finally:
            self._active_forms.discard(key)

    # --- adnotacje (stemple, pola formularzy…) — ich wygląd drukuje się jak treść strony
    def annotations(self, page):
        """Wygląd (/AP /N) adnotacji z flagą „drukuj” i bez „ukryta” — kolory, overprint, fonty
        i obrazy w stemplu drukują się jak reszta strony (przegląd kodu 27.09, A7)."""
        for annot in (page.get("/Annots") or []):
            try:
                flags = int(annot.get("/F", 0))
                if not flags & 4 or flags & 2:           # bez „Print” albo „Hidden” — nie drukuje się
                    continue
                ap = annot.get("/AP")
                n = ap.get("/N") if ap is not None else None
                if n is None:
                    continue
                if not isinstance(n, pikepdf.Stream):    # słownik stanów (pole wyboru…) — bieżący /AS
                    st = annot.get("/AS")
                    n = n.get(st) if st is not None else None
                    if not isinstance(n, pikepdf.Stream):
                        continue
                self._form(n, _annot_ctm(n, annot.get("/Rect")), page.get("/Resources"), 0)
            except Exception:
                self.unknown_ops += 1

    def _pattern(self, operands, resources, ctm, kind, depth):
        try:
            pd = resources.get("/Pattern") if resources is not None else None
            name = operands[-1] if operands else None
            if pd is None or name is None or name not in pd:
                return
            pat = pd[name]
            ptype = int(pat.get("/PatternType", 1))
            mtx = pat.get("/Matrix")
            m = [float(x) for x in mtx] if mtx is not None else [1, 0, 0, 1, 0, 0]
            if ptype == 2:
                sh = pat.get("/Shading")
                self._record(self.classify(sh.get("/ColorSpace"), resources), "shading")
            else:
                res = pat.get("/Resources") or resources
                self.walk(pat, res, _mul(m, ctm), depth + 1)
        except Exception:
            self.unknown_ops += 1

    def _font(self, name, resources):
        try:
            fd = resources.get("/Font") if resources is not None else None
            if fd is None or name not in fd:
                return
            f = fd[name]
            base = str(f.get("/BaseFont", "?")).lstrip("/")
            desc = f.get("/FontDescriptor")
            if desc is None and "/DescendantFonts" in f:
                desc = f["/DescendantFonts"][0].get("/FontDescriptor")
            embedded = desc is not None and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3"))
            # Type 3: kształty liter są w samym pliku (/CharProcs), bez pliku fontu — to font
            # w pełni osadzony, choć nie ma /FontFile (częste w eksportach z CorelDRAW)
            if str(f.get("/Subtype", "")) == "/Type3":
                embedded = True
            self.fonts[(base, embedded)] += 1
        except Exception:
            pass


def _nums(operands) -> list:
    out = []
    for x in operands:
        try:
            out.append(float(x))
        except Exception:
            pass
    return out or [0.0]


THIN_FILE_MM = 0.25     # zbieramy kreski cieńsze w PLIKU; próg na wydruku (× skala) liczy interfejs


def _template_color(cs: dict, v: list) -> bool:
    """Kreska w kolorze linii wytycznych (cyjan / czerwień) — to szablon, nie projekt."""
    fam = cs.get("family")
    if fam == "CMYK" and len(v) >= 4:
        c, m, y, k = v[:4]
        return (c > 0.9 and m < 0.1 and y < 0.1 and k < 0.1) or (c < 0.1 and m > 0.85 and y > 0.8 and k < 0.1)
    if fam == "RGB" and len(v) >= 3:
        r, g, b = v[:3]
        return (r < 0.1 and g > 0.6 and b > 0.85) or (r > 0.85 and g < 0.2 and b < 0.2)
    return False


HEAVY_SUM = 3.6         # suma farb (1 = 100 %) ponad limit drukarni — jak ink.TAC_LIMIT
HEAVY_K = 0.85          # i dużo czerni: to „czarne” pole, a nie ciemny kolor


def _heavy(cs: dict, v: list) -> bool:
    """Jednolita czerń z za dużą ilością farby: CMYK (np. 100/100/100/100) albo kolor
    „Registration” (separacja All = 100 % każdej farby). Tę da się poprawić (steps.step_black)."""
    fam = cs.get("family")
    if fam == "CMYK" and len(v) >= 4:
        return sum(v[:4]) > HEAVY_SUM and v[3] >= HEAVY_K
    if fam == "Spot" and cs.get("spot") == "All":
        return len(v) >= 1 and v[0] * 4 > HEAVY_SUM
    return False


def _white(cs: dict, v: list, opm: int) -> bool:
    """Czy farba to BIEL, która z overprintem zniknie: CMYK 0/0/0/0 przy OPM 1 (zera nie zakrywają
    tła — tak zapisuje Illustrator). Kolor dodatkowy („White” do druku białą farbą) jest celowy."""
    fam = cs.get("family")
    # Skala szarości i RGB z overprintem ZAKRYWAJĄ tło — tak liczy Ghostscript i tak pokazuje
    # Acrobat („Podgląd wyjściowy” z symulacją nadruku, Tomasz 29.09). RGB zamienione na CMYK
    # daje 0/0/0/0 — to wyłapie analiza wersji po zamianie kolorów.
    if fam == "CMYK":
        return len(v) >= 4 and max(v[:4]) <= 0.001 and opm == 1
    return False


class _InlineDict:
    """Słownik obrazu inline z pełnymi nazwami kluczy (w BI…ID wolno skróty: /W, /CS, /BPC…)."""
    ABBR = {"/Width": "/W", "/Height": "/H", "/ColorSpace": "/CS", "/BitsPerComponent": "/BPC",
            "/ImageMask": "/IM", "/Filter": "/F", "/Decode": "/D", "/Interpolate": "/I"}

    def __init__(self, obj):
        self.obj = obj

    def get(self, key, default=None):
        v = self.obj.get(key)
        if v is None and key in self.ABBR:
            v = self.obj.get(self.ABBR[key])
        return default if v is None else v

    def __contains__(self, key):
        return self.get(key) is not None


OPS_BUDGET = 3_000_000        # operatorów na analizę — powyżej: formy zagnieżdżone setki razy


def _annot_ctm(form, rect):
    """Macierz, którą PDF stawia wygląd adnotacji w jej /Rect: BBox przekształcony /Matrix formy
    ma wypełnić /Rect (PDF 1.7, 12.5.5). `_form` sam dokłada /Matrix — tu reszta."""
    r = [float(v) for v in rect]
    bb = [float(v) for v in form.get("/BBox", [0, 0, 1, 1])]
    mtx = form.get("/Matrix")
    m = [float(v) for v in mtx] if mtx is not None else [1, 0, 0, 1, 0, 0]
    pts = [(bb[0], bb[1]), (bb[2], bb[1]), (bb[0], bb[3]), (bb[2], bb[3])]
    xs = [m[0] * x + m[2] * y + m[4] for x, y in pts]
    ys = [m[1] * x + m[3] * y + m[5] for x, y in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    sx = (max(r[0], r[2]) - min(r[0], r[2])) / (x1 - x0) if x1 > x0 else 1.0
    sy = (max(r[1], r[3]) - min(r[1], r[3])) / (y1 - y0) if y1 > y0 else 1.0
    return [sx, 0, 0, sy, min(r[0], r[2]) - x0 * sx, min(r[1], r[3]) - y0 * sy]


def _mul(m, n):
    """m × n (najpierw m, potem n) dla macierzy PDF [a b c d e f]."""
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return [a * a2 + b * c2, a * b2 + b * d2,
            c * a2 + d * c2, c * b2 + d * d2,
            e * a2 + f * c2 + e2, e * b2 + f * d2 + f2]


# ----------------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------------
def _fonts_missing(path: str, page: int | None) -> list:
    """Fonty NIEOSADZONE (i niestandardowe) użyte na stronie: [{name, visible}]. Widoczny = tekst
    w nim się drukuje (nie Tr 3/7). Rozdział „Fonty” nie pozwala takiego zostawić, a podgląd
    mówi, że litery są narysowane krojem zastępczym (Tomasz 29.09)."""
    try:
        import fontfix
        out = [{"name": m["name"], "visible": bool(m["widoczny"])} for m in fontfix.missing(path, page)]
    except Exception as e:
        print(f"[adChecker] fonts_missing: {type(e).__name__}: {e}")
        return []
    if out and page is not None:
        boxes = font_boxes(path, page, [m["name"] for m in out if m["visible"]])
        for m in out:
            m["boxes"] = boxes.get(_fkey(m["name"]), []) if m["visible"] else []
    return out


def _fkey(name: str) -> str:
    return (name or "").split("+")[-1].replace(" ", "").replace("-", "").replace(",", "").lower()


def font_boxes(path: str, page: int, names: list, limit: int = 80) -> dict:
    """Gdzie na stronie stoi WIDOCZNY tekst w podanych fontach: {klucz fontu: [[fx, fy, fw, fh]]}
    (ułamki strony, y od góry; jedna ramka na wiersz). Do zaznaczenia na podglądzie liter, które
    wyjdą krojem zastępczym (Tomasz 29.09)."""
    import pymupdf
    want = {_fkey(n) for n in names}
    out: dict = {}
    if not want:
        return out
    try:
        d = pymupdf.open(path)
        try:
            pg = d[page]
            W, H = pg.rect.width or 1, pg.rect.height or 1
            for b in pg.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
                for ln in b.get("lines", []):
                    rows: dict = {}
                    for sp in ln.get("spans", []):
                        k = _fkey(sp.get("font", ""))
                        if k not in want or sp.get("alpha", 255) == 0 or not sp.get("text", "").strip():
                            continue
                        x0, y0, x1, y1 = sp["bbox"]
                        r = rows.setdefault(k, [x0, y0, x1, y1])
                        r[0], r[1], r[2], r[3] = min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)
                    for k, (x0, y0, x1, y1) in rows.items():
                        lst = out.setdefault(k, [])
                        if len(lst) < limit:
                            lst.append([round(x0 / W, 5), round(y0 / H, 5), round((x1 - x0) / W, 5), round((y1 - y0) / H, 5)])
        finally:
            d.close()
    except Exception as e:
        print(f"[adChecker] font_boxes: {type(e).__name__}: {e}")
    return out


def flat_image(path: str, page: int | None) -> dict | None:
    """Strona, która JUŻ jest jednym obrazem na całą stronę (eksport „spłaszczony” z Photoshopa,
    obraz 120 ppi w PDF-ie): w treści tylko q/Q/cm/gs i jedno `Do` obrazu, który pokrywa stronę.
    Spłaszczanie takiej strony tylko przelicza piksele od nowa — nowszy Ghostscript potrafi przy
    tym przesunąć pojedyncze rzędy i dać drobne ząbki na krawędziach (Tomasz 29.09,
    adFrame_Smart_100x250_1_1). Zwraca {w, h, ppi} obrazu (ppi w pliku) albo None."""
    if page is None:
        return None
    try:
        with pikepdf.open(path) as pdf:
            pg = pdf.pages[page]
            mb = [float(v) for v in (pg.obj.get("/MediaBox") or [0, 0, 0, 0])]
            if pg.obj.get("/Annots"):
                return None
            res = pg.obj.get("/Resources")
            xo = res.get("/XObject") if res is not None else None
            ctm, stack, found = [1, 0, 0, 1, 0, 0], [], None
            for operands, op in pikepdf.parse_content_stream(pg):
                o = str(op)
                if o == "q":
                    stack.append(ctm)
                elif o == "Q":
                    ctm = stack.pop() if stack else ctm
                elif o == "cm":
                    ctm = _mul([float(x) for x in operands], ctm)
                elif o == "gs":
                    g = res.get("/ExtGState", {}).get(operands[0]) if res is not None else None
                    if g is not None and any(k in g for k in ("/SMask", "/BM", "/ca", "/CA", "/OP", "/op")):
                        return None
                elif o == "Do":
                    im = xo.get(operands[0]) if xo is not None else None
                    if found is not None or im is None or str(im.get("/Subtype", "")) != "/Image" \
                            or "/SMask" in im or "/Mask" in im or bool(im.get("/ImageMask", False)):
                        return None
                    # obraz pokrywa całą stronę (bez obrotu, z dokładnością do 0,5 pt)
                    if abs(ctm[1]) > 1e-6 or abs(ctm[2]) > 1e-6 or ctm[0] <= 0 or ctm[3] <= 0:
                        return None
                    box = (ctm[4], ctm[5], ctm[4] + ctm[0], ctm[5] + ctm[3])
                    if max(abs(a - b) for a, b in zip(box, mb)) > 0.5:
                        return None
                    found = {"w": int(im.get("/Width", 0)), "h": int(im.get("/Height", 0)),
                             "ppi": round(int(im.get("/Width", 0)) / (ctm[0] / 72.0), 1)}
                else:
                    return None                      # jakakolwiek inna treść — to nie „sam obraz”
            return found
    except Exception:
        return None


def _text_boxes(path: str, page: int | None, limit: int = 600) -> list:
    """Widoczny tekst strony: jedna ramka na wiersz [fx, fy, fw, fh] (ułamki strony, y od góry).
    Do sprawdzenia obszaru bezpiecznego — napis przy krawędzi może zostać ucięty albo schowany
    w ramie (Tomasz 29.09, „edge cases”)."""
    if page is None:
        return []
    import pymupdf
    out = []
    try:
        d = pymupdf.open(path)
        try:
            pg = d[page]
            W, H = pg.rect.width or 1, pg.rect.height or 1
            for b in pg.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
                for ln in b.get("lines", []):
                    sp = [s for s in ln.get("spans", []) if s.get("alpha", 255) != 0 and s.get("text", "").strip()]
                    if not sp or len(out) >= limit:
                        continue
                    x0 = min(s["bbox"][0] for s in sp); y0 = min(s["bbox"][1] for s in sp)
                    x1 = max(s["bbox"][2] for s in sp); y1 = max(s["bbox"][3] for s in sp)
                    out.append([round(x0 / W, 5), round(y0 / H, 5), round((x1 - x0) / W, 5), round((y1 - y0) / H, 5)])
        finally:
            d.close()
    except Exception as e:
        print(f"[adChecker] text_boxes: {type(e).__name__}: {e}")
    return out


def analyze_pdf(path: str, only_page: int | None = None) -> dict:
    """`only_page` — fakty tylko o tej stronie (do druku idzie zawsze jedna strona)."""
    pdf = pikepdf.open(path)
    try:
        an = Analyzer(pdf)
        pages = []
        page_sizes = []
        for i, page in enumerate(pdf.pages):
            res = page.get("/Resources")
            grp = page.get("/Group")
            if grp is not None and (only_page is None or i == only_page) and str(grp.get("/S", "")) == "/Transparency":
                an.transparency["strona z grupą przezroczystości"] += 1
            before_imgs = len(an.images)
            an.page_index = i
            try:
                mb = page.get("/MediaBox") or page.obj.get("/MediaBox")
                an.page_box = tuple(float(v) for v in mb)
            except Exception:
                an.page_box = (0.0, 0.0, 0.0, 0.0)
            page_sizes.append(((an.page_box[2] - an.page_box[0]) * MM_PER_PT, (an.page_box[3] - an.page_box[1]) * MM_PER_PT))
            if only_page is not None and i != only_page:
                pages.append({"index": i, "images": 0})
                continue
            w0 = len(an.white_op)
            an.walk(page, res, [1, 0, 0, 1, 0, 0])
            an.annotations(page)
            pages.append({"index": i, "images": len(an.images) - before_imgs})
            # biały z overprintem → ułamki strony (y od góry), do ramek na podglądzie
            bx0, by0, bx1, by1 = an.page_box
            pw, ph = (bx1 - bx0) or 1, (by1 - by0) or 1
            an.white_boxes = getattr(an, "white_boxes", []) + [
                [round((b[0] - bx0) / pw, 5), round((by1 - b[3]) / ph, 5),
                 round((b[2] - b[0]) / pw, 5), round((b[3] - b[1]) / ph, 5)] for b in an.white_op[w0:]]
            # cienkie kreski: ramka (ułamki strony, min. 0,2 % boku — kreska pozioma ma zerową
            # wysokość) i grubość w mm pliku
            an.thin_boxes = [
                [round((b[0] - bx0) / pw, 5), round((by1 - b[3]) / ph, 5),
                 round(max(b[2] - b[0], 0.002 * pw) / pw, 5), round(max(b[3] - b[1], 0.002 * ph) / ph, 5), b[4]]
                for b in an.thin]

        # Realny detal obrazów liczy detailmap.py (rozdział „Jakość wydruku") — tu tylko fakty.
        coverage = {}

        # output intents
        intents = []
        for oi in (pdf.Root.get("/OutputIntents") or []):
            try:
                prof = oi.get("/DestOutputProfile")
                icc = icc_info(prof.read_bytes()) if prof is not None else {}
                intents.append({
                    "subtype": str(oi.get("/S", "")).lstrip("/"),
                    "identifier": str(oi.get("/OutputConditionIdentifier", "") or ""),
                    "info": str(oi.get("/Info", "") or ""),
                    "profile": icc.get("desc"), "profile_space": icc.get("space"),
                })
            except Exception:
                pass

        info = pdf.docinfo
        meta = {
            "producer": str(info.get("/Producer", "") or ""),
            "creator": str(info.get("/Creator", "") or ""),
            "pdf_version": pdf.pdf_version,
        }
        res = _summarize_pdf(an, pages, intents, meta, coverage, page_sizes)
    finally:
        pdf.close()
    res["fonts_missing"] = _fonts_missing(path, only_page)
    res["text_boxes"] = _text_boxes(path, only_page)
    res["flat_image"] = flat_image(path, only_page)
    return res


def _summarize_pdf(an: Analyzer, pages, intents, meta, coverage=None, page_sizes=None) -> dict:
    fam_counts = defaultdict(lambda: Counter())
    for (fam, kind), n in an.usage.items():
        fam_counts[fam][kind] += n
    families = {fam: dict(c) for fam, c in fam_counts.items()}

    # obrazy
    imgs = sorted(an.images, key=lambda r: (r["min_ppi"] is None, r["min_ppi"] or 0))
    # wszystkie obrazy (do MAX_IMAGE_RECORDS), od najsłabszego; klucz „worst” zostaje dla zgodności z UI
    worst = [{k: v for k, v in r.items() if k != "placements"}
             | {"placements": r["placements"][:24], "placement_count": len(r["placements"])}
             for r in imgs[:MAX_IMAGE_RECORDS]]
    # WSZYSTKIE umiejscowienia WSZYSTKICH obrazów (także masek) w ułamkach strony — maska dla mapy
    # detalu (detailmap): poza obrazami jest wektor, który nie ma rozdzielczości. Bez limitu 24.
    image_boxes = []
    for r in an.images:
        for p in r["placements"]:
            pg = p.get("page", 0)
            if page_sizes and pg < len(page_sizes) and page_sizes[pg][0] > 0 and page_sizes[pg][1] > 0:
                pw, ph = page_sizes[pg]
                image_boxes.append([pg, round(p["x_mm"] / pw, 5), round(p["y_mm"] / ph, 5), round(p["bw_mm"] / pw, 5), round(p["bh_mm"] / ph, 5)])
    min_ppi = min((r["min_ppi"] for r in an.images if r["min_ppi"]), default=None)
    has_images = len(an.images) > 0 or an.inline_images > 0

    # werdykt kolorystyczny (opis, nie ocena)
    proc = [f for f in ("CMYK", "RGB", "Gray", "Lab") if f in families]
    spots = [{"name": n, "uses": c, "pantone": "pantone" in n.lower(), "alt": an.spot_alt.get(n)}
             for n, c in an.spots.most_common()]
    icc = [{"desc": d, "family": f, "uses": c} for (d, f), c in an.icc_profiles.most_common()]
    parts = []
    if proc:
        parts.append(" + ".join(proc))
    if spots:
        npant = sum(1 for s in spots if s["pantone"])
        parts.append(f"{len(spots)} kolor(y) dodatkowe" + (f" (w tym {npant} PANTONE)" if npant else ""))
    if "DeviceN" in families and not spots:
        parts.append("DeviceN")
    verdict = "; ".join(parts) if parts else "brak informacji o kolorze (pusty plik?)"
    # „mieszane” = więcej niż jeden model procesowy (Gray traktujemy jako część CMYK) albo spoty obok procesu
    proc_models = [f for f in proc if f != "Gray"]
    mixed = len(proc_models) > 1 or (bool(spots) and bool(proc))

    return {
        "kind": "pdf",
        "pages": len(pages),
        "meta": meta,
        "color": {
            "verdict": verdict,
            "mixed": mixed,
            "families": families,          # {'CMYK': {'fill': 48, 'image': 1}, ...}
            "spots": spots,
            "devicen": [{"names": list(k), "uses": v} for k, v in an.devicen.items()],
            "icc_profiles": icc,
            "output_intents": intents,
        },
        "resolution": {
            "has_images": has_images,
            "image_count": len(an.images),
            "inline_images": an.inline_images,
            "min_ppi": min_ppi,
            "worst": worst,
            "records_truncated": max(0, len(an.images) - len(worst)),
            "coverage": coverage or {},
            "image_boxes": image_boxes,          # [page, fx, fy, fw, fh] — wszystkie użycia
            "image_boxes_complete": an.inline_images == 0,   # obrazy inline nie mają pozycji -> maska niepełna
            "page_sizes_mm": page_sizes or [],
        },
        "overprint_uses": an.overprint_uses,
        "white_overprint": getattr(an, "white_boxes", []),
        "thin_lines": getattr(an, "thin_boxes", []),
        "heavy_black": an.heavy_black,
        "transparency": dict(an.transparency),
        "fonts": [{"name": n, "embedded": e, "uses": c} for (n, e), c in an.fonts.most_common()],
        "parse_warnings": an.unknown_ops + (1 if an.truncated else 0),
        "per_page": pages,
        "_images": an.images,     # pełne rekordy (xref, wszystkie umiejscowienia) — server zdejmuje przed wysłaniem do UI
    }


# ----------------------------------------------------------------------------
# Rastry
# ----------------------------------------------------------------------------
_MODE_FAMILY = {"RGB": "RGB", "RGBA": "RGB", "RGBX": "RGB", "CMYK": "CMYK", "L": "Gray", "LA": "Gray",
                "1": "Gray (1-bit)", "P": "Indexed", "PA": "Indexed", "I;16": "Gray 16-bit", "I": "Gray 32-bit",
                "LAB": "Lab", "YCbCr": "RGB (YCbCr)", "HSV": "RGB (HSV)", "F": "Float"}


def analyze_raster(path: str) -> dict:
    with Image.open(path) as im:
        mode = im.mode
        frames = getattr(im, "n_frames", 1)
        icc = icc_info(im.info["icc_profile"]) if im.info.get("icc_profile") else None
        dpi = im.info.get("dpi")
        fam = _MODE_FAMILY.get(mode, mode)
        alpha = mode in ("RGBA", "LA", "PA") or "transparency" in im.info
        bits = {"1": 1, "I;16": 16, "I": 32, "F": 32}.get(mode, 8)
        return {
            "kind": "raster",
            "pages": frames,
            "meta": {"format": im.format, "mode": mode, "bits": bits,
                     "compression": str(im.info.get("compression", "")),
                     "producer": "", "creator": str(im.info.get("software", "") or "")},
            "color": {
                "verdict": fam + (f" ({icc['desc']})" if icc and icc.get("desc") else ", bez profilu ICC"),
                "mixed": False,
                "families": {fam: {"image": 1}},
                "spots": [], "devicen": [],
                "icc_profiles": ([{"desc": icc.get("desc") or "(profil bez nazwy)", "family": icc.get("space"), "uses": 1}] if icc else []),
                "output_intents": [],
            },
            "resolution": {
                "has_images": True, "image_count": 1, "inline_images": 0,
                "min_ppi": round(float(dpi[0]), 1) if dpi and dpi[0] else None,
                "dpi_meta": [round(float(dpi[0]), 1), round(float(dpi[1]), 1)] if dpi and dpi[0] and dpi[1] else None,
                "width_px": im.width, "height_px": im.height,
                "worst": [],
            },
            "overprint_uses": 0,
            "transparency": {"kanał alfa": 1} if alpha else {},
            "fonts": [],
            "parse_warnings": 0,
            "per_page": [{"index": i, "images": 1} for i in range(frames)],
        }


def analyze(path: str, page: int | None = None) -> dict:
    """Dyspozycja po TREŚCI, nie po rozszerzeniu: wszystko, co da się otworzyć jako PDF
    (PDF, AI, kanoniczne PDF z SVG/EPS), idzie przez analizę obiektów — każdy raster w środku
    jest oceniany w natywnych pikselach, wektor nie ma rozdzielczości; reszta = jeden raster."""
    try:
        with pikepdf.open(path):
            is_pdf = True
    except Exception:
        is_pdf = False
    if is_pdf:
        return analyze_pdf(path, page)
    return analyze_raster(path)
