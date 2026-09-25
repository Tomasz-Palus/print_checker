"""
Indeks wymiarów szablonów — do sugerowania produktu po WYMIARZE pliku.

Lista produktów nie zawiera wymiarów szablonów; są one dopiero w PDF-ach
wytycznych (strona 2+: „W x H [mm]”, skala na stronie 1). Indeks powstaje przez
pobranie i sparsowanie wytycznych każdego produktu (guidelines.get_guidelines —
z cache w data/guidelines/), w tle, z możliwością wznowienia. Wynik:
data/template_index.json:
    { "<hash>": {"scale": "1:1"|"1:10"|null, "templates": [{"role","w","h","missing"}], "ok": true},
      "<hash>": {"ok": false, "error": "..."} }
Ok. 1000 PDF-ów × ~300 KB ≈ 300 MB na dysku; pobieranie 8 wątkami — zwykle 2–4 min.
"""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import guidelines
import products

import paths

DATA_DIR = paths.DATA
INDEX_PATH = paths.seeded("template_index.json")   # indeks z dnia wydania, potem uzupełniany

_lock = threading.Lock()
_index: dict = {}
_status = {"running": False, "done": 0, "total": 0, "errors": 0, "last_error": None, "started": None, "finished": None}
_stop = False
MAX_ERROR_STREAK = 15
WORKERS = 8          # równoległe pobrania


def _read(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def load() -> dict:
    """Indeks użytkownika + indeks z instalatora. Instalator każdej wersji wiezie indeks z dnia
    wydania; produkty, których użytkownik jeszcze nie ma (albo ma tylko nieudane próby), bierzemy
    stamtąd — nowa wersja programu przynosi też nowe wymiary."""
    global _index
    with _lock:
        if not _index:
            _index = _read(INDEX_PATH) if os.path.exists(INDEX_PATH) else {}
            ro = os.path.join(paths.DATA_RO, "template_index.json")
            if os.path.abspath(ro) != os.path.abspath(INDEX_PATH):
                added = 0
                for k, v in _read(ro).items():
                    if k not in _index or (not _index[k].get("ok") and v.get("ok")):
                        _index[k] = v
                        added += 1
                if added:
                    print(f"[indeks] z instalatora dołożono {added} produktów")
        return _index


def _save() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = INDEX_PATH + ".tmp"
    with _lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_index, f, ensure_ascii=False)
    os.replace(tmp, INDEX_PATH)


def entry_from_guidelines(data: dict) -> dict:
    return {
        "ok": True,
        "scale": data.get("scale"),
        "templates": [{"role": t.get("role"), "w": t.get("width_mm"), "h": t.get("height_mm"),
                       "missing": bool(t.get("dims_missing"))} for t in data.get("templates", [])],
    }


def add_from_guidelines(hash_: str, data: dict) -> None:
    """Wywoływane też przy zwykłym pobraniu wytycznych — indeks rośnie przy okazji."""
    if not hash_:
        return
    load()
    with _lock:
        _index[hash_] = entry_from_guidelines(data)
    try:
        _save()
    except OSError:
        pass


def status() -> dict:
    idx = load()
    total = len(products.get_products())
    ok = sum(1 for v in idx.values() if v.get("ok"))
    with _lock:
        st = dict(_status)
    st.update({"indexed": ok, "failed": sum(1 for v in idx.values() if not v.get("ok")), "total_products": total})
    return st


def _fetch_one(p: dict) -> tuple[str, dict]:
    h = p["hash"]
    try:
        data = guidelines.get_guidelines(h)
        return h, entry_from_guidelines(data)
    except Exception as e:
        return h, {"ok": False, "error": f"{type(e).__name__}: {e}", "name": p.get("name")}


def _worker(retry_failed: bool) -> None:
    """Pobiera wytyczne brakujących produktów RÓWNOLEGLE (WORKERS wątków) — pobieranie
    to głównie czekanie na sieć, więc 8 wątków daje ~6–8× krótszy czas niż po kolei."""
    idx = load()
    plist = products.get_products()
    todo = [p for p in plist if p["hash"] not in idx or (retry_failed and not idx[p["hash"]].get("ok"))]
    with _lock:
        _status.update({"running": True, "done": 0, "total": len(todo), "errors": 0, "last_error": None,
                        "started": time.time(), "finished": None})
    streak = 0   # kolejne błędy z rzędu — przy braku sieci przerywamy, zamiast mielić 1000 timeoutów
    n = 0
    pool = ThreadPoolExecutor(max_workers=WORKERS)
    try:
        it = iter(todo)
        pending = set()
        def submit_next():
            p = next(it, None)
            if p is not None:
                pending.add(pool.submit(_fetch_one, p))
        for _ in range(WORKERS):
            submit_next()
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                h, entry = fut.result()
                with _lock:
                    _index[h] = entry
                    _status["done"] += 1
                    if entry.get("ok"):
                        streak = 0
                    else:
                        streak += 1
                        _status["errors"] += 1
                        _status["last_error"] = f"{entry.get('name')}: {entry['error']}"
                n += 1
                if n % 20 == 0:
                    try:
                        _save()
                    except OSError:
                        pass
            if _stop or streak >= MAX_ERROR_STREAK:
                if streak >= MAX_ERROR_STREAK:
                    with _lock:
                        _status["last_error"] = f"przerwano po {streak} błędach z rzędu (brak połączenia?) — ostatni: {_status['last_error']}"
                for fut in pending:
                    fut.cancel()
                break
            for _ in range(len(done)):
                submit_next()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        try:
            _save()
        except OSError:
            pass
        with _lock:
            _status["running"] = False
            _status["finished"] = time.time()


def start_build(retry_failed: bool = False) -> dict:
    global _stop
    with _lock:
        if _status["running"]:
            return status()
    _stop = False
    threading.Thread(target=_worker, args=(retry_failed,), daemon=True).start()
    time.sleep(0.05)
    return status()


def stop_build() -> dict:
    global _stop
    _stop = True
    return status()
