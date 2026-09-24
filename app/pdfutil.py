"""Drobne narzędzia do PDF-ów, z których korzysta kilka modułów."""
from __future__ import annotations

import os

import pikepdf

MM = 25.4 / 72.0          # 1 pt w mm

# 14 fontów standardowych PDF-a — kształt ustala specyfikacja, każdy program ma je wbudowane
# (Ghostscript i MuPDF: metryczne klony URW). Nieosadzona Helvetica wygląda wszędzie tak samo.
BASE14 = {
    "helvetica", "helvetica-bold", "helvetica-oblique", "helvetica-boldoblique",
    "times-roman", "times-bold", "times-italic", "times-bolditalic",
    "courier", "courier-bold", "courier-oblique", "courier-boldoblique",
    "symbol", "zapfdingbats",
}


def is_base14(name: str) -> bool:
    return (name or "").split("+")[-1].lower().replace(",", "-").replace(" ", "") in BASE14


def is_pdf(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in (".pdf", ".ai")


def all_dicts(pdf):
    """Wszystkie słowniki pliku — pośrednie ORAZ zagnieżdżone bezpośrednio w innych.

    `pdf.objects` zwraca tylko obiekty z własnym numerem, a stan graficzny bywa wpisany
    wprost w zasoby strony — tak jest w PRINT_CHECKER_TEST_100x200_SZABLON_PASERY.pdf:
    analiza liczyła 3 użycia overprintu, a naprawa ich nie widziała (Tomasz 24.09).
    Każdy krok w osobnym try: różne wersje pikepdf zwracają liczby z tablic raz jako obiekty
    PDF, raz jako liczby Pythona — u Tomasza wywracało to całe przejście."""
    def walk(o, depth):
        if depth > 12:
            return
        try:
            if isinstance(o, pikepdf.Array):
                for x in list(o):
                    try:
                        if isinstance(x, (pikepdf.Dictionary, pikepdf.Array)) and not getattr(x, "is_indirect", True):
                            yield from walk(x, depth + 1)
                    except Exception:
                        continue
                return
            if not isinstance(o, (pikepdf.Dictionary, pikepdf.Stream)):
                return
            d = o.stream_dict if isinstance(o, pikepdf.Stream) else o
            keys = list(d.keys())
        except Exception:
            return
        yield d
        for k in keys:
            try:
                v = d[k]
                if isinstance(v, (pikepdf.Dictionary, pikepdf.Array)) and not getattr(v, "is_indirect", True):
                    yield from walk(v, depth + 1)
            except Exception:
                continue

    for obj in pdf.objects:
        try:
            yield from walk(obj, 0)
        except Exception:
            continue
    # jawnie: /Resources /ExtGState stron i obiektów formy (także zasoby bezpośrednie)
    try:
        pages = list(pdf.pages)
    except Exception:
        pages = []
    for pg in pages:
        try:
            yield from _extgstates(pg.obj.get("/Resources"), 0)
        except Exception:
            continue


def _extgstates(res, depth):
    if res is None or depth > 8:
        return
    try:
        eg = res.get("/ExtGState")
        for k in list(eg.keys()) if eg is not None else []:
            g = eg[k]
            if isinstance(g, (pikepdf.Dictionary, pikepdf.Stream)):
                yield g
    except Exception:
        pass
    try:
        xo = res.get("/XObject")
        for k in list(xo.keys()) if xo is not None else []:
            x = xo[k]
            if str(x.get("/Subtype", "")) == "/Form":
                yield from _extgstates(x.get("/Resources"), depth + 1)
    except Exception:
        pass


def uses_overprint(path: str) -> bool:
    """Czy plik włącza overprint (/OP albo /op = true w jakimkolwiek stanie graficznym)."""
    if not is_pdf(path):
        return False
    try:
        with pikepdf.open(path) as pdf:
            for d in all_dicts(pdf):
                try:
                    if bool(d.get("/OP", False)) or bool(d.get("/op", False)):
                        return True
                except Exception:
                    continue
    except Exception as e:
        print(f"[adChecker] uses_overprint: {type(e).__name__}: {e}")
    return False


def fonts_in(path: str) -> list[tuple[str, bool]]:
    """[(nazwa, czy_osadzony)] — po jednym wpisie na font. Type 3 ma kształty liter w pliku."""
    import pymupdf
    d = pymupdf.open(path)
    try:
        seen = {}
        for pg in d:
            for f in pg.get_fonts(full=True):
                name, ext = f[3], (f[1] or "")
                emb = ext not in ("", "n/a") or str(f[2]) == "Type3"
                seen[name] = seen.get(name, True) and emb
        return sorted(seen.items())
    finally:
        d.close()


def spot_names(path: str) -> list[str]:
    """Nazwy kolorów dodatkowych (Separation/DeviceN) obecnych w pliku."""
    out = []
    try:
        with pikepdf.open(path) as pdf:
            for obj in pdf.objects:
                try:
                    if isinstance(obj, pikepdf.Array) and len(obj) > 1 and str(obj[0]) in ("/Separation", "/DeviceN"):
                        n = obj[1]
                        names = [str(x).lstrip("/") for x in n] if isinstance(n, pikepdf.Array) else [str(n).lstrip("/")]
                        out += [x for x in names if x not in out and x.lower() not in ("all", "none", "registration_all")]
                except Exception:
                    continue
    except Exception:
        pass
    return out[:12]


def page_sizes_mm(path: str) -> list[list[float]]:
    """Wymiar każdej strony w mm (tak, jak widzi go MuPDF — z obrotem)."""
    import render
    d = render.open_doc(path)
    try:
        return [[round(p.rect.width * MM, 2), round(p.rect.height * MM, 2)] for p in d]
    finally:
        d.close()
