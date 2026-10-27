"""Zamówienia na piramidy podglądu: kto co liczy, jak daleko jest i kiedy przestać.

Klucz widoku = wersja pliku + strona + symulacje + rozdzielczość. Wersje są NIEZMIENNE
(każda poprawka to nowy plik o nowym numerze), więc gotowa piramida nigdy nie przestaje
być prawdziwa — nie ma czego unieważniać ani nadpisywać w trakcie oglądania.
"""
from __future__ import annotations

import os
import re
import shutil
import threading
import time
import traceback
import uuid

import render

_views: dict = {}                 # (job_id, key) -> wpis
_lock = threading.Lock()
_gs_lock = threading.Lock()       # jeden przebieg naraz — dwa zajechałyby komputer
FORGOTTEN_S = 120.0               # tyle bez pytania o stan = widok porzucony (zamknięta karta);
                                  # zwykłe porzucenie przeglądarka zgłasza sama (cancel)
_plans: dict = {}                 # (zadanie, wersja, strona, mm) -> plan — bez otwierania pliku co 0,6 s
MAX_PLANS = 200                   # najstarsze wypadają (słownik trzyma kolejność dodania)


def key_of(vid: str, page: int, op: bool, proof: bool, W: int) -> str:
    return f"{vid}_p{page}_{int(op)}{int(proof)}_{W}_r{render.RENDER_VER}"


def _public(key: str, pl: dict, e: dict) -> dict:
    return {"key": key, "plan": pl, **{k: e[k] for k in ("state", "done", "total", "quick", "err") if k in e}}


def request(job, vid: str, src: str, page: int, print_mm: tuple, op: bool, proof: bool, start: bool,
            full: bool = True, lazy: bool = False) -> dict:
    """Stan widoku; przy `start` — zamawia liczenie (albo je wznawia po błędzie/przerwaniu).

    `full=False` — sam podgląd całej strony (ov.jpg, dłuższy bok 2048 px), bez kafelków do
    przybliżania. Przybliżać można tylko w „Jakości wydruku” (Tomasz 28.09), więc poza nią pełna
    darmo — to ją pokazywał pasek „pełna jakość” przy suwakach.

    `lazy=True` (doc 20, Tomasz 27.10 — przybliżanie wszędzie): strona, którą MuPDF rysuje tak samo jak
    Ghostscript (server.mupdf_tiles_ok) — bez piramidy liczonej z góry: od razu podgląd całości,
    a kafelki powstają, gdy przeglądarka o nie poprosi (`tile`)."""
    pk = (job.id, vid, page, round(print_mm[0], 2), round(print_mm[1], 2))
    pl = _plans.get(pk)
    if pl is None:
        if render.is_raster(src):
            # raster: prawdziwe piksele z Pillow — wymiar strony z MuPDF przy DPI ≥ 72 jest już
            # w punktach i podgląd liczył się w za małej rozdzielczości (przegląd 09.10, A1).
            # `src` to plik JEDNEJ strony (Job.page_path), więc klatka 0.
            from PIL import Image
            with Image.open(src) as im:
                native = (im.width, im.height)
            pl = render.plan(native[0], native[1], print_mm[0], print_mm[1], native)
        else:
            with render.MUPDF_LOCK:          # przegląd 09.10, B24
                doc = render.open_doc(src)
                try:
                    r = doc[page].rect
                finally:
                    doc.close()
            pl = render.plan(r.width, r.height, print_mm[0], print_mm[1], None)
        with _lock:
            # górna granica: każdy inny wymiar wydruku to nowy wpis (przegląd 09.10, C)
            if len(_plans) >= MAX_PLANS:
                for old in list(_plans)[:len(_plans) - MAX_PLANS + 1]:
                    _plans.pop(old, None)
            _plans[pk] = pl
    if not full:
        pl = {**pl, "levels": []}                 # render.build: bez poziomów = sam podgląd całości
    lazy = lazy and full and bool(pl["levels"]) and not render.is_raster(src)
    key = key_of(vid, page, op, proof, pl["w"]) + ("" if full else "_ov") + ("_mu" if lazy else "")
    out = os.path.join(job.dir, "view_" + key)
    with _lock:
        e = _views.get((job.id, key))
        if e:
            e["seen"] = time.time()
        if e and not (start and e["state"] in ("stale", "err")):
            return _public(key, pl, e)
        if not start:
            return {"key": key, "plan": pl, "state": "idle"}
        # ta sama wersja i symulacje w INNEJ rozdzielczości (zmiana skali/produktu) — stara
        # ma się poddać od razu, żeby nie zajmowała procesora
        same = f"{vid}_p{page}_{int(op)}{int(proof)}_"
        for (jid, k2), old in list(_views.items()):
            # tylko INNA rozdzielczość; podgląd całości i pełna piramida tej samej wersji żyją obok siebie
            if jid == job.id and k2 != key and k2.startswith(same) and k2.split("_")[3] != str(pl["w"]):
                old["stop"] = True
                _views.pop((jid, k2), None)
                shutil.rmtree(os.path.join(job.dir, "view_" + k2), ignore_errors=True)
        total = 1 + (pl["levels"][0]["rows"] if pl["levels"] else 0) + max(0, len(pl["levels"]) - 1)
        e = _views[(job.id, key)] = {"state": "queued", "done": 0, "total": 1 if lazy else total,
                                     "tok": uuid.uuid4().hex, "seen": time.time()}
        e.update(pl=pl, out=out, src=src, page=page, op=op, proof=proof)
        if lazy:
            e["lazy"] = True
    target = _lazy_worker if lazy else _worker
    threading.Thread(target=target, args=(job, key, src, page, pl, out, op, proof, e["tok"]), daemon=True).start()
    return _public(key, pl, e)


