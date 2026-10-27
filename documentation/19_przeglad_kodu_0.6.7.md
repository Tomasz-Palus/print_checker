# 19 — Testy i przegląd kodu (wersja 0.6.7, 09.10.2026)

Na prośbę Tomasza: gruntowne testy z przypadkami brzegowymi i przegląd całego kodu. **Bez zmian
w kodzie** — to lista do naprawy.

- **Jak zrobione:** sześć niezależnych przeglądów: serwer i dane, poprawki PDF, analiza i jakość,
  interfejs (Playwright), aktualizacje i budowanie, testy end-to-end przez API.
  Najważniejsze znaleziska (A1, A2, A3, A4, A6, A7) Claude sprawdził jeszcze raz sam.
- **Środowisko:** kopia `app/` z repozytorium (stan = commit „adChecker 0.6.7”, bez lokalnych
  zmian), Linux, Ghostscript 10.02 (u Tomasza 10.07), PyMuPDF 1.28.2 (ta sama co w instalatorze).
  Wytyczne z `app/data/guidelines`, sieć do noname.tey.pl i GitHuba zamockowana.
- **Zakres E2E:** 67 przypadków (16 prawdziwych plików, 37 syntetycznych, 9 nazw plików,
  5 z wymiarem ręcznym). Każdy: wgranie → strony → propozycje → wytyczne → analiza → szablon,
  spady, wymiar, CMYK, czerń, overprint, krzywe, spłaszczenie → cofnięcie → jakość → pobranie.
  - Nic nie wisiało; oryginał zawsze nietknięty.
  - Pobrany PDF zawsze: 1 strona, wymiar ±1 mm, sam CMYK, bez overprintu.
  - Czasy (2 rdzenie): wgranie < 1,2 s; spłaszczenie 4–42 s; najdłuższy pełny przepływ 91 s
    (SOFT_BAG 4030×2270 mm).
- **Testy do powtórzenia:** `Claude outputs/testy_0.6.7.tgz` (skrypty w podfolderach `serwer`,
  `poprawki`, `analiza`, `interfejs`, `aktualizacje`, `e2e` + wyniki). Ścieżki są pod Linuksa
  w kontenerze Claude'a — do uruchomienia w kolejnej sesji, nie na Windowsie.
- **Oznaczenia:** [T] — potwierdzone testem, [K] — z czytania kodu.

## A. Pilne: zły plik przechodzi albo dobry się psuje

1. **[T] JPG/PNG/TIFF z DPI powyżej 72 ma zły wymiar** (`render.py:274–279` `inspect`, też
   `views.py:313`).
   - **Przyczyna:** dla obrazów MuPDF podaje wymiar strony już w punktach (px × 72/DPI), a kod
     traktuje go jak piksele i dzieli przez DPI drugi raz.
   - **Skala:** obraz 1000×500 mm wychodzi jako 720×360 mm przy 100 dpi, 480×240 przy 150 dpi,
     240×120 przy 300 dpi. `width_px` też zły.
   - **Skutek:**
     - poprawny JPG 100 dpi w wymiarze szablonu → „zły wymiar”, brak propozycji;
     - gorzej: JPG o 39 % za duży (1251×2732 mm) jest widziany jako 901×1967 → propozycja
       adFlag DROP S i „zgadza się”;
     - podgląd w za małej rozdzielczości.
   - **Czemu nie wyszło wcześniej:** testy rastrów miały 9, 20 i 72,5 dpi.
   - **Poprawka:** piksele z Pillow (`im.size`, przy TIFF `seek(i)`), mm = px / DPI × 25,4.
2. **[T] Błąd sprawdzania domyka rozdziały bez decyzji.**
   - **Analiza** (`state.js:250` `settledByChoice`: `a?.error` → „done”): przy 500 albo braku
     połączenia Kolory, Overprint, Fonty i Spłaszczenie są domknięte, a Pobierz pisze „Plik gotowy
     do druku”. Analiza nie jest ponawiana.
   - **Jakość** (`quality.js:40`, `:378`): „nie udało się sprawdzić” → dalej do akceptacji.
   - **Szablon** (`state.js:154`, `chapters.js:44`): przy błędzie rozdział domknięty, szablon idzie
     do druku.
   - **Poprawka:** przy błędzie rozdział zostaje do decyzji z „Sprawdź jeszcze raz”; ewentualnie
     świadome „pomiń”, które Pobierz wypisuje jako ostrzeżenie.
