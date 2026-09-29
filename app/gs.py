"""Ghostscript — jedno miejsce na wszystko, co go dotyczy.

Tu siedzą też OBEJŚCIA JEGO BŁĘDÓW. Każde jest opisane przy swojej funkcji i każde
wynika z konkretnego zgłoszenia — nie usuwać bez sprawdzenia na pliku, który je wywołał.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import threading

import paths

ICC_DIR = paths.ICC_DIR

# Windows: Ghostscript to program konsolowy — bez tej flagi każde wywołanie z okna programu
# błyskałoby czarnym oknem konsoli.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

# Profil FOGRA39: najpierw ADOBE (te same liczby co w Photoshopie), potem nasza kopia.
FOGRA_NAME = "Coated FOGRA39 (ISO 12647-2:2004)"
FOGRA_CANDIDATES = [
    r"C:\Program Files (x86)\Common Files\Adobe\Color\Profiles\Recommended\CoatedFOGRA39.icc",
    r"C:\Program Files\Common Files\Adobe\Color\Profiles\Recommended\CoatedFOGRA39.icc",
    r"C:\Windows\System32\spool\drivers\color\CoatedFOGRA39.icc",
    "/Library/Application Support/Adobe/Color/Profiles/Recommended/CoatedFOGRA39.icc",
    os.path.join(ICC_DIR, "CoatedFOGRA39.icc"),
]

THREADS = max(2, min(8, os.cpu_count() or 4))
SPEED = [f"-dNumRenderingThreads={THREADS}", "-dMaxBitmap=100000000"]

# Bez „fill adjust" — w PODGLĄDZIE i przy SPŁASZCZANIU. Ghostscript domyślnie pogrubia wypełnienia
# o ułamek piksela: w podglądzie krzywe wychodziły grubsze niż tekst (Tomasz 24.09), a spłaszczenie
# do 150 ppi zapisywało to pogrubienie na stałe w pliku (tekst o 3,6 % grubszy). Przy renderze
# w rozdzielczości drukarki (1200 dpi) ułamek piksela nie ma znaczenia — tam niczego nie ruszamy.
PREVIEW_PRE = ["-c", "0 0 .setfilladjust2", "-f"]

# pdfwrite ma zostawić obrazy DOKŁADNIE takie, jakie są: bez zmniejszania i bez ponownej
# kompresji JPEG. Domyślnie Ghostscript koduje od nowa obrazy zapisane bezstratnie (Flate) jako
# JPEG — po „fontach na krzywe" raster 96 px dostawał kolorowe obwódki (Tomasz 24.09).
PDFWRITE_KEEP_IMAGES = [
    "-dPassThroughJPEGImages=true", "-dPassThroughJPXImages=true",
    "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false", "-dDownsampleMonoImages=false",
    "-dAutoFilterColorImages=false", "-dColorImageFilter=/FlateEncode",
    "-dAutoFilterGrayImages=false", "-dGrayImageFilter=/FlateEncode"]

# pdfwrite domyślnie (/PageByPage) OBRACA stronę, na której większość tekstu biegnie pionowo —
# plik do druku zmieniał orientację po zamianie na CMYK (przegląd kodu 27.09, A11). Zawsze /None.
PDFWRITE_NO_ROTATE = ["-dAutoRotatePages=/None"]

# Ile pamięci wolno dać na render całej strony naraz (patrz aa_args).
FULLPAGE_MAX = 1_500_000_000

_exe = None


def exe() -> str:
    """Ścieżka do Ghostscripta (błąd, gdy go nie ma — bez niego program nie działa)."""
    global _exe
    if _exe:
        return _exe
    # zainstalowany program ma własnego Ghostscripta (tę samą wersję, na której wszystko sprawdzono)
    b = paths.bundled_gs()
    if b:
        _exe = b
        return b
    for name in ("gswin64c", "gswin32c", "gs"):
        p = shutil.which(name)
        if p:
            _exe = p
            return p
    for pat in ("C:/Program Files/gs/gs*/bin/gswin64c.exe",
                "C:/Program Files (x86)/gs/gs*/bin/gswin32c.exe"):
        hits = sorted(glob.glob(pat))
        if hits:
            _exe = hits[-1]
            return _exe
    raise RuntimeError("Nie znalazłem Ghostscripta — zainstaluj go (ghostscript.com).")


def fogra() -> str:
    for c in FOGRA_CANDIDATES:
        if os.path.exists(c):
            return c
    raise RuntimeError("Brak profilu Coated FOGRA39 — wgraj plik .icc do app/data/icc.")


def srgb() -> str:
    return os.path.join(ICC_DIR, "sRGB.icc")


def arg_path(p: str) -> str:
    """Ścieżka w argumencie Ghostscripta: ukośniki w przód (Windows)."""
    return os.path.abspath(p).replace("\\", "/")


def safe_icc(src: str, near_dir: str) -> str:
    """Kopia profilu obok plików zadania, pod nazwą bez spacji i nawiasów.

    Ghostscript czyta parametry jak łańcuchy PostScriptu: „\\" to znak ucieczki, a nawias
    domyka łańcuch. Ścieżka Adobe „C:\\Program Files (x86)\\…" kończyła się „Unrecoverable
    error" (Tomasz). Kopia w katalogu zadania tego problemu nie ma."""
    out = os.path.join(near_dir, "icc_" + os.path.basename(src).replace(" ", "_"))
    try:
        if not os.path.exists(out) or os.path.getsize(out) != os.path.getsize(src):
            shutil.copyfile(src, out)
    except OSError:
        out = src
    return arg_path(out)


