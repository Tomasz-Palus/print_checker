# 16 — Instalator na Windows i Maca (wersja 0.3, 24.09.2026)

Decyzja Tomasza: program trafi na razie do ludzi w Adsystem, jako instalator. Potrzebne są wersje
na Windows i macOS; Linux na razie nie.

Odrzucone:
- **wtyczka do Chrome** — wtyczka nie uruchomi Pythona ani Ghostscripta;
- **darmowe serwery** — na Hugging Face od lata 2026 darmowy plan nie uruchamia aplikacji w Pythonie
  (Docker), Oracle w 2026 obciął darmowy serwer o połowę, Render ma za mało mocy; do tego pliki
  klientów trafiałyby do obcej firmy;
- **serwer w sieci firmowej** — Tomasz wybrał instalator.

Repozytorium jest publiczne na GitHubie (`Tomasz-Palus/adChecker`). Instalatory buduje GitHub.

## Co trafia na GitHub

Tylko `app/`, `documentation/`, `packaging/`, `.github/` i `README.md`. Pilnuje tego `.gitignore`
w wersji „lista dozwolonych”: wszystko jest wykluczone poza tym, co wymienione.

Nigdy nie trafiają:
- `przykladowe projekty` (pliki klientów), `_kopia_*`, `wersje`;
- pliki robocze (`app/work`);
- pobrane wytyczne, fonty i lista produktów z sieci.

## Zmiany w programie

- **`app/version.py`** — numer wersji w jednym miejscu (0.3), User-Agent i adres repozytorium.
  Znaczek wersji w nagłówku bierze numer z `/api/version`.
- **`app/paths.py`** — gdzie co leży.
  - Pliki programu (tylko do odczytu, w paczce: `sys._MEIPASS`):
    - `static/`
    - profile ICC
    - zapasowa lista produktów
    - indeks wymiarów z dnia wydania
    - Ghostscript w `gs/`
  - Pliki użytkownika:
    - Windows: `%LOCALAPPDATA%\adChecker`
    - Mac: `~/Library/Application Support/adChecker`
    - W środku: `work/`, `data/` (wytyczne, lista produktów, indeks, fonty), `adchecker.log`,
      `webview/` (pamięć okna).
  - W trybie deweloperskim (`python server.py`) oba to nadal folder `app/`.
  - Moduły `jobs`, `products`, `guidelines`, `sizeindex`, `fontfix` i `gs` biorą ścieżki
    z `paths`.
  - Indeks wymiarów z paczki kopiuje się do folderu użytkownika przy pierwszym starcie
    (`paths.seeded`).
- **`gs.py`:**
  - Najpierw Ghostscript z paczki (ta sama wersja 10.07.1, na której wszystko sprawdzono).
  - Na Windows `CREATE_NO_WINDOW`, bo inaczej każde wywołanie błyska oknem konsoli.
  - Foldery fontów Maca: `~/Library/Fonts`, `/Library/Fonts`, `/System/Library/Fonts` (+
    `Supplemental`).
  - Profil Adobe FOGRA39 z Maca.
- **`app/desktop.py`** — start zainstalowanego programu:
  - `multiprocessing.freeze_support()` jako pierwsze — procesy liczące jakość w paczce.
  - Dziennik do `adchecker.log`.
  - **Stały port 47315.** Pamięć okna (kalibracja, ustawienia, samouczek) jest przypisana do
    adresu. Port 5000 zajmuje na Macu AirPlay.
  - Drugie uruchomienie otwiera działający program w przeglądarce, zamiast startować drugi serwer,
    który skasowałby pliki robocze pierwszego.
  - Serwer produkcyjny **waitress**. Flask w trybie debug wystawiał konsolę wykonującą kod.
  - **Okno programu (pywebview):**
    - Windows: Edge WebView2 (`gui="edgechromium"`, nigdy stary silnik IE); Mac: WebKit.
    - `private_mode=False` i `storage_path`, żeby pamięć okna przetrwała zamknięcie.
    - Linki zewnętrzne (PDF wytycznych, nowa wersja) otwierają się w przeglądarce.
  - Gdy okna nie da się otworzyć — zwykła przeglądarka. Program kończy się sam 3 minuty po
    zamknięciu karty; strona co 20 s woła `/api/alive`.
  - **Pobieranie w oknie:** „Pobierz plik do druku” otwiera systemowe „Zapisz jako”
    (`Api.save_download`, w `quality.js` przez `window.pywebview.api`). Okno nie ma paska
    pobierania przeglądarki. `server.download_file` jest wspólne z trasą `/download`.
  - **`ADCHECK_SELFTEST=1`** — test zbudowanego programu bez okna: Ghostscript z paczki, wgranie
    pliku przykładowego, analiza, zamiana na CMYK, ocena jakości (procesy liczące). GitHub
    uruchamia go po każdym budowaniu.
