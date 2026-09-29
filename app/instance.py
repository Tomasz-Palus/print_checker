"""Jeden działający adChecker na komputerze (przegląd kodu 27.09, C19).

Dawniej drugie uruchomienie pytało pierwsze przez HTTP (1,5 s). Gdy pierwsze było zajęte
(spłaszczenie, wielki plik) albo port zajmował inny program, drugie uznawało, że nic nie działa,
brało inny port i CZYŚCIŁO work/ — kasując pliki działającego programu.

Teraz decyduje blokada pliku w folderze użytkownika, trzymana przez cały czas działania
(system zdejmuje ją sam, gdy proces się kończy — także po awarii). Port działającego programu
leży obok, w osobnym pliku (na Windowsie zablokowanego pliku nie da się czytać).
"""
from __future__ import annotations

import os
import sys

import paths

LOCK = os.path.join(paths.USER_DIR, "adchecker.lock")
PORT_FILE = os.path.join(paths.USER_DIR, "adchecker.port")
_held = None


def acquire() -> bool:
    """True — jesteśmy jedyni (blokada trzymana do końca procesu); False — inny adChecker działa."""
    global _held
    if _held is not None:
        return True
    f = open(LOCK, "a+")
    try:
        if sys.platform == "win32":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _held = f
    return True


def save_port(port: int) -> None:
    try:
        with open(PORT_FILE, "w") as f:
            f.write(str(port))
    except OSError:
        pass


def running_port(default: int) -> int:
    """Port działającego adCheckera (z pliku obok blokady) — do otwarcia go w przeglądarce."""
    try:
        with open(PORT_FILE) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return default


def busy() -> bool:
    """Czy inny adChecker trzyma blokadę (sprawdzenie bez zatrzymywania jej)."""
    global _held
    if _held is not None:
        return False
    if not acquire():
        return True
    release()
    return False


def release() -> None:
    global _held
    if _held is None:
        return
    try:
        if sys.platform == "win32":
            import msvcrt
            _held.seek(0)
            msvcrt.locking(_held.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(_held.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    _held.close()
    _held = None