3. **[T] XSS — nazwa fontu z pliku klienta wykonuje się jako HTML** (`viewer.js:413`).
   - `d.innerHTML = <span>⚠ ${m.label}</span>`, a etykieta to `/BaseFont` nieosadzonego fontu.
   - Test: font `/<img src=x onerror=alert(1)>` → `alert` wykonany w oknie programu.
   - **Skutek:** kod z PDF-u ma dostęp do `/api/*` (także `update/install`) i `pywebview.api`.
   - To samo bez `esc()`: `frameLabel` (`viewer.js:400`), „Ostatni błąd” w Ustawieniach
     (`settings.js:63`, nazwa produktu ze strony).
   - **Poprawka:** `textContent` albo `esc()`.
4. **[T] „Zamień na CMYK” zostawia grupę przezroczystości strony w RGB** (`steps.py:637`
   `_splice`; robi to pdfwrite).
   - Po konwersji `/Group /CS /DeviceRGB` (i `/I true`). W renderze CMYK (spłaszczenie, RIP)
     czerń K100 wychodzi jako `[174 173 165 189]`, cyjan 100 % jako `[176 36 0 0]`.
     Po zmianie `/CS` na DeviceCMYK — czyste wartości.
   - Plik już w CMYK z grupą RGB (dokument RGB z Illustratora) nie ma jak tego naprawić —
     Kolory mówią „już w CMYK-u”.
   - **Poprawka:** po `_splice` (także w szybkiej ścieżce) ustawić `/CS` grupy strony i grup form
     (poza maskami SMask) na DeviceCMYK albo profil docelowy; wykrywać grupę RGB w analizie.
5. **[T] „Dopasuj wymiar” gubi grupę przezroczystości strony** (`steps.py:268–271`,
   `show_pdf_page`). Na `strony.pdf` przy skali 100 % render CMYK zmienia się na 83 % pikseli;
   spłaszczenie utrwala zły kolor. **Poprawka:** kopiować `/Group` na nową stronę i formę
   (tak jak OutputIntent w `_keep_doc_level`).
6. **[T] Podmiana fontu niewykryta, gdy nazwa ma spację** (`gs.py:267`, `steps.py:621–626`) —
   luka w poprawce A1/A14 z doc 18.
   - Wzorzec `(\S+)` nie łapie „Loading font Foo Bar Sans (or substitute)”. Krzywe i spłaszczenie
     utrwalają zamiennik bez ostrzeżenia; CMYK osadza go jako `EDOLUF+Foo Bar Sans`, więc
     ostrzeżenie znika.
   - Nazwa z nawiasem (`Foo(Bar)Sans`): CMYK pada błędem gs (`/NeverEmbed` psuje PostScript).
   - **Poprawka:** wzorzec `Loading font (.+?) \(or substitute\) from`; nazwy w NeverEmbed
     jako ciągi `(…) cvn` z cytowaniem.
7. **[T] Jakość: filtr widoczności chowa prawdziwe problemy** (`detailmap.py:797`, `:802–818`,
   `:877`).
   - **Regresja A8:** obraz nieczytelny (JPX 14 ppi) znowu „ok” — MuPDF go nie rysuje, więc mapa
     widoczności uznaje go za zakryty.
   - **Próg względny 2 %** (`VIS_MIN_SHARE`): obraz 14 ppi widoczny przez okno 21×21 mm → „ok”;
     plansza 5×5 m (1:10) w oknie 70×70 cm → „ok”. Typowa sytuacja: duże zdjęcie mocno
     przycięte ramką.
   - **Wzory:** obraz we wzorze liczony w miejscu pierwszej płytki, nie wypełnianego obszaru →
     „poza stroną”/„niewidoczny” → „ok”.
   - **Poprawka:** próg bezwzględny w mm na wydruku (np. `MIN_REGION_MM`); obrazy nieczytelne
     i we wzorach bez filtra widoczności (albo mapa widoczności z Ghostscripta).
