"""
Lista produktów Adsystem.

Źródło: https://noname.tey.pl/adlogo/?langs=en
Strona to zwykły HTML (tabela generowana po stronie serwera):
    kolumna 1 = nazwa produktu
    kolumna 2 = kod produktu + link do PDF-a wytycznych (z logo)
    kolumna 3 = kod produktu + link do PDF-a wytycznych (bez logo, nl=1)

Strategia:
    1. przy starcie / na żądanie pobieramy stronę i parsujemy tabelę,
    2. wynik zapisujemy w data/products_cache.json (ważny 24 h),
    3. gdy pobranie się nie uda -> używamy cache (nawet przeterminowanego),
    4. gdy nie ma cache -> używamy data/products_snapshot.json (migawka
       zapisana w repozytorium, wykonana 2026-09-03).

Wiersze na stronie się powtarzają (ten sam produkt, ten sam hash) —
deduplikujemy po hashu.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

SOURCE_URL = "https://noname.tey.pl/adlogo/?langs=en"
REQUIREMENTS_URL = "https://noname.tey.pl/file/requirements"
CACHE_TTL_S = 24 * 3600

import paths
from version import UA

DATA_DIR = paths.DATA
CACHE_PATH = os.path.join(DATA_DIR, "products_cache.json")
SNAPSHOT_PATH = os.path.join(paths.DATA_RO, "products_snapshot.json")   # zapasowa kopia z paczki

_lock = threading.Lock()
_state: dict = {"products": [], "source": None, "fetched": None, "error": None}


# ----------------------------------------------------------------------------
# Parsowanie HTML
# ----------------------------------------------------------------------------
class _TableParser(HTMLParser):
    """Zbiera wiersze <tr> tabeli jako listę komórek; każda komórka =
    (tekst, href pierwszego linku w komórce lub None)."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[tuple[str, str | None]]] = []
        self._row = None
        self._cell = None
        self._href = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._href = None
        elif tag == "a" and self._cell is not None and self._href is None:
            self._href = dict(attrs).get("href")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(("".join(self._cell).strip(), self._href))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def parse_products_html(html: str) -> list[dict]:
    parser = _TableParser()
    parser.feed(html)
    seen = set()
    products = []
    for row in parser.rows:
        if len(row) < 2:
            continue
        name, _ = row[0]
        code, href = row[1]
        if not href or not code:
            continue  # nagłówek albo pusty wiersz
        q = parse_qs(urlparse(href).query)
        h = (q.get("hash") or [None])[0]
        if not h or h in seen:
            continue
        seen.add(h)
        products.append({"name": name, "code": code, "hash": h})
    return products


def requirements_url(hash_: str, lang: str = "en", no_logo: bool = False) -> str:
    nl = "&nl=1" if no_logo else ""
    return f"{REQUIREMENTS_URL}?type=product{nl}&hash={hash_}&lang={lang}"


# ----------------------------------------------------------------------------
# Pobieranie / cache
# ----------------------------------------------------------------------------
def _fetch_remote(timeout: float = 15.0) -> list[dict]:
    req = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": UA}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    products = parse_products_html(html)
    if len(products) < 100:  # coś poszło nie tak – strona się zmieniła?
        raise RuntimeError(f"Sparsowano tylko {len(products)} produktów")
    return products


def _load_json(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save_cache(products: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"fetched_ts": time.time(), "products": products}, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def _set(products, source, fetched_ts=None, error=None):
    with _lock:
        _state["products"] = products
        _state["source"] = source
        _state["fetched"] = fetched_ts
        _state["error"] = error


def load_products(force_refresh: bool = False) -> dict:
    """Zwraca dict: products, source ('remote'|'cache'|'snapshot'), fetched, error."""
    cache = _load_json(CACHE_PATH)
    cache_fresh = bool(cache) and (time.time() - cache.get("fetched_ts", 0)) < CACHE_TTL_S

    if cache_fresh and not force_refresh:
        _set(cache["products"], "cache", cache["fetched_ts"])
        return status()

    try:
        products = _fetch_remote()
        _save_cache(products)
        _set(products, "remote", time.time())
        return status()
    except Exception as e:  # brak sieci, timeout, zmiana strony...
        err = f"{type(e).__name__}: {e}"

    if cache:
        _set(cache["products"], "cache", cache.get("fetched_ts"), err)
        return status()

    snap = _load_json(SNAPSHOT_PATH) or {"products": []}
    _set(snap["products"], "snapshot", None, err)
    return status()


def status() -> dict:
    with _lock:
        return {
            "count": len(_state["products"]),
            "source": _state["source"],
            "fetched": _state["fetched"],
            "error": _state["error"],
        }


def get_products() -> list[dict]:
    if not _state["products"]:
        load_products()
    with _lock:
        return list(_state["products"])
