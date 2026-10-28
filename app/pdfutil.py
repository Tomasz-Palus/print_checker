"""Drobne narzędzia do PDF-ów, z których korzysta kilka modułów."""
from __future__ import annotations

import os
import threading as _th

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


# Treść strony / formy: lista operatorów z `pikepdf.parse_content_stream` zajmuje ok. 1 GB na milion
# operatorów (28.10: płaska treść 8 mln operatorów — wektor z CAD, 71 MB — zabrała 11 GB pamięci). Duża
# treść idzie strumieniowo: kawałki po STREAM_BATCH operatorów, pamięć stała.
STREAM_RAW = 512_000              # treść większa (spakowana; po rozpakowaniu zwykle 3–10×) — strumieniowo
STREAM_BATCH = 20_000


def _content_streams(container) -> list:
    obj = container.obj if isinstance(container, pikepdf.Page) else container
    c = obj.get("/Contents") if isinstance(container, pikepdf.Page) else obj
    items = list(c) if isinstance(c, pikepdf.Array) else [c]
    return [x for x in items if isinstance(x, pikepdf.Stream)]


def _raw_length(container) -> int:
    try:
        return sum(int(x.get("/Length", 0)) for x in _content_streams(container))
    except Exception:
        return 0


def iter_ops(container):
    """(operandy, operator jako str) po kolei, jak `parse_content_stream`; obraz w treści (BI … EI) jako
    ([PdfInlineImage], "INLINE IMAGE"). Mała treść — zwykła lista; duża — strumieniowo (obiekt z `n`)."""
    if _raw_length(container) <= STREAM_RAW:
        return [(ins.operands, str(ins.operator)) for ins in pikepdf.parse_content_stream(container)]
    # Do wątku idzie treść SPAKOWANA i opis filtrów — rozpakowuje dopiero parser w osobnym PDF-ie
    parts = []
    for st in _content_streams(container):
        f, d = st.get("/Filter"), st.get("/DecodeParms")
        parts.append((st.read_raw_bytes(), f.unparse() if f is not None else None, d.unparse() if d is not None else None))
    return _StreamOps(parts)


class _Stop(Exception):
    pass


_OPERATOR = pikepdf.ObjectType.operator
_PLAIN = {int, float, bool, __import__("decimal").Decimal}


def _own(o):
    """Kopia operandu niezależna od tymczasowego PDF-a parsera (obiekt pikepdf żyje tylko razem ze swoim
    plikiem — po jego zamknięciu odczyt kończy się błędem pamięci)."""
    if not isinstance(o, pikepdf.Object):
        return o                                 # int, Decimal, bool — już wartości Pythona
    t = o._type_code
    if t == pikepdf.ObjectType.name_:
        return pikepdf.Name(str(o))
    if t == pikepdf.ObjectType.string:
        return pikepdf.String(bytes(o))
    if t == pikepdf.ObjectType.array:
        return pikepdf.Array([_own(x) for x in o])
    if t == pikepdf.ObjectType.dictionary:
        return pikepdf.Dictionary({k: _own(v) for k, v in o.items()})
    if t == pikepdf.ObjectType.inlineimage:
        return pikepdf.String(o._inline_image_raw_bytes())
    if t == pikepdf.ObjectType.boolean:
        return bool(o)
    if t == pikepdf.ObjectType.integer:
        return int(o)
    if t == pikepdf.ObjectType.real:
        from decimal import Decimal
        return Decimal(str(o))
    return None


class _StreamOps:
    """Operatory dużej treści po kolei; `n` — ile już podano (budżet analizy), `error` — treść urwana
    błędem (dalsza część nieodczytana)."""

    def __init__(self, parts: list):
        self.parts, self.n, self.error = parts, 0, None

    def __iter__(self):
        parts, self.parts = self.parts, None     # treść oddana wątkowi — tu jej nie trzymamy
        try:
            for batch in _stream_batches(parts):
                self.n += len(batch)
                yield from batch
        except Exception as e:                   # uszkodzona treść: koniec tu, błąd do sprawdzenia przez `error`
            self.error = e