def _own_icc_dir() -> str | None:
    """Katalog profili, z którymi Ghostscript przyszedł (default_rgb.icc, lab.icc, ps_*.icc…)."""
    root = os.path.dirname(os.path.dirname(exe()))
    for d in [os.path.join(root, "iccprofiles"), *sorted(glob.glob("/usr/share/ghostscript/*/iccprofiles")),
              "/usr/share/color/icc/ghostscript"]:
        if os.path.exists(os.path.join(d, "default_cmyk.icc")):
            return d
    return None


def cmyk_target_args(icc_path: str, work_dir: str) -> list:
    """Konwersja do CMYK w pdfwrite PRZEZ WSKAZANY PROFIL.

    BŁĄD/OGRANICZENIE GHOSTSCRIPTA (sprawdzone 24.09 na 10.02; opisane też przez innych dla
    9.27): pdfwrite IGNORUJE `-sOutputICCProfile` — przelicza zawsze przez swój domyślny profil
    CMYK (default_cmyk.icc). Stara wersja programu podawała FOGRA39 i wynik wychodził na profilu
    Ghostscripta (szarość 200/200/200: 52/43/44/0 zamiast 67/48/52/0 jak w Photoshopie).
    Obejście: kopia katalogu profili Ghostscripta, w której default_cmyk.icc = nasz profil.
    Wynik zgadza się z littleCMS (silnik Photoshopa) co do ±1/255. Przy okazji CMYK już
    w pliku (DeviceCMYK) jest traktowany jako ten sam profil — zostaje bez zmian."""
    src = _own_icc_dir()
    if not src:
        raise RuntimeError("Nie znalazłem katalogu profili Ghostscripta (iccprofiles) — bez niego "
                           "konwersja poszłaby na złym profilu. Zainstaluj Ghostscripta ponownie.")
    out = os.path.join(work_dir, "gs_icc")
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(src, "*.icc")):
        dst = os.path.join(out, os.path.basename(f))
        if not os.path.exists(dst):
            shutil.copyfile(f, dst)
    shutil.copyfile(icc_path, os.path.join(out, "default_cmyk.icc"))
    d = arg_path(out) + "/"
    return ["--permit-file-read=" + d, "-sICCProfilesDir=" + d]


