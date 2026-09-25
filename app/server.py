"""adChecker — przygotowanie pliku do druku bez grafika DTP.

Uruchomienie deweloperskie: python server.py (albo run.bat) → http://127.0.0.1:5000
Zainstalowany program startuje przez desktop.py (własne okno, serwer produkcyjny).
Serwer to same trasy HTTP; logika siedzi w modułach (jobs, steps, render, …).
"""
from __future__ import annotations

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


def job_or_404(jid):
    job = jobs.get(jid)
    if not job:
        raise LookupError
    return job


@app.errorhandler(LookupError)
def _nojob(_):
    return err("Nie ma takiego zadania — wgraj plik jeszcze raz.", 404)


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
        return err(f"Nie udało się otworzyć pliku: {type(e).__name__}: {e}")
    job.suggestions = suggestions_for(job, 0)
    return jsonify(job.to_json())


def suggestions_for(job, page: int) -> list:
    """Propozycje produktu dla strony: z nazwy pliku, z treści (szablon zostawiony w pliku)
    i z wymiaru strony (także netto, gdy strona ma spady)."""
    p = job.info["pages"][page]
    hints = content_hints(job.original.path, page)
    job.info["template_frames"] = hints.get("ramki", [])
    return suggest.suggest_all(job.info["name"], p.get("width_mm"), p.get("height_mm"),
                               products.get_products(), sizeindex.load(), limit=5,
                               trim_mm=p.get("trim_mm"), hints=hints)


@app.get("/api/jobs/<jid>/suggest")
def api_suggest(jid):
    """Propozycje dla wybranej strony (strona jest wybierana przed produktem)."""
    job = job_or_404(jid)
    page = request.args.get("page", 0, type=int)
    if not 0 <= page < job.info["page_count"]:
        return err("Nie ma takiej strony.", 404)
    job.suggestions = suggestions_for(job, page)
    return jsonify(job.to_json())


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
    cache = os.path.join(job.dir, f"thumb_{n}.png")
    if not os.path.exists(cache):
        with open(cache, "wb") as fh:
            fh.write(render.page_png(job.original.path, n, 240))
    return send_file(cache, mimetype="image/png", max_age=3600)


@app.get("/api/jobs/<jid>/analysis")
def api_analysis(jid):
    """Fakty o stronie wersji pliku: kolory, profile, spoty, obrazy, overprint, przezroczystość,
    fonty. Zawsze o JEDNEJ stronie — do druku idzie jedna."""
    job = job_or_404(jid)
    v = job.version(request.args.get("v"))
    if v is None:
        return err("Tej wersji pliku już nie ma.", 404)
    page = request.args.get("page", 0, type=int)
    if not 0 <= page < job.info["page_count"]:
        return err("Nie ma takiej strony.")
    cache = job.analysis.setdefault(v.id, {})
    if page not in cache:
        try:
            res = analyze.analyze(v.path, page)
        except Exception as e:
            return err(f"Analiza nie powiodła się: {type(e).__name__}: {e}", 500)
        job.images.setdefault(v.id, {})[page] = res.pop("_images", None)
        cache[page] = res
    return jsonify({"version": v.id, "page": page, **cache[page]})


def gl_pdf(hash_: str) -> str | None:
    """Ścieżka do PDF-u wytycznych w pamięci podręcznej — z przeglądarki przychodzi tylko skrót."""
    if hash_ and HASH_RE.fullmatch(hash_):
        p = guidelines.pdf_path_for(hash_)
        if os.path.exists(p):
            return p
    return None


@app.get("/api/jobs/<jid>/frames")
def api_frames(jid):
    """Czy w pliku został szablon z wytycznych. Zawsze na ORYGINALE — usuwanie szablonu jest
    pierwszą poprawką, więc to dokładnie ten plik, na którym zadziała."""
    job = job_or_404(jid)
    page = request.args.get("page", 0, type=int)
    glp = request.args.get("glpage", -1, type=int)
    mm = job.original.pages_mm[page]
    if job.info["kind"] == "raster" or not mm or not mm[0]:
        return jsonify({"found": 0, "known": False, "pixels": False, "foreign": 0})
    try:
        r = frames.find(job.original.path, page, tuple(mm), gl_pdf(request.args.get("gl", "")), glp if glp >= 0 else None)
        # linie w kolorach wytycznych na obrazie strony — ale tylko gdy nie tłumaczą ich ramki
        # WEKTOROWE (bez wytycznych wektorowy szablon wyglądał jak „wtopiony w obraz")
        pixels = not r["found"] and not r["foreign"] and frames.in_pixels(job.original.path, page, tuple(mm))
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


