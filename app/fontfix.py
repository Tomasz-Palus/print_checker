"""Nieosadzone fonty — jak sobie z nimi poradzić BEZ kroju zastępczego.

Ustalenie Tomasza (24.09): program ma pozwolić osobie nietechnicznej przygotować plik do
druku bez grafika DTP. Font OSADZONY nie jest problemem — kształty liter są w pliku (tak samo
korzysta z nich Photoshop). Problemem jest font NIEOSADZONY: w pliku jest tylko nazwa,
bez kształtów. Test w Photoshopie (pliki `Test_font_*.pdf`): osadzony Lora Italic → poprawny,
nieosadzony → same kropki. Krój zastępczy jest wykluczony.

Co robimy, po kolei:
  1. `text_usage` — czy tekst w tym foncie w ogóle się DRUKUJE. Tekst w trybie niewidocznym
     (Tr 3 / Tr 7 — np. warstwa OCR ze skanu) na wydruk nie trafia, więc brak fontu nic nie
     zmienia.
  2. `fetch` — pobieramy PRAWDZIWY font po nazwie z Google Fonts (API css2, a gdy nie działa —
     oficjalne repozytorium google/fonts na GitHubie). Wiele fontów z plików klientów jest
     darmowych. Pobrane leżą w `data/fonts` i drugi raz nie są ściągane.
  3. `embed` — osadzamy go w PDF-ie. Litery dopasowujemy po Unicode (ToUnicode / kodowanie
     → cmap fontu), a nie po numerach glifów, bo numeracja w pobranym pliku może być inna niż
     w foncie, którego użył projektant. Jeśli fontowi brakuje choć jednej potrzebnej litery —
     odmawiamy (to byłby częściowy krój zastępczy).

Po osadzeniu plik jest „zwykłym" plikiem z osadzonym fontem: krzywe, spłaszczenie, podgląd
i Photoshop działają na nim normalnie.
"""
from __future__ import annotations

import io
import os
import re
import urllib.request

import pikepdf

import paths
from version import VERSION

FONT_DIR = paths.FONTS
UA_TTF = "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)"   # stary UA → Google daje .ttf
TIMEOUT = 20

_WEIGHTS = [  # najdłuższe najpierw — „extrabold" zanim „bold"
    ("extralight", 200), ("ultralight", 200), ("extrabold", 800), ("ultrabold", 800),
    ("semibold", 600), ("demibold", 600), ("hairline", 100), ("thin", 100),
    ("light", 300), ("regular", 400), ("normal", 400), ("book", 400), ("roman", 400),
    ("medium", 500), ("bold", 700), ("black", 900), ("heavy", 900),
]


# --------------------------------------------------------------------------------------
# 1. czy tekst się drukuje
# --------------------------------------------------------------------------------------
def text_usage(path: str) -> dict:
    """{nazwa fontu: {"widoczne": n, "niewidoczne": m}} — liczba operatorów pokazujących
    tekst, z podziałem na tryb widoczny i niewidoczny (Tr 3 = niewidoczny, Tr 7 = tylko
    maska przycięcia — oba nie zostawiają farby)."""
    out: dict = {}

    def walk(container, resources, depth, seen):
        if depth > 10:
            return
        try:
            ops = pikepdf.parse_content_stream(container)
        except Exception:
            return
        tr, font, stack = 0, None, []
        fonts = resources.get("/Font") if resources is not None else None
        for operands, op in ops:
            o = str(op)
            try:
                if o == "q":
                    stack.append((tr, font))
                elif o == "Q":
                    if stack:
                        tr, font = stack.pop()
                elif o == "Tr":
                    tr = int(operands[0])
                elif o == "Tf":
                    fd = fonts[operands[0]] if fonts is not None and operands[0] in fonts else None
                    font = _base(fd) if fd is not None else None
                elif o in ("Tj", "TJ", "'", '"') and font:
                    e = out.setdefault(font, {"widoczne": 0, "niewidoczne": 0})
                    e["niewidoczne" if tr in (3, 7) else "widoczne"] += 1
                elif o == "Do" and resources is not None:
                    xo = resources.get("/XObject")
                    if xo is None or operands[0] not in xo:
                        continue
                    x = xo[operands[0]]
                    if str(x.get("/Subtype", "")) != "/Form" or x.objgen in seen:
                        continue
                    walk(x, x.get("/Resources") or resources, depth + 1, seen | {x.objgen})
            except Exception:
                continue

    with pikepdf.open(path) as pdf:
        for pg in pdf.pages:
            walk(pg, pg.obj.get("/Resources"), 0, frozenset())
    return out