def _lazy_worker(job, key, src, page, pl, out, op, proof, tok):
    """Widok na żądanie: podgląd całości MuPDF-em (bez kolejki Ghostscripta). Gdy MuPDF nie daje rady —
    zwykła piramida Ghostscripta pod tym samym kluczem."""
    e = _views.get((job.id, key))
    if not e or e.get("tok") != tok:
        return
    e["state"] = "run"
    try:
        r = render.build_lazy(src, page, pl, out)
    except Exception as ex:
        r = None
        _log(job, key, ex)
    with _lock:
        e = _views.get((job.id, key))
        if not e or e.get("tok") != tok:
            return
        if r:
            e.update(state="done", done=1, cur=r[0], cpage=r[1])
            return
        e.update(lazy=False, state="queued", total=1 + (pl["levels"][0]["rows"] if pl["levels"] else 0)
                 + max(0, len(pl["levels"]) - 1))
    _worker(job, key, src, page, pl, out, op, proof, tok)


_regions: dict = {}               # zadanie -> ostatnio zamówiony wycinek (starsze nieaktualne — widok się przesunął)
_region_busy: set = set()


def region(job, key: str, lvl: int, box: tuple) -> bool:
    """Przeglądarka przybliżyła widok, którego piramida (Ghostscript) jeszcze się liczy: najpierw widoczny
    kawałek (render.gs_block), obok piramidy. Jeden wycinek naraz na zadanie; liczy się ostatnie zamówienie."""
    with _lock:
        e = _views.get((job.id, key))
        if not e or e.get("lazy") or e.get("state") == "done" or "pl" not in e or not e["pl"]["levels"] \
                or render.is_raster(e["src"]):
            return False
        _regions[job.id] = (key, lvl, box, dict(e))
        if job.id in _region_busy:
            return True
        _region_busy.add(job.id)
    threading.Thread(target=_region_worker, args=(job,), daemon=True).start()
    return True


def _region_worker(job) -> None:
    while True:
        with _lock:
            want = _regions.pop(job.id, None)
            if want is None:
                _region_busy.discard(job.id)
                return
        key, lvl, box, e = want
        try:
            t0 = time.time()
            n = render.gs_block(e["src"], e["page"], e["pl"], lvl, box, e["op"], e["proof"], e["out"])
            print(f"[adChecker] wycinek podglądu: {n} kafli (poziom {lvl}) w {time.time() - t0:.1f} s")
        except Exception as ex:
            _log(job, key + " (wycinek)", ex)


