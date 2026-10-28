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

import pdfutil

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
        # Gradient przycięty kształtem (litery, krzywe) albo kształt wypełniony wzorem gradientowym —
        # Ghostscript nie wygładza krawędzi przycięcia nawet z AlphaBits; spłaszczenie liczy wtedy z
        # nadpróbkowaniem (steps.step_flatten, 28.10). Kontrakt `clipped_shading`.
        self.clipped_shading = 0
        self.clipped_shading_text = 0   # …w tym gradient w LITERACH (przycięcie tekstem, tekst wypełniony wzorem)
        self._clip_in = False
        self._clip_text_in = False
        self.heavy_black = 0            # jednolite czernie ponad limit farby (CMYK / Registration) — da się poprawić
        self._lw_in = 1.0               # grubość linii przekazywana do formy
        self.transparency = Counter()   # rodzaj -> liczba
        self.inline_images = 0
        self.unknown_ops = 0
        self.fonts = Counter()          # (basefont, embedded) -> użycia Tf
        self.visited_forms = set()
        self._active_forms = set()      # formy w toku (ochrona przed cyklem: forma rysuje samą siebie)
        self._budget = OPS_BUDGET       # ile operatorów wolno przejść (formy wielokrotnie zagnieżdżone)
        self.truncated = False          # budżet się skończył — analiza niepełna
        self.partial = set()            # powody niepełnej analizy: budget | depth | stream (przegląd 09.10, B13)
        self._ops_cache: dict = {}      # objgen formy/wzoru/glifu → sparsowane operatory (przegląd 09.10, B25)
        # Powtórka formy (28.10): forma użyta drugi raz w tym samym stanie (overprint, przycięcie, maska…)
        # daje ten sam wynik — dokładamy go bez przechodzenia treści; obrazy z nowym położeniem. Wcześniej
        # symbol powtórzony 30 000 razy wyczerpywał budżet i reszta pliku zostawała niesprawdzona.
        self._form_memo: dict = {}      # klucz stanu → (liczniki, Counter-y, obrazy [(…, macierz względna)], group_rgb)
        self._journals: list = []       # dzienniki formy w pierwszym przejściu: wywołania _image, liczniki obrazów
        self._img_depth = 0
        self._memo_hold: list = []      # zasoby bez numeru użyte w kluczu (żeby id się nie powtórzyło)
        self._pat_hits = 0              # wzory z obrazami (miejsce zależy od malowanego obszaru — bez powtórki)
        self._in_mask = 0               # > 0: wewnątrz formy maski miękkiej (/SMask /G) — jej kolory się nie drukują
        self._mask_seen = set()         # (maska, macierz) już przejrzane
        self._plog = None               # lista (rekord, umiejscowienie) obrazów z bieżącego wzoru
        self._t3_plain = set()          # glify Type3 bez obrazów — kolejne wystąpienia pomijamy
        self._n_place = 0               # licznik umiejscowień obrazów
        self.group_rgb = False          # grupa przezroczystości strony/formy z /CS RGB (kontrakt `group_rgb`)
        self.blend_undeclared = False   # przezroczystość na stronie bez /Group /CS (kontrakt `blend_space_missing`)
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
        if self._in_mask:               # maska miękka to kształt, nie farba
            return
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
    def _extgstate(self, name, resources, ctm=None, depth=0):
        try:
            gsd = resources.get("/ExtGState")
            if gsd is None or name not in gsd:
                return {}
            g = gsd[name]
            sm = g.get("/SMask")
            if ctm is not None and isinstance(sm, pikepdf.Dictionary) and isinstance(sm.get("/G"), pikepdf.Stream):
                self._soft_mask(sm.get("/G"), ctm, resources, depth)
            return self._extgstate_dict(g)
        except Exception:
            return {}

    def _soft_mask(self, form, ctm, resources, depth):
        """Forma maski miękkiej (/SMask /G): jej obrazy wyznaczają kształt na wydruku — mają mieć
        rozdzielczość jak każdy obraz; kolorów i overprintu w niej nie liczymy (przegląd 09.10, B12)."""
        try:
            key = (form.objgen, tuple(round(float(v), 3) for v in ctm[:6]))
        except Exception:
            key = (id(form), 0)
        if key in self._mask_seen:
            return
        self._mask_seen.add(key)
        self._in_mask += 1
        try:
            self._form(form, ctm, resources, depth, mask=True)
        finally:
            self._in_mask -= 1

    def _extgstate_dict(self, g) -> dict:
        try:
            if self._in_mask:
                return {}
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
    def _image(self, xobj, ctm, resources, name, inline=False, role=None):
        if self._img_depth:                          # maska obrazu z wnętrza _image — powtórzy ją sam obraz
            return self._image_body(xobj, ctm, resources, name, inline, role)
        for j in self._journals:                     # forma w pierwszym przejściu — do powtórki
            j["imgs"].append((xobj, ctm, resources, name, inline, role))
        self._img_depth += 1
        try:
            if not self._journals:
                return self._image_body(xobj, ctm, resources, name, inline, role)
            # liczniki z pierwszego zobaczenia obrazu (kolor, profil, maska) liczą się raz na obraz —
            # nie wchodzą do różnicy doliczanej przy powtórce formy
            before = {k: Counter(getattr(self, k)) for k in self._REPLAY_CNT} if self._is_new_image(xobj, inline) else None
            self._image_body(xobj, ctm, resources, name, inline, role)
            if before is not None:
                for k, c0 in before.items():
                    d = getattr(self, k) - c0
                    if d:
                        for j in self._journals:
                            j["excl"].setdefault(k, Counter()).update(d)
        finally:
            self._img_depth -= 1

    def _is_new_image(self, xobj, inline) -> bool:
        if inline:
            return True
        try:
            return xobj.objgen not in self._img_by_xref
        except Exception:
            return True

    def _image_body(self, xobj, ctm, resources, name, inline=False, role=None):
        try:
            key = xobj.objgen if not inline else ("inline", id(xobj))
        except Exception:
            key = (id(xobj), 0)
        if role is None and self._in_mask:
            role = "softmask"           # obraz w formie maski miękkiej — kształt, nie kolor
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
                # „smask”/„softmask” — maska (kształt), nie farba: tylko liczba pikseli (przegląd 09.10, B12)
                "role": role,
            }
            self._img_by_xref[key] = rec
            self.images.append(rec)
            if not mask and role is None:
                self._record(c, "image")
            if rec["smask"] and role is None:
                self.transparency["obraz z maską (SMask)"] += 1
        # maska obrazu (/SMask albo /Mask-strumień) o MNIEJSZEJ liczbie pikseli niż obraz — schodki na
        # konturze; ta sama rozdzielczość nic nowego nie mówi. Obraz < 8 px (kolor) — kształt niesie maska.
        if not inline and role is None:
            for mk in ("/SMask", "/Mask"):
                ms = xobj.get(mk)
                if isinstance(ms, pikepdf.Stream):
                    try:
                        mw, mh = int(ms.get("/Width", 0)), int(ms.get("/Height", 0))
                        if mw * mh and (mw * mh < w * h or min(w, h) < 8):
                            self._image(ms, ctm, resources, f"{name}{mk}", role="smask")
                    except Exception:
                        self.unknown_ops += 1
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
        self._n_place += 1
        if self._plog is not None:                   # obraz we wzorze — miejsce poprawi wypełnienie
            self._plog.append((rec, rec["placements"][-1]))
        if ppi and (rec["min_ppi"] is None or ppi < rec["min_ppi"]):
            rec["min_ppi"] = round(ppi, 1)

    # --- strumień treści
    def _ops(self, container):
        """Sparsowane operatory strumienia; formy, wzory i glify — raz na obiekt (przegląd 09.10, B25:
        forma użyta 12 000 razy była parsowana 12 000 razy)."""
        key = None
        if isinstance(container, pikepdf.Stream):
            try:
                key = container.objgen if container.objgen != (0, 0) else None
            except Exception:
                key = None
        if key is not None and key in self._ops_cache:
            return self._ops_cache[key]
        # duża treść (miliony operatorów) — strumieniowo, bez listy w pamięci i bez zapamiętywania
        ops = pdfutil.iter_ops(container)
        if key is not None and isinstance(ops, list):
            self._ops_cache[key] = ops
        return ops

    def walk(self, container, resources, ctm, depth=0):
        # Niepełna analiza nie może przejść po cichu (przegląd 09.10, B13): powód trafia do `partial`.
        if self._budget <= 0:
            self.truncated = True
            self.partial.add("budget")
            return
        if depth > MAX_DEPTH:
            self.partial.add("depth")
            return
        try:
            ops = self._ops(container)
        except Exception:
            self.unknown_ops += 1
            self.partial.add("stream")
            return
        if isinstance(ops, list):
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
        # kolor ustawiony samym `cs`/`CS` (bez sc) maluje kolorem początkowym — liczymy go przy
        # malowaniu (przegląd 09.10, C); wzór: obrazy z ostatniego `scn` czekają na obszar wypełnienia
        fill_dirty = stroke_dirty = False
        pat_fill = pat_stroke = None
        t3 = None                              # bieżący font Type3 (Tf)
        in_mask = self._in_mask
        clip_shaped = self._clip_in            # przycięcie nieprostokątne (krzywe, ukos, litery)
        clip_text = self._clip_text_in         # …z liter
        path_shaped = text_clip = pat_shading = False
        for operands, o in ops:
            try:
                if o in ("c", "v", "y", "l"):
                    path_shaped = True
                if o in ("m", "l", "c", "v", "y", "re"):
                    # obrys ścieżki potrzebny tylko dla bieli z overprintem i obszaru wzoru —
                    # poza tym wystarczy wiedzieć, że ścieżka jest (przegląd 09.10, B25)
                    if not (ov.get("op") or ov.get("OP") or pat_fill or pat_stroke):
                        if pbox is None:
                            pbox = True
                        continue
                    vals = [float(x) for x in operands]
                    if o == "re":
                        x, y, w, h = vals
                        vals = [x, y, x + w, y + h]
                    for j in range(0, len(vals) - 1, 2):
                        px, py = ctm[0] * vals[j] + ctm[2] * vals[j + 1] + ctm[4], ctm[1] * vals[j] + ctm[3] * vals[j + 1] + ctm[5]
                        pbox = [px, py, px, py] if not isinstance(pbox, list) else [min(pbox[0], px), min(pbox[1], py),
                                                                                    max(pbox[2], px), max(pbox[3], py)]
                    continue
                if o == "w":
                    lw = float(operands[0])
                    continue
                if o in ("W", "W*"):
                    if path_shaped:
                        clip_shaped = True
                    continue
                if o in ("f", "F", "f*", "B", "B*", "b", "b*", "S", "s", "n"):
                    if pat_shading and o not in ("S", "s", "n"):
                        self.clipped_shading += 1
                        if clip_text:
                            self.clipped_shading_text += 1
                    path_shaped = False
                    if pbox is not None and o != "n":
                        fills, strokes = o not in ("S", "s"), o not in ("f", "F", "f*")
                        if fills and fill_dirty:
                            self._record(fill_cs, "fill"); fill_dirty = False
                        if strokes and stroke_dirty:
                            self._record(stroke_cs, "stroke"); stroke_dirty = False
                        if fills and pat_fill and isinstance(pbox, list):
                            self._pattern_area(pat_fill, pbox)
                        if strokes and pat_stroke and isinstance(pbox, list):
                            self._pattern_area(pat_stroke, pbox)
                        if not in_mask:
                            if (fills and _heavy(fill_cs, fill_v)) or (strokes and _heavy(stroke_cs, stroke_v)):
                                self.heavy_black += 1
                            if isinstance(pbox, list):
                                if fills and ov.get("op") and _white(fill_cs, fill_v, ov.get("OPM", 0)):
                                    self._white_hit(pbox)
                                elif strokes and ov.get("OP") and _white(stroke_cs, stroke_v, ov.get("OPM", 0)):
                                    self._white_hit(pbox)
                    pbox = None
                    continue
                if o in ("Tj", "TJ", "'", '"') and tr >= 4:
                    text_clip = True                     # tekst jako przycięcie — działa od ET
                if o in ("Tj", "TJ", "'", '"') and pat_shading and tr in (0, 2, 4, 6):
                    self.clipped_shading += 1
                    self.clipped_shading_text += 1
                if o in ("Tj", "TJ", "'", '"') and tr not in (3, 7):
                    fills = tr in (0, 2, 4, 6)
                    if fills and fill_dirty:
                        self._record(fill_cs, "fill"); fill_dirty = False
                    if tr in (1, 2, 5, 6) and stroke_dirty:
                        self._record(stroke_cs, "stroke"); stroke_dirty = False
                    pat = pat_fill if fills else pat_stroke
                    if pat:
                        self._pattern_area(pat, self._text_box(operands, ctm, tm, tsize))
                    if t3 is not None:               # glify Type3 to zwykła treść (przegląd 09.10, B12)
                        self._type3(t3, operands, o, ctm, tm, tsize, resources, depth, ov, lw)
                if not in_mask and o in ("Tj", "TJ", "'", '"') and tr not in (3, 7) and \
                        _heavy(*((fill_cs, fill_v) if tr in (0, 2, 4, 6) else (stroke_cs, stroke_v))):
                    self.heavy_black += 1
                if not in_mask and o in ("Tj", "TJ", "'", '"') and tr not in (3, 7) and ov.get("op" if tr in (0, 2, 4, 6) else "OP"):
                    cs_, v_ = (fill_cs, fill_v) if tr in (0, 2, 4, 6) else (stroke_cs, stroke_v)
                    if _white(cs_, v_, ov.get("OPM", 0)):
                        self._white_hit(self._text_box(operands, ctm, tm, tsize))
                if o == "Tr":
                    tr = int(operands[0])
                elif o == "BT":
                    tm = [1, 0, 0, 1, 0, 0]
                elif o == "ET" and text_clip:
                    clip_shaped, clip_text, text_clip = True, True, False
                elif o == "Tm":
                    tm = [float(x) for x in operands]
                elif o in ("Td", "TD"):
                    tm = [tm[0], tm[1], tm[2], tm[3], tm[4] + float(operands[0]) * tm[0] + float(operands[1]) * tm[2],
                          tm[5] + float(operands[0]) * tm[1] + float(operands[1]) * tm[3]]
                if o == "q":
                    stack.append((ctm, fill_cs, stroke_cs, dict(ov), fill_v, stroke_v, lw,
                                  fill_dirty, stroke_dirty, pat_fill, pat_stroke, clip_shaped, pat_shading, clip_text))
                elif o == "Q":
                    if stack:
                        (ctm, fill_cs, stroke_cs, ov, fill_v, stroke_v, lw,
                         fill_dirty, stroke_dirty, pat_fill, pat_stroke, clip_shaped, pat_shading, clip_text) = stack.pop()
                elif o == "cm":
                    m = [float(x) for x in operands]
                    ctm = _mul(m, ctm)
                elif o in ("g", "rg", "k"):
                    fill_cs = {"family": {"g": "Gray", "rg": "RGB", "k": "CMYK"}[o]}; self._record(fill_cs, "fill")
                    fill_v = _nums(operands); fill_dirty = False; pat_fill = None; pat_shading = False
                elif o in ("G", "RG", "K"):
                    stroke_cs = {"family": {"G": "Gray", "RG": "RGB", "K": "CMYK"}[o]}; self._record(stroke_cs, "stroke")
                    stroke_v = _nums(operands); stroke_dirty = False; pat_stroke = None
                elif o == "cs":
                    fill_cs = self.classify(operands[0], resources); fill_v = [0.0]; fill_dirty = True; pat_fill = None
                    pat_shading = False
                elif o == "CS":
                    stroke_cs = self.classify(operands[0], resources); stroke_v = [0.0]; stroke_dirty = True; pat_stroke = None
                elif o in ("sc", "scn"):
                    fill_v = _nums(operands); fill_dirty = False
                    if fill_cs.get("family") == "Pattern":
                        try:                             # wzór gradientowy (PatternType 2) — wypełniony kształt
                            pd = resources.get("/Pattern") if resources is not None else None
                            pat_shading = bool(pd is not None and operands and int(pd[operands[-1]].get("/PatternType", 1)) == 2)
                        except Exception:
                            pat_shading = False
                        if fill_cs.get("base"):          # wzór bezbarwny (PaintType 2): kolor z bazy
                            self._record(fill_cs["base"], "fill")
                        pat_fill = self._pattern(operands, resources, base_ctm, "fill", depth)
                    else:
                        self._record(fill_cs, "fill")
                elif o in ("SC", "SCN"):
                    stroke_v = _nums(operands); stroke_dirty = False
                    if stroke_cs.get("family") == "Pattern":
                        if stroke_cs.get("base"):
                            self._record(stroke_cs["base"], "stroke")
                        pat_stroke = self._pattern(operands, resources, base_ctm, "stroke", depth)
                    else:
                        self._record(stroke_cs, "stroke")
                elif o == "sh":
                    if clip_shaped:
                        self.clipped_shading += 1
                        if clip_text:
                            self.clipped_shading_text += 1
                    shd = resources.get("/Shading") if resources is not None else None
                    if shd is not None and operands[0] in shd:
                        self._record(self.classify(shd[operands[0]].get("/ColorSpace"), resources), "shading")
                elif o == "gs":
                    ov.update(self._extgstate(operands[0], resources, ctm, depth))
                elif o == "Tf":
                    tsize = float(operands[1])
                    t3 = self._font(operands[0], resources)
                elif o in ("BI", "INLINE IMAGE"):   # pikepdf: „INLINE IMAGE” (przegląd kodu 27.09, A6)
                    self.inline_images += 1
                    if operands and isinstance(operands[0], pikepdf.PdfInlineImage):
                        try:
                            idict = _InlineDict(operands[0].obj)
                            if fill_dirty and bool(idict.get("/ImageMask", False)):   # maska maluje kolorem wypełnienia
                                self._record(fill_cs, "fill"); fill_dirty = False
                            self._image(idict, ctm, resources, "inline", inline=True)
                        except Exception:
                            self.unknown_ops += 1
                elif o == "Do":
                    xod = resources.get("/XObject") if resources is not None else None
                    if xod is None or operands[0] not in xod:
                        continue
                    xo = xod[operands[0]]
                    st = str(xo.get("/Subtype", ""))
                    if st == "/Image":
                        if fill_dirty and bool(xo.get("/ImageMask", False)):
                            self._record(fill_cs, "fill"); fill_dirty = False
                        self._image(xo, ctm, resources, operands[0])
                    elif st == "/Form":
                        self._ov_in = dict(ov)          # forma dziedziczy stan overprintu i grubość linii
                        self._lw_in = lw
                        self._clip_in, self._clip_text_in = clip_shaped, clip_text     # …i przycięcie
                        try:
                            self._form(xo, ctm, resources, depth)
                        finally:
                            self._ov_in = {}
                            self._lw_in = 1.0
                            self._clip_in = self._clip_text_in = False
            except Exception:
                self.unknown_ops += 1
        if not isinstance(ops, list):
            self._budget -= getattr(ops, "n", 0)
            if getattr(ops, "error", None) is not None:
                self.unknown_ops += 1
                self.partial.add("stream")

    def _form(self, xo, ctm, parent_res, depth, mask=False):
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
            if not self._in_mask:
                self.transparency["grupa przezroczystości"] += 1
            # grupa mieszana w RGB (nie maska miękka — tam /CS to przestrzeń maski) — kontrakt `group_rgb`
            if not mask and not self._in_mask and self._group_rgb(grp, res):
                self.group_rgb = True
        self.visited_forms.add(key)
        if key in self._active_forms:                # forma rysuje samą siebie (cykl) — koniec
            self.unknown_ops += 1
            return
        ck = self._memo_key(key, xo, parent_res, mask)
        rec = self._form_memo.get(ck) if ck is not None else None
        if rec is not None:
            self._replay(rec, ctm)
            return
        snap = self._snap() if ck is not None else None
        journal = {"imgs": [], "excl": {}}
        self._journals.append(journal)
        self._active_forms.add(key)
        try:
            self.walk(xo, res, _mul(m, ctm), depth + 1)
        finally:
            self._active_forms.discard(key)
            self._journals.pop()
        if snap is not None:
            rec = self._delta(snap, journal, ctm)
            if rec is not None:
                self._form_memo[ck] = rec

    _REPLAY_INT = ("overprint_uses", "clipped_shading", "clipped_shading_text", "heavy_black", "inline_images",
                   "unknown_ops")
    _REPLAY_CNT = ("usage", "spots", "devicen", "icc_profiles", "transparency", "fonts")

    def _memo_key(self, key, xo, parent_res, mask):
        """Stan, od którego zależy wynik formy — ten sam stan = ten sam wynik (poza miejscem obrazów)."""
        if not isinstance(key, tuple) or tuple(key) == (0, 0):
            return None
        pk = None
        if xo.get("/Resources") is None:             # forma korzysta z zasobów rodzica
            try:
                pk = tuple(parent_res.objgen)
            except Exception:
                return None
            if pk == (0, 0):
                # zasoby bez numeru (zwykle słownik w stronie): ten sam obiekt Pythona przez całe przejście
                # strony; trzymany w _memo_hold, więc jego id nie trafi się innemu słownikowi
                pk = ("id", id(parent_res))
                self._memo_hold.append(parent_res)
        try:
            ov = tuple(sorted(self._ov_in.items()))
        except Exception:
            return None
        return (tuple(key), pk, ov, round(float(self._lw_in), 3), self._clip_in, self._clip_text_in,
                self._in_mask, mask)

    def _snap(self):
        return ({k: getattr(self, k) for k in self._REPLAY_INT}, {k: Counter(getattr(self, k)) for k in self._REPLAY_CNT},
                len(self.white_op), len(self.partial), self.truncated, self._pat_hits, self.group_rgb)

    def _delta(self, snap, journal, ctm):
        ints0, cnts0, nwhite, npart, trunc, pats, grgb = snap
        # biel z overprintem i obrazy wzorów mają położenie z malowanego kształtu; niepełne przejście —
        # nie wiadomo, co pominięto: takiej formy nie powtarzamy
        if len(self.white_op) != nwhite or len(self.partial) != npart or self.truncated != trunc or self._pat_hits != pats:
            return None
        imgs = []
        if journal["imgs"]:
            inv = _inv(ctm)
            if inv is None:
                return None
            imgs = [(xobj, _mul(a, inv), res, name, inline, role) for xobj, a, res, name, inline, role in journal["imgs"]]
        ints = {k: getattr(self, k) - v for k, v in ints0.items() if getattr(self, k) != v}
        cnts = {}
        for k, c0 in cnts0.items():
            d = getattr(self, k) - c0 - journal["excl"].get(k, Counter())
            if k == "transparency":
                d.pop("grupa przezroczystości", None)    # liczona raz na formę, nie na użycie
            if d:
                cnts[k] = d
        return ints, cnts, imgs, (self.group_rgb and not grgb)

    def _replay(self, rec, ctm):
        ints, cnts, imgs, grgb = rec
        for k, v in ints.items():
            setattr(self, k, getattr(self, k) + v)
        for k, d in cnts.items():
            getattr(self, k).update(d)
        if grgb:
            self.group_rgb = True
        for xobj, rel, res, name, inline, role in imgs:
            self._image(xobj, _mul(rel, ctm), res, name, inline, role)
        self._budget -= len(imgs) + 1

    def _group_rgb(self, grp, res) -> bool:
        try:
            cs = grp.get("/CS")
            return cs is not None and self.classify(cs, res).get("family") == "RGB"
        except Exception:
            return False

    def _pattern_area(self, entry, box):
        """Obrazy ze wzoru dostają miejsce WYPEŁNIANEGO obszaru, nie pierwszej płytki (ta bywa poza
        stroną albo tam, gdzie nic nie jest namalowane — przegląd 09.10, A7). Pierwsze malowanie
        poprawia umiejscowienie, kolejne dokładają nowe (do 200 na wzór)."""
        if not box or not isinstance(box, list):
            return
        self._pat_hits += 1
        bx0, by0, bx1, by1 = self.page_box
        for rec, p in entry["items"]:
            q = p if not entry["used"] else dict(p)
            if entry["used"] and len(rec["placements"]) >= 200 + entry["n0"]:
                continue
            x0, y0, x1, y1 = box
            q.update({"x_mm": round((x0 - bx0) * MM_PER_PT, 2), "y_mm": round((by1 - y1) * MM_PER_PT, 2),
                      "bw_mm": round((x1 - x0) * MM_PER_PT, 2), "bh_mm": round((y1 - y0) * MM_PER_PT, 2),
                      "rect_pdf": [round(float(v), 3) for v in box], "ctm": None, "pattern": True})
            if entry["used"]:
                rec["placements"].append(q)
        entry["used"] = True

    def _type3(self, f, operands, o, ctm, tm, tsize, resources, depth, ov, lw):
        """Glify fontu Type3 (/CharProcs) — obrazy, kolory (glif d0) i fonty w nich drukują się jak
        reszta strony (przegląd 09.10, B12). Macierz glifu: FontMatrix × rozmiar i przesunięcie
        w tekście × Tm × CTM; przesunięcie z /Widths (bez Tc/Tw/Tz — wystarczy do miejsca obrazu)."""
        try:
            procs = f.get("/CharProcs")
            if procs is None:
                return
            fm = [float(v) for v in (f.get("/FontMatrix") or [0.001, 0, 0, 0.001, 0, 0])]
            res = f.get("/Resources") or resources
            diffs = {}
            enc = f.get("/Encoding")
            if isinstance(enc, pikepdf.Dictionary) and enc.get("/Differences") is not None:
                code = 0
                for x in enc.get("/Differences"):
                    if isinstance(x, pikepdf.Name):
                        diffs[code] = x; code += 1
                    else:
                        code = int(x)
            first = int(f.get("/FirstChar", 0) or 0)
            widths = [float(w) for w in (f.get("/Widths") or [])]
            items = operands[0] if o == "TJ" else ([operands[2]] if o == '"' else [operands[0]])
            tx = 0.0
            done = set()
            for it in items:
                if not isinstance(it, (pikepdf.String, bytes, str)):        # TJ: przesunięcie w 1/1000
                    try:
                        tx -= float(it) / 1000.0 * tsize
                        continue
                    except Exception:
                        pass
                for code in bytes(it):
                    name = diffs.get(code)
                    proc = procs.get(name) if name is not None else None
                    if proc is None:                     # bez /Differences: kod = nazwa niepewna — każdy glif raz
                        for nm in list(procs.keys()):
                            if nm not in done:
                                done.add(nm)
                                self._glyph(procs[nm], res, _mul(_mul(fm, [tsize, 0, 0, tsize, tx, 0]), _mul(tm, ctm)), depth, ov, lw)
                    else:
                        self._glyph(proc, res, _mul(_mul(fm, [tsize, 0, 0, tsize, tx, 0]), _mul(tm, ctm)), depth, ov, lw)
                    wi = code - first
                    tx += (widths[wi] if 0 <= wi < len(widths) else 0.0) * fm[0] * tsize
        except Exception:
            self.unknown_ops += 1

    def _glyph(self, proc, res, m, depth, ov, lw):
        if not isinstance(proc, pikepdf.Stream):
            return
        try:
            key = proc.objgen
        except Exception:
            key = id(proc)
        if key in self._t3_plain or key in self._active_forms:
            return
        n0 = self._n_place
        self._ov_in, self._lw_in = dict(ov), lw
        self._active_forms.add(key)
        try:
            self.walk(proc, res, m, depth + 1)
        finally:
            self._active_forms.discard(key)
            self._ov_in, self._lw_in = {}, 1.0
        if self._n_place == n0:
            self._t3_plain.add(key)                  # bez obrazów — kolory i fonty już policzone

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
                eg = pat.get("/ExtGState")              # overprint w samym wzorze cieniowanym (przegląd 09.10, C)
                if isinstance(eg, pikepdf.Dictionary):
                    self._extgstate_dict(eg)
                return None
            res = pat.get("/Resources") or resources
            outer, self._plog = self._plog, []
            try:
                self.walk(pat, res, _mul(m, ctm), depth + 1)
                items = self._plog
            finally:
                self._plog = outer
            if items:
                self._pat_hits += 1
            if outer is not None:
                outer.extend(items)
            # obrazy wzoru — ich miejsce na stronie ustali dopiero malowanie (_pattern_area)
            return {"items": items, "used": False, "n0": 0} if items else None
        except Exception:
            self.unknown_ops += 1
        return None

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
            t3 = str(f.get("/Subtype", "")) == "/Type3"
            if t3:
                embedded = True
            self.fonts[(base, embedded)] += 1
            return f if t3 else None                 # Type3 — walk przejdzie glify (_type3)
        except Exception:
            pass
        return None