8. **[T] TIFF wielostronicowy — do druku idzie zła strona** (`server.py:470–474`, `steps.py:304`,
   `:653`). Po wyborze strony 2: CMYK i wymiar robią się na stronie 1, analiza kolorów pokazuje
   stronę 1, pobranie bez poprawek oddaje cały TIFF. **Poprawka:** przy wyborze strony wyciąć ją
   do osobnego pliku.
9. **[T] Zmiana produktu albo roli w trakcie poprawki** (`product.js:99`, `:217`, `:277`;
   `steps.js:26`, `:82`).
   - „Dopasuj wymiar” do 500×1000, w trakcie zmiana produktu na 200×200 → Wymiar pokazuje
     „dopasowany — 200 × 200”, a strona ma 500×1000.
   - Nieudane cofnięcie przy zmianie produktu jest połykane (`catch(_){}`) — ten sam skutek.
   - Serwer pobiera zawsze ostatnią wersję i ignoruje `?v=` (`server.py:451–470`): gdy cofnięcie
     przeszło, a odpowiedź nie doszła, pobrany plik ma inny wymiar niż zaakceptowany.
   - **Poprawka:** przyciski produktu/roli/stron nieaktywne przy `S.busy`; w `applyStep`
     porównywać stronę/produkt/rolę; błąd cofnięcia pokazać; serwer 409, gdy `v` ≠ ostatnia.
10. **[T] Uszkodzone pobranie wytycznych nadpisuje dobrą kopię** (`guidelines.py:415–416`).
    Zapis przed parsowaniem: obcięty PDF → 502, ale kopia już nadpisana. Potem bez sieci
    `frames.find` po cichu nie znajduje szablonu (3 → 0) — szablon zostałby w druku.
    **Poprawka:** parsować z pliku tymczasowego, `os.replace` dopiero po sukcesie.

## B. Ważne

11. **[T] Rozdział Fonty nie widzi nieosadzonego fontu** we wzorze, w glifie Type3
    i w bezpośrednim słowniku fontu (`fontfix.py:375–399`), choć `analyze.fonts` go pokazuje.
12. **[T] Analiza nie widzi treści w kilku miejscach, które się drukują** (`analyze.py`,
    `detailmap.py:976`): glify Type3 (`/CharProcs` — obrazy i RGB), maski `ImageMask`
    (zeskanowane logo 1-bit), niskorozdzielcze `/SMask`/`/Mask` (schodki na konturze), maska
    miękka w ExtGState (`/SMask /G`), formy głębiej niż 12 poziomów.
13. **[T] Analiza niepełna przechodzi po cichu** (`analyze.py:330`, `:339`). Po wyczerpaniu
    budżetu operatorów albo głębokości reszta treści znika, a `parse_warnings` nie trafia ani do
    UI, ani do jakości (wynik „vector”/„ok”). **Poprawka:** ostrzeżenie „analiza niepełna”
    i nigdy „ok” w takim wypadku.
14. **[T] Powiększenie 3–4× przy nominalnych ≥ 120 ppi nie jest wykrywane** (`detailmap.py:77`
    `THRESHOLD = 0.045`, `_knee`). Obraz o widmie naturalnym powiększony 3× (realnie 100 ppi)
    i 4× (75 ppi) → „ok”; to samo na zdjęciu z przykładów. Przy f = prawdziwe powiększenie
    E(f)/E(8) ≈ 0,055 > 0,045. `THRESHOLD = 0.08` wykrywa 3× i 4× bez fałszywych alarmów
    na trzech próbkach — **do kalibracji na plikach Tomasza**.
