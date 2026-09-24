"""Zamówienia na piramidy podglądu: kto co liczy, jak daleko jest i kiedy przestać.

Klucz widoku = wersja pliku + strona + symulacje + rozdzielczość. Wersje są NIEZMIENNE
(każda poprawka to nowy plik o nowym numerze), więc gotowa piramida nigdy nie przestaje
być prawdziwa — nie ma czego unieważniać ani nadpisywać w trakcie oglądania.
"""
from __future__ import annotations

import os
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


def key_of(vid: str, page: int, op: bool, proof: bool, W: int) -> str:
    return f"{vid}_p{page}_{int(op)}{int(proof)}_{W}_r{render.RENDER_VER}"


def _public(key: str, pl: dict, e: dict) -> dict:
    return {"key": key, "plan": pl, **{k: e[k] for k in ("state", "done", "total", "quick", "err") if k in e}}


def request(job, vid: str, src: str, page: int, print_mm: tuple, op: bool, proof: bool, start: bool) -> dict:
    """Stan widoku; przy `start` — zamawia liczenie (albo je wznawia po błędzie/przerwaniu)."""
    pk = (job.id, vid, page, round(print_mm[0], 2), round(print_mm[1], 2))
    pl = _plans.get(pk)
    if pl is None:
        doc = render.open_doc(src)
        try:
            r = doc[page].rect
            native = (r.width, r.height) if render.is_raster(src) else None
            pl = _plans[pk] = render.plan(r.width, r.height, print_mm[0], print_mm[1], native)
        finally:
            doc.close()
    key = key_of(vid, page, op, proof, pl["w"])
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
            if jid == job.id and k2 != key and k2.startswith(same):
                old["stop"] = True
                _views.pop((jid, k2), None)
                shutil.rmtree(os.path.join(job.dir, "view_" + k2), ignore_errors=True)
        total = 1 + (pl["levels"][0]["rows"] if pl["levels"] else 0) + max(0, len(pl["levels"]) - 1)
        e = _views[(job.id, key)] = {"state": "queued", "done": 0, "total": total, "tok": uuid.uuid4().hex,
                                     "seen": time.time()}
    threading.Thread(target=_worker, args=(job, key, src, page, pl, out, op, proof, e["tok"]), daemon=True).start()
    return _public(key, pl, e)


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
    for f in os.listdir(job.dir):
        if f.startswith("view_") and (vids is None or f[5:].split("_p")[0] in vids):
            shutil.rmtree(os.path.join(job.dir, f), ignore_errors=True)