def tile(job, key: str, name: str) -> str | None:
    """Ścieżka kafelka: gotowy z dysku albo — w widoku na żądanie — policzony teraz (MuPDF)."""
    out = os.path.join(job.dir, "view_" + key)
    p = os.path.join(out, name)
    if os.path.exists(p):
        return p
    # widok na żądanie dopiero startuje (podgląd całości MuPDF-em, ułamek sekundy) — chwilę czekamy,
    # zamiast odsyłać „jeszcze nie ma” (przeglądarka ponawia dopiero po 1,5 s)
    for _ in range(100):
        with _lock:
            e = _views.get((job.id, key))
            if not e or not e.get("lazy") or e.get("state") not in ("queued", "run"):
                break
        time.sleep(0.05)
    with _lock:
        e = _views.get((job.id, key))
        e = dict(e) if e and e.get("lazy") and e.get("state") == "done" else None
    m = re.fullmatch(r"L(\d+)_(\d+)_(\d+)\.jpg", name)
    if not e or not m:
        return None
    try:
        return render.lazy_tile(e["cur"], e["cpage"], e["pl"], int(m[1]), int(m[2]), int(m[3]), out, e["cur"])
    except Exception as ex:
        _log(job, key, ex)
        return None


def _worker(job, key, src, page, pl, out, op, proof, tok):
    def mine():
        e = _views.get((job.id, key))
        return e if e is not None and e.get("tok") == tok else None

    def set_(**kw):
        with _lock:
            e = mine()
            if e:
                e.update(kw)

    def stop():
        # Widok porzucony (przeglądarka odwołała go albo od dawna nie pyta — zamknięta karta)
        # nie może blokować kolejki Ghostscripta.
        with _lock:
            e = mine()
            return not e or bool(e.get("stop")) or time.time() - e.get("seen", 0) > FORGOTTEN_S

    def progress(band, quick):
        with _lock:
            e = mine()
            if not e:
                return
            if quick:
                e["quick"] = True
            if band is not None:
                e["done"] = max(e["done"], 1 + band)

    # Przybliżenie poza „Jakością” zamawia piramidę i zaraz potem widoczny wycinek (region) — wycinek ma
    # pierwszeństwo: piramida rusza, gdy go nie ma (na 2 rdzeniach oba naraz liczyły się 3× dłużej).
    time.sleep(2.0)
    t0 = time.time()
    while job.id in _region_busy and time.time() - t0 < 120 and not stop():
        time.sleep(0.2)
    with _gs_lock:
        if not stop():
            set_(state="run")
            try:
                render.build(src, page, pl, out, op, proof, progress, stop)
            except Exception as ex:
                set_(state="err", err=f"{type(ex).__name__}: {ex}")
                _log(job, key, ex)
                return
        # przerwany (porzucony albo zastąpiony) = „stale": ponowne zamówienie liczy od nowa
        halted = stop()
        with _lock:
            e = mine()
            if e:
                e.update(state="stale" if halted else "done", done=e["total"])


def _log(job, key, ex) -> None:
    """Błąd pełnej jakości do `work/_bledy_podgladu.log` — na Windowsie bywa inaczej niż w testach."""
    txt = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {job.id} {key}: {type(ex).__name__}: {ex}\n{traceback.format_exc()}\n"
    print("[adChecker] podgląd — błąd:", txt)
    try:
        with open(os.path.join(os.path.dirname(job.dir), "_bledy_podgladu.log"), "a", encoding="utf-8") as fh:
            fh.write(txt)
    except OSError:
        pass


def cancel(job, key: str) -> None:
    with _lock:
        e = _views.get((job.id, key))
        if e and e["state"] in ("queued", "run"):
            e["stop"] = True
            _views.pop((job.id, key), None)


def drop(job, vids: set | None = None) -> None:
    """Zapomina widoki zadania (wszystkie albo tylko wskazanych wersji) i kasuje ich kafelki."""
    with _lock:
        for (jid, k), e in list(_views.items()):
            if jid == job.id and (vids is None or k.split("_p")[0] in vids):
                e["stop"] = True
                _views.pop((jid, k), None)
        for pk in [pk for pk in _plans if pk[0] == job.id and (vids is None or pk[1] in vids)]:
            _plans.pop(pk, None)
    if not os.path.isdir(job.dir):
        return
    render.forget_docs(job.dir)                   # kafelki na żądanie trzymają pliki otwarte
    for f in os.listdir(job.dir):
        if f.startswith("view_") and (vids is None or f[5:].split("_p")[0] in vids):
            shutil.rmtree(os.path.join(job.dir, f), ignore_errors=True)