15. **[T] Spłaszczenie bez OutputIntent bierze profil pierwszego obrazu CMYK**
    (`steps.py:1066` → `file_icc`). Mały obraz z profilem SWOP → cała strona przez SWOP.
    **Poprawka:** tylko OutputIntent, inaczej FOGRA39.
16. **[T] 16-bitowy obraz w skali szarości robi się biały** po CMYK albo „Dopasuj wymiar”
    (`steps.py:326`, `:670`; Pillow obcina do 255). **Poprawka:** najpierw `>> 8`.
17. **[T] „Tło z krawędzi” zostawia biały pas ~0,5 mm** w drugiej osi (`steps.py:270`,
    `keep_proportion=True`). Odbicie lustrzane w porządku.
18. **[T] JPG bez DPI pobiera się bez DPI** (`size.js:158`). RIP przyjmie 72 dpi: 600×1200 px
    → 212×423 mm zamiast 1015×2014. **Poprawka:** wpisać DPI z wymiaru szablonu przy pobraniu.
19. **[T] Spóźnione wytyczne poprzedniego produktu** (`product.js:84` bez `glSeq++`,
    `state.js:73`) — produkt spoza listy 500×500 dostaje skalę 1:10 → Wymiar „5000 × 5000”,
    jakość i spłaszczenie ×10.
20. **[T] Propozycje produktu dla złej strony** — punkt D z doc 18 nadal otwarty
    (`server.py:200–216` zapisuje wynik w `job`, `product.js:293` nie sprawdza `S.page`).
21. **[T] Równoległe zapisy przez wspólny `.tmp`** (`guidelines.py:72–77`, `sizeindex._save`,
    `products._save_cache`) — 1 na 30 rund daje 502. Też: podwójny start indeksu wymiarów
    (`running` ustawiane w wątku) → 42 pobrania na 30 produktów.
22. **[T] Jakość przy wymiarze ≤ 0 albo NaN daje „ok”** (`server.py:426–437`); interfejs dziś
    tego nie wysyła, ale serwer powinien odrzucić (400).
23. **Aktualizacje:**
    - **[T] B16 nadal nieaktywne** — `update_key.py` ma pusty `PUBLIC_KEY`, więc podmienione
      wydanie (instalator + plik sum) zainstaluje się. Ed25519 sam w sobie poprawny (wektory
      RFC 8032, zgodność z OpenSSL, odrzucanie niekanonicznych S).
    - **[T] Downgrade/replay:** wersja z niepodpisanego `tag_name`; tag `v9.9.9` ze starym,
      poprawnie podpisanym instalatorem 0.6.5 → instaluje się. **Poprawka:** wersja z nazwy
      zasobu w podpisanym pliku sum musi równać się tagowi i być > `VERSION`.
    - **[T] `/api/update/install` kończy przez `os._exit` bez `_shutdown()`** (`server.py:566–573`)
      — Ghostscript i procesy jakości zostają (C20 tylko przy zamknięciu okna).
    - **[K] Zły podpis → interfejs i tak pokazuje „Jest nowa wersja — pobierz”** z linkiem do
      podmienionego wydania (`main.js:480–485`). Potrzebny osobny status bez linku.
24. **[K] PyMuPDF wołany z kilku wątków naraz** (detailmap w tle + trasy Flaska);
    `mupdf_warnings(reset=True)` jest globalne (`render.py:377–380`) — równoległy wątek może
    skasować ostrzeżenie „overly large”. **Poprawka:** jedna blokada wokół MuPDF.
25. **[T] Wydajność analizy:** forma użyta 12 000 razy (3,6 mln operatorów) → 51 s; forma parsowana
    od nowa przy każdym użyciu. **Poprawka:** cache operatorów per obiekt.

## C. Drobne

- [T] „Usuń szablon” wycina cały blok BT…ET razem ze stanem tekstu (`frames.py:402`) — gdy
  kolejny tekst klienta korzysta z `Tf`/koloru ustawionego w usuniętym bloku, znika.
- [T] Nadmiarowe `Q` na początku treści psuje obrót wpisany przez `normalize_geometry`
  (`render.py:182`).
