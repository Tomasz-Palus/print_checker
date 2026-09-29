# 18 — Przegląd kodu (wersja 0.4.7, 27.09.2026)

Przegląd całego programu na prośbę Tomasza. Bez zmian w kodzie — to lista do naprawy.

- **Jak zrobiony:** pięć niezależnych przeglądów (serwer, obróbka PDF, analiza i jakość, interfejs,
  budowanie i wydania).
- **Weryfikacja:** większość znalezisk sprawdzona małymi plikami testowymi. Najważniejsze
  (1, 2, 3, 6) Claude sprawdził jeszcze raz sam.
- **Stan kodu:** kod w repozytorium Tomasza był zgodny z kopią Claude'a (sumy md5).
- **Oznaczenia:** [T] — potwierdzone testem, [K] — z czytania kodu.

## A. Pilne: program może przepuścić zły plik albo zepsuć poprawny

1. **[T] Spłaszczenie nie wykrywa podmienionego fontu** (`gs.py` `stream`, `steps.py` flatten).
   - **Przyczyna:** `gs.stream` zawsze dodaje `-q`, a z `-q` Ghostscript nie pisze „Loading font …
     (or substitute)”. Sprawdzone: bez `-q` komunikat jest, z `-q` go nie ma.
   - **Skutek:** zamiennik fontu zostaje „wypalony” w obrazie, wbrew zasadzie „nigdy
     zamiennik”.
   - **Pochodzenie:** błąd wprowadzony w 0.4.3–0.4.4, gdy spłaszczenie przeszło na nadpróbkowanie
     strumieniem (wcześniej `gs.run` bez `-q`).
2. **[T] Analiza poprzedniego pliku trafia do nowego** (`main.js` `loadAnalysis`, `state.js`
   `factsKey`).
   - **Przyczyna:** klucz analizy to `"<wersja>:<strona>"`, a oryginał każdego pliku to `v0`. Przy
     wgraniu nowego pliku nie jest unieważniane zapytanie w toku (`anSeq`, `anBusy`).
   - **Scenariusz:** plik A się analizuje, użytkownik wrzuca plik B. Odpowiedź dla A zostaje
     przypisana B. Kolory, overprint i fonty oceniane są z pliku A.
   - **Gorszy wariant:** A odpowie 404 (zadanie już usunięte). Wtedy „błąd analizy” zamyka
     rozdziały Kolory, Overprint, Fonty i Spłaszczenie bez decyzji, a plik da się pobrać.
3. **[T] Zmiana strony zostawia decyzje z poprzedniej strony** (`product.js` `setPage`).
   - **Przyczyna:** decyzje są czyszczone tylko wtedy, gdy była już poprawka. Zostają
     `settle`/`choice` (wymiar „zgadza się”, „zostaw jak jest”…) i akceptacja.
   - **Skutek:** strona 2 może przejść do pobrania bez sprawdzenia, nawet w złym wymiarze.
4. **[K] Wolna poprawka kończy się po wgraniu nowego pliku i nadpisuje zadanie** (`steps.js`
   `applyStep`, `undoStep`).
   - **Przyczyna:** odpowiedź nie sprawdza, czy zadanie jest nadal to samo.
   - **Skutek:** program wraca do starego, usuniętego zadania — wszystko kończy się błędem „Nie ma
     takiego zadania”, a nagłówek pokazuje nowy plik.
5. **[K] Kliknięcia w stare rozdziały podczas wgrywania albo po błędzie wgrania zapisują decyzje
   dla następnego pliku.** Przykład: „Zatwierdź wymiar”, gdy nie ma pliku, ustawia
   `settle.resize = "ok"`. Rozdziały od Szablonu do Spłaszczenia nie są chowane, gdy nie ma
   zadania.
6. **[T] Obrazy „inline” są niewidoczne dla analizy** (`analyze.py:336`).
   - **Przyczyna:** pikepdf podaje operator `"INLINE IMAGE"`, a kod szuka `"BI"`.
   - **Skutek:** obraz RGB nie wymaga zamiany na CMYK, a jakość ocenia plik jako „sam wektor” —
     obraz o niskiej rozdzielczości przechodzi.
7. **[T] Adnotacje (np. stemple) są pomijane** (`analyze.py`, brak `/Annots`). Kolor RGB, overprint
   i nieosadzony font w stemplu nie są wykrywane, choć drukują się.
8. **[T] Obraz, którego nie da się zdekodować, jest pomijany w całości** (`detailmap.py:773`), także
   w sprawdzeniu liczby pikseli, które pikseli nie potrzebuje. Przykład: obraz JPX 14 ppi → werdykt
   „ok”.
9. **[T] Wzory (tiling pattern) mają źle liczoną skalę** (`analyze.py:382`). Pattern z obrazem
   przy `cm 0.1`: raport 72 ppi zamiast 7,2 ppi → „ok”.