_sim: dict = {}
_sim_lock = threading.Lock()


def sim_profile(src: str | None) -> str:
    """Profil CMYK „maszyny” w symulacji druku: profil zapisany w PLIKU (deklaracja OutputIntent
    albo osadzony profil CMYK — np. ISO Coated v2), a gdy go nie ma — FOGRA39.

    Tomasz 29.09 (1878, liście na zdjęciu bardziej pomarańczowe w „druk” niż w „ekran”): zdjęcie
    CMYK z profilem ISO Coated v2 symulacja przeliczała na FOGRA39 — liczby farb zmieniały się
    średnio o 10 %, a kolor miejscami o kilkanaście punktów (inna generacja czerni). Drukarnia
    dostaje jednak TE liczby i drukuje je tak, jak opisuje je profil pliku (ISO Coated v2 i FOGRA39
    to ta sama norma druku). Plik przeliczony na FOGRA39 (Kolory) ma już FOGRA39 w deklaracji."""
    if not src:
        return fogra()
    with _sim_lock:
        if src in _sim:
            return _sim[src]
    out = fogra()
    try:
        import hashlib
        import io
        import steps
        from PIL import ImageCms
        data, _ = steps.file_icc(src)
        if data:
            prof = ImageCms.ImageCmsProfile(io.BytesIO(data)).profile
            if prof.xcolor_space.strip() == "CMYK" and prof.device_class.strip() == "prtr":
                p = os.path.join(os.path.dirname(os.path.abspath(src)),
                                 "icc_sym_" + hashlib.sha1(data).hexdigest()[:12] + ".icc")
                if not os.path.exists(p):
                    with open(p + ".part", "wb") as f:
                        f.write(data)
                    os.replace(p + ".part", p)
                out = p
    except Exception as e:
        print(f"[adChecker] profil symulacji: {type(e).__name__}: {e}")
    with _sim_lock:
        _sim[src] = out
    return out


def color_args(src: str | None = None) -> list:
    """CMYK na ekran przez profil pliku (albo FOGRA39) — tak, jak pokazuje go Photoshop.
    `--permit-file-read` jest konieczne: w trybie -dSAFER Ghostscript czyta tylko to, na co
    dostał zgodę."""
    p = arg_path(sim_profile(src))
    return ["--permit-file-read=" + p, "-sDefaultCMYKProfile=" + p]


def proof_args(src: str | None = None) -> list:
    """Symulacja druku: strona liczona do CMYK maszyny (profil pliku albo FOGRA39 — sim_profile),
    intencja relatywna kolorymetryczna + BPC. CMYK w tym profilu przechodzi bez zmian. Na ekran
    przelicza render.proof_rgb tym samym profilem. (`-sProofProfile` się nie nadaje — przesuwa też CMYK.)"""
    p = arg_path(sim_profile(src))
    return ["--permit-file-read=" + p, "-sOutputICCProfile=" + p, "-sDefaultCMYKProfile=" + p,
            "-dRenderIntent=1", "-dBlackPtComp=1"]


def overprint_args(on: bool) -> list:
    """/simulate = pokaż, jak overprint wyjdzie z drukarki. Wyłączony — JAWNIE /disable:
    na urządzeniu CMYK (symulacja druku kolorów) Ghostscript domyślnie overprint NAKŁADA
    (sprawdzone 24.09 na 10.02: żółte koło na cyjanie wychodziło zielone w symulacji samych
    kolorów). Podgląd bez symulacji ma pokazywać plik jak na ekranie (decyzja Tomasza)."""
    return ["-dOverprint=/simulate"] if on else ["-dOverprint=/disable"]


