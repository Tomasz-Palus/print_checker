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
        self.transparency = Counter()   # rodzaj -> liczba
        self.inline_images = 0
        self.unknown_ops = 0
        self.fonts = Counter()          # (basefont, embedded) -> użycia Tf
        self.visited_forms = set()
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
        except Exception:
            pass

    # --- obrazy
    def _image(self, xobj, ctm, resources, name):
        try:
            key = xobj.objgen
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
                "xref": key[0] if isinstance(key, tuple) else None,
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
        if depth > 12:
            return
        try:
            ops = pikepdf.parse_content_stream(container)
        except Exception:
            self.unknown_ops += 1
            return
        stack = []
        fill_cs = {"family": "Gray"}   # domyślnie DeviceGray
        stroke_cs = {"family": "Gray"}
        fill_pattern_cs = None
        for operands, op in ops:
            o = str(op)
            try:
                if o == "q":
                    stack.append((ctm, fill_cs, stroke_cs))
                elif o == "Q":
                    if stack:
                        ctm, fill_cs, stroke_cs = stack.pop()
                elif o == "cm":
                    m = [float(x) for x in operands]
                    ctm = _mul(m, ctm)
                elif o == "g":
                    fill_cs = {"family": "Gray"}; self._record(fill_cs, "fill")
                elif o == "G":
                    stroke_cs = {"family": "Gray"}; self._record(stroke_cs, "stroke")
                elif o == "rg":
                    fill_cs = {"family": "RGB"}; self._record(fill_cs, "fill")
                elif o == "RG":
                    stroke_cs = {"family": "RGB"}; self._record(stroke_cs, "stroke")
                elif o == "k":
                    fill_cs = {"family": "CMYK"}; self._record(fill_cs, "fill")
                elif o == "K":
                    stroke_cs = {"family": "CMYK"}; self._record(stroke_cs, "stroke")
                elif o == "cs":
                    fill_cs = self.classify(operands[0], resources)
                elif o == "CS":
                    stroke_cs = self.classify(operands[0], resources)
                elif o in ("sc", "scn"):
                    if fill_cs.get("family") == "Pattern":
                        self._pattern(operands, resources, ctm, "fill", depth)
                    else:
                        self._record(fill_cs, "fill")
                elif o in ("SC", "SCN"):
                    if stroke_cs.get("family") == "Pattern":
                        self._pattern(operands, resources, ctm, "stroke", depth)
                    else:
                        self._record(stroke_cs, "stroke")
                elif o == "sh":
                    shd = resources.get("/Shading") if resources is not None else None
                    if shd is not None and operands[0] in shd:
                        self._record(self.classify(shd[operands[0]].get("/ColorSpace"), resources), "shading")
                elif o == "gs":
                    self._extgstate(operands[0], resources)
                elif o == "Tf":
                    self._font(operands[0], resources)
                elif o == "BI":
                    self.inline_images += 1
                    if operands and isinstance(operands[0], pikepdf.PdfInlineImage):
                        ii = operands[0]
                        try:
                            cs = ii.obj.get("/CS") or ii.obj.get("/ColorSpace")
                            self._record(self.classify(cs, resources), "inline")
                        except Exception:
                            pass
                elif o == "Do":
                    xod = resources.get("/XObject") if resources is not None else None
                    if xod is None or operands[0] not in xod:
                        continue
                    xo = xod[operands[0]]
                    st = str(xo.get("/Subtype", ""))
                    if st == "/Image":
                        self._image(xo, ctm, resources, operands[0])
                    elif st == "/Form":
                        self._form(xo, ctm, resources, depth)
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
        self.walk(xo, res, _mul(m, ctm), depth + 1)

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
            an.walk(page, res, [1, 0, 0, 1, 0, 0])
            pages.append({"index": i, "images": len(an.images) - before_imgs})

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
        return _summarize_pdf(an, pages, intents, meta, coverage, page_sizes)
    finally:
        pdf.close()


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
        "transparency": dict(an.transparency),
        "fonts": [{"name": n, "embedded": e, "uses": c} for (n, e), c in an.fonts.most_common()],
        "parse_warnings": an.unknown_ops,
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