- [T] „Popraw czerń” nie wchodzi do wzorów i glifów Type3; `cs` Registration bez `scn` → K100.
- [T] Obrazy < 8 px w którymś boku pomijane, także w sprawdzeniu ppi (`detailmap.py:1008`) —
  obraz 4×4 px na całą stronę → „ok”.
- [T] Kolor ustawiony samym `cs` (bez `sc`) i kolor bazowy wzoru PaintType 2 nie są liczone;
  overprint w `/ExtGState` wzoru cieniowanego nie jest liczony.
- [T] Wymiar szablonu z wytycznych: pierwszy napis „AxB mm” wygrywa („Keder 9x3mm” nad
  wymiarem → 9×3 mm). W 17 prawdziwych wytycznych nie wystąpiło.
- [T] Ramka szablonu obrócona o 90° w treści pliku nie jest rozpoznawana (`suggest.py:265`).
- [T] Błędy wgrania z wewnętrzną ścieżką zamiast komunikatu (pusty JPG, śmieci jako `.png`,
  `.ai` bez PDF-u). PDF nazwany `.jpg` przechodzi jako raster.
- [T] API: złe ciało JSON → 500 zamiast 400; `/steps` bez sprawdzenia strony i wartości
  (`w_mm=0` → strona US Letter, `flatten k=0` → 1,2 ppi opisane jako 120). Kroki PDF wysłane dla
  obrazu → 500. Interfejs tego nie wysyła.
- [T] Zapasowa nazwa przy pobraniu bez `safe_name()` (`server.py:471`) — trafia do „Zapisz jako”.
- [T] Plik o nazwie `.pdf` odrzucany jako „brak rozszerzenia”.
- [T] Komunikat „przycięte 1330,8 × -0 mm”.
- [T] Fałszywy „szablon w pikselach” na szumowym zdjęciu RGB.
- [T] Błąd cofnięcia nie jest pokazywany (`steps.js:57–61`).
- [T] „Zapisano: …” przechodzi na inny plik (D z doc 18, nadal otwarte).
- [T] Dwa okna pytania naraz — Tab przestaje działać w całym programie (`util.js:171–194`).
- [K] Podgląd po 30 nieudanych próbach zostaje „wczytuję podgląd…” bez komunikatu.
- [K] Spłaszczenie (`gs.stream`) bez limitu czasu — zawieszony gs trzyma blokadę zadania.
- [K] `_gs_page` (`steps.py:410`) przy każdym błędzie ponawia bez `-dSAFER`.
- [K] Klucz w pamięci obrazów (`detailmap.py:924`) bez położenia — możliwa zamiana wyników
  obrazów tego samego wymiaru.
- [T] Aktualizacje: skrypt podmiany na Macu bez `shlex.quote` (D z doc 18); TOCTOU między
  weryfikacją a uruchomieniem; dwa `install()` = dwa instalatory; `0.6.7.0` > `0.6.7`.
- [K] CI (B17 nadal): Ghostscript bez sumy, zależności bez `--require-hashes`, Inno Setup bez
  wersji, akcje po tagu; sekret podpisu dostępny z `workflow_dispatch` na dowolnej gałęzi.
- [K] Mac (C23 nadal): `LSMinimumSystemVersion 11.0` przy paczce wymagającej 14; brak `certifi`,
  a błąd sprawdzania aktualizacji jest połykany.

## D. Do decyzji Tomasza

- **Sufit 400 Mpx przy spłaszczaniu** obniża rozdzielczość poniżej 120 ppi: 5080×5080 mm → 100 ppi,
  baner 20 m → 114 ppi. Program to mówi, ale to wbrew „120 ppi zawsze”.
- **Mieszanie Multiply na stronie bez `/Group /CS`:** Ghostscript miesza w CMYK, MuPDF/Poppler
  w RGB — po spłaszczeniu wyraźnie jaśniej (114 zamiast 77 w szarości). Warto sprawdzić, czy
  podgląd zgadza się wtedy z wydrukiem.