10. **[T] Strony obrócone (`/Rotate`), z CropBoxem albo UserUnit są źle obsługiwane:**
    - **Wymiar** (`steps.py` resize, `show_pdf_page`): przy `/Rotate 90` pół strony wychodzi
      białe, treść jest bokiem.
    - **Spady** (`steps.py` trim, `render.inspect`): rozmiary liczone w surowym MediaBoxie. Przy
      obróconej stronie wynik jest poziomy zamiast pionowego. Przy UserUnit 10 wymiary są 10×
      za małe.
    - **Szablon** (`frames.py`): na stronie z `/Rotate 90` szablon nie zostaje znaleziony —
      zostałby w druku.
    - **Jakość** (`detailmap.py` filtr widoczności): na obróconej stronie prawdziwy problem
      (36 ppi) zostaje uznany za „zakryty” → „ok”.
    - **Podgląd** (`render.py` `_gs_args`): brak `-dUseCropBox`. Przy CropBox mniejszym od
      MediaBoxa podgląd jest zniekształcony i przesunięty względem ramek.
11. **[T] Zamiana na CMYK może obrócić stronę** (`steps.py` cmyk, `render.canonicalize`). pdfwrite
    bez `-dAutoRotatePages=/None` dodaje `/Rotate` stronie z pionowym tekstem, więc plik do druku
    zmienia orientację.
12. **[T] Usuwanie szablonu kasuje tekst klienta** (`frames.py:276`). Tekst podobnej wielkości
    w pobliżu etykiety szablonu (np. stopka „www… tel.” przy „Linia cięcia”) jest usuwany razem
    z nią.
13. **[T] „Dopasuj wymiar” gubi profil kolorów pliku (OutputIntent)** (`steps.py` resize). Potem
    „profil z pliku” i spłaszczenie po cichu biorą FOGRA39.
14. **[T] Podmiana fontu CID nie jest wykrywana** (`gs.substituted`). Komunikat „Loading CIDFont …
    substitute” nie pasuje do wzorca, więc „tekst na krzywe” może zamienić na krzywe zamiennik.

## B. Bezpieczeństwo

15. **[T] Każda strona internetowa może wysłać polecenie do programu.**
    - **Przyczyna:** serwer na stałym porcie (47315) nie sprawdza nagłówków Origin i Host.
    - **Skutek:** strona otwarta w przeglądarce może wgrać plik (który przejdzie przez
      Ghostscripta) albo wywołać `/api/update/install` — program się zamyka.
    - **Poprawka:** odrzucać zapytania z obcym Origin/Host.
16. **[K] Suma SHA-256 aktualizacji chroni tylko przed uszkodzeniem, nie przed podmianą.**
    - **Przyczyna:** plik sum leży w tym samym wydaniu co instalator, a instalator nie ma podpisu.
      Ten, kto przejmie konto albo token GitHuba, może podmienić oba — a aktualizacja instaluje
      się po cichu.
    - **Poprawka:** podpis pliku sum własnym kluczem (np. minisign), a klucz publiczny w programie.
17. **[K] Budowanie na GitHubie ma szerokie uprawnienia i niesprawdzane pobrania.**
    - Token z prawem zapisu we wszystkich zadaniach.
    - Ghostscript pobierany bez sumy kontrolnej.
    - Zależności zależności niespięte wersjami ani sumami.
    - Inno Setup z Chocolatey bez wersji.
    - Poprawka: `contents: read` poza zadaniem wydania, `persist-credentials: false`, sumy.
18. **[K] Pliki klientów mogą zostać na komputerze albo trafić do repozytorium.**
    - Odinstalowanie nie usuwa `%LOCALAPPDATA%\adChecker` (`work/` z plikami ostatniej sesji,
      pobrane fonty, pamięć okna).
    - `python desktop.py` uruchomiony z repozytorium zapisuje pamięć okna (z podglądami plików
      klientów) do `app/webview/`, którego nie ma w `.gitignore`. `run.bat` tego nie robi.

## C. Stabilność i wygoda

19. **[K] Drugie uruchomienie może skasować pliki robocze działającego programu**
    (`desktop.py`).
    - Scenariusz: pierwszy program jest zajęty dłużej niż 1,5 s albo port zajmuje inny program.
      Drugi uznaje, że nic nie działa, i czyści `work/`.
    - Poprawka: prawdziwa blokada jednej instancji.
20. **[K] Zamknięcie okna zostawia działający Ghostscript** (`os._exit`). Proces liczy dalej nawet
    kilkanaście minut.
21. **[T] Pobieranie i miniatury:**
    - Dwa pobrania naraz (podwójne kliknięcie) mogą dać obcięty PDF.
    - Nieudana miniatura zostaje jako pusty plik i jest serwowana dalej.
    - Poprawka: zapis przez plik tymczasowy.
22. **[T] Każdy `IndexError`/`KeyError` kończy się komunikatem „wgraj plik jeszcze raz”**
    (`server.py`, handler `LookupError`). Przykład: numer strony spoza zakresu. Mylące i ukrywa
    prawdziwe błędy.
