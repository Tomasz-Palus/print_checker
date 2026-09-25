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


def color_args() -> list:
    """CMYK na ekran przez FOGRA39 — tak, jak pokazuje go Photoshop. `--permit-file-read`
    jest konieczne: w trybie -dSAFER Ghostscript czyta tylko to, na co dostał zgodę."""
    p = arg_path(fogra())
    return ["--permit-file-read=" + p, "-sDefaultCMYKProfile=" + p]


def proof_args() -> list:
    """Symulacja druku (rozdział „Kolory"): strona liczona do CMYK FOGRA39, intencja
    relatywna kolorymetryczna + BPC. CMYK przechodzi bez zmian (±2/255). Na ekran przelicza
    render.proof_rgb. (`-sProofProfile` się nie nadaje — przesuwa też CMYK.)"""
    p = arg_path(fogra())
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
    """Fonty, za które Ghostscript wziął ZAMIENNIK (decyzja Tomasza: nigdy kroju zastępczego).

    Tylko bez `-q` Ghostscript pisze „Loading font X (or substitute) from <ścieżka>". Font
    z systemu ma ścieżkę w katalogu fontów, zamiennik — w zasobach Ghostscripta (Resource/Font,
    na Windowsie `%rom%`). Fonty standardowe PDF-a (Helvetica…) pomijamy: ich zamiennik jest
    wzorcowy."""
    from pdfutil import is_base14
    skip = {x.split("+")[-1] for x in ignore}
    out = []
    for m in re.finditer(r"Loading font (\S+) \(or substitute\) from (.+)", log):
        name, path = m.group(1), m.group(2).strip().lower().replace("\\", "/")
        if is_base14(name) or name.split("+")[-1] in skip:
            continue
        if "%rom%" in path or "resource/font" in path or ("/ghostscript/" in path and "/fonts/" not in path):
            if name not in out:
                out.append(name)
    return out


def run(args: list, timeout: int = 900) -> subprocess.CompletedProcess:
    """Ghostscript z listą argumentów (bez nazwy programu). Tekst wyjścia zawsze czytelny."""
    return subprocess.run([exe(), "-dNOPAUSE", "-dBATCH", *args], capture_output=True, text=True, **NO_WINDOW,
                          encoding="utf-8", errors="replace", timeout=timeout)


def log_of(r: subprocess.CompletedProcess, n: int = 400) -> str:
    return ((r.stderr or "") + " " + (r.stdout or "")).strip()[-n:] or "brak komunikatu"


def stream(args: list) -> subprocess.Popen:
    """Ghostscript z obrazem na stdout (piramida podglądu).

    Komunikaty (stderr) czytamy NA BIEŻĄCO w osobnym wątku: na Windowsie bufor potoku ma
    ~4 KB — przy wielu ostrzeżeniach Ghostscript stawał i czekał, a my czekaliśmy na obraz
    (pełna jakość wisiała w połowie bez błędu). Ostatnie ~4 KB zostają w `p.err_tail`."""
    p = subprocess.Popen([exe(), "-q", "-dNOPAUSE", "-dBATCH", *args],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1 << 20, **NO_WINDOW)
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
    threading.Thread(target=drain, daemon=True).start()
    return p