- **Aktualizacje:** `/api/version` raz na 6 h pyta GitHuba o najnowsze wydanie. Gdy jest nowsze,
  w nagłówku pojawia się zielony link „Jest nowa wersja X — pobierz”.

## Budowanie (`packaging/` + `.github/workflows/build.yml`)

- **`adchecker.spec` (PyInstaller):**
  - Program jako jeden folder (`adChecker.exe` z `_internal`, na Macu `adChecker.app`), bez okna
    konsoli.
  - Pliki Ghostscripta z `bin/` idą jako programy, żeby na Macu zostały podpisane i leżały tam,
    gdzie wolno kod.
- **Windows:**
  - Ghostscript z oficjalnego instalatora Artifexu, zainstalowany po cichu na maszynie GitHuba.
    Kopiowane są `bin` (`gswin64c.exe`, `gsdll64.dll`), `lib`, `Resource` i `iccprofiles`.
  - Instalator **Inno Setup** (`windows/adchecker.iss`), po polsku:
    - bez uprawnień administratora, do `%LOCALAPPDATA%\Programs\adChecker`;
    - skróty w menu Start i na pulpicie;
    - przy aktualizacji najpierw usuwa stary `_internal`, żeby biblioteki się nie mieszały.
- **Mac (Apple Silicon, macOS 11+):**
  - Ghostscript budowany ze źródeł (`build_gs_mac.sh`). Jeden plik `gs` z zasobami w środku
    i własnymi bibliotekami. Skrypt przerywa budowanie, gdy `otool -L` pokaże biblioteki spoza
    systemu (np. z Homebrew na maszynie GitHuba).
  - Podpis ad-hoc (`codesign -s -`) i DMG z aplikacją i skrótem do Aplikacji.
- **Wydanie:** każde wypchnięcie zmian w `app/` lub `packaging/` buduje oba instalatory, uruchamia
  self-test i wrzuca pliki do wydania `v<wersja>` (`--clobber` nadpisuje). Nowy numer w
  `version.py` = nowe wydanie. Opis wydania to `packaging/INSTRUKCJA.md` (instalacja krok po kroku,
  w tym ostrzeżenia Windows i Maca).
- **Wersje przypięte** w `packaging/requirements-build.txt`: PyInstaller 6.22.3, pywebview 6.2.1,
  waitress 3.0.2, PyMuPDF 1.28.2, pikepdf 10.13, Pillow 12.3, NumPy 2.4.6, fontTools 4.66,
  Flask 3.1.3. Ghostscript 10.07.1 w `build.yml`.

## Bez podpisu cyfrowego

Na użytek wewnętrzny program nie ma płatnego podpisu. Instrukcja przy wydaniu mówi, co kliknąć
przy pierwszym uruchomieniu:
- Windows: „Więcej informacji → Uruchom mimo to”;
- Mac: „Ustawienia systemowe → Prywatność i ochrona → Otwórz mimo to”.

Podpis kosztuje: Windows — certyfikat, kilkaset zł rocznie; Apple Developer — 99 USD rocznie.

## Test w sandboksie (Linux)

Ghostscript 10.07.1 zbudowany ze źródeł tymi samymi opcjami co na Macu. Wyszedł jeden plik bez
zewnętrznych bibliotek (tylko libc i libm).

Paczka PyInstallera: 198 MB.
- Self-test: OK (gs 10.07.1 z paczki, CMYK, jakość „bad”, 3 obszary).
- Cały samouczek na zbudowanym programie, od powitania do końca, w trybie przeglądarki: OK.
- Program zamknął się sam po zamknięciu karty.

Windowsa i Maca sprawdzają self-test na GitHubie i Tomasz.