- **Próg metody kolana** (B14) — zmiana wymaga kalibracji na prawdziwych plikach.
- `adWall_Vario_Prosta_Light_400_SOFT_BAG` z folderu „poprawne” dostaje „bad” (dwa obrazy
  73 ppi) — to prawda o pliku, nie błąd programu.

## Regresje z doc 18 — stan

| Punkt | Wynik |
|---|---|
| A1, A14 (podmiana fontu, CID) | działa — poza nazwami ze spacją (A6) |
| A2–A5 (wyścigi w interfejsie) | działa |
| A6, A7, A9 (inline, adnotacje, wzory) | działa |
| A8 (obraz nieczytelny) | **regresja** (A7 wyżej) |
| A10, A11 (obrót, CropBox, UserUnit, ujemny MediaBox, CMYK nie obraca) | działa (porównanie obrazów) |
| A12, A13 (stopka klienta, OutputIntent) | działa |
| B15 (Origin/Host) | działa (także `127.0.0.1.evil.com`, Origin `null`, inny port) |
| B16 (podpis aktualizacji) | kod gotowy i poprawny, **klucz nadal pusty** |
| C19, C20, C21, C22, C25, C26, C27, C28 | działa (C20 poza ścieżką aktualizacji) |
| D: ppi rastra z obu boków, 16-bit szary w jakości | działa |
| D: propozycje dla złej strony, „Zapisano”, skrypt Maca, przycisk aktualizacji | nadal otwarte |

## Sprawdzone i w porządku

- Odrzucanie złych plików: pusty, 1 bajt, nie-PDF, 0 stron, hasło do otwarcia, `.cdr`, za duży;
  hasło uprawnień zdjęte, uszkodzony xref naprawiony — z notatką.
- Path traversal zablokowany (jid, kafelki, hash wytycznych, `/static/..`, nazwa wgrywanego pliku).
- Nazwy z polskimi znakami, spacjami, 250 znaków, `../`, `"<>` — wgranie i pobranie w porządku.
- Kolejność poprawek wymuszona; cofanie ucina dalsze wersje i usuwa ich pliki.
- Overprint w zagnieżdżonych miejscach (wzór, Type3, forma w formie) wyłączany w całości.
- Obrazy obrócone, pochylone, odbite, wąskie paski — ppi z macierzy poprawne; skala 1:10 poprawna.
- Dekodowanie do oceny detalu: Lab, Separation, DeviceN, Indexed, 16 bit, ICC, JPX, JPEG CMYK.
- Obraz 800 Mpx w 1:10 → „bad” w 191 s (2 rdzenie), bez ponownego dekodowania całości.
- Ed25519 zgodny z RFC 8032 i OpenSSL.
- Pozostałe miejsca z nazwami plików/produktów/ról używają `esc()` lub `textContent`;
  localStorage w try/catch.

## Proponowana kolejność naprawy

1. **0.6.8:** A1 (wymiar rastra), A2 (błędy domykające rozdziały), A3 (XSS), A6 (nazwa fontu).
   Małe zmiany, duży skutek.
2. **0.6.9:** A4, A5, B15 (grupy przezroczystości i profil przy spłaszczeniu), B16 (16-bit).
3. **0.7:** A7, B12, B13 (widoczność i niewidziane miejsca w analizie), B14 po kalibracji.
4. **0.7.x:** A8–A10, B18–B22 (TIFF, wyścigi w interfejsie i zapisach, JPG bez DPI).
5. **Osobno:** B23 (klucz aktualizacji — wymaga Tomasza), B24, B25, część C.

## Stan naprawy — wersja 0.6.8 (09.10.2026)

Wszystko z części A, B i C naprawione w 0.6.8, z wyjątkami niżej. Każda naprawa sprawdzona testem
przed/po; potem pełna regresja na złożonej wersji: E2E (69 przypadków), zestawy testów
serwera, poprawek, analizy (112/115 — 3 to znane ograniczenia, niżej), aktualizacji (34/34),
interfejsu w Playwright (21/21, w tym pełny przepływ na SOFT_BAG, `strony.pdf` str. 2, JPG
i TIFF str. 2). Czas pełnego przepływu bez zmian (−2,6 % łącznie).

