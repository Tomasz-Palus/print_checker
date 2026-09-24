"""
Sugerowanie produktu na podstawie nazwy wgranego pliku.

Obserwacja (przykładowe pliki): nazwa pliku to zwykle nazwa produktu z
zamienionymi znakami specjalnymi na "_" plus dopiski (_1, _przod, _tyl,
timestamp), np.
    Wydruk_adFrame_LMD_LMS_LMSM__do_3mb_medium250__1.pdf
    -> "Wydruk adFrame LMD/LMS/LMSM (do 3mb/medium250)"
    adWall_Vario_Prosta_Light_300_dwustronne_przod.pdf
    -> "adWall Vario Prosta Light 300 dwustronne"

Algorytm:
    1. normalizacja: małe litery, polskie znaki -> ascii, wszystko co nie jest
       literą/cyfrą -> spacja; z nazwy pliku usuwamy typowe dopiski,
    2. punktacja = pokrycie tokenów produktu w nazwie pliku (ważone długością
       tokenu) + bonus za dokładne zawieranie znormalizowanej nazwy produktu
       w nazwie pliku + podobieństwo sekwencyjne (difflib),
    3. zwracamy top N z wynikiem >= progu.
"""
from __future__ import annotations

import difflib
import os
import re
import unicodedata

_STRIP_WORDS = {
    "przod", "front", "final", "v", "ok", "druk", "print", "copy",
    "kopia", "cmyk", "rgb", "x", "wydruk",
}
_PARENS_RE = re.compile(r"\([^)]*\)")