23. **[K] Mac:**
    - Paczka wymaga macOS 14 (pikepdf ma tylko takie koło dla arm64), a instalator deklaruje 11.
    - Możliwy brak certyfikatów HTTPS w paczce — aktualizacje, wytyczne i fonty nie działałyby.
      Do sprawdzenia na prawdziwym Macu.
24. **[K] Wydania:**
    - Brak `concurrency` — dwa szybkie wypchnięcia mogą wydać złą wersję.
    - Numer wersji z literami (np. `0.5-rc1`) po cichu blokuje aktualizacje na zawsze.
    - Nieudana cicha instalacja (np. antywirus) zostawia zepsuty program bez dziennika — przydałby
      się `/LOG`.
25. **[T] Spłaszczenie strony szerszej niż 65 500 px** (np. baner 20 m w 1:10) pada dopiero po
    kilku minutach renderu — limit JPEG.
26. **[T] Formy odwołujące się do siebie** (albo wielokrotnie zagnieżdżone) zawieszają analizę.
27. **[K] Nieudana ocena jakości nie da się powtórzyć** bez ponownego wgrania pliku
    (`quality.py:47`).
28. **[K] Klawiatura:**
    - Enter w oknie pytania zawsze potwierdza, nawet gdy zaznaczone jest „Zostaw” — można tak
      stracić pracę.
    - Spacja nie klika przycisków (przejmuje ją przesuwanie podglądu).
    - Zwiniętego rozdziału nie da się rozwinąć klawiaturą.

## D. Drobne

- **Przycisk aktualizacji:** może pokazywać nowszą wersję niż ta, którą zainstaluje (pobrana
  0.4.8, a wydano już 0.4.9).
- **Cofnięcie poprawki:** nie usuwa plików „pobierz_…” ani wyników oceny jakości tej wersji.
- **Dziennik błędów podglądu:** leży w `work/`, więc znika przy każdym starcie.
- **Tryb przeglądarki:** kończy się po uśpieniu laptopa na ponad 3 minuty.
- **Mac, skrypt podmiany:** źle cytuje ścieżkę z nietypowymi znakami.
- **Propozycje produktu:** przy szybkim przełączaniu stron mogą przyjść dla złej strony (serwer
  i interfejs).
- **Komunikat „Zapisano: …”:** przechodzi na inny plik albo stronę.
- **Obraz rastrowy:** ppi liczone tylko z szerokości (`quality.py:68`).
- **16-bitowe obrazy szare:** tracą szczegół przed pomiarem (`detailmap.py:294`).
- **Ukryte warstwy (OCG):** są analizowane jak widoczne. **Zrobione w 0.5.9** (`prepare.bake_print_state` — stan do druku wpisany przy wgraniu).

## Sprawdzone i w porządku

- Brak XSS — nazwy plików, produktów i fontów przechodzą przez `esc()`.
- Brak nieskończonej pętli rysowania i wycieków timerów.
- Indeksy wersji w porządku.
- Dziedziczone MediaBox/Resources działają.
- Multiprocessing na Windows w porządku (`freeze_support`).
- Skala 1:10 liczona dobrze.
- Zapisy cache (produkty, wytyczne) odporne na awarie.
- AppId instalatora stały, `.gitignore` wyklucza pliki klientów.

## Propozycja kolejności naprawy

1. **0.4.8:** A1, A2, A3, A4, A5 (błędy przepuszczające zły plik, głównie interfejs), A11 i B15
   (proste i ważne).
2. **0.4.9:** A6–A9, A14 (analiza: inline, adnotacje, pattern, nieczytelne obrazy, CID) i C21, C22.
3. **0.5:** A10, A12, A13 — obrócone strony, CropBox, UserUnit (większa przebudowa geometrii)
   i szablon.
4. **Osobno:** B16–B18, C19–C20, C23–C24 — podpis aktualizacji, CI, jedna instancja, Mac.

## Stan naprawy

- **0.4.8:** A1, A2, A3, A4, A5, A11, A14, B15 — zrobione.
- **0.4.9:** A6, A7, A8, A9, C21, C22, C26, C27 — zrobione.
- **0.5:** A10 (obrót, CropBox), A12, A13 — zrobione. UserUnit — zrobione w 0.5.9 (`normalize_geometry`, przy pobraniu wraca).
- **0.5.3:** z części D — ppi rastra z obu boków, 16-bitowe obrazy szare, ogromny obraz
  liczony bez tego, co leży nad nim (i bez założenia, że leży prosto) — zrobione.
- **0.6.0:** B16 (podpis aktualizacji — czeka na klucz Tomasza), B18, C19, C20, C28 — zrobione;
  B17 i C24 częściowo (uprawnienia, persist-credentials, concurrency, numer wersji, /LOG).
- **Zostaje:**
  - B17 — sumy kontrolne Ghostscripta i zależności, wersja Inno Setup.
  - C23 (Mac — na prawdziwym Macu), C25 (do sprawdzenia
    po przejściu spłaszczenia na zapis bezstratny) i drobne z części D.