def _base(fd) -> str:
    return str(fd.get("/BaseFont", "?")).lstrip("/")


# --------------------------------------------------------------------------------------
# 2. pobieranie
# --------------------------------------------------------------------------------------
def parse_name(base: str, weight_hint: float | None = None, italic_hint: bool = False) -> dict:
    """„ABCDEF+OpenSans-SemiBoldItalic" → {family: "Open Sans", key: "opensans",
    weight: 600, italic: True}."""
    n = base.split("+")[-1]
    fam, style = n, ""
    for sep in ("-", ",", "_"):
        if sep in n:
            fam, style = n.split(sep, 1)
            break
    else:                                     # „LoraBoldItalic" — odcinamy znane końcówki
        low = n.lower()
        for suf in ("italic", "oblique"):
            if low.endswith(suf):
                style = n[-len(suf):] + style
                n = n[:-len(suf)]
                low = low[:-len(suf)]
        for k, _ in _WEIGHTS:
            if low.endswith(k) and len(low) > len(k):
                style = n[-len(k):] + style
                n = n[:-len(k)]
                break
        fam = n
    fam = re.sub(r"(MT|PS|Std|Pro)$", "", fam) if fam not in ("Pro",) else fam
    s = style.lower().replace(" ", "")
    italic = italic_hint or "italic" in s or "oblique" in s or s.endswith("it")
    weight = None
    for k, w in _WEIGHTS:
        if k in s:
            weight = w
            break
    if weight is None:
        weight = int(round(weight_hint / 100) * 100) if weight_hint else 400
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])", " ", fam).strip()
    return {"family": spaced, "key": re.sub(r"[^a-z0-9]", "", fam.lower()),
            "weight": weight, "italic": italic}