def _stream_batches(parts: list):
    """Generator kawałków: osobny wątek parsuje treść (pikepdf.StreamParser) w OSOBNYM, pustym PDF-ie — pikepdf
    nie jest bezpieczny dla wątków, a główny plik czyta w tym czasie analiza. Kawałki przez kolejkę."""
    import queue
    q: queue.Queue = queue.Queue(maxsize=3)
    stop = _th.Event()

    def put(x):
        while not stop.is_set():
            try:
                q.put(x, timeout=0.2)
                return
            except queue.Full:
                continue
        raise _Stop

    class P(pikepdf.StreamParser):
        def __init__(self):
            super().__init__()
            self.batch, self.operands, self.bi = [], [], None

        def handle_object(self, obj, offset, length):
            if obj.__class__ in _PLAIN:          # liczby — najczęstsze, bez kopiowania
                self.operands.append(obj)
                return
            if obj is None:                      # nieczytelny kawałek treści — jak parse_content_stream: None
                self.operands.append(None)
                return
            if obj._type_code == _OPERATOR:
                o = str(obj)
                if o == "BI":
                    self.bi = []
                elif o == "ID" and self.bi is not None:
                    self.bi.extend(self.operands)
                elif o == "EI" and self.bi is not None:
                    try:
                        img = pikepdf.PdfInlineImage(image_data=self.operands[-1], image_object=tuple(self.bi))
                        self.batch.append(([img], "INLINE IMAGE"))
                    except Exception:
                        pass
                    self.bi = None
                else:
                    self.batch.append((self.operands, o))
                self.operands = []
                if len(self.batch) >= STREAM_BATCH:
                    put(self.batch)
                    self.batch = []
            else:
                self.operands.append(_own(obj))

        def handle_eof(self):
            pass

    def run():
        try:
            tmp = pikepdf.new()
            pg = tmp.add_blank_page()
            streams = []
            while parts:
                raw, f, d = parts.pop(0)
                st = tmp.make_stream(raw)
                del raw
                if f is not None:
                    st["/Filter"] = pikepdf.Object.parse(f)
                if d is not None:
                    st["/DecodeParms"] = pikepdf.Object.parse(d)
                streams.append(st)
            pg.obj["/Contents"] = streams[0] if len(streams) == 1 else pikepdf.Array(streams)
            p = P()
            pg.parse_contents(p)
            if p.batch:
                put(p.batch)
            put(None)
        except _Stop:
            pass
        except Exception as e:                  # błąd parsowania — jak parse_content_stream: wyjątek
            try:
                put(e)
            except _Stop:
                pass

    t = _th.Thread(target=run, daemon=True)
    t.start()
    try:
        while True:
            b = q.get()
            if b is None:
                return
            if isinstance(b, Exception):
                raise b
            yield b
    finally:
        stop.set()


def wrap_page(pdf, page, prefix: bytes) -> None:
    """Treść strony w `q <prefix> … Q` — odporne na NIEZRÓWNOWAŻONE q/Q w treści.

    Nadmiarowe `Q` (pliki sklejane, stemplowane) zdejmowało nasze `q … cm` i dalsza treść rysowała
    się bez obrotu / skali (przegląd 09.10, C — normalize_geometry). Dlatego po naszym `q` idzie tyle
    zapasowych `q`, ile treść ma nadmiarowych `Q`, a na końcu tyle `Q`, ile trzeba, żeby wrócić do
    stanu początkowego (także gdy treść zostawia niezamknięte `q`)."""
    depth, low = 0, 0
    try:
        for ins in pikepdf.parse_content_stream(page, "q Q"):
            o = str(ins.operator)
            if o == "q":
                depth += 1
            elif o == "Q":
                depth -= 1
                low = min(low, depth)
    except Exception:
        depth, low = 0, 0
    extra = -low
    page.contents_add(pdf.make_stream(b"q " + prefix + b"\n" + b"q\n" * extra), prepend=True)
    close = 1 + extra + depth
    page.contents_add(pdf.make_stream(b"\n" + b"Q\n" * max(1, close)), prepend=False)


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


def raster_dpi(im):
    """DPI obrazu z Pillow albo None. TIFF bez znacznika XResolution: Pillow podaje umowne (1, 1) —
    to brak DPI, nie 1 dpi (przegląd 09.10, A1/B18)."""
    d = im.info.get("dpi")
    if (im.format or "") == "TIFF" and 282 not in getattr(im, "tag_v2", {}):
        return None
    try:
        return (float(d[0]), float(d[1])) if d and d[0] and d[1] else None
    except (TypeError, ValueError, IndexError):
        return None


# PyMuPDF nie jest bezpieczny dla wielu wątków naraz (ocena jakości w tle + trasy serwera) —
# jedna blokada na cały program (przegląd 09.10, B24). RLock: funkcje pod blokadą mogą wołać inne.
import functools as _ft
import threading as _th
MUPDF_LOCK = _th.RLock()


def mupdf_locked(fn):
    @_ft.wraps(fn)
    def run(*a, **kw):
        with MUPDF_LOCK:
            return fn(*a, **kw)
    return run


fonts_in = mupdf_locked(fonts_in)
page_sizes_mm = mupdf_locked(page_sizes_mm)
