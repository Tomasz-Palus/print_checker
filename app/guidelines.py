"""
Wytyczne produktu (PDF z noname.tey.pl) — pobieranie i parsowanie.

Budowa PDF-a wytycznych (sprawdzone na 4 przykładach, 2026-09-03):

  strona 1  — opis A4 (595x842 pt). Cały tekst jest W KRZYWYCH (brak warstwy
              tekstowej). W wierszu z ikoną „DPI” stoi
              „Rozdzielczość: 120 ppi - skala 1:1”  albo
              „Rozdzielczość: 1200 ppi - skala 1:10”.
              Innych skal nie ma i nie będzie (ustalenie Tomasza).
              Skalę rozpoznajemy po SZEROKOŚCI grupy ścieżek z wartością
              (druga grupa w wierszu ikony DPI): ~92 pt dla 1:1, ~107 pt dla 1:10.
  strony 2+ — szablony, po jednym na stronę. Rozmiar strony w pt odpowiada
              dokładnie wymiarowi „W x H [mm]” z tekstu (1 mm = 72/25.4 pt).
              Tekst (normalna warstwa tekstowa): rola pliku (bold, największy
              rozmiar, np. „Dach 1”, „Przod”, „Wrota”, „Owijka”), wymiar
              „W x H [mm]”, nazwa produktu.
              Rysunki: niebieski = kształt produktu, czerwony = obszar
              ochronny, żółty = obszar technologiczny. Uwaga: „linie” są zwykle
              WYPEŁNIONYMI cienkimi pierścieniami (obrys zamieniony na fill),
              czasem prawdziwym stroke — dlatego SVG odtwarza fill/stroke 1:1
              z PDF-a zamiast rysować własne linie.

Cache: data/guidelines/<hash>.pdf + <hash>.json (wersjonowany PARSER_VERSION).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

import pymupdf

from products import requirements_url

PARSER_VERSION = 4
import paths
from version import UA

DATA_DIR = paths.GUIDELINES
MM_PER_PT = 25.4 / 72.0

# progi rozpoznania skali (szerokość grupy ścieżek z wartością w pt)
SCALE_WIDTH_THRESHOLD = 100.0


# ----------------------------------------------------------------------------
# Pobieranie
# ----------------------------------------------------------------------------
def pdf_path_for(hash_: str) -> str:
    return os.path.join(DATA_DIR, f"{hash_}.pdf")


def json_path_for(hash_: str) -> str:
    return os.path.join(DATA_DIR, f"{hash_}.json")


def download_pdf(hash_: str, timeout: float = 30.0) -> bytes:
    """Pobiera PDF wytycznych ze strony (zawsze przez sieć). Rzuca wyjątek przy braku sieci."""
    req = urllib.request.Request(
        requirements_url(hash_), headers={"User-Agent": UA}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if not data.startswith(b"%PDF"):
        raise RuntimeError("Serwer nie zwrócił pliku PDF (możliwa zmiana strony lub brak dostępu).")
    return data


def _write_atomic(path: str, data: bytes) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def fetch_pdf(hash_: str, force: bool = False, timeout: float = 30.0) -> str:
    """Zwraca ścieżkę do PDF-u w cache; pobiera tylko gdy brak (albo force)."""
    path = pdf_path_for(hash_)
    if os.path.exists(path) and not force and os.path.getsize(path) > 1000:
        return path
    _write_atomic(path, download_pdf(hash_, timeout=timeout))
    return path


# ----------------------------------------------------------------------------
# Skala (strona 1)
# ----------------------------------------------------------------------------
def _count_subpaths(items) -> int:
    """Liczba podścieżek w ścieżce (nowa podścieżka = start ≠ koniec poprzedniej)."""
    n, cur = 0, None
    for it in items:
        if it[0] == "re":
            n += 1; cur = None; continue
        p1 = it[1]
        pend = it[2] if it[0] == "l" else it[4] if it[0] == "c" else None
        if cur is None or abs(cur.x - p1.x) > 1e-3 or abs(cur.y - p1.y) > 1e-3:
            n += 1
        cur = pend
    return n


def detect_scale(page) -> dict:
    """Zwraca {'scale': '1:1'|'1:10'|None, 'method': str, 'value_width_pt': float|None}."""
    try:
        small_imgs = []
        for img in page.get_images(full=True):
            if img[2] < 300 and img[3] < 300:  # ikonki (~140 px), nie zdjęcie produktu
                for r in page.get_image_rects(img[0]):
                    if r.x0 < 100:  # lewa kolumna ikon
                        small_imgs.append(r)
        if not small_imgs:
            return {"scale": None, "method": "no-icons", "value_width_pt": None}
        dpi_icon = min(small_imgs, key=lambda r: r.y0)  # ikona DPI jest pierwsza od góry
        y0, y1 = dpi_icon.y0 - 4, dpi_icon.y1 + 4
        groups = []
        for dr in page.get_drawings():
            r = dr["rect"]
            if r.x0 > dpi_icon.x1 and r.y0 >= y0 and r.y1 <= y1 and r.width > 20:
                groups.append({"rect": r, "items": dr["items"]})
        groups.sort(key=lambda r: r["rect"].x0)
        if len(groups) < 2:
            return {"scale": None, "method": "no-text-groups", "value_width_pt": None}
        value = groups[1]  # [0] = „Rozdzielczość:”/„Resolution:”, [1] = „120 ppi - skala 1:1”
        w = float(value["rect"].width)
        n = _count_subpaths(value["items"])
        # Liczba podścieżek (glifów z uwzględnieniem dziur) jest niezależna od języka:
        #   „120 ppi - skala 1:1” / „120 ppi - scale 1:1”   -> 22
        #   „1200 ppi - skala 1:10” / „1200 ppi - scale 1:10” -> 26 (dwa dodatkowe „0”)
        #   „0 ppi – 1:0 scale” (wytyczne-zaślepka bez wymiaru) -> 21
        if n == 26:
            scale = "1:10"
        elif n == 22:
            scale = "1:1"
        elif n == 21:
            scale = None
        else:  # nieznany wariant – zapas po szerokości
            scale = "1:10" if w > SCALE_WIDTH_THRESHOLD else "1:1"
        return {"scale": scale, "method": f"subpaths={n}", "value_width_pt": round(w, 1)}
    except Exception as e:  # pragma: no cover
        return {"scale": None, "method": f"error: {e}", "value_width_pt": None}


# ----------------------------------------------------------------------------
# Szablony (strony 2+)
# ----------------------------------------------------------------------------
_DIM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\s*\[?\s*mm\s*\]?", re.I)


def _color_class(rgb) -> str:
    if not rgb:
        return "other"
    r, g, b = rgb
    if b > 0.5 and b > r + 0.2 and b >= g:
        return "shape"      # niebieski — kształt produktu
    if r > 0.6 and g < 0.45 and b < 0.45:
        return "safe"       # czerwony — obszar ochronny
    if r > 0.6 and g > 0.6 and b < 0.45:
        return "tech"       # żółty — obszar technologiczny
    return "other"


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _pt(p) -> str:
    return f"{_fmt(p.x)} {_fmt(p.y)}"


def _items_to_d(items) -> str:
    """Zamienia listę itemów PyMuPDF (l/c/re/qu) na atrybut d ścieżki SVG."""
    d = []
    cur = None  # aktualny punkt

    def moveto(p):
        nonlocal cur
        d.append(f"M{_pt(p)}")
        cur = p

    for it in items:
        kind = it[0]
        if kind == "l":
            p1, p2 = it[1], it[2]
            if cur is None or abs(cur.x - p1.x) > 1e-3 or abs(cur.y - p1.y) > 1e-3:
                moveto(p1)
            d.append(f"L{_pt(p2)}")
            cur = p2
        elif kind == "c":
            p1, p2, p3, p4 = it[1], it[2], it[3], it[4]
            if cur is None or abs(cur.x - p1.x) > 1e-3 or abs(cur.y - p1.y) > 1e-3:
                moveto(p1)
            d.append(f"C{_pt(p2)} {_pt(p3)} {_pt(p4)}")
            cur = p4
        elif kind == "re":
            r = it[1]
            orient = it[2] if len(it) > 2 else 1
            if orient is not None and orient < 0:   # przeciwny kierunek = „dziura” przy nonzero
                d.append(f"M{_fmt(r.x0)} {_fmt(r.y0)}V{_fmt(r.y1)}H{_fmt(r.x1)}V{_fmt(r.y0)}Z")
            else:
                d.append(f"M{_fmt(r.x0)} {_fmt(r.y0)}H{_fmt(r.x1)}V{_fmt(r.y1)}H{_fmt(r.x0)}Z")
            cur = None
        elif kind == "qu":
            q = it[1]
            d.append(f"M{_pt(q.ul)}L{_pt(q.ur)}L{_pt(q.lr)}L{_pt(q.ll)}Z")
            cur = None
    return "".join(d)


def _rgb_hex(rgb) -> str:
    r, g, b = [max(0, min(255, int(round(c * 255)))) for c in rgb]
    return f"#{r:02x}{g:02x}{b:02x}"


def drawings_to_svg(page) -> tuple[str, dict]:
    """SVG z samych rysunków strony (bez tekstu), viewBox w pt strony.
    Każda ścieżka dostaje class = safe|shape|tech|other (wg koloru)."""
    r = page.rect
    parts = []
    counts = {"safe": 0, "shape": 0, "tech": 0, "other": 0}
    for dr in page.get_drawings():
        d = _items_to_d(dr["items"])
        if not d:
            continue
        typ = dr.get("type", "")
        fill = dr.get("fill")
        stroke = dr.get("color")
        cls = _color_class(fill if "f" in typ else stroke)
        counts[cls] += 1
        attrs = [f'class="{cls}"', f'd="{d}"']
        if "f" in typ and fill:
            attrs.append(f'fill="{_rgb_hex(fill)}"')
            if dr.get("fill_opacity") is not None and dr["fill_opacity"] < 1:
                attrs.append(f'fill-opacity="{_fmt(dr["fill_opacity"])}"')
            if dr.get("even_odd"):
                attrs.append('fill-rule="evenodd"')
        else:
            attrs.append('fill="none"')
        if "s" in typ and stroke:
            attrs.append(f'stroke="{_rgb_hex(stroke)}"')
            attrs.append(f'stroke-width="{_fmt(dr.get("width") or 1.0)}"')
            if dr.get("dashes") and dr["dashes"] not in ("[] 0", "[ ] 0"):
                m = re.findall(r"[\d.]+", dr["dashes"].split("]")[0])
                if m:
                    attrs.append(f'stroke-dasharray="{" ".join(m)}"')
            if dr.get("lineCap"):
                cap = {0: "butt", 1: "round", 2: "square"}.get(dr["lineCap"][0] if isinstance(dr["lineCap"], tuple) else dr["lineCap"])
                if cap:
                    attrs.append(f'stroke-linecap="{cap}"')
        parts.append(f"<path {' '.join(attrs)}/>")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(r.width)} {_fmt(r.height)}" '
        f'width="{_fmt(r.width)}" height="{_fmt(r.height)}" preserveAspectRatio="none">'
        + "".join(parts) + "</svg>"
    )
    return svg, counts


def parse_template_page(page, index: int) -> dict:
    spans = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            for s in line["spans"]:
                t = s["text"].replace("\x01", "")  # \x01 = glif spoza mapy fontu (np. Ø, ś)
                if t.strip():
                    spans.append({"text": t, "size": s["size"], "bold": "bold" in s["font"].lower(), "y": s["bbox"][1]})
    # scal spany w tej samej linii (np. nazwa produktu rozbita na 2 spany)
    lines: list[dict] = []
    for s in sorted(spans, key=lambda s: (round(s["y"]), 0)):
        if lines and abs(lines[-1]["y"] - s["y"]) < s["size"] * 0.5:
            lines[-1]["text"] += s["text"]
        else:
            lines.append(dict(s))

    for ln in lines:
        ln["text"] = " ".join(ln["text"].split())
    role, dims, product_name = None, None, None
    for ln in lines:
        m = _DIM_RE.search(ln["text"])
        if m and dims is None:
            dims = (float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", ".")))
            continue
    text_lines = [ln for ln in lines if not _DIM_RE.search(ln["text"])]
    if text_lines:
        role_ln = max(text_lines, key=lambda ln: (ln["bold"], ln["size"]))
        role = role_ln["text"]
        rest = [ln for ln in text_lines if ln is not role_ln]
        if rest:
            product_name = max(rest, key=lambda ln: len(ln["text"]))["text"]

    svg, counts = drawings_to_svg(page)
    r = page.rect
    # „0 x 0 [mm]” = wytyczne-zaślepka dla produktów o zmiennym wymiarze (np. adFrame LMD do 3mb):
    # strona PDF ma wtedy umowny rozmiar, a wymiar wydruku trzeba podać ręcznie
    dims_missing = dims is not None and (dims[0] <= 0 or dims[1] <= 0)
    return {
        "page": index,                      # indeks strony w PDF-ie (od 0)
        "role": role or f"Szablon {index}",
        "width_mm": dims[0] if dims else round(r.width * MM_PER_PT, 2),
        "height_mm": dims[1] if dims else round(r.height * MM_PER_PT, 2),
        "dims_from_text": dims is not None,
        "dims_missing": dims_missing,
        "product_name": product_name,
        "page_width_pt": round(r.width, 3),
        "page_height_pt": round(r.height, 3),
        "svg": svg,
        "layers": counts,
    }


def parse_pdf(path: str) -> dict:
    doc = pymupdf.open(path)
    try:
        if len(doc) < 2:
            raise RuntimeError("PDF wytycznych ma mniej niż 2 strony — brak szablonu.")
        scale = detect_scale(doc[0])
        templates = [parse_template_page(doc[i], i) for i in range(1, len(doc))]
        return {
            "parser_version": PARSER_VERSION,
            "parsed_at": time.time(),
            "page_count": len(doc),
            "scale": scale["scale"],
            "scale_detect": scale,
            "templates": templates,
        }
    finally:
        doc.close()


# ----------------------------------------------------------------------------
# API modułu
# ----------------------------------------------------------------------------
def _load_cached_json(hash_: str) -> dict | None:
    jpath = json_path_for(hash_)
    if not os.path.exists(jpath):
        return None
    try:
        with open(jpath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if data.get("parser_version") == PARSER_VERSION else None


def _save_json(hash_: str, data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(json_path_for(hash_), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def get_guidelines(hash_: str, force: bool = False) -> dict:
    """Wytyczne z cache (JSON) — pobiera z sieci tylko, gdy w cache nic nie ma (albo force).
    Używane przez indeks wymiarów. Do pracy z produktem służy get_guidelines_fresh."""
    if not force:
        data = _load_cached_json(hash_)
        if data:
            return data
    pdf = fetch_pdf(hash_, force=force)
    data = parse_pdf(pdf)
    data.update({"hash": hash_, "source": "remote", "fetched_at": time.time()})
    _save_json(hash_, data)
    return data


def get_guidelines_fresh(hash_: str, timeout: float = 20.0) -> dict:
    """ZAWSZE próbuje pobrać aktualny PDF ze strony (potwierdzenie produktu musi dawać
    bieżący szablon). Gdy pobrany plik jest bajt w bajt taki sam jak w cache, nie parsuje
    ponownie. Gdy sieć nie działa — zwraca kopię z cache oznaczoną `stale=True`
    (+ `stale_error`), a gdy cache też nie ma — rzuca wyjątek."""
    path = pdf_path_for(hash_)
    try:
        fresh = download_pdf(hash_, timeout=timeout)
    except Exception as e:
        cached = _load_cached_json(hash_)
        if not cached and os.path.exists(path) and os.path.getsize(path) > 1000:
            cached = parse_pdf(path)          # jest PDF w cache, ale bez JSON-u (np. stara wersja parsera)
            cached.update({"hash": hash_, "fetched_at": os.path.getmtime(path)})
            _save_json(hash_, cached)
        if cached:
            cached = dict(cached)
            cached["stale"] = True
            cached["stale_error"] = f"{type(e).__name__}: {e}"
            cached["source"] = "cache"
            return cached
        raise
    same = False
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                same = f.read() == fresh
        except OSError:
            same = False
    if same:
        cached = _load_cached_json(hash_)
        if cached:
            cached = dict(cached)
            cached.update({"source": "remote", "stale": False, "fetched_at": time.time(), "unchanged": True})
            _save_json(hash_, cached)
            return cached
    _write_atomic(path, fresh)
    data = parse_pdf(path)
    data.update({"hash": hash_, "source": "remote", "stale": False, "fetched_at": time.time(), "unchanged": False})
    _save_json(hash_, data)
    return data


def public_view(data: dict, include_svg: bool = True) -> dict:
    out = {k: v for k, v in data.items() if k != "templates"}
    out["templates"] = []
    for t in data["templates"]:
        t2 = dict(t)
        if not include_svg:
            t2.pop("svg", None)
        out["templates"].append(t2)
    return out