def _nums(operands) -> list:
    out = []
    for x in operands:
        try:
            out.append(float(x))
        except Exception:
            pass
    return out or [0.0]


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


OPS_BUDGET = 5_000_000        # operatorów na analizę — powyżej: formy zagnieżdżone setki razy (po B25 ~3 s / mln)
MAX_DEPTH = 40                # zagnieżdżenie form/wzorów/glifów (cykle łapie _active_forms); głębiej → `partial`
PARTIAL_TEXT = {"budget": "plik ma bardzo dużo elementów — przejrzana tylko część",
                "depth": "elementy zagnieżdżone zbyt głęboko — część pominięta",
                "stream": "części treści strony nie da się odczytać"}


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


def _inv(m):
    """Odwrotność macierzy PDF; None dla zdegenerowanej (skala 0)."""
    a, b, c, d, e, f = (float(x) for x in m)
    det = a * d - b * c
    if abs(det) < 1e-12:
        return None
    ia, ib, ic, id_ = d / det, -b / det, -c / det, a / det
    return [ia, ib, ic, id_, -(e * ia + f * ic), -(e * ib + f * id_)]


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
    import render
    try:
        with render.MUPDF_LOCK:          # PyMuPDF z wątków serwera (przegląd 09.10, B24)
            d = pymupdf.open(path)
            try:
                pg = d[page]
                W, H = pg.rect.width or 1, pg.rect.height or 1
                blocks = pg.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]
            finally:
                d.close()
        if True:
            for b in blocks:
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
            if pdfutil._raw_length(pg) > 100_000:     # sam obraz to kilka operatorów — duża treść to nie to
                return None
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