**Zmiany zachowania widoczne dla użytkownika:**
- Błąd sprawdzania (analiza, szablon, jakość) nie domyka rozdziału: „Sprawdź jeszcze raz” albo
  „Pomiń sprawdzanie” — pominięte i niepełne sprawdzenia są wypisane w Akceptacji i Pobierz
  („Nie wszystko sprawdzono”), zamiast „Plik gotowy do druku”.
- Analiza niepełna (bardzo złożony plik) → ostrzeżenie i „Rozumiem, idę dalej”; jakość daje
  wtedy „sprawdzona częściowo”, nigdy „w porządku”.
- Kolory: plik CMYK z przezroczystością mieszaną w RGB też wymaga „Zamień na CMYK” (zmienia
  tylko przestrzeń mieszania, wartości kolorów zostają).
- Jakość: zgłasza też kontury/maski i obrazy nieczytelne; mocno przycięte zdjęcia nie są już
  chowane (próg 1 cm² widocznej części na wydruku); powiększenie 3–4× wykrywane (próg bloków 0,08,
  skalibrowany na przykładowych plikach — zero nowych alarmów na treści w natywnej rozdzielczości).
- Produkt, rola i strony zablokowane w trakcie poprawki; pobranie innej wersji niż zaakceptowana
  odrzucone („Plik zmienił się…”).
- Obraz bez DPI: przy pobraniu dostaje DPI z wymiaru wydruku.
- TIFF wielostronicowy: wybrana strona wycinana do osobnego pliku.
- Aktualizacja odrzucona (zły podpis, suma, wersja) — bez przycisku i linku, wpis w dzienniku.

**Nie zrobione / ograniczenia:**
- **B23, klucz aktualizacji** — wymaga Tomasza (kroki niżej). Do tego czasu podpis nie działa.
- **JPG bez DPI** — nagłówek JPG zapisuje DPI jako liczbę całkowitą: przy bardzo niskim DPI
  (~15) wymiar wychodzi do 1,5 % mniejszy; przy ~150 dpi ok. 0,3 %. PNG i TIFF dokładnie.
- **Analiza po wyczerpaniu budżetu** (5 mln operatorów) — reszta treści nadal niesprawdzona, ale
  analiza jest oznaczona jako niepełna (B13). Powiększenie obrazu 1-bitowego — niewykrywane.
- **Font jako bezpośredni słownik** (bez numeru obiektu) — zgłaszany jako brak, nie osadzany
  z Google Fonts.
- **Grupy przezroczystości** dostają `/DeviceCMYK`, nie ICC profilu (interpretację CMYK i tak
  wyznacza OutputIntent).
- **Inno Setup w CI** pobierany teraz z wydania autora z sumą SHA-256 (Chocolatey zablokowany
  w sandboksie) — pierwszy przebieg GitHuba pokaże, czy działa. Lock zależności
  (`packaging/requirements-build.lock`, `--require-hashes`) przypina też zależności zależności
  do bieżących wersji z PyPI.
- **Część D** (sufit 400 Mpx, Multiply) — bez zmian, czeka na decyzję.

**Kroki dla Tomasza — klucz aktualizacji (B16/B23):**
1. W katalogu repozytorium: `py packaging\klucz_aktualizacji.py` — wpisze klucz publiczny do
   `app\update_key.py`, prywatny pokaże na ekranie (zapisz w menedżerze haseł).
2. GitHub → Settings → Environments → **release** (utwórz, jeśli nie ma) → Deployment branches:
   tylko `main` → sekret `ADCHECKER_SIGN_KEY` = klucz prywatny.
3. Usuń stary sekret `ADCHECKER_SIGN_KEY` z poziomu repozytorium, jeśli jest.
4. Podbij wersję i wypchnij. Ochrona działa od aktualizacji PO wersji z kluczem.
