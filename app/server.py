"""adChecker — przygotowanie pliku do druku bez grafika DTP.

Uruchomienie deweloperskie: python server.py (albo run.bat) → http://127.0.0.1:5000
Zainstalowany program startuje przez desktop.py (własne okno, serwer produkcyjny).
Serwer to same trasy HTTP; logika siedzi w modułach (jobs, steps, render, …).
"""
from __future__ import annotations

import math
import os
import re
import sys
import threading
import time
import webbrowser

from flask import Flask, jsonify, request, send_file, send_from_directory

import analyze
import frames
import guidelines
import jobs
import products
import quality
import render
import sizeindex
import suggest
import views
import paths
import updater
from version import VERSION

STATIC = paths.STATIC
HOST, PORT = "127.0.0.1", int(os.environ.get("ADCHECK_PORT", "5000"))
MAX_UPLOAD_MB = 1024
HASH_RE = re.compile(r"[0-9a-fA-F]{32,256}")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024


def err(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


class JobNotFound(Exception):
    """Zadania nie ma (program uruchomiony od nowa, plik usunięty). Osobny wyjątek — wcześniej
    handler łapał KAŻDY LookupError (IndexError, KeyError) i każdy błąd kończył się radą „wgraj
    plik jeszcze raz” (przegląd kodu 27.09, C22)."""


def job_or_404(jid):
    job = jobs.get(jid)
    if not job:
        raise JobNotFound
    return job


class BadRequest(Exception):
    """Złe parametry zapytania → 400 z tym komunikatem (dawniej część kończyła się 500)."""


def body_dict() -> dict:
    """Ciało JSON — musi być obiektem (lista, liczba → 400, nie 500) (przegląd 09.10, C)."""
    b = request.get_json(silent=True)
    if b is None:
        return {}
    if not isinstance(b, dict):
        raise BadRequest("Złe dane zapytania.")
    return b


def arg_page(job, name: str = "page") -> int:
    """Numer strony z adresu: brak = 0; nie-liczba albo spoza pliku → 400."""
    raw = request.args.get(name, "0")
    try:
        page = int(raw)
    except (TypeError, ValueError):
        raise BadRequest("Zły numer strony.")
    if not 0 <= page < job.info["page_count"]:
        raise BadRequest("Nie ma takiej strony.")
    return page


def pos_float(v, what: str = "wartość") -> float:
    """Liczba skończona i dodatnia — wymiar ≤ 0 albo NaN dawał w ocenie jakości „ok”
    (przegląd 09.10, B22)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise BadRequest(f"Zła {what}.")
    if not math.isfinite(x) or x <= 0:
        raise BadRequest(f"Zła {what}.")
    return x


# ---------------------------------------------------------------------------- tylko ten komputer
# Serwer słucha na 127.0.0.1 na stałym porcie — ale KAŻDA strona otwarta w przeglądarce może
# wysłać tu zapytanie (formularz, fetch no-cors), a przez „DNS rebinding” nawet czytać odpowiedzi.
# Dlatego (przegląd kodu 27.09, B15):
# - nagłówek Host musi wskazywać ten komputer (127.0.0.1 / localhost / [::1]);
# - zapytanie z nagłówkiem Origin (każde z przeglądarki poza zwykłym GET) musi pochodzić z tej samej
#   strony co program. Zapytania bez Origin (self-test, sprawdzanie drugiego uruchomienia) przechodzą.
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _hostname(hostport: str) -> str:
    h = (hostport or "").strip().lower()
    if h.startswith("["):
        return h[:h.find("]") + 1]
    return h.split(":", 1)[0]


@app.before_request
def _only_this_computer():
    if _hostname(request.host) not in LOCAL_HOSTS:
        return err("Zapytanie spoza tego komputera — odrzucone.", 403)
    origin = request.headers.get("Origin")
    if origin is not None:
        from urllib.parse import urlsplit
        o = urlsplit(origin)
        if o.scheme not in ("http", "https") or o.netloc.lower() != request.host.lower():
            return err("Zapytanie z innej strony — odrzucone.", 403)
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        return err("Zapytanie z innej strony — odrzucone.", 403)


@app.errorhandler(JobNotFound)
def _nojob(_):
    return err("Nie ma takiego zadania — wgraj plik jeszcze raz.", 404)


@app.errorhandler(BadRequest)
def _bad(e):
    return err(str(e) or "Złe parametry.", 400)


@app.errorhandler(Exception)
def _crash(e):
    """Nieprzewidziany błąd: JSON z nazwą błędu (interfejs pokazuje go w rozdziale) i ślad w dzienniku."""
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    import traceback
    traceback.print_exc()
    return err(f"Błąd programu: {type(e).__name__}: {e}", 500)


@app.errorhandler(413)
def _too_large(_):
    return err(f"Plik za duży (limit {MAX_UPLOAD_MB} MB).", 413)


# ----------------------------------------------------------------------------
# strona
# ----------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/static/<path:name>")
def static_files(name):
    resp = send_from_directory(STATIC, name)
    resp.headers["Cache-Control"] = "no-cache"          # po zmianie kodu przeglądarka bierze nowy
    return resp


# ----------------------------------------------------------------------------
# produkty i wytyczne
# ----------------------------------------------------------------------------
@app.get("/api/products")
def api_products():
    items = products.get_products()
    return jsonify({"status": products.status(), "products": items})


@app.post("/api/products/refresh")
def api_products_refresh():
    st = products.load_products(force_refresh=True)
    return jsonify({"status": st, "products": products.get_products()})


@app.get("/api/guidelines/<hash_>")
def api_guidelines(hash_):
    """ZAWSZE aktualne wytyczne ze strony (wymaganie Tomasza); kopia lokalna tylko, gdy sieć
    nie działa — odpowiedź ma wtedy `stale: true`."""
    if not HASH_RE.fullmatch(hash_):
        return err("Nieprawidłowy identyfikator wytycznych.")
    try:
        data = guidelines.get_guidelines_fresh(hash_)
    except Exception as e:
        return err(f"Nie udało się pobrać wytycznych: {type(e).__name__}: {e}", 502)
    sizeindex.add_from_guidelines(hash_, data)           # indeks wymiarów rośnie przy okazji
    return jsonify(guidelines.public_view(data))


@app.get("/api/sizeindex/status")
def api_sizeindex_status():
    return jsonify(sizeindex.status())


@app.post("/api/sizeindex/build")
def api_sizeindex_build():
    return jsonify(sizeindex.start_build(retry_failed=request.args.get("retry") == "1"))


@app.post("/api/sizeindex/stop")
def api_sizeindex_stop():
    return jsonify(sizeindex.stop_build())


# ----------------------------------------------------------------------------
# plik
# ----------------------------------------------------------------------------
@app.post("/api/upload")
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return err("Brak pliku.")
    try:
        job = jobs.create(f)
    except render.UnsupportedFormat as e:
        return err(str(e), 415)
    except Exception as e:
        import prepare
        if isinstance(e, prepare.Unreadable):
            return err(str(e), 415)
        import traceback
        traceback.print_exc()                 # szczegóły (ze ścieżką) tylko w dzienniku
        return err(f"Nie udało się otworzyć pliku ({type(e).__name__}).", 415)
    if job.info.get("page_count", 0) < 1:
        jobs.delete(job.id)
        return err("Plik nie ma żadnej strony.", 415)
    # propozycje dla strony 1 zapisane przy wgraniu — zadanie nie jest jeszcze nikomu znane;
    # dla innych stron /suggest liczy je bez zapisu w zadaniu (przegląd 09.10, B20)
    sugs, ramki = suggestions_safe(job, 0)
    job.suggestions, job.info["template_frames"] = sugs, ramki
    return jsonify({**job.to_json(), "page": 0})


def suggestions_for(job, page: int) -> tuple[list, list]:
    """(propozycje, ramki szablonu) dla strony: z nazwy pliku, z treści (szablon zostawiony
    w pliku) i z wymiaru strony (także netto, gdy strona ma spady). Nic nie zapisuje w zadaniu —
    wspólny `job.info["template_frames"]` przy szybkim przełączaniu stron dostawał ramki innej
    strony (przegląd 09.10, B20)."""
    p = job.info["pages"][page]
    hints = content_hints(job.original.path, page)
    return (suggest.suggest_all(job.info["name"], p.get("width_mm"), p.get("height_mm"),
                                products.get_products(), sizeindex.load(), limit=5,
                                trim_mm=p.get("trim_mm"), hints=hints),
            hints.get("ramki", []))


def suggestions_safe(job, page: int) -> tuple[list, list]:
    try:
        return suggestions_for(job, page)
    except Exception as e:                    # propozycje to wygoda — plik i tak się otwiera
        print(f"[propozycje] {type(e).__name__}: {e}")
        return [], []


def job_json_for_page(job, page: int, sugs: list, ramki: list) -> dict:
    """Stan zadania z propozycjami KONKRETNEJ strony (pole `page`) — bez zapisu w zadaniu."""
    out = job.to_json()
    out["file"] = {**out["file"], "template_frames": ramki}
    out["suggestions"], out["page"] = sugs, page
    return out


@app.get("/api/jobs/<jid>/suggest")
def api_suggest(jid):
    """Propozycje dla wybranej strony (strona jest wybierana przed produktem). Odpowiedź ma
    `page` — interfejs odrzuca propozycje dla strony, która nie jest już wybrana."""
    job = job_or_404(jid)
    page = arg_page(job)
    sugs, ramki = suggestions_for(job, page)
    return jsonify(job_json_for_page(job, page, sugs, ramki))


@render._pdfutil.mupdf_locked
def content_hints(path: str, page: int = 0) -> dict:
    """Podpowiedzi do sugestii produktu z TREŚCI pliku: napisy i ramki w kolorach wytycznych.
    Klient często zostawia szablon w projekcie, a ten mówi wprost, do jakiego jest produktu."""
    if not path.lower().endswith((".pdf", ".ai")):
        return {}
    out = {"tekst": "", "ramki": []}
    try:
        d = render.open_doc(path)
        try:
            out["tekst"] = d[page].get_text()[:200000]
        finally:
            d.close()
        shapes, texts = frames.shapes(path, page)
        out["tekst"] += " " + " ".join(t["tekst"] for t in texts)[:200000]
        out["ramki"] = [[round(z["w"], 1), round(z["h"], 1)] for z in shapes
                        if frames.color_class(z) is not None and z["w"] >= 50 and z["h"] >= 50][:20]
    except Exception:
        pass
    return out


@app.get("/api/jobs/<jid>")
def api_job(jid):
    return jsonify(job_or_404(jid).to_json())


@app.delete("/api/jobs/<jid>")
def api_job_delete(jid):
    job = jobs.get(jid)
    if job:
        quality.forget(job)
    jobs.delete(jid)
    return jsonify({"ok": True})


@app.get("/api/jobs/<jid>/thumb/<int:n>.png")
def api_thumb(jid, n):
    job = job_or_404(jid)
    if not 0 <= n < job.info["page_count"]:
        return err("Nie ma takiej strony.", 404)
    cache = os.path.join(job.dir, f"thumb_{job.original.id}_{n}.png")      # po obrocie — nowa miniatura
    if not os.path.exists(cache):
        # przez plik tymczasowy: po błędzie renderu nie zostaje pusty plik, a równoległe
        # zapytanie nie dostaje połowy obrazka (przegląd kodu 27.09, C21)
        png = render.page_png(job.original.path, n, 240)
        tmp = f"{cache}.{threading.get_ident()}.part"
        with open(tmp, "wb") as fh:
            fh.write(png)
        os.replace(tmp, cache)
    return send_file(cache, mimetype="image/png", max_age=3600)


@app.get("/api/jobs/<jid>/analysis")
def api_analysis(jid):
    """Fakty o stronie wersji pliku: kolory, profile, spoty, obrazy, overprint, przezroczystość,
    fonty. Zawsze o JEDNEJ stronie — do druku idzie jedna."""
    job = job_or_404(jid)
    v = job.version(request.args.get("v"))
    if v is None:
        return err("Tej wersji pliku już nie ma.", 404)
    page = arg_page(job)
    try:
        res = job.analysis_of(v, page)       # raz na wersję i stronę (przegląd 09.10, C)
    except Exception as e:
        return err(f"Analiza nie powiodła się: {type(e).__name__}: {e}", 500)
    return jsonify({"version": v.id, "page": page, **res})


@app.get("/api/jobs/<jid>/ink")
def api_ink(jid):
    """Suma farb na wydruku (ink.py) — ostatnia wersja, jedna strona. Obraz (JPG/TIFF): pomijamy."""
    job = job_or_404(jid)
    v = job.version(request.args.get("v"))
    if v is None:
        return err("Tej wersji pliku już nie ma.", 404)
    page = arg_page(job)
    if render.is_raster(v.path):
        return jsonify({"version": v.id, "page": page, "skip": True})
    cache, key = job.ink, (v.id, page)
    if key not in cache:
        import ink
        try:
            wmm, hmm = v.pages_mm[page]
            cache[key] = ink.measure(v.path, page, (wmm / render.MM, hmm / render.MM))
        except Exception as e:
            return err(f"Nie udało się policzyć farby: {type(e).__name__}: {e}", 500)
    return jsonify({"version": v.id, "page": page, **cache[key]})


def gl_pdf(hash_: str) -> str | None:
    """Ścieżka do PDF-u wytycznych w pamięci podręcznej — z przeglądarki przychodzi tylko skrót."""
    if hash_ and HASH_RE.fullmatch(hash_):
        p = guidelines.pdf_path_for(hash_)
        if os.path.exists(p):
            return p
    return None


def _image_boxes(job, page: int) -> list:
    """Gdzie na stronie oryginału leżą obrazy (mm, y od góry) — z analizy (ta sama pamięć co
    /analysis). Obrazki < 8 px to wypełnienia, nie zdjęcia."""
    v = job.original
    job.analysis_of(v, page)
    out = []
    for rec in job.images.get(v.id, {}).get(page) or []:
        if rec.get("mask") or rec.get("width", 0) < 8 or rec.get("height", 0) < 8:
            continue
        for p in rec.get("placements") or []:
            if p.get("page", page) == page and p.get("bw_mm") and p.get("bh_mm"):
                out.append((p["x_mm"], p["y_mm"], p["bw_mm"], p["bh_mm"]))
    return out


@app.get("/api/jobs/<jid>/frames")
def api_frames(jid):
    """Czy w pliku został szablon z wytycznych. Zawsze na ORYGINALE — usuwanie szablonu jest
    pierwszą poprawką, więc to dokładnie ten plik, na którym zadziała."""
    job = job_or_404(jid)
    page = arg_page(job)
    glp = request.args.get("glpage", -1, type=int)
    mm = job.original.pages_mm[page]
    if job.info["kind"] == "raster":
        # Obraz (JPG/PNG/TIFF): szablonu wektorowego w nim nie ma — sprawdzamy tylko, czy linie
        # wytycznych nie są wtopione w piksele. Wcześniej od razu „bez wytycznych” (known: False),
        # choć wytyczne produktu były wczytane (Tomasz 27.10, adWall L 200, JPG bez DPI).
        # Wymiar w mm służy tylko do progu grubości linii (14 mm) — obraz bez DPI dostaje wymiar
        # wydruku z interfejsu (w_mm, h_mm).
        size = tuple(mm) if mm and mm[0] else None
        if not size:
            w, h = request.args.get("w_mm", type=float), request.args.get("h_mm", type=float)
            size = (w, h) if w and h and w > 0 and h > 0 and math.isfinite(w) and math.isfinite(h) else None
        try:
            pixels = bool(size) and frames.in_pixels(job.page_path(job.original, page), 0, size, None)
        except Exception as e:
            return err(f"Nie udało się przeszukać obrazu: {type(e).__name__}: {e}", 500)
        return jsonify({"found": 0, "known": bool(gl_pdf(request.args.get("gl", ""))), "raster": True,
                        "pixels": bool(pixels), "checked": bool(size), "foreign": 0})
    if not mm or not mm[0]:
        return jsonify({"found": 0, "known": False, "pixels": False, "foreign": 0})
    try:
        r = frames.find(job.original.path, page, tuple(mm), gl_pdf(request.args.get("gl", "")), glp if glp >= 0 else None)
        # linie w kolorach wytycznych na obrazie strony — ale tylko gdy nie tłumaczą ich ramki
        # WEKTOROWE (bez wytycznych wektorowy szablon wyglądał jak „wtopiony w obraz")
        pixels = not r["found"] and not r["foreign"] and frames.in_pixels(job.original.path, page, tuple(mm),
                                                                          _image_boxes(job, page))
        # szablon przykryty grafiką nie drukuje się — nie ma czego zgłaszać
        hidden = bool(r["found"]) and not frames.visible(job.original.path, page, r["found"])
    except Exception as e:
        return err(f"Nie udało się przeszukać pliku: {type(e).__name__}: {e}", 500)
    m = r["match"]
    texts = sum(1 for z in r["found"] if not z.get("w"))
    return jsonify({"found": len(r["found"]), "hidden": hidden,
                    "lines": m.get("lines", 0), "lines_total": m.get("lines_total", 0),
                    "texts": texts, "err_mm": m.get("err_mm", 0), "scale": m.get("scale", 1),
                    "known": bool(m.get("known")), "pixels": bool(pixels), "foreign": r["foreign"]})


@app.post("/api/jobs/<jid>/rotate")
def api_rotate(jid):
    """Obraca cały plik o 90° / 180° (Tomasz 29.09) — nowy punkt wyjścia, poprawki przepadają."""
    job = job_or_404(jid)
    body = body_dict()
    try:
        deg = int(body.get("deg", 90))
        page = int(body.get("page", 0))
    except (TypeError, ValueError):
        return err("Złe parametry obrotu.")
    if not 0 <= page < job.info["page_count"]:
        return err("Nie ma takiej strony.")
    try:
        quality.forget(job)
        job.rotate(deg)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
        return err(f"Nie udało się obrócić pliku: {type(e).__name__}: {e}", 500)
    sugs, ramki = suggestions_safe(job, page)
    return jsonify(job_json_for_page(job, page, sugs, ramki))


RASTER_STEPS = {"resize", "cmyk"}            # obraz (JPG/PNG/TIFF) ma tylko te poprawki


def check_step_params(job, name: str, p: dict) -> dict:
    """Strona i liczby poprawki (przegląd 09.10, C): `w_mm=0` dawało stronę US Letter,
    `flatten k=0` — 1,2 ppi opisane jako 120; kroki PDF dla obrazu kończyły się 500."""
    try:
        page = int(p.get("page", 0) or 0)
    except (TypeError, ValueError):
        raise BadRequest("Zły numer strony.")
    if not 0 <= page < job.info["page_count"]:
        raise BadRequest("Nie ma takiej strony.")
    p["page"] = page
    if job.info.get("kind") == "raster" and name not in RASTER_STEPS:
        raise BadRequest("Ta poprawka nie dotyczy obrazu (JPG, PNG, TIFF).")
    if name == "resize":
        p["w_mm"], p["h_mm"] = pos_float(p.get("w_mm"), "szerokość"), pos_float(p.get("h_mm"), "wysokość")
    elif name == "trim":                                  # 0 = bez wymiaru netto
        for k in ("w_mm", "h_mm"):
            if p.get(k) not in (None, "", 0):
                p[k] = pos_float(p[k], "wymiar")
    for k in ("scale", "k"):
        if k in p and p[k] is not None:
            p[k] = pos_float(p[k], "skala")
    for k in ("dx_mm", "dy_mm"):
        if k in p and p[k] is not None:
            try:
                p[k] = float(p[k])
            except (TypeError, ValueError):
                raise BadRequest("Złe przesunięcie.")
            if not math.isfinite(p[k]):
                raise BadRequest("Złe przesunięcie.")
    return p


@app.post("/api/jobs/<jid>/steps")
def api_step(jid):
    """Nakłada poprawkę na ostatnią wersję pliku → nowa wersja."""
    job = job_or_404(jid)
    body = body_dict()
    name, params = body.get("name", ""), body.get("params") or {}
    if not isinstance(name, str) or not isinstance(params, dict):
        return err("Złe dane poprawki.")
    params = check_step_params(job, name, dict(params))
    if name == "frames":
        params["gl_pdf"] = gl_pdf(params.get("gl", ""))
        glp = params.get("glpage")
        params["gl_page"] = int(glp) if isinstance(glp, int) and glp >= 0 else None
        params["foreign"] = params.get("foreign") is True
    try:
        job.apply(name, params)
    except ValueError as e:
        print(f"[poprawka {name}] {e}")            # do dziennika — przy zgłoszeniu widać, co się stało
        return err(str(e))
    except Exception as e:
        import traceback
        print(f"[poprawka {name}] {type(e).__name__}: {e}\n{traceback.format_exc()}")
        return err(f"Poprawka nie powiodła się: {type(e).__name__}: {e}", 500)
    return jsonify(job.to_json())


# ----------------------------------------------------------------------------
# jakość wydruku i pobieranie (etap 4)
# ----------------------------------------------------------------------------
@app.get("/api/jobs/<jid>/quality")
def api_quality(jid):
    """Ocena jakości obrazów (quality.py). Startuje w tle przy pierwszym pytaniu, potem stan.
    k = ile razy wydruk jest większy od strony pliku (skala wytycznych; raster — z wymiaru
    wydruku); w_mm/h_mm = wymiar wydruku (raster: z niego liczy się ppi)."""
    job = job_or_404(jid)
    page = arg_page(job)
    try:
        k = round(pos_float(request.args.get("k", "1"), "skala"), 4)
        block = int(request.args.get("block", "128"))
        # wymiar wydruku ≤ 0 albo NaN dawał werdykt „ok” (przegląd 09.10, B22)
        pm = (pos_float(request.args["w_mm"], "szerokość"), pos_float(request.args.get("h_mm"), "wysokość")) \
            if request.args.get("w_mm") else None
    except (TypeError, ValueError, KeyError):
        return err("Złe parametry.")
    if not (0.01 <= k <= 100):
        return err("Złe parametry.")
    if block not in (64, 128):
        block = 128
    try:
        return jsonify(quality.request(job, page, k, block, pm))
    except Exception as e:
        return err(f"Nie udało się sprawdzić jakości: {type(e).__name__}: {e}", 500)


def safe_name(txt: str) -> str:
    """Nazwa pliku z nazwy produktu i roli: bez znaków, których nie lubi system plików."""
    name = "".join(ch if (ch.isalnum() or ch in " ._-()") else "-" for ch in (txt or "")).strip(" .-")
    while "--" in name:
        name = name.replace("--", "-")
    return name[:120]


@app.get("/api/jobs/<jid>/download")
def api_download(jid):
    """Plik do druku: OSTATNIA wersja, zawsze JEDNA strona (zasada Tomasza — PDF-a z kilkoma
    stronami nie pobieramy nigdy). Obraz — jak jest (JPG/TIFF po ewentualnej zamianie na CMYK)."""
    job = job_or_404(jid)
    page = arg_page(job)
    # `v` = wersja, którą użytkownik zaakceptował. Gdy to nie ostatnia (cofnięcie przeszło, a
    # odpowiedź nie doszła) — 409, zamiast pobrać plik o innym wymiarze (przegląd 09.10, A9)
    want = request.args.get("v")
    if want and want != job.head.id:
        return err("Plik zmienił się od chwili akceptacji — sprawdź go jeszcze raz przed pobraniem.", 409)
    pm = None
    if request.args.get("w_mm") or request.args.get("h_mm"):
        pm = (pos_float(request.args.get("w_mm"), "szerokość"), pos_float(request.args.get("h_mm"), "wysokość"))
    path, fname, mime = download_file(job, page, request.args.get("name", ""), pm)
    resp = send_file(path, mimetype=mime, as_attachment=True, download_name=fname)
    resp.headers["Cache-Control"] = "no-store"
    return resp


_download_lock = threading.Lock()


def download_file(job, page: int, name: str, print_mm: tuple | None = None) -> tuple[str, str, str]:
    """(ścieżka, nazwa pliku, typ) pliku do druku — wspólne dla przeglądarki i okna programu
    (tam zapisuje go okno „Zapisz jako", desktop.py). `print_mm` = wymiar wydruku (mm) — obraz
    bez zapisanego DPI dostaje DPI = piksele / ten wymiar (przegląd 09.10, B18)."""
    v = job.head
    # zapasowa nazwa też przez safe_name — trafia do okna „Zapisz jako” (przegląd 09.10, C)
    base = safe_name(name) or safe_name(os.path.splitext(job.info["name"])[0] + "_do_druku") or "do_druku"
    path = job.page_path(v, page)            # wielostronicowy obraz: tylko wybrana strona (A8)
    ext = os.path.splitext(path)[1].lower()
    if render.is_raster(path):
        if print_mm:
            path = _with_dpi(job, path, print_mm)
    else:
        ext = ".pdf"
        import prepare
        wmm, hmm = (v.pages_mm[page] if page < len(v.pages_mm) else (0, 0))
        uu = prepare.user_unit_for(wmm / render.MM, hmm / render.MM)
        if job.info["page_count"] > 1 or uu > 1:
            # strona ponad 200 cali (≈ 5 m) — wraca UserUnit, inaczej Acrobat i RIP-y jej nie przyjmą
            path = os.path.join(job.dir, f"pobierz_{v.id}_p{page}.pdf")
            # jeden naraz i przez plik tymczasowy: podwójne kliknięcie (albo okno „Zapisz jako”
            # równolegle) dawało obcięty PDF (przegląd kodu 27.09, C21)
            with _download_lock:
                if not os.path.exists(path):
                    import pikepdf
                    tmp = path + ".part"
                    with pikepdf.open(v.path) as pdf:
                        keep = pdf.pages[page]
                        out = pikepdf.new()
                        out.pages.append(keep)
                        if uu > 1:
                            prepare.with_user_unit(out, out.pages[0], uu)
                        if "/OutputIntents" in pdf.Root:        # profil kolorystyczny idzie z plikiem
                            oi = pdf.Root.OutputIntents
                            out.Root.OutputIntents = out.copy_foreign(oi if oi.is_indirect else pdf.make_indirect(oi))
                        out.save(tmp)
                    os.replace(tmp, path)
    mime = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".tif": "image/tiff", ".tiff": "image/tiff", ".png": "image/png"}.get(ext, "application/octet-stream")
    return path, base + ext, mime


def _with_dpi(job, path: str, print_mm: tuple) -> str:
    """Obraz BEZ zapisanego DPI → kopia z DPI = piksele / wymiar wydruku. Bez DPI RIP przyjmie
    72 dpi: 600×1200 px wyszłoby 212×423 mm zamiast 1015×2014 (przegląd 09.10, B18).
    Piksele zostają nietknięte: JPG i PNG — tylko nagłówek; TIFF — zapis bezstratny.
    DPI jednakowe w obu osiach (większe z dwóch — obraz nie wyjdzie poza wymiar wydruku)."""
    from PIL import Image
    with Image.open(path) as im:
        d = im.info.get("dpi")
        if im.format == "TIFF" and 282 not in getattr(im, "tag_v2", {}):
            d = None                                     # Pillow podaje wtedy umowne (1, 1)
        if d and d[0] and d[1]:
            return path                                  # DPI jest — nic nie zmieniamy
        W, H, fmt = im.width, im.height, im.format
    pw, ph = print_mm
    if (W >= H) != (pw >= ph):                           # wymiar podany w drugiej orientacji
        pw, ph = ph, pw
    dpi = max(W / (pw / 25.4), H / (ph / 25.4))
    ext = os.path.splitext(path)[1].lower()
    out = os.path.join(job.dir, f"pobierz_{os.path.splitext(os.path.basename(path))[0]}_dpi{dpi:.3f}{ext}")
    with _download_lock:
        if os.path.exists(out):
            return out
        tmp = f"{out}.{threading.get_ident()}.part"
        with open(path, "rb") as f:
            data = f.read()
        if fmt == "JPEG":
            data = _jpeg_density(data, dpi)
            with open(tmp, "wb") as f:
                f.write(data)
        elif fmt == "PNG":
            data = _png_phys(data, dpi)
            with open(tmp, "wb") as f:
                f.write(data)
        elif fmt == "TIFF":
            with Image.open(path) as im:
                kw = {"dpi": (dpi, dpi)}
                if im.info.get("icc_profile"):
                    kw["icc_profile"] = im.info["icc_profile"]
                comp = im.info.get("compression")
                # JPEG w TIFF-ie zapisany jeszcze raz straciłby jakość — wtedy LZW (bezstratnie)
                kw["compression"] = comp if comp in ("raw", "tiff_lzw", "tiff_adobe_deflate", "packbits") else "tiff_lzw"
                im.save(tmp, "TIFF", **kw)
        else:
            return path                                  # GIF/BMP/WEBP — bez zmian
        os.replace(tmp, out)
    return out


def _jpeg_density(data: bytes, dpi: float) -> bytes:
    """Gęstość w nagłówku JFIF (APP0): istniejący poprawiony, brakujący dopisany za SOI.
    JFIF zapisuje liczby całkowite — jednostka (cale / cm) dająca mniejszy błąd."""
    import struct
    per_cm = dpi / 2.54
    unit, val = (1, round(dpi)) if abs(round(dpi) - dpi) / dpi <= abs(round(per_cm) - per_cm) / per_cm or round(per_cm) < 1 \
        else (2, round(per_cm))
    val = max(1, min(65535, val))
    dens = struct.pack(">BHH", unit, val, val)
    if data[2:4] == b"\xff\xe0" and data[6:11] == b"JFIF\x00":
        return data[:13] + dens + data[18:]
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01" + dens + b"\x00\x00"
    return data[:2] + app0 + data[2:]


def _png_phys(data: bytes, dpi: float) -> bytes:
    """Chunk pHYs (piksele na metr) przed pierwszym IDAT; stary pHYs (np. bez jednostki) wypada."""
    import struct
    import zlib
    ppm = max(1, round(dpi / 0.0254))
    body = b"pHYs" + struct.pack(">IIB", ppm, ppm, 1)
    phys = struct.pack(">I", 9) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    out, i, done = [data[:8]], 8, False
    while i + 8 <= len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        typ = data[i + 4:i + 8]
        chunk = data[i:i + 12 + n]
        if typ == b"pHYs":
            i += 12 + n
            continue
        if typ == b"IDAT" and not done:
            out.append(phys)
            done = True
        out.append(chunk)
        i += 12 + n
    return b"".join(out)


@app.get("/api/jobs/<jid>/progress")
def api_step_progress(jid):
    """Postęp trwającej poprawki (dziś: spłaszczenie) — bez blokady zadania, bo poprawka ją trzyma."""
    return jsonify(job_or_404(jid).progress or {})


@app.delete("/api/jobs/<jid>/steps/<name>")
def api_step_undo(jid, name):
    """Cofa poprawkę razem ze wszystkim, co zrobiono po niej."""
    job = job_or_404(jid)
    job.undo(name)
    return jsonify(job.to_json())


# ----------------------------------------------------------------------------
# podgląd w pełnej jakości (piramida)
# ----------------------------------------------------------------------------
# Miękkie maski (maska luminancji z gradientem, obraz z maską) MuPDF liczy inaczej niż Ghostscript
# i Acrobat — na adWall 400 dorysowywał ukośne „kliny” na pasach kurtyny (doc 20, Tomasz 27.10).
MUPDF_TILES_NO = ("maska", "obraz z maską")


def mupdf_tiles_ok(job, v, page: int, op: bool, proof: bool) -> bool:
    """Czy kafelki tej strony może rysować MuPDF (na żądanie, setne części sekundy) zamiast piramidy
    Ghostscripta — tylko tam, gdzie wynik jest taki sam (doc 20): treść CMYK / szarość / spot,
    bez miękkich masek, bez symulacji overprintu; na ekranie bez przezroczystości mieszanej w RGB."""
    if op or job.info.get("kind") == "raster":
        return False
    try:
        a = job.analysis_of(v, page)
    except Exception:
        return False
    if not a or a.get("error") or a.get("partial"):
        return False
    fam = (a.get("color") or {}).get("families") or {}
    if any("RGB" in f or f in ("Lab", "Unknown", "Indexed") for f in fam):
        return False
    if any(k.startswith(MUPDF_TILES_NO) for k in (a.get("transparency") or {})):
        return False
    return proof or not (a.get("blend_space_missing") or a.get("group_rgb"))


@app.route("/api/jobs/<jid>/view", methods=["GET", "POST"])
def api_view(jid):
    """GET = stan, POST = policz (jeśli trzeba). `w_mm`/`h_mm` = wymiar NA WYDRUKU —
    od niego zależy rozdzielczość (120 ppi wydruku)."""
    job = job_or_404(jid)
    v = job.version(request.args.get("v"))
    if v is None:
        return jsonify({"state": "gone"})
    page = arg_page(job)
    # NaN / nieskończoność / ≤ 0 — 400 (przegląd 09.10, B22); 1e9 mm podgląd i tak przycina (MAX_MPX)
    mm = (pos_float(request.args.get("w_mm"), "szerokość"), pos_float(request.args.get("h_mm"), "wysokość"))
    op, pr = request.args.get("op") == "1", request.args.get("pr") == "1"
    # „Krzywe” nie zmieniają wyglądu (podgląd i tak rysuje tekst z krzywych — render.text_as_curves):
    # widok poprzedniej wersji, bez liczenia od nowa (doc 20, krok 3). „Wyłącz overprint” — też, gdy
    # podgląd nie symuluje overprintu (Ghostscript z /disable i MuPDF overprint pomijają: piksele
    # identyczne, sprawdzone 29.10); z symulacją widać właśnie tę zmianę, więc liczy się od nowa.
    while v.step == "outline" or (v.step == "overprint" and not op):
        i = job.versions.index(v)
        if i == 0:
            break
        v = job.versions[i - 1]
    full = request.args.get("full", "1") == "1"
    try:
        lazy = full and mupdf_tiles_ok(job, v, page, op, pr)
        # wielostronicowy obraz: podgląd wybranej strony, nie zawsze pierwszej (A8)
        return jsonify(views.request(job, v.id, job.page_path(v, page), page, mm, op, pr, request.method == "POST",
                                     full=full, lazy=lazy))
    except Exception as e:
        return jsonify({"state": "err", "err": f"{type(e).__name__}: {e}"})


@app.post("/api/jobs/<jid>/view/<key>/region")
def api_view_region(jid, key):
    """Widoczny kawałek przybliżenia, zanim policzy się cała piramida (doc 20): poziom i prostokąt kafli."""
    job = job_or_404(jid)
    b = body_dict()
    try:
        lvl = int(b.get("lvl")); box = tuple(int(b[k]) for k in ("x0", "y0", "x1", "y1"))
    except (TypeError, ValueError, KeyError):
        return err("Zły wycinek.")
    return jsonify({"ok": views.region(job, key, lvl, box)})


@app.post("/api/jobs/<jid>/view/<key>/cancel")
def api_view_cancel(jid, key):
    """Przeglądarka już tego widoku nie potrzebuje (inna strona, inna wersja) — zwalniamy kolejkę."""
    views.cancel(job_or_404(jid), key)
    return jsonify({"ok": True})


@app.get("/api/jobs/<jid>/tile/<key>/<name>")
def api_tile(jid, key, name):
    """Kafelek — czysty odczyt z dysku, nic się tu nie liczy. Brak = jeszcze niepoliczony."""
    job = job_or_404(jid)
    if not re.fullmatch(r"[A-Za-z0-9_]+", key) or not re.fullmatch(r"(ov|ov_q|L\d+_\d+_\d+)\.jpg", name):
        return err("Zły adres kafelka.")
    p = views.tile(job, key, name)               # widok na żądanie: kafel liczony teraz (MuPDF)
    if not p:
        return err("Jeszcze nie policzony.", 404)
    return send_file(p, mimetype="image/jpeg", max_age=86400)


# ----------------------------------------------------------------------------
# wersja programu i aktualizacje
# ----------------------------------------------------------------------------
@app.get("/api/version")
def api_version():
    """Wersja programu i stan aktualizacji (updater.py): nowsze wydanie, pobieranie, gotowe."""
    return jsonify(updater.state())


@app.post("/api/update/install")
def api_update_install():
    """„Zaktualizuj teraz": uruchamia instalację i zamyka program (nowa wersja wstaje sama)."""
    msg = updater.install()
    if msg:
        return err(msg)
    # najpierw odpowiedź, potem koniec — po zatrzymaniu Ghostscripta i procesów jakości, jak przy
    # zamknięciu okna (przegląd 09.10, B23)
    import instance
    threading.Timer(1.0, lambda: (instance.shutdown(), os._exit(0))).start()
    return jsonify({"ok": True})


# Okno przeglądarki żyje? (program bez własnego okna kończy się sam, gdy nikt go nie używa)
last_seen = {"t": time.time()}


@app.post("/api/alive")
def api_alive():
    last_seen["t"] = time.time()
    return jsonify({"ok": True})


# ----------------------------------------------------------------------------
def main():
    # przy reloaderze Flaska ten sam kod startuje dwa razy (proces nadzorcy i proces serwera) —
    # blokadę bierze tylko serwujący; drugi run.bat nie skasuje plików działającego (C19)
    import instance
    if not (instance.acquire() if os.environ.get("WERKZEUG_RUN_MAIN") == "true" else not instance.busy()):
        print("[adChecker] już działa w innym oknie — zamknij je najpierw.")
        sys.exit(1)
    jobs.clean_work_dir()
    st = products.load_products()
    print(f"[adChecker] produkty: {st['count']} (źródło: {st['source']})"
          + (f" — uwaga: {st['error']}" if st.get("error") else ""))
    url = f"http://{HOST}:{PORT}/"
    print(f"[adChecker {VERSION}] {url}")
    # przy reloaderze proces startuje dwa razy — przeglądarkę otwiera tylko ten, który serwuje
    if "--no-browser" not in sys.argv and os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host=HOST, port=PORT, debug=True, use_reloader=True)


if __name__ == "__main__":
    main()
