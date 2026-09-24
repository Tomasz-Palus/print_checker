# adChecker

Przygotowanie pliku do druku wielkoformatowego Adsystem **bez grafika DTP**: program sprawdza plik
z wytycznymi produktu i krok po kroku prowadzi przez poprawki — szablon, spady, wymiar, kolory CMYK,
overprint, fonty, spłaszczenie, jakość obrazów — a na końcu daje gotowy plik do druku.
Oryginał nigdy nie jest zmieniany.

**Pobierz:** zakładka [Releases](../../releases/latest) — instalator na Windows i macOS
(instrukcja instalacji jest przy każdym wydaniu).

## Dla programisty

- `app/` — program: serwer Flask (Python) + interfejs w przeglądarce (`app/static`).
  Uruchomienie deweloperskie: `app/run.bat` albo `python app/server.py` → http://127.0.0.1:5000.
  Potrzebny Ghostscript w systemie.
- `app/desktop.py` — start zainstalowanego programu (własne okno, serwer produkcyjny).
- `packaging/` — budowanie instalatorów (PyInstaller, Inno Setup, Ghostscript na Maca).
- `.github/workflows/build.yml` — GitHub buduje instalatory przy każdej zmianie w `app/`;
  numer wersji jest w `app/version.py` (nowy numer = nowe wydanie).
- `documentation/` — opis każdego etapu budowy programu i decyzji.

## Składniki

Python, Flask, waitress, PyMuPDF, pikepdf, Pillow, NumPy, fontTools, pywebview i Ghostscript.
Ghostscript i PyMuPDF są na licencji GNU AGPL v3.