def _get(url: str, ua: str | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua or f"adChecker/{VERSION}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _from_css(p: dict) -> bytes | None:
    fam = p["family"].replace(" ", "+")
    url = (f"https://fonts.googleapis.com/css2?family={fam}:ital,wght@"
           f"{1 if p['italic'] else 0},{p['weight']}")
    css = _get(url, UA_TTF).decode("utf-8", "replace")
    urls = re.findall(r"url\((https://[^)]+)\)", css)
    datas = []
    for u in urls:
        try:
            datas.append(_to_ttf(_get(u, UA_TTF)))
        except Exception:
            continue
    datas = [d for d in datas if d]
    if not datas:
        return None
    # kilka plików (podzbiory latin / latin-ext …) — bierzemy ten z największą liczbą znaków
    return max(datas, key=lambda d: len(_cmap(d)))


def _from_github(p: dict) -> bytes | None:
    base = "https://raw.githubusercontent.com/google/fonts/main"
    meta, lic = None, None
    for lic in ("ofl", "apache", "ufl"):
        try:
            meta = _get(f"{base}/{lic}/{p['key']}/METADATA.pb").decode("utf-8", "replace")
            break
        except Exception:
            continue
    if not meta:
        return None
    wpis = []
    for blok in re.findall(r"fonts \{(.*?)\n\}", meta, re.S):
        st = re.search(r'style: "(\w+)"', blok)
        wg = re.search(r"weight: (\d+)", blok)
        fn = re.search(r'filename: "([^"]+)"', blok)
        if st and wg and fn:
            wpis.append((st.group(1) == "italic", int(wg.group(1)), fn.group(1)))
    cand = [w for w in wpis if w[0] == p["italic"]]
    if not cand:
        return None
    zmienny = [w for w in cand if "[" in w[2]]
    if zmienny:
        data = _get(f"{base}/{lic}/{p['key']}/{urllib.request.quote(zmienny[0][2])}")
        return _instance(data, p["weight"])
    dokladny = [w for w in cand if w[1] == p["weight"]]
    if not dokladny:
        return None
    return _get(f"{base}/{lic}/{p['key']}/{urllib.request.quote(dokladny[0][2])}")


def _instance(data: bytes, weight: int) -> bytes | None:
    """Z fontu zmiennego wycinamy statyczną grubość (tak robi też Google Fonts API)."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    f = TTFont(io.BytesIO(data))
    if "fvar" not in f:
        return data
    loc = {}
    for ax in f["fvar"].axes:
        if ax.axisTag == "wght":
            if not (ax.minValue <= weight <= ax.maxValue):
                return None               # tej grubości w rodzinie nie ma
            loc["wght"] = weight
        else:
            loc[ax.axisTag] = ax.defaultValue
    inst = instancer.instantiateVariableFont(f, loc)
    buf = io.BytesIO()
    inst.save(buf)
    return buf.getvalue()


def _to_ttf(data: bytes) -> bytes | None:
    if data[:4] == b"wOF2" or data[:4] == b"wOFF":
        from fontTools.ttLib import TTFont
        f = TTFont(io.BytesIO(data))
        f.flavor = None
        buf = io.BytesIO()
        f.save(buf)
        return buf.getvalue()
    return data


def _cmap(data: bytes) -> dict:
    from fontTools.ttLib import TTFont
    try:
        return TTFont(io.BytesIO(data)).getBestCmap() or {}
    except Exception:
        return {}


def fetch(base: str, weight_hint: float | None = None, italic_hint: bool = False) -> tuple[bytes | None, str]:
    """Font po nazwie z PDF-a: (bajty .ttf albo None, skąd / dlaczego nie)."""
    p = parse_name(base, weight_hint, italic_hint)
    os.makedirs(FONT_DIR, exist_ok=True)
    cache = os.path.join(FONT_DIR, f"{p['key']}-{p['weight']}{'i' if p['italic'] else ''}.ttf")
    if os.path.exists(cache):
        return open(cache, "rb").read(), f"Google Fonts: {p['family']} (z pamięci)"
    powody = []
    for zrodlo, fn in (("Google Fonts", _from_css), ("Google Fonts (GitHub)", _from_github)):
        try:
            data = fn(p)
        except Exception as e:
            powody.append(f"{zrodlo}: {type(e).__name__}")
            continue
        if data:
            with open(cache, "wb") as fh:
                fh.write(data)
            return data, f"{zrodlo}: {p['family']} {p['weight']}{' kursywa' if p['italic'] else ''}"
        powody.append(f"{zrodlo}: brak „{p['family']}”")
    return None, "; ".join(powody)


# --------------------------------------------------------------------------------------
# 3. osadzanie
# --------------------------------------------------------------------------------------
def _parse_tounicode(stream) -> dict:
    """CMap ToUnicode → {kod: tekst}. Obsługuje bfchar i bfrange (także z tablicą)."""
    try:
        s = bytes(stream.read_bytes()).decode("latin-1")
    except Exception:
        return {}
    h = lambda x: int(x, 16)
    u = lambda x: bytes.fromhex(x).decode("utf-16-be", "replace")
    m = {}
    for blok in re.findall(r"beginbfchar(.*?)endbfchar", s, re.S):
        for a, b in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", blok):
            m[h(a)] = u(b)
    for blok in re.findall(r"beginbfrange(.*?)endbfrange", s, re.S):
        for a, b, rest in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(\[[^\]]*\]|<[0-9A-Fa-f]*>)", blok):
            lo, hi = h(a), h(b)
            if rest.startswith("["):
                for i, v in enumerate(re.findall(r"<([0-9A-Fa-f]*)>", rest)):
                    m[lo + i] = u(v)
            else:
                start = bytearray(bytes.fromhex(rest[1:-1]))
                for i in range(hi - lo + 1):
                    v = bytearray(start)
                    v[-1] = (v[-1] + i) & 0xFF
                    m[lo + i] = bytes(v).decode("utf-16-be", "replace")
    return m


def _simple_unicodes(fd) -> dict:
    """Czcionka prosta: kod → znak z kodowania (Encoding + Differences)."""
    from fontTools import agl
    enc = fd.get("/Encoding")
    base, diffs = "/StandardEncoding", {}
    if isinstance(enc, pikepdf.Name):
        base = str(enc)
    elif isinstance(enc, pikepdf.Dictionary):
        base = str(enc.get("/BaseEncoding", "/StandardEncoding"))
        code = 0
        for x in enc.get("/Differences", []):
            if isinstance(x, int) or (hasattr(x, "is_integer") and x.is_integer):
                code = int(x)
            else:
                diffs[code] = str(x).lstrip("/")
                code += 1
    codec = {"/WinAnsiEncoding": "cp1252", "/MacRomanEncoding": "mac_roman"}.get(base, "latin-1")
    fc = int(fd.get("/FirstChar", 32))
    lc = int(fd.get("/LastChar", 255))
    m = {}
    for c in range(fc, lc + 1):
        if c in diffs:
            t = agl.toUnicode(diffs[c])
            if t:
                m[c] = t
        else:
            try:
                ch = bytes([c]).decode(codec)
                if ch.isprintable():
                    m[c] = ch
            except Exception:
                pass
    return m


def _used_codes(pdf, target_objgens: set) -> dict:
    """Kody faktycznie użyte w tekście dla wskazanych fontów — sprawdzamy tylko te litery,
    które stoją w pliku (font nie musi mieć całego alfabetu)."""
    used: dict = {}

    def walk(container, resources, depth, seen):
        if depth > 10:
            return
        try:
            ops = pikepdf.parse_content_stream(container)
        except Exception:
            return
        fonts = resources.get("/Font") if resources is not None else None
        cur, two = None, False
        for operands, op in ops:
            o = str(op)
            try:
                if o == "Tf" and fonts is not None and operands[0] in fonts:
                    f = fonts[operands[0]]
                    cur = f.objgen if f.objgen in target_objgens else None
                    two = str(f.get("/Subtype", "")) == "/Type0"
                elif cur and o in ("Tj", "'", '"', "TJ"):
                    items = operands[0] if o == "TJ" else [operands[-1]]
                    for it in items:
                        if not isinstance(it, pikepdf.String):
                            continue                 # liczby w TJ to odstępy, nie litery
                        b = bytes(it)
                        s = used.setdefault(cur, set())
                        if two:
                            s.update(int.from_bytes(b[i:i + 2], "big") for i in range(0, len(b) - 1, 2))
                        else:
                            s.update(b)
                elif o == "Do" and resources is not None:
                    xo = resources.get("/XObject")
                    if xo is None or operands[0] not in xo:
                        continue
                    x = xo[operands[0]]
                    if str(x.get("/Subtype", "")) == "/Form" and x.objgen not in seen:
                        walk(x, x.get("/Resources") or resources, depth + 1, seen | {x.objgen})
            except Exception:
                continue

    for pg in pdf.pages:
        walk(pg, pg.obj.get("/Resources"), 0, frozenset())
    return used


def missing(path: str) -> list[dict]:
    """Fonty nieosadzone i niestandardowe: [{name, objgens, widoczny}]."""
    from pdfutil import is_base14
    usage = text_usage(path)
    wynik: dict = {}
    with pikepdf.open(path) as pdf:
        for obj in pdf.objects:
            if not isinstance(obj, pikepdf.Dictionary) or obj.get("/Type") != "/Font":
                continue
            st = str(obj.get("/Subtype", ""))
            if st in ("/Type3", "/CIDFontType0", "/CIDFontType2"):
                continue
            name = _base(obj)
            if is_base14(name):
                continue
            desc = obj.get("/FontDescriptor")
            if st == "/Type0":
                try:
                    desc = obj["/DescendantFonts"][0].get("/FontDescriptor")
                except Exception:
                    desc = None
            if desc is not None and any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                continue
            e = wynik.setdefault(name, {"name": name, "objgens": [], "widoczny": False})
            e["objgens"].append(list(obj.objgen))
            u = usage.get(name) or {}
            e["widoczny"] = e["widoczny"] or bool(u.get("widoczne")) or not u
    return list(wynik.values())


def embed(src: str, dst: str, fetcher=fetch) -> dict:
    """Osadza w pliku pobrane fonty dla wszystkich WIDOCZNYCH nieosadzonych fontów.
    Zwraca {"osadzone": [(nazwa, źródło)], "niewidoczne": [nazwy], "brak": [(nazwa, powód)]}.
    Plik `dst` powstaje tylko wtedy, gdy coś osadzono."""
    from fontTools.ttLib import TTFont
    brak, osadzone, niewidoczne = [], [], []
    lista = missing(src)
    if not lista:
        return {"osadzone": [], "niewidoczne": [], "brak": []}
    with pikepdf.open(src) as pdf:
        targets = {tuple(g) for e in lista for g in e["objgens"]}
        used = _used_codes(pdf, targets)
        for e in lista:
            if not e["widoczny"]:
                niewidoczne.append(e["name"])
                continue
            fonts = [pdf.get_object(*g) for g in e["objgens"]]
            f0 = fonts[0]
            desc0 = f0.get("/FontDescriptor")
            if str(f0.get("/Subtype", "")) == "/Type0":
                desc0 = f0["/DescendantFonts"][0].get("/FontDescriptor")
            wh = float(desc0.get("/FontWeight")) if desc0 is not None and "/FontWeight" in desc0 else None
            ital = bool(desc0 is not None and float(desc0.get("/ItalicAngle", 0) or 0) != 0)
            data, skad = fetcher(e["name"], wh, ital)
            if not data:
                brak.append((e["name"], skad))
                continue
            try:
                tt = TTFont(io.BytesIO(data))
                cmap = tt.getBestCmap() or {}
                gid = {n: i for i, n in enumerate(tt.getGlyphOrder())}
            except Exception as ex:
                brak.append((e["name"], f"uszkodzony plik fontu ({type(ex).__name__})"))
                continue
            ok, powod = True, ""
            plan = []
            for f in fonts:
                sub = str(f.get("/Subtype", ""))
                kody = used.get(f.objgen, set())
                if sub == "/Type0":
                    if str(f.get("/Encoding", "")) != "/Identity-H" or "/ToUnicode" not in f:
                        ok, powod = False, "nietypowe kodowanie tekstu (bez ToUnicode / nie Identity-H)"
                        break
                    tu = _parse_tounicode(f["/ToUnicode"])
                    mapa = {}
                    for c in kody:
                        t = tu.get(c, "")
                        g = cmap.get(ord(t[0])) if t else None
                        if g is None:
                            ok, powod = False, f"w pobranym foncie brakuje znaku „{t or '?'}”"
                            break
                        mapa[c] = gid.get(g, 0)
                    if not ok:
                        break
                    plan.append((f, "cid", mapa))
                else:
                    uni = _simple_unicodes(f)
                    for c in kody:
                        t = uni.get(c)
                        if t and ord(t[0]) not in cmap and not t.isspace():
                            ok, powod = False, f"w pobranym foncie brakuje znaku „{t}”"
                            break
                    if not ok:
                        break
                    plan.append((f, "simple", None))
            if not ok:
                brak.append((e["name"], powod))
                continue
            ff = pdf.make_stream(data)
            ff["/Length1"] = len(data)
            for f, kind, mapa in plan:
                if kind == "cid":
                    d = f["/DescendantFonts"][0]
                    d["/Subtype"] = pikepdf.Name("/CIDFontType2")
                    n = (max(mapa) + 1) if mapa else 1
                    arr = bytearray(2 * n)
                    for c, g in mapa.items():
                        arr[2 * c:2 * c + 2] = g.to_bytes(2, "big")
                    d["/CIDToGIDMap"] = pdf.make_stream(bytes(arr))
                    desc = d.get("/FontDescriptor")
                else:
                    f["/Subtype"] = pikepdf.Name("/TrueType")
                    desc = f.get("/FontDescriptor")
                    if desc is None:
                        desc = pdf.make_indirect(pikepdf.Dictionary(
                            Type=pikepdf.Name("/FontDescriptor"), FontName=pikepdf.Name("/" + e["name"]),
                            Flags=32, FontBBox=[0, -250, 1000, 900], ItalicAngle=0, Ascent=900,
                            Descent=-250, CapHeight=700, StemV=80))
                        f["/FontDescriptor"] = desc
                    fl = int(desc.get("/Flags", 32))
                    desc["/Flags"] = (fl & ~4) | 32          # nie-symboliczny: kodowanie → Unicode → glif
                    if "/Encoding" not in f:
                        f["/Encoding"] = pikepdf.Name("/StandardEncoding")
                for k in ("/FontFile", "/FontFile3"):
                    if k in desc:
                        del desc[k]
                desc["/FontFile2"] = ff
            osadzone.append((e["name"], skad))
        if osadzone:
            pdf.save(dst)
    return {"osadzone": osadzone, "niewidoczne": niewidoczne, "brak": brak}