def aa_args(overprint: bool, w_px: float, h_px: float, ncomp: int = 3) -> list:
    """Wygładzanie krawędzi — BEZPIECZNIE przy symulacji overprintu.

    BŁĄD GHOSTSCRIPTA (10.02 i 10.07): `-dOverprint=/simulate` + AlphaBits przy stronie
    renderowanej PASAMI gubi prawie całą treść — podgląd pokazywał jeden obraz, a spłaszczenie
    dawało BIAŁĄ stronę (Tomasz 24.09, plik PRINT_CHECKER_TEST_100x200_SZABLON_PASERY.pdf).
    Obejście: przy overprincie cała strona naraz w pamięci (~12× rozmiaru strony); gdy to za
    dużo — bez wygładzania; wtedy piramida podglądu i spłaszczenie liczą 2× gęściej i uśredniają
    same (nadpróbkowanie)."""
    aa = ["-dTextAlphaBits=4", "-dGraphicsAlphaBits=4"]
    if not overprint:
        return aa
    need = int(max(1.0, w_px) * max(1.0, h_px) * ncomp * 12) + 64_000_000
    return aa + [f"-dMaxBitmap={need}"] if need <= FULLPAGE_MAX else []


def font_path_args() -> list:
    """Fonty zainstalowane w systemie — nieosadzony font bierzemy stamtąd (to TEN font),
    zamiast z tabeli zamienników Ghostscripta."""
    win = os.environ.get("WINDIR") or r"C:\Windows"
    home = os.path.expanduser("~")
    dirs = [d for d in (os.path.join(win, "Fonts"),
                        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
                        # macOS: fonty użytkownika, zainstalowane, systemowe (Supplemental = Arial, Times…)
                        os.path.join(home, "Library", "Fonts"), "/Library/Fonts", "/System/Library/Fonts",
                        "/System/Library/Fonts/Supplemental",
                        "/usr/share/fonts", "/usr/local/share/fonts", os.path.join(home, ".local", "share", "fonts"))
            if d and os.path.isdir(d)]
    return ["-sFONTPATH=" + os.pathsep.join(dirs)] if dirs else []


def substituted(log: str, ignore=()) -> list[str]:
    """Fonty, za które Ghostscript wziął ZAMIENNIK (program o nich ostrzega i zaznacza je na podglądzie).

    Tylko bez `-q` Ghostscript pisze „Loading font X (or substitute) from <ścieżka>" (przy
    `stream` — `quiet=False`; przegląd kodu 27.09: spłaszczenie szło z `-q` i nic nie widziało). Font
    z systemu ma ścieżkę w katalogu fontów, zamiennik — w zasobach Ghostscripta (Resource/Font,
    na Windowsie `%rom%`). Fonty standardowe PDF-a (Helvetica…) pomijamy: ich zamiennik jest
    wzorcowy."""
    from pdfutil import is_base14
    skip = {x.split("+")[-1] for x in ignore}
    out = []
    # font CID (np. japoński, chiński, czasem polski z Worda): Ghostscript mówi wprost „substitute”
    # i bierze krój z CIDFSubst (review 27.09, A14)
    for m in re.finditer(r"Loading CIDFont (\S+) substitute from", log):
        name = m.group(1)
        if name.split("+")[-1] not in skip and name not in out:
            out.append(name)
    for m in re.finditer(r"Loading font (\S+) \(or substitute\) from (.+)", log):
        name, path = m.group(1), m.group(2).strip().lower().replace("\\", "/")
        if is_base14(name) or name.split("+")[-1] in skip:
            continue
        if "%rom%" in path or "resource/font" in path or ("/ghostscript/" in path and "/fonts/" not in path):
            if name not in out:
                out.append(name)
    return out


# ----------------------------------------------------------------------------
# działające procesy Ghostscripta — kończą się razem z programem (przegląd kodu 27.09, C20)
# ----------------------------------------------------------------------------
# Zamknięcie okna kończy program przez os._exit, a Ghostscript liczący duże spłaszczenie albo
# podgląd pracował dalej nawet kilkanaście minut (bez okna, zajmując procesor i pliki w work/).
# Każdy proces trafia do rejestru (kill_all przy zamknięciu), a na Windowsie dodatkowo do „zadania”
# systemu (Job Object) z KILL_ON_JOB_CLOSE — Windows zabija go sam, nawet gdy program padnie.
_procs: set = set()
_procs_lock = threading.Lock()
_win_job = None