def _ascii(s: str) -> str:
    s = s.replace("ł", "l").replace("Ł", "L")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def normalize(s: str) -> str:
    s = _ascii(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


_SYNONYMS = {
    "jednostronne": "jednostronny", "jednostronna": "jednostronny",
    "dwustronne": "dwustronny", "dwustronna": "dwustronny",
    "back": "tyl",
}


def tokens(s: str) -> list[str]:
    return [_SYNONYMS.get(t, t) for t in normalize(s).split()]


def filename_tokens(filename: str) -> list[str]:
    base = os.path.splitext(os.path.basename(filename))[0]
    toks = tokens(base)
    out = []
    for t in toks:
        if t in _STRIP_WORDS:
            continue
        if t.isdigit() and len(t) >= 8:  # timestampy / hashe
            continue
        out.append(t)
    return out


def score(filename: str, product_name: str, product_code: str = "") -> float:
    ft = filename_tokens(filename)
    if not ft:
        return 0.0
    fset = set(ft)
    fjoined = " ".join(ft)
    fcompact = fjoined.replace(" ", "")

    pt = [t for t in tokens(product_name) if t not in ("wydruk",)]
    if not pt:
        return 0.0

    # pokrycie tokenów produktu (ważone długością; liczby ważniejsze)
    total = 0.0
    hit = 0.0
    for t in pt:
        w = len(t) + (3 if any(c.isdigit() for c in t) else 0)
        total += w
        if t in fset or (len(t) >= 4 and t in fcompact):
            hit += w
    coverage = hit / total if total else 0.0

    # pokrycie w drugą stronę (ile tokenów pliku wyjaśnia produkt) – karze
    # produkty ogólne, gdy plik ma więcej szczegółów
    pset = set(pt)
    pcompact = "".join(pt)
    fhit = sum(1 for t in ft if t in pset or (len(t) >= 4 and t in pcompact))
    fcov = fhit / len(ft)

    # dokładne zawieranie
    pn = " ".join(pt)
    contains = 1.0 if pn and pn in fjoined else 0.0

    seq = difflib.SequenceMatcher(None, fjoined, pn).ratio()

    # kod produktu w nazwie pliku – mocny sygnał
    code_hit = 0.0
    if product_code:
        cn = normalize(product_code).replace(" ", "")
        if len(cn) >= 6 and cn in fcompact:
            code_hit = 1.0

    return 0.55 * coverage + 0.15 * fcov + 0.15 * contains + 0.10 * seq + 0.25 * code_hit


def suggest(filename: str, products: list[dict], limit: int = 5, threshold: float = 0.45) -> list[dict]:
    scored = []
    for p in products:
        s = score(filename, p["name"], p.get("code", ""))
        if s >= threshold:
            scored.append((s, p))
    scored.sort(key=lambda x: (-x[0], len(x[1]["name"])))
    return [dict(p, score=round(s, 3), basis="name") for s, p in scored[:limit]]


# ----------------------------------------------------------------------------
# Sugestie po WYMIARZE pliku (gdy nazwa nic nie mówi)
# ----------------------------------------------------------------------------
# Źródła wymiaru produktu:
#   1. indeks szablonów (data/template_index.json, z PDF-ów wytycznych) — pewne,
#      ze skalą; 2. nazwa produktu („100x250” = cm, „49,6x297,6cm”, „600” = szerokość
#      w cm) — przybliżone, bez skali.
# Plik może być w dobrej skali albo złej (1:1 zamiast 1:10 i odwrotnie), więc
# porównujemy wymiar pliku z rozmiarem wydruku P ORAZ z P/10.
_NAME_WH = re.compile(r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\s*(cm|mm|m)?\b")
_NAME_W = re.compile(r"(?<![\dxX×,.])(\d{2,4})(?![\dxX×,.])")


def _near(a: float, b: float, rel: float, abs_mm: float) -> bool:
    return abs(a - b) <= max(abs_mm, rel * max(a, b))


def _match_dims(fw: float, fh: float, W: float, H: float | None, rel: float, abs_mm: float) -> bool:
    """Plik (fw×fh) pasuje do W×H w dowolnej orientacji; H=None -> tylko szerokość."""
    if H is None:
        return _near(fw, W, rel, abs_mm) or _near(fh, W, rel, abs_mm)
    return (_near(fw, W, rel, abs_mm) and _near(fh, H, rel, abs_mm)) or \
           (_near(fw, H, rel, abs_mm) and _near(fh, W, rel, abs_mm))


def _dims_err(fw: float, fh: float, W: float, H: float) -> tuple[float, bool]:
    """Względna odchyłka wymiaru pliku od szablonu (w lepszej orientacji) i czy obrócony."""
    e1 = max(abs(fw - W), abs(fh - H)) / max(W, H, 1e-6)
    e2 = max(abs(fw - H), abs(fh - W)) / max(W, H, 1e-6)
    return (e1, False) if e1 <= e2 else (e2, True)


def dims_from_product_name(name: str) -> tuple[float, float | None] | None:
    """(W_mm, H_mm|None) z nazwy produktu albo None. Jednostka domyślna: cm.
    Pary małych liczb (np. namioty „3x3”, „8x8”) to metry — pomijamy (za mało pewne)."""
    m = _NAME_WH.search(name)
    if m:
        w = float(m.group(1).replace(",", ".")); h = float(m.group(2).replace(",", "."))
        unit = (m.group(3) or "cm").lower()
        if unit == "mm":
            return (w, h)
        if unit == "m":
            return (w * 1000, h * 1000)
        if w <= 12 and h <= 12:      # namioty w metrach itp. — niejednoznaczne
            return None
        return (w * 10, h * 10)
    m = _NAME_W.search(name)
    if m:
        w = float(m.group(1))
        if 30 <= w <= 2000:           # szerokość w cm (adWall 300/600, adStand 85…)
            return (w * 10, None)
    return None


def suggest_by_size(fw_mm: float, fh_mm: float, products: list[dict], index: dict | None, limit: int = 5) -> list[dict]:
    if not fw_mm or not fh_mm:
        return []
    index = index or {}
    out = []
    for p in products:
        h = p.get("hash")
        entry = index.get(h)
        best = None
        if entry and entry.get("ok"):
            k = 10 if entry.get("scale") == "1:10" else 1
            for t in entry.get("templates", []):
                if t.get("missing") or not t.get("w") or not t.get("h"):
                    continue
                P_w, P_h = t["w"] * k, t["h"] * k              # rozmiar wydruku
                T_w, T_h = t["w"], t["h"]                      # rozmiar strony w pliku wg wytycznych
                if _match_dims(fw_mm, fh_mm, T_w, T_h, 0.03, 3):
                    # Wynik zależy od tego, JAK blisko: przy tolerancji 3 % wymiar 1000×2000
                    # pasuje do kilkunastu produktów 100x200 i wszystkie miały po 90 % —
                    # o kolejności decydowała długość nazwy (zgłoszenie Tomasza: „Air GATE
                    # ROUND" dla pliku 100x200, bo jego szablon 1999×1041 pasował OBRÓCONY).
                    e, rot = _dims_err(fw_mm, fh_mm, T_w, T_h)
                    sc = round(0.9 - min(0.1, e * 3) - (0.04 if rot else 0), 3)
                    cand = (sc, f"wymiar {fmt(fw_mm)}×{fmt(fh_mm)} mm {'≈' if e > 0.002 else '='} szablon „{t['role']}” {fmt(T_w)}×{fmt(T_h)} mm"
                                 + (" (obrócony)" if rot else "")
                                 + (f" (skala 1:10 → {fmt(P_w)}×{fmt(P_h)} mm na wydruku)" if k == 10 else ""), "ok")
                elif k == 10 and _match_dims(fw_mm, fh_mm, P_w, P_h, 0.03, 3):
                    cand = (0.75, f"wymiar {fmt(fw_mm)}×{fmt(fh_mm)} mm = rozmiar wydruku {fmt(P_w)}×{fmt(P_h)} mm, ale plik powinien być w skali 1:10 ({fmt(T_w)}×{fmt(T_h)} mm)", "scale")
                elif k == 1 and _match_dims(fw_mm, fh_mm, P_w / 10, P_h / 10, 0.03, 3):
                    cand = (0.75, f"wymiar {fmt(fw_mm)}×{fmt(fh_mm)} mm = 1/10 szablonu {fmt(P_w)}×{fmt(P_h)} mm, ale ten produkt jest w skali 1:1", "scale")
                else:
                    continue
                if best is None or cand[0] > best[0]:
                    best = cand
        else:
            d = dims_from_product_name(p["name"])
            if d:
                W, H = d
                full = H is not None
                if _match_dims(fw_mm, fh_mm, W, H, 0.08 if full else 0.04, 8 if full else 4):
                    cand = (0.7 if full else 0.5, f"wymiar {fmt(fw_mm)}×{fmt(fh_mm)} mm pasuje do {fmt(W)}{'×' + fmt(H) if full else ' (szer.)'} mm z nazwy produktu", "name-dims")
                elif _match_dims(fw_mm, fh_mm, W / 10, None if H is None else H / 10, 0.08 if full else 0.04, 3):
                    cand = (0.6 if full else 0.4, f"wymiar {fmt(fw_mm)}×{fmt(fh_mm)} mm = 1/10 z {fmt(W)}{'×' + fmt(H) if full else ''} mm z nazwy produktu (plik w skali 1:10?)", "name-dims")
                else:
                    continue
                best = cand
        if best:
            out.append(dict(p, score=best[0], basis="size", note=best[1], scale_hint=best[2]))
    out.sort(key=lambda x: (-x["score"], len(x["name"])))
    return out[:limit]


def suggest_by_content(hints: dict | None, products: list[dict], index: dict | None,
                       limit: int = 5) -> list[dict]:
    """Sugestie z TREŚCI pliku — z szablonu, który klient zostawił w projekcie.

    Dwa sygnały, oba mocniejsze od samego wymiaru strony:
      * napis z pełną nazwą produktu (szablony Adsystem mają ją pod wymiarem, np.
        „Wydruk Pop-up Lightbox 100x200 [keder 9x3mm]"),
      * ramka w kolorze wytycznych o wymiarze dokładnie takim jak szablon produktu
        (±1,5 mm) — wymiary szablonów różnią się między produktami o kilka milimetrów
        (1012×2010, 1015×2014, 1020×2018…), więc dokładny wymiar ramki mocno zawęża wybór."""
    if not hints:
        return []
    index = index or {}
    text = " " + normalize(hints.get("tekst") or "") + " "
    ramki = [r for r in (hints.get("ramki") or []) if r and r[0] >= 50 and r[1] >= 50]
    wyniki: dict[str, dict] = {}
    # napisy: bierzemy najdłuższe trafienia („… 100x200 tył" zawiera „… 100x200")
    trafione = []
    if text.strip():
        for p in products:
            pn = normalize(p["name"])
            if len(pn) >= 10 and (" " + pn + " ") in text:
                trafione.append((pn, p))
    for pn, p in trafione:
        if any(pn != qn and (" " + pn + " ") in (" " + qn + " ") for qn, _ in trafione):
            continue
        wyniki[p["hash"]] = dict(p, score=0.96, basis="content", scale_hint="ok",
                                 note="w pliku jest napis z nazwą produktu (zostawiony szablon)")
    for p in products:
        e = index.get(p["hash"])
        if not e or not e.get("ok"):
            continue
        for t in e.get("templates", []):
            if t.get("missing") or not t.get("w") or not t.get("h"):
                continue
            for rw, rh in ramki:
                if abs(rw - t["w"]) <= 1.5 and abs(rh - t["h"]) <= 1.5:
                    note = f"w pliku jest ramka szablonu {fmt(rw)}×{fmt(rh)} mm = szablon „{t['role']}” tego produktu"
                    if p["hash"] in wyniki:
                        wyniki[p["hash"]]["score"] = 0.98
                        wyniki[p["hash"]]["note"] = "w pliku jest napis z nazwą produktu i " + note[len("w pliku jest "):]
                    else:
                        wyniki[p["hash"]] = dict(p, score=0.9, basis="content", scale_hint="ok", note=note)
                    break
            else:
                continue
            break
    out = sorted(wyniki.values(), key=lambda x: (-x["score"], len(x["name"])))
    return out[:limit]


def fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def suggest_all(filename: str, fw_mm, fh_mm, products: list[dict], index: dict | None,
                limit: int = 5, trim_mm=None, hints: dict | None = None) -> list[dict]:
    """Najpierw nazwa pliku; gdy nazwa nie daje pewnej sugestii (< 0,6), dokładamy
    sugestie po wymiarze (pierwsze), a słabe nazwowe za nimi.

    `trim_mm` to wymiar NETTO (TrimBox), gdy plik ma spady. Szukamy wtedy po obu wymiarach,
    bo plik ze spadami jest o te kilkanaście milimetrów większy od formatu i o tyle właśnie
    mija się z każdym szablonem — a szablony w wytycznych podają wymiar, jaki ma mieć plik.
    Zgłoszenie Tomasza (`spady.pdf`): strona 973,3 × 1973,3 mm nie pasowała do niczego,
    a jej format netto 950 × 1950 mm pasuje."""
    by_name = suggest(filename, products, limit=limit)
    if by_name and by_name[0]["score"] >= 0.6:
        return by_name
    by_size = suggest_by_size(fw_mm, fh_mm, products, index, limit=limit * 3)
    has_trim = bool(trim_mm and len(trim_mm) == 2 and trim_mm[0] and trim_mm[1] and (
            abs(trim_mm[0] - (fw_mm or 0)) > 0.5 or abs(trim_mm[1] - (fh_mm or 0)) > 0.5))
    if has_trim:
        # plik ma format netto — to on jest zamierzonym wymiarem, strona ze spadami tylko go
        # obrasta; trafienie po wymiarze brutto jest więc słabsze
        for x in by_size:
            x["score"] = round(x["score"] - 0.02, 3)
    if trim_mm and len(trim_mm) == 2 and trim_mm[0] and trim_mm[1] and (
            abs(trim_mm[0] - (fw_mm or 0)) > 0.5 or abs(trim_mm[1] - (fh_mm or 0)) > 0.5):
        for x in suggest_by_size(trim_mm[0], trim_mm[1], products, index, limit=limit * 3):
            x["note"] += " — po odjęciu spadów"
            by_size.append(x)
        best: dict = {}
        for x in by_size:                              # ten sam produkt tylko raz, z lepszym wynikiem
            if x["hash"] not in best or x["score"] > best[x["hash"]]["score"]:
                best[x["hash"]] = x
        by_size = list(best.values())
    # zostawiony szablon (napis z nazwą produktu, ramka o dokładnym wymiarze) idzie przed
    # samym wymiarem strony
    by_content = suggest_by_content(hints, products, index, limit=limit)
    best = {}
    for x in by_content + by_size:
        if x["hash"] not in best or x["score"] > best[x["hash"]]["score"]:
            best[x["hash"]] = x
    by_size = sorted(best.values(), key=lambda x: (-x["score"], len(x["name"])))[:limit]
    seen = {x["hash"] for x in by_size}
    merged = by_size + [x for x in by_name if x["hash"] not in seen]
    return merged[:limit]
