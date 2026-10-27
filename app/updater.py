"""Aktualizacje programu (wersja 0.4) — przycisk „Zaktualizuj teraz" (decyzja Tomasza).

1. Raz na 6 h (i przy starcie) pytamy GitHuba o najnowsze wydanie (`version.REPO`).
2. Gdy jest nowsze, a program jest ZAINSTALOWANY (paczka PyInstallera), w tle pobieramy
   instalator dla tego systemu i sprawdzamy jego sumę SHA-256 z pliku SHA256SUMS.txt w wydaniu —
   uszkodzony plik nie zostanie uruchomiony. Gdy program ma klucz (update_key.py), plik sum
   musi mieć jeszcze poprawny podpis Ed25519 (SHA256SUMS.txt.sig) — podmieniony nie przejdzie.
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
# status: idle → downloading → ready → installing; error (sieć — spróbujemy później, link do
# wydania) albo rejected (zły podpis / suma / wersja — bez linku i przycisku, przegląd 09.10, B23).
# `ver` — wersja, którą pobieramy / mamy gotową (przycisk pokazuje ją, a nie nowszą z GitHuba).
_st = {"checked": 0.0, "latest": None, "url": None, "asset": None, "sums": None, "sig": None,
       "status": "idle", "progress": 0, "error": None, "file": None, "ver": None, "sha": None}


class Rejected(Exception):
    """Wydanie nie przeszło sprawdzenia (podpis, suma, wersja) — nie instalujemy i nie podsuwamy."""


def _vt(v: str | None) -> tuple | None:
    """Numer wersji jako krotka bez końcowych zer („0.6.7.0” = „0.6.7”); None — numer niepoprawny."""
    try:
        t = [int(x) for x in str(v).split(".")]
    except ValueError:
        return None
    if not t or any(x < 0 for x in t):
        return None
    while len(t) > 1 and t[-1] == 0:
        t.pop()
    return tuple(t)


def _newer(a: str | None, b: str) -> bool:
    ta, tb = (_vt(a) if a else None), _vt(b)
    return ta is not None and tb is not None and ta > tb


def _ssl_ctx():
    """Mac: certyfikaty z certifi (paczka PyInstallera nie widzi systemowych — przegląd 09.10, C23).
    Windows zostaje przy magazynie systemu (firmowe proxy z własnym certyfikatem)."""
    if sys.platform != "darwin":
        return None
    try:
        import ssl
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


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
    ctx = _ssl_ctx()
    return urllib.request.urlopen(req, timeout=timeout, **({"context": ctx} if ctx else {}))


def _check() -> None:
    try:
        with _get(f"https://api.github.com/repos/{REPO}/releases/latest", 8) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        # brak sieci / GitHub — spróbujemy później; ślad w dzienniku (np. brak certyfikatów na Macu)
        print(f"[aktualizacja] sprawdzenie nieudane: {type(e).__name__}: {e}")
        return
    latest = str(d.get("tag_name", "")).lstrip("v") or None
    suffix = _asset_suffix()
    # nazwa zasobu tylko jako nazwa pliku i DOKŁADNIE dla wersji z tagu (przegląd 09.10, B23)
    want_name = f"adChecker-{latest}{suffix}" if latest and suffix else None
    assets = {os.path.basename(a.get("name", "")): a.get("browser_download_url") for a in d.get("assets", [])}
    with _lock:
        st = _st["status"]
        if st in ("downloading", "installing"):
            return
        # gotowa wersja zostaje, chyba że wyszła jeszcze nowsza; odrzucone wydanie nie wraca w kółko
        if st == "ready" and not _newer(latest, _st["ver"] or VERSION):
            return
        if st == "rejected" and latest == _st["ver"]:
            return
        _st["latest"], _st["url"] = latest, d.get("html_url")
        _st["asset"] = (want_name, assets[want_name]) if want_name in assets else None
        _st["sums"] = assets.get("SHA256SUMS.txt")
        _st["sig"] = assets.get("SHA256SUMS.txt.sig")
        go = can_self_update() and _newer(latest, VERSION) and _st["asset"]
        if can_self_update() and _newer(latest, VERSION) and not _st["asset"]:
            # nowsza wersja bez instalatora adChecker-<tag>-… (np. stary pod nowym tagiem) — odrzucona
            _st.update(status="rejected", ver=latest, file=None,
                       error=f"wydanie {latest} nie ma instalatora adChecker-{latest} dla tego systemu")
            print(f"[aktualizacja] ODRZUCONE wydanie {latest}: {_st['error']}")
        if go:
            _st.update(status="downloading", progress=0, error=None, ver=latest, file=None, sha=None)
    if go:
        _download()


def _parse_sums(raw: bytes) -> dict:
    """SHA256SUMS.txt → {nazwa pliku: suma}."""
    out = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2:
            out[parts[1].lstrip("*")] = parts[0].lower()
    return out


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download() -> None:
    name, url = _st["asset"]
    ver = _st["ver"]
    folder = os.path.join(paths.USER_DIR, "update")
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, os.path.basename(name))
    try:
        if not _st["sums"]:
            raise Rejected("wydanie nie ma pliku sum kontrolnych")
        with _get(_st["sums"]) as r:
            sums_raw = r.read()
        _check_signature(sums_raw)
        # podpisany plik sum musi opisywać TĘ wersję: `name` to adChecker-<tag>-…, więc stary
        # podpisany plik pod nowym tagiem (downgrade / replay) jej nie ma (przegląd 09.10, B23)
        want = _parse_sums(sums_raw).get(name)
        if not want or not _newer(ver, VERSION):
            raise Rejected(f"podpisany plik sum nie opisuje instalatora wersji {ver}")
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
        if total and done != total:
            raise RuntimeError("pobieranie przerwane")       # sieć — spróbujemy później
        if h.hexdigest() != want:
            raise Rejected("suma kontrolna instalatora się nie zgadza")
        os.replace(dst + ".part", dst)
        with _lock:
            _st.update(status="ready", progress=100, file=dst, sha=want)
        print(f"[aktualizacja] pobrana {name}")
    except Rejected as e:
        with _lock:
            _st.update(status="rejected", error=str(e), file=None)
        print(f"[aktualizacja] ODRZUCONE wydanie {ver}: {e} — nie instaluję i nie podsuwam")
    except Exception as e:
        with _lock:
            _st.update(status="error", error=f"{type(e).__name__}: {e}")
        print(f"[aktualizacja] błąd pobierania: {e}")


def _check_signature(sums_raw: bytes) -> None:
    """Podpis pliku sum (SHA256SUMS.txt.sig, Ed25519) kluczem wpisanym w program (B16).
    Suma SHA-256 sama chroni tylko przed uszkodzeniem: plik sum leży w tym samym wydaniu co
    instalator, więc ten, kto przejmie konto GitHuba, podmieniłby oba. Podpisu bez klucza
    prywatnego (sekret w GitHubie, nie w repozytorium) nie podrobi."""
    import base64
    import binascii
    import ed25519
    import update_key
    if not update_key.PUBLIC_KEY:
        print("[aktualizacja] program nie ma klucza — sprawdzam tylko sumę SHA-256")
        return
    if not _st.get("sig"):
        raise Rejected("wydanie nie jest podpisane")
    with _get(_st["sig"]) as r:
        raw = r.read().strip()
    try:
        sig = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise Rejected("podpis wydania jest nieczytelny")
    if not ed25519.verify(bytes.fromhex(update_key.PUBLIC_KEY), sums_raw, sig):
        raise Rejected("podpis wydania się nie zgadza")
    print("[aktualizacja] podpis wydania poprawny")


def state() -> dict:
    """Stan dla nagłówka (/api/version). Przy okazji — raz na 6 h — sprawdzenie w tle.
    Przycisk pokazuje wersję pobieraną / gotową (`ver`), nie nowszą, która wyszła w międzyczasie.
    `rejected` — bez numeru i linku: interfejs nie podsuwa podmienionego wydania (B23)."""
    if time.time() - _st["checked"] > CHECK_EVERY_S:
        _st["checked"] = time.time()
        threading.Thread(target=_check, daemon=True).start()
    with _lock:
        st = dict(_st)
    if st["status"] == "rejected":
        return {"version": VERSION, "update": None, "update_url": None, "self_update": can_self_update(),
                "status": "rejected", "progress": 0, "error": st["error"]}
    shown = st["ver"] if st["status"] in ("downloading", "ready", "installing") else st["latest"]
    new = _newer(shown, VERSION)
    return {"version": VERSION, "update": shown if new else None,
            "update_url": st["url"] if new else None,
            "self_update": can_self_update(), "status": st["status"] if new else "idle",
            "progress": st["progress"], "error": st["error"]}


def install() -> str | None:
    """Uruchamia instalację pobranej wersji. Zwraca komunikat błędu albo None — wtedy program
    ma się zaraz zamknąć (robi to wywołujący, po wysłaniu odpowiedzi)."""
    with _lock:                                  # drugie kliknięcie nie uruchomi drugiego instalatora
        if _st["status"] != "ready" or not _st["file"] or not os.path.exists(_st["file"]):
            return "Nowa wersja nie jest jeszcze pobrana."
        _st["status"] = "installing"
        f, want = _st["file"], _st["sha"]
    try:
        # plik mógł się zmienić od pobrania — sprawdzamy sumę tuż przed uruchomieniem (TOCTOU, B23)
        if not want or _sha256(f) != want:
            with _lock:
                _st.update(status="rejected", error="pobrany instalator zmienił się po sprawdzeniu", file=None)
            print("[aktualizacja] ODRZUCONE: instalator zmienił się po sprawdzeniu sumy")
            return "Pobrany plik aktualizacji zmienił się po sprawdzeniu — nie instaluję."
        if sys.platform == "win32":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            # dziennik instalacji obok dziennika programu — nieudana cicha instalacja (np. antywirus)
            # nie może zostawić zepsutego programu bez śladu (przegląd kodu C24)
            log = os.path.join(paths.USER_DIR, "instalacja.log")
            subprocess.Popen([f, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={log}"], creationflags=flags,
                             close_fds=True)
            return None
        if sys.platform == "darwin":
            msg = _install_mac(f)
        else:
            msg = "Ten system nie ma automatycznej aktualizacji."
    except Exception as e:
        msg = f"Nie udało się uruchomić aktualizacji: {e}"
    if msg:
        with _lock:
            if _st["status"] == "installing":
                _st["status"] = "ready"
    return msg


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
    # czekamy, aż ten proces się zamknie, podmieniamy i uruchamiamy nową wersję; ścieżki przez
    # shlex.quote — folder z „$(…)”, „"” albo „`” w nazwie nie może wykonać polecenia (B23)
    import shlex
    a, old, nw = shlex.quote(app), shlex.quote(app + ".stara"), shlex.quote(new)
    script = (f'while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.5; done; '
              f'rm -rf {old}; mv {a} {old} && mv {nw} {a} && '
              f'rm -rf {old}; open {a}')
    subprocess.Popen(["/bin/sh", "-c", script], start_new_session=True, close_fds=True)
    return None