def _real_transparency(t) -> int:
    """Ile razy strona naprawdę miesza (krycie, tryby, maski) — sama grupa przezroczystości nie miesza."""
    return sum(v for k, v in t.items() if "grupa przezroczystości" not in k)


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
                if an._group_rgb(grp, res):          # kontrakt `group_rgb` (przegląd 09.10, A4)
                    an.group_rgb = True
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
            t0 = _real_transparency(an.transparency)
            an.walk(page, res, [1, 0, 0, 1, 0, 0])
            an.annotations(page)
            # Przezroczystość bez zadeklarowanej przestrzeni mieszania (Tomasz 27.10, „Multiply”): przestrzeń
            # wybiera wtedy urządzenie — podgląd na ekran miesza w RGB, RIP i spłaszczenie (urządzenie
            # CMYK) w CMYK. Zmierzone: K50 × szarość 50 % w Multiply — podgląd 78, druk 100 (jaśniej);
            # krycie 50 % i Screen — też wyraźnie inaczej. Z /CS /DeviceCMYK podgląd = druk.
            if _real_transparency(an.transparency) > t0 and (grp is None or grp.get("/CS") is None):
                an.blend_undeclared = True
            pages.append({"index": i, "images": len(an.images) - before_imgs})
            # biały z overprintem → ułamki strony (y od góry), do ramek na podglądzie
            bx0, by0, bx1, by1 = an.page_box
            pw, ph = (bx1 - bx0) or 1, (by1 - by0) or 1
            an.white_boxes = getattr(an, "white_boxes", []) + [
                [round((b[0] - bx0) / pw, 5), round((by1 - b[3]) / ph, 5),
                 round((b[2] - b[0]) / pw, 5), round((b[3] - b[1]) / ph, 5)] for b in an.white_op[w0:]]

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
        "clipped_shading": an.clipped_shading,
        "clipped_shading_text": an.clipped_shading_text,
        "white_overprint": getattr(an, "white_boxes", []),
        "heavy_black": an.heavy_black,
        "transparency": dict(an.transparency),
        "fonts": [{"name": n, "embedded": e, "uses": c} for (n, e), c in an.fonts.most_common()],
        "parse_warnings": an.unknown_ops + (1 if an.truncated else 0),
        # analiza niepełna (budżet, głębokość, nieczytelny strumień) — jakość nie da wtedy „ok”/„vector”
        "partial": bool(an.partial),
        "partial_reason": "; ".join(PARTIAL_TEXT[k] for k in ("budget", "depth", "stream") if k in an.partial),
        "group_rgb": an.group_rgb,
        "blend_space_missing": an.blend_undeclared,
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
        import pdfutil
        dpi = pdfutil.raster_dpi(im)
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
            "parse_warnings": 0, "partial": False, "partial_reason": "", "group_rgb": False,
            "blend_space_missing": False,
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