@app.post("/api/jobs/<jid>/steps")
def api_step(jid):
    """Nakłada poprawkę na ostatnią wersję pliku → nowa wersja."""
    job = job_or_404(jid)
    body = request.get_json(silent=True) or {}
    name, params = body.get("name", ""), dict(body.get("params") or {})
    if name == "frames":
        params["gl_pdf"] = gl_pdf(params.get("gl", ""))
        glp = params.get("glpage")
        params["gl_page"] = int(glp) if isinstance(glp, int) and glp >= 0 else None
    try:
        job.apply(name, params)
    except ValueError as e:
        return err(str(e))
    except Exception as e:
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
    try:
        page = request.args.get("page", 0, type=int)
        k = round(float(request.args.get("k", "1")), 4)
        block = int(request.args.get("block", "128"))
        pm = (float(request.args["w_mm"]), float(request.args["h_mm"])) if request.args.get("w_mm") else None
    except (TypeError, ValueError):
        return err("Złe parametry.")
    if not (0 <= page < job.info["page_count"]) or not (0.01 <= k <= 100):
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
    path, fname, mime = download_file(job, request.args.get("page", 0, type=int), request.args.get("name", ""))
    resp = send_file(path, mimetype=mime, as_attachment=True, download_name=fname)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def download_file(job, page: int, name: str) -> tuple[str, str, str]:
    """(ścieżka, nazwa pliku, typ) pliku do druku — wspólne dla przeglądarki i okna programu
    (tam zapisuje go okno „Zapisz jako", desktop.py)."""
    v = job.head
    base = safe_name(name) or os.path.splitext(job.info["name"])[0] + "_do_druku"
    ext = os.path.splitext(v.path)[1].lower()
    path = v.path
    if not render.is_raster(v.path):
        ext = ".pdf"
        if job.info["page_count"] > 1:
            path = os.path.join(job.dir, f"pobierz_{v.id}_p{page}.pdf")
            if not os.path.exists(path):
                import pikepdf
                with pikepdf.open(v.path) as pdf:
                    keep = pdf.pages[page]
                    out = pikepdf.new()
                    out.pages.append(keep)
                    if "/OutputIntents" in pdf.Root:        # profil kolorystyczny idzie z plikiem
                        out.Root.OutputIntents = out.copy_foreign(pdf.Root.OutputIntents)
                    out.save(path)
    mime = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".tif": "image/tiff", ".tiff": "image/tiff", ".png": "image/png"}.get(ext, "application/octet-stream")
    return path, base + ext, mime


@app.delete("/api/jobs/<jid>/steps/<name>")
def api_step_undo(jid, name):
    """Cofa poprawkę razem ze wszystkim, co zrobiono po niej."""
    job = job_or_404(jid)
    job.undo(name)
    return jsonify(job.to_json())


# ----------------------------------------------------------------------------
# podgląd w pełnej jakości (piramida)
# ----------------------------------------------------------------------------
@app.route("/api/jobs/<jid>/view", methods=["GET", "POST"])
def api_view(jid):
    """GET = stan, POST = policz (jeśli trzeba). `w_mm`/`h_mm` = wymiar NA WYDRUKU —
    od niego zależy rozdzielczość (120 ppi wydruku)."""
    job = job_or_404(jid)
    v = job.version(request.args.get("v"))
    if v is None:
        return jsonify({"state": "gone"})
    try:
        page = int(request.args.get("page", 0))
        mm = (float(request.args["w_mm"]), float(request.args["h_mm"]))
    except (KeyError, ValueError):
        return err("Złe parametry.")
    if not 0 <= page < job.info["page_count"] or min(mm) <= 0:
        return err("Złe parametry.")
    op, pr = request.args.get("op") == "1", request.args.get("pr") == "1"
    try:
        return jsonify(views.request(job, v.id, v.path, page, mm, op, pr, request.method == "POST"))
    except Exception as e:
        return jsonify({"state": "err", "err": f"{type(e).__name__}: {e}"})


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
    p = os.path.join(job.dir, "view_" + key, name)
    if not os.path.exists(p):
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
    threading.Timer(1.0, lambda: os._exit(0)).start()      # najpierw odpowiedź, potem koniec
    return jsonify({"ok": True})


# Okno przeglądarki żyje? (program bez własnego okna kończy się sam, gdy nikt go nie używa)
last_seen = {"t": time.time()}


@app.post("/api/alive")
def api_alive():
    last_seen["t"] = time.time()
    return jsonify({"ok": True})


# ----------------------------------------------------------------------------
def main():
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
