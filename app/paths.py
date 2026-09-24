"""Gdzie co leży — jedno miejsce dla całego programu (wersja 0.3: instalator).

Dwa rodzaje plików:
- PROGRAMU (tylko do odczytu): kod, `static/`, profile ICC, zapasowa lista produktów, indeks
  wymiarów z dnia wydania, Ghostscript. W zainstalowanym programie leżą w folderze instalacji
  (PyInstaller: `sys._MEIPASS`), który bywa zablokowany do zapisu.
- UŻYTKOWNIKA (zapis): pliki robocze, pobrane wytyczne, lista produktów z sieci, indeks
  wymiarów, pobrane fonty, dziennik. Folder zależy od systemu:
    Windows  %LOCALAPPDATA%\\adChecker
    macOS    ~/Library/Application Support/adChecker
    Linux    ~/.local/share/adChecker
W trybie deweloperskim (python server.py) oba to folder `app/` — jak dotąd.
"""
from __future__ import annotations

import os
import shutil
import sys

FROZEN = bool(getattr(sys, "frozen", False))

# pliki programu
APP_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(APP_DIR, "static")
DATA_RO = os.path.join(APP_DIR, "data")
ICC_DIR = os.path.join(DATA_RO, "icc")


def _user_dir() -> str:
    if not FROZEN:
        return os.path.dirname(os.path.abspath(__file__))
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "adChecker")


# pliki użytkownika
USER_DIR = _user_dir()
DATA = os.path.join(USER_DIR, "data")
WORK = os.path.join(USER_DIR, "work")
GUIDELINES = os.path.join(DATA, "guidelines")
FONTS = os.path.join(DATA, "fonts")
LOG = os.path.join(USER_DIR, "adchecker.log")
WEBVIEW = os.path.join(USER_DIR, "webview")      # pamięć okna (kalibracja, ustawienia, samouczek)
for _d in (USER_DIR, DATA, WORK):
    os.makedirs(_d, exist_ok=True)


def seeded(name: str) -> str:
    """Plik danych, który program dostaje w paczce, a potem sam aktualizuje (indeks wymiarów).
    Przy pierwszym uruchomieniu kopia z paczki trafia do folderu użytkownika."""
    user = os.path.join(DATA, name)
    ro = os.path.join(DATA_RO, name)
    if not os.path.exists(user) and os.path.exists(ro) and os.path.abspath(ro) != os.path.abspath(user):
        try:
            shutil.copyfile(ro, user)
        except OSError:
            return ro
    return user


def bundled_gs() -> str | None:
    """Ghostscript dołączony do instalatora (folder `gs/` obok programu)."""
    name = "gswin64c.exe" if sys.platform == "win32" else "gs"
    p = os.path.join(APP_DIR, "gs", "bin", name)
    return p if os.path.exists(p) else None