def _job_handle():
    global _win_job
    if _win_job is not None or sys.platform != "win32":
        return _win_job
    try:
        import ctypes
        from ctypes import wintypes

        class _Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class _Io(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ("R", "W", "O", "RT", "WT", "OT")]

        class _Ext(ctypes.Structure):
            _fields_ = [("Basic", _Basic), ("Io", _Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        h = k32.CreateJobObjectW(None, None)
        info = _Ext()
        info.Basic.LimitFlags = 0x2000                     # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if h and k32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):
            _win_job = (k32, h)
    except Exception as e:
        print(f"[adChecker] Job Object: {type(e).__name__}: {e}")
        _win_job = False
    return _win_job


def _track(p: subprocess.Popen) -> None:
    with _procs_lock:
        _procs.add(p)
    j = _job_handle()
    if j:
        try:
            j[0].AssignProcessToJobObject(j[1], int(p._handle))
        except Exception:
            pass


def _untrack(p: subprocess.Popen) -> None:
    with _procs_lock:
        _procs.discard(p)


def kill_all() -> int:
    """Zabija wszystkie działające procesy Ghostscripta (zamknięcie programu). Zwraca ich liczbę."""
    with _procs_lock:
        ps = [p for p in _procs if p.poll() is None]
        _procs.clear()
    for p in ps:
        try:
            p.kill()
        except Exception:
            pass
    return len(ps)


def run(args: list, timeout: int = 900) -> subprocess.CompletedProcess:
    """Ghostscript z listą argumentów (bez nazwy programu). Tekst wyjścia zawsze czytelny."""
    cmd = [exe(), "-dNOPAUSE", "-dBATCH", *args]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", **NO_WINDOW)
    _track(p)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise
    finally:
        _untrack(p)
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def log_of(r: subprocess.CompletedProcess, n: int = 400) -> str:
    return ((r.stderr or "") + " " + (r.stdout or "")).strip()[-n:] or "brak komunikatu"


def stream(args: list, quiet: bool = True) -> subprocess.Popen:
    """Ghostscript z obrazem na stdout (piramida podglądu).

    Komunikaty (stderr) czytamy NA BIEŻĄCO w osobnym wątku: na Windowsie bufor potoku ma
    ~4 KB — przy wielu ostrzeżeniach Ghostscript stawał i czekał, a my czekaliśmy na obraz
    (pełna jakość wisiała w połowie bez błędu). Ostatnie ~4 KB zostają w `p.err_tail`."""
    # quiet=False: pełny dziennik (np. „Loading font … (or substitute)”) — bez `-q` Ghostscript pisze
    # komunikaty na stdout, więc przekierowujemy je na stderr, żeby nie wmieszały się w obraz
    head = ["-q"] if quiet else ["-sstdout=%stderr"]
    p = subprocess.Popen([exe(), *head, "-dNOPAUSE", "-dBATCH", *args],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1 << 20, **NO_WINDOW)
    _track(p)
    p.err_tail = b""
    p.err_all = bytearray()          # cały dziennik (do 2 MB) — np. zamienione fonty przy spłaszczaniu

    def drain():
        try:
            for chunk in iter(lambda: p.stderr.read(4096), b""):
                p.err_tail = (p.err_tail + chunk)[-4096:]
                if len(p.err_all) < 2_000_000:
                    p.err_all += chunk
        except Exception:
            pass
        try:
            p.wait()
        except Exception:
            pass
        _untrack(p)                  # koniec procesu (stderr zamknięty) — zdejmujemy z rejestru
    threading.Thread(target=drain, daemon=True).start()
    return p
