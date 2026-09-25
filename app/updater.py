"""Aktualizacje programu (wersja 0.4) — przycisk „Zaktualizuj teraz" (decyzja Tomasza).

1. Raz na 6 h (i przy starcie) pytamy GitHuba o najnowsze wydanie (`version.REPO`).
2. Gdy jest nowsze, a program jest ZAINSTALOWANY (paczka PyInstallera), w tle pobieramy
   instalator dla tego systemu i sprawdzamy jego sumę SHA-256 z pliku SHA256SUMS.txt w wydaniu —
   uszkodzony albo podmieniony plik nie zostanie uruchomiony.
3. Nagłówek pokazuje przycisk „Zaktualizuj do X”. Kliknięcie: program uruchamia instalację
   i sam się zamyka; po instalacji nowa wersja startuje sama.
   - Windows: instalator Inno Setup po cichu (/VERYSILENT); uruchomienie po instalacji robi
     wpis [Run] ze znacznikiem `skipifnotsilent` (packaging/windows/adchecker.iss).
   - macOS: obraz DMG montowany w tle, nowa aplikacja podmienia starą po zamknięciu programu
     (mały skrypt czeka, aż proces się skończy), potem `open`. NIESPRAWDZONE na prawdziwym Macu.
W trybie deweloperskim (python server.py) niczego nie pobieramy — tylko link do wydania.

Plik pobrany przez program (a nie przeglądarkę) nie ma znacznika „z internetu”, więc Windows nie
pokazuje przy aktualizacji ostrzeżenia SmartScreen, a macOS — Gatekeepera.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import paths
from version import REPO, UA, VERSION

CHECK_EVERY_S = 6 * 3600
_lock = threading.Lock()
_st = {"checked": 0.0, "latest": None, "url": None, "asset": None, "sums": None,
       "status": "idle", "progress": 0, "error": None, "file": None}


def _newer(a: str | None, b: str) -> bool:
    try:
        return a is not None and tuple(int(x) for x in a.split(".")) > tuple(int(x) for x in b.split("."))
    except ValueError:
        return False


def _asset_suffix() -> str | None:
    if sys.platform == "win32":
        return "-Windows-instalator.exe"
    if sys.platform == "darwin":
        return "-macOS.dmg"
    return None


def can_self_update() -> bool:
    return paths.FROZEN and _asset_suffix() is not None


def _get(url: str, timeout: float = 20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _check() -> None:
    try:
        with _get(f"https://api.github.com/repos/{REPO}/releases/latest", 8) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:
        return                                   # brak sieci / GitHub — cisza, spróbujemy później
    latest = str(d.get("tag_name", "")).lstrip("v") or None
    suffix = _asset_suffix()
    assets = {a.get("name", ""): a.get("browser_download_url") for a in d.get("assets", [])}
    with _lock:
        _st["latest"], _st["url"] = latest, d.get("html_url")
        _st["asset"] = next(((n, u) for n, u in assets.items() if suffix and n.endswith(suffix)), None)
        _st["sums"] = assets.get("SHA256SUMS.txt")
        go = can_self_update() and _newer(latest, VERSION) and _st["asset"] and _st["status"] in ("idle", "error")
        if go:
            _st.update(status="downloading", progress=0, error=None)
    if go:
        _download()


def _download() -> None:
    name, url = _st["asset"]
    folder = os.path.join(paths.USER_DIR, "update")
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, name)
    try:
        want = None
        if _st["sums"]:
            with _get(_st["sums"]) as r:
                for line in r.read().decode("utf-8", "replace").splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[1].lstrip("*") == name:
                        want = parts[0].lower()
        if not want:
            raise RuntimeError("wydanie nie ma sumy kontrolnej instalatora")
        h = hashlib.sha256()
        with _get(url, 60) as r, open(dst + ".part", "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    _st["progress"] = int(done * 100 / total)
        if h.hexdigest() != want:
            raise RuntimeError("suma kontrolna się nie zgadza — plik uszkodzony")
        os.replace(dst + ".part", dst)
        with _lock:
            _st.update(status="ready", progress=100, file=dst)
        print(f"[aktualizacja] pobrana {name}")
    except Exception as e:
        with _lock:
            _st.update(status="error", error=f"{type(e).__name__}: {e}")
        print(f"[aktualizacja] błąd pobierania: {e}")


def state() -> dict:
    """Stan dla nagłówka (/api/version). Przy okazji — raz na 6 h — sprawdzenie w tle."""
    if time.time() - _st["checked"] > CHECK_EVERY_S:
        _st["checked"] = time.time()
        threading.Thread(target=_check, daemon=True).start()
    new = _newer(_st["latest"], VERSION)
    return {"version": VERSION, "update": _st["latest"] if new else None,
            "update_url": _st["url"] if new else None,
            "self_update": can_self_update(), "status": _st["status"] if new else "idle",
            "progress": _st["progress"], "error": _st["error"]}


def install() -> str | None:
    """Uruchamia instalację pobranej wersji. Zwraca komunikat błędu albo None — wtedy program
    ma się zaraz zamknąć (robi to wywołujący, po wysłaniu odpowiedzi)."""
    if _st["status"] != "ready" or not _st["file"] or not os.path.exists(_st["file"]):
        return "Nowa wersja nie jest jeszcze pobrana."
    f = _st["file"]
    try:
        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([f, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], creationflags=flags,
                             close_fds=True)
            return None
        if sys.platform == "darwin":
            return _install_mac(f)
    except Exception as e:
        return f"Nie udało się uruchomić aktualizacji: {e}"
    return "Ten system nie ma automatycznej aktualizacji."


def _install_mac(dmg: str) -> str | None:
    # /…/adChecker.app/Contents/MacOS/adChecker → /…/adChecker.app
    app = os.path.abspath(os.path.join(os.path.dirname(sys.executable), "..", ".."))
    if not app.endswith(".app"):
        return "Nie znalazłem aplikacji do podmiany."
    if app.startswith("/Volumes/"):
        return "Program działa prosto z obrazu DMG — przeciągnij go najpierw do folderu Aplikacje."
    if not os.access(os.path.dirname(app), os.W_OK):
        return "Brak uprawnień do folderu z programem — zainstaluj nową wersję ręcznie."
    mnt = tempfile.mkdtemp(prefix="adchecker_dmg_")
    subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", mnt, dmg],
                   check=True, capture_output=True)
    try:
        src = os.path.join(mnt, "adChecker.app")
        new = app + ".nowa"
        shutil.rmtree(new, ignore_errors=True)
        subprocess.run(["ditto", src, new], check=True, capture_output=True)
    finally:
        subprocess.run(["hdiutil", "detach", mnt, "-quiet"], capture_output=True)
    # czekamy, aż ten proces się zamknie, podmieniamy i uruchamiamy nową wersję
    script = (f'while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.5; done; '
              f'rm -rf "{app}.stara"; mv "{app}" "{app}.stara" && mv "{new}" "{app}" && '
              f'rm -rf "{app}.stara"; open "{app}"')
    subprocess.Popen(["/bin/sh", "-c", script], start_new_session=True, close_fds=True)
    return None
