# Przepisanie programu od nowa (od 24.09.2026)

Decyzja Tomasza z 24.09: zapisać obecny stan jako kopię zapasową i przepisać kod od nowa,
tak żeby był jak najprostszy i czysty, a wygląd jak najbardziej przyjazny dla osoby
nietechnicznej: jak najmniej informacji na ekranie, wyjaśnienia schowane pod „?".

- **Kopia zapasowa:** `print_checker/_kopia_2026-09-24/`. Są w niej kod, strona, dane
  (bez pobranych PDF-ów wytycznych) i dokumentacja. Ta wersja działa tak jak przed
  przepisaniem.
- **Nowa wersja:** `print_checker/app_nowy/`, port **5001** (stara w `app/` zostaje na 5000).
  Obie mogą działać naraz, więc da się je porównywać. Gdy nowa będzie kompletna
  i sprawdzona, zamienimy je miejscami.

## Etapy

| Etap | Zakres | Stan |
|---|---|---|
| 1 | Plik, strona, produkt, rola i nowy podgląd (pełna jakość, powiększenie, nawigator, szablon). Do tego ustawienia. | sprawdzony przez Tomasza 24.09 |
| 2 | Szablon z wytycznych, spady, wymiar (z dokładaniem tła). | sprawdzony przez Tomasza 24.09 |
| 3 | Kolory (z symulacją druku), overprint (z symulacją), fonty, spłaszczenie. | sprawdzony przez Tomasza 24.09 |
| 4 | Jakość wydruku, pobieranie pliku, sprzątanie `analyze.py` i `detailmap.py`, zamiana wersji. | gotowy do sprawdzenia (zamiana wersji — po akceptacji) |

## Co się zmienia w działaniu

1. **Rozdziały jak lista kontrolna.** Każdy rozdział ma:
   - status w nagłówku: numer, ✓ (zrobione) albo ! (do zrobienia),
   - jedno zdanie o stanie, jeden przycisk,
   - „?" z wyjaśnieniem.

   Zrobiony rozdział zwija się do jednej linijki z podsumowaniem; kliknięcie w nagłówek go
   rozwija (strzałka ▸/▾).
2. **Po kolei.** Kolejny rozdział otwiera się, gdy poprzedni jest zrobiony, nie ma w nim
   nic do zrobienia albo zostanie pominięty.
3. **Łańcuch wersji.** Oryginał to v0, a każda poprawka tworzy nowy, osobny plik (v1, v2…)
   z poprzedniego. Wersje się nie zmieniają.
   - Nic nie jest nadpisywane w trakcie oglądania. Znikają przez to blokady plików na
     Windowsie, odpowiedzi „409 — trwa poprawka" i nieaktualne kafelki (nowa wersja =
     nowy numer = nowe kafelki).
4. **Cofnięcie poprawki** cofa ją razem z krokami zrobionymi po niej. Tak działało już
   cofanie wymiaru; teraz jest jedna zasada dla wszystkich rozdziałów.
5. **Suwak w rozdziale** pokazuje stan tuż przed i tuż po tym kroku. Znika liczenie wersji
   „wszystko oprócz jednej poprawki" — kilkanaście sekund Ghostscripta przy pierwszym ruchu
   suwaka i źródło kłopotów z pełną jakością.
6. **Podgląd tylko z piramidy.** Nie ma już osobnego obrazu 1600 px:
   - od razu przychodzi szybki podgląd całej strony (`ov_q.jpg`),
   - pod spodem liczy się pełna jakość (kafelki `L…`),
   - na końcu powstaje dokładny podgląd całości (`ov.jpg`, bez gubienia cienkich linii).

   Wszystko z Ghostscripta, z profilem FOGRA39, więc warstwy nigdy nie różnią się kolorem
   przez sposób renderowania.
7. **Porzucony podgląd nie blokuje kolejki.**
   - Przeglądarka odwołuje podgląd, którego już nie ogląda (inna strona, inna wersja).
   - Gdy w ogóle przestanie pytać o jego stan (np. zamknięta karta), serwer przerywa go
     po 2 minutach.

   Wcześniej zmiana strony czekała, aż skończy się liczenie poprzedniej.
8. **Podgląd rastrów** (JPG/PNG/TIFF) liczy Pillow, nie Ghostscript: CMYK przez profil,
   w natywnej rozdzielczości obrazu.
9. **Powiększanie (poprawka Tomasza 24.09):**
   - lupki jak w Photoshopie: przycisk wybiera narzędzie (albo klawisz Z, Alt+Z dla −;
     Esc wyłącza),
   - potem kliknięcie w podgląd powiększa/pomniejsza ×1,5, a przeciągnięcie zaznacza obszar:
     - lupka +: zaznaczony obszar wypełnia okno,
     - lupka −: całe okno mieści się w zaznaczonym obszarze,
   - spacja trzymana = chwilowo przesuwanie,
   - Ctrl + kółko (względem kursora), przeciąganie przesuwa widok.

   „Rzeczywista wielkość" (dawne „100 %") to największe możliwe przybliżenie — bardziej się
   nie da. Przycisk „Podgląd szablonu" stoi na środku paska i się wyróżnia (domyślnie
   wyłączony). Przy „Dopasuj" podgląd nie ma pasków przewijania (na 4K ułamki pikseli je
   włączały).
10. **Numery rozdziałów** liczą się same, z tych, które są widoczne.
11. **Strona przed produktem** (Tomasz 24.09): plik → strona → produkt → rola. Propozycje
    produktu i roli liczą się z wymiaru i treści WYBRANEJ strony (`/api/jobs/<id>/suggest`).
    Zmiana strony wymaga ponownego zatwierdzenia roli.
12. Większa strzałka zwijania rozdziału, długa nazwa pliku zawija się w polu,
    „PDF wytycznych" to zwykły przycisk.

## Co przeszło 1:1 (obejścia i ustalenia — nie ruszać bez sprawdzenia)

**Ghostscript** (`gs.py`):
- Overprint `/simulate` + wygładzanie przy renderze pasami gubi treść. Dlatego przy
  overprincie cała strona renderuje się naraz (`MaxBitmap` ~12× strony, do 1,5 GB), a gdy
  to za dużo — bez wygładzania, z nadpróbkowaniem 2× w piramidzie.
- Podgląd bez „fill adjust" (`0 0 .setfilladjust2`): krzywe wyglądają tak samo jak font.
- Komunikaty (stderr) czytane na bieżąco w osobnym wątku (bufor potoku na Windowsie ~4 KB).
- Ścieżka profilu ICC jako kopia bez spacji i nawiasów (Program Files (x86)), plus
  `--permit-file-read`.
- Kroju zastępczego nie używamy nigdy. Wykrycie: gs bez `-q`, wiersz
  „Loading font … (or substitute)" ze ścieżką w zasobach Ghostscripta.
- Symulacja druku: gs liczy do CMYK FOGRA39 (relatywna + BPC), na ekran przelicza ImageCms.
- **NOWE (etap 3):** zapis PDF (pdfwrite) ignoruje `-sOutputICCProfile` — konwersja do CMYK
  idzie przez podmieniony `default_cmyk.icc` w kopii katalogu profili Ghostscripta
  (`gs.cmyk_target_args`). Szczegóły w sekcji etapu 3.
- **NOWE (etap 3):** na urządzeniu CMYK Ghostscript domyślnie nakłada overprint — podgląd bez
  symulacji dostaje jawnie `-dOverprint=/disable`.

**Pliki i analiza:**
- Overprint szukany we wszystkich słownikach, także zagnieżdżonych bezpośrednio
  (`pdfutil.all_dicts`).
- Type 3 = font osadzony; 14 fontów standardowych PDF-a = w porządku.
- MuPDF odmawia obrazów > ~0,5 Gpx: wtedy wycinki i miniatury renderuje Ghostscript.
- Skrajny wiersz/kolumna renderu jaśniejszy (częściowe pokrycie): `render.fix_edges`.

**Produkt i wytyczne:**
- Wytyczne zawsze świeże ze strony; kopia lokalna tylko przy braku sieci, na żółto.
- Sugestia produktu: nazwa pliku, potem treść (szablon zostawiony w pliku), potem wymiar.
- Rola: nazwa pliku, a bez trafienia — wymiar (ramka szablonu, format netto, strona).

**Kolejność rozdziałów:** strona → produkt → rola → szablon z wytycznych → spady → wymiar → kolory
→ overprint → fonty → spłaszczenie → jakość.

**Szablon z wytycznych** (`frames.py`, przepisany, wynik identyczny ze starą wersją na pliku
testowym: 3 obiekty, zgodność 1,0, odchyłka 2 mm):
- porównanie całego szablonu,
- skan raz, na oryginale,
- usuwanie jako pierwsza poprawka.

Poprawka przy okazji: kolory ustawiane przez `sc/scn` z liczbami dziesiętnymi były
wcześniej pomijane. pikepdf zwraca je jako `Decimal`, a stary kod przyjmował tylko
`int/float`.

## Nowa budowa programu

Serwer (Python):

| Plik | Co robi |
|---|---|
| `server.py` | same trasy HTTP |
| `jobs.py` | zadanie = wgrany plik + łańcuch wersji (dopisz / utnij) |
| `steps.py` | poprawki; każda to funkcja „plik wejściowy → nowy plik". Ghostscript przepisuje tylko wybraną stronę, wynik wklejamy w kopię pliku (`_gs_page` + `_splice`) |
| `render.py` | otwieranie plików, miniatury, wycinki do analizy, piramida podglądu |
| `views.py` | zamówienia na piramidy: kolejka, postęp, przerywanie porzuconych |
| `gs.py` | wszystko o Ghostscripcie, w tym obejścia jego błędów |
| `pdfutil.py` | drobne narzędzia PDF (overprint, fonty, spoty, wymiary stron) |
| `frames.py`, `fontfix.py`, `suggest.py`, `guidelines.py`, `products.py`, `sizeindex.py` | jak wcześniej, oczyszczone |
| `analyze.py`, `detailmap.py` | fakty o stronie / mapa detalu obrazów — oczyszczone w etapie 4 (wyniki identyczne) |
| `quality.py` | rozdział „Jakość wydruku”: która wersja, skala, werdykt dla człowieka |

Strona (`static/`):

| Plik | Co robi |
|---|---|
| `index.html`, `style.css` | szkielet i wygląd |
| `js/state.js` | cały stan w jednym miejscu + jedna pętla rysowania (`changed()` → wszystko się odrysowuje) |
| `js/viewer.js` | podgląd: scena (ramka + warstwy w mm), piramida, powiększenie, nawigator, linie szablonu, podświetlenie |
| `js/product.js` | rozdziały Produkt, Rola, Strona |
| `js/chapters.js`, `js/size.js` | rozdziały Szablon, Spady, Wymiar |
| `js/print.js` | rozdziały Kolory, Overprint, Fonty, Spłaszczenie + symulacje druku |
| `js/quality.js` | rozdziały Jakość wydruku i Pobierz plik, nawigacja po słabych miejscach |
| `js/settings.js` | kalibracja monitora, dokładność oceny jakości, indeks wymiarów |
| `js/help.js` | teksty pod „?" |
| `js/util.js` | drobiazgi (API, okno „na pewno?", obsługa rozdziałów) |
| `js/main.js` | start, wgrywanie pliku, pętla rysowania |

## Etap 1 — co sprawdzić

1. Uruchom `app_nowy/run.bat` i otwórz http://127.0.0.1:5001.
2. Wgraj plik i sprawdź:
   - czy sugestia produktu jest ta sama co w starej wersji,
   - potwierdzenie produktu, wybór i zatwierdzenie roli,
   - przy pliku wielostronicowym: wybór strony (lista albo miniatura).
3. Podgląd:
   - przycisk „Szablon",
   - „100 %", + / −, Ctrl + kółko, podwójne kliknięcie, przeciąganie, nawigator,
   - czy pełna jakość zawsze się doczytuje (także po zmianie strony i po potwierdzeniu
     produktu w skali 1:10).
4. Ustawienia: kalibracja, indeks wymiarów.

Testy w kontenerze (Playwright) przeszły na:
- `PRINT_CHECKER_TEST_100x200_SZABLON_PASERY.pdf` (3 strony, spady),
- `Wydruk_adWall_Vario_Prosta_600_43…` (skala 1:10, overprint),
- `strony.pdf` (zmiana strony: nowa strona widoczna po 0,8 s),
- `1788264646af029f_q1.jpg` (raster, wymiar spoza listy).

## Etap 2 — szablon z wytycznych, spady, wymiar

**Serwer:**
- `steps.py`: poprawki `frames`, `trim` i `resize`. Kod przeniesiony ze starego `fixes.py`
  bez zmian w działaniu. Sprawdzone: wynik jest identyczny co do piksela ze starą wersją
  (render porównawczy na `fonty.pdf` i `1815_czcionki.pdf`, tło z krawędzi i odbicie
  lustrzane, przycięcie spadów).
- Każda poprawka zapisuje nowy plik. Nie ma już `_swap`, `forget_doc`, ponawiania przy
  blokadzie pliku na Windowsie ani plików tymczasowych w miejscu docelowym.
- Poprawka, która zmienia geometrię strony, zwraca `map` = {s, dx, dy}: jak punkt starej
  strony przechodzi na nową. Podgląd kładzie dzięki temu „przed" i „po" dokładnie na sobie:
  - przy spadach wersja „przed" wystaje poza stronę „po",
  - przy wymiarze projekt leży tam, gdzie wylądował.
- Nowe trasy:
  - `GET /api/jobs/<id>/frames` — szukanie szablonu, zawsze na oryginale,
  - `POST /api/jobs/<id>/steps` — nałożenie poprawki,
  - `DELETE /api/jobs/<id>/steps/<nazwa>` — cofnięcie poprawki razem z późniejszymi.
- Serwer pilnuje kolejności: poprawki „wcześniejszej" nie da się nałożyć na „późniejszą".

**Rozdziały** (`js/chapters.js`, `js/size.js`, wspólne `js/steps.js`):
- **Szablon z wytycznych.** Stany:
  - czysto,
  - szablon w projekcie → „Usuń szablon" albo „zostaw jak jest",
  - szablon wtopiony w obraz → „rozumiem, idę dalej",
  - ramki w kolorach wytycznych, które nie pasują do szablonu tego produktu → „rozumiem,
    idę dalej".

  Po usunięciu jest suwak przed/po.
- **Spady.** Źródło formatu netto: TrimBox albo ArtBox, a bez nich strona równomiernie
  większa od wytycznych. Przyciski: „Przytnij spady" albo „zostaw spady". Po przycięciu
  suwak przed/po pokazuje stronę ze spadem wystającą poza format.
- **Wymiar wydruku:**
  - Gdy wymiar się zgadza: „Zatwierdź wymiar" i link „popraw kadr", który odsłania suwaki.
  - Gdy się nie zgadza, suwaki są widoczne od razu:
    - wielkość w %, ze skrótami „rozmiar pliku", „wypełnij format", „cały projekt",
    - zwinięta skala projektu 1:10 / 1:1 / 10:1, z podpowiedzią przy złej skali,
    - przesunięcie w poziomie i w pionie,
    - tło z krawędzi albo odbicie lustrzane,
    - „pokaż tylko to, co się wydrukuje".
  - Podgląd pokazuje format (zielona ramka) z projektem pod nim, razem z podglądem
    dołożonego tła. Podgląd tła zgadza się z plikiem wynikowym — sprawdzone na zrzutach.
  - Obraz (raster): tylko informacja i „Rozumiem, idę dalej", bo obrazu nie skalujemy.
- **Cofnij** przy każdej poprawce. Przy decyzji „zostaw jak jest" ten sam przycisk to
  „Zmień decyzję". Cofnięcie cofa też kroki zrobione po nim — program o to pyta i je
  wymienia.
- Zmiana strony, produktu albo roli zdejmuje wszystkie poprawki (z pytaniem).
- **Suwak główny** pod podglądem („przed poprawkami ↔ po poprawkach") pojawia się, gdy po
  ostatniej zmianie wymiaru lub spadów są jeszcze inne poprawki.

**Dopisane po uwagach Tomasza (24.09):**

- **Szablon przykryty grafiką.** Program sprawdza, czy znaleziony szablon w ogóle widać
  (`frames.visible`). Robi to tak:
  - renderuje stronę dwa razy: raz z szablonem, raz bez niego (MuPDF, 2000 px dłuższy bok);
  - liczy piksele, które różnią się o więcej niż 24 poziomy;
  - jeśli jest ich mniej niż 40, szablon jest przykryty.

  Wtedy rozdział jest od razu zamknięty z napisem „przykryty — nie drukuje się". Zostaje
  tylko cichy przycisk „Usuń mimo to”.
  - `adWall_Vario_Prosta_Light_400` → różnica 0 pikseli, szablon przykryty.
  - `PRINT_CHECKER_TEST_100x200_SZABLON_PASERY` → około 72 000 pikseli, szablon widoczny.
  - Linia włosowa (0,25 pt) na stronie 5 m też wychodzi wyraźnie: MuPDF rysuje ją na co
    najmniej 1 px.
  - Sprawdzenie trwa poniżej 1 s i robi się tylko wtedy, gdy szablon został znaleziony.
- **Podmiana pliku.** Gdy wgrywasz inny plik, a coś już zostało zrobione z obecnym, program
  pyta: „Wgrać inny plik?”. W pytaniu wymienia, co przepadnie:
  - wybór strony, produktu i roli;
  - nałożone poprawki;
  - decyzje w rozdziałach.

  „Zostaw obecny” niczego nie rusza. Świeżo wgrany plik, z którym nic jeszcze nie zrobiono,
  podmienia się bez pytania.

## Etap 3 — kolory, overprint, fonty, spłaszczenie

Rozdziały idą po wymiarze, każdy dopiero po domknięciu poprzedniego:
kolory → overprint → fonty → spłaszczenie. Każdy działa tak samo:
- fakty o stronie (analiza ostatniej wersji pliku),
- jedno zdanie, co jest nie tak,
- przycisk poprawki i „zostaw jak jest”,
- po poprawce: „Cofnij” i suwak przed/po.

Gdy nie ma czego poprawiać, rozdział od razu jest zamknięty (np. „Kolory są w CMYK —
w porządku”). Przy obrazie (JPG/PNG/TIFF) są tylko kolory. Overprintu, fontów ani
przezroczystości obraz nie ma, więc tych rozdziałów nie widać.

**Kolory**
- Kiedy rozdział się zgłasza: na stronie jest RGB, Lab, kolory dodatkowe (PANTONE, złoto,
  Registration…) albo nieznana przestrzeń. Gray obok CMYK jest w porządku.
- „Pokaż, jak wydrukuje” włącza symulację druku. Suwak „ekran ↔ druk” pokazuje ten sam plik
  na ekranie i z drukarki.
- „Zamień na CMYK”:
  - RGB jako sRGB, profil FOGRA39, intencja relatywna + BPC;
  - kolory dodatkowe idą przez swoją alternatywę;
  - CMYK zostaje nietknięty. Gdy są same spoty, jest szybka ścieżka i wartości CMYK zostają bez zmian.
- Profil (zwinięty): Coated FOGRA39 (domyślnie) / zostaw profil z pliku (tylko gdy plik ma
  profil CMYK) / bez profilu.
- Obraz RGB → CMYK przez ImageCms:
  - JPG zostaje JPG-iem (jakość 95), reszta zapisuje się jako TIFF bez strat;
  - przezroczystość ląduje na białym, DPI zostaje.

**Overprint**
- Symulacja jak przy kolorach. „Wyłącz overprint” zeruje /OP i /op we wszystkich stanach
  graficznych.
- Suwak przed/po pokazuje obie strony Z symulacją overprintu — bez niej wyglądają tak samo.
- Po naprawie przycisk symulacji znika.

**Fonty**
- „Zamień na krzywe” używa Ghostscripta z `-dNoOutputFonts`. Nieosadzone fonty program
  bierze po kolei:
  1. Google Fonts (fontfix);
  2. fonty systemu;
  3. jeśli nigdzie ich nie ma — odmowa z instrukcją. Kroju zastępczego nie ma nigdy
     (sprawdzone na spreparowanym pliku z nieistniejącym fontem).
- Po zamianie sprawdzamy, czy na stronie nie zostały fonty.

**Spłaszczenie**
- Rozdział zgłasza się tylko wtedy, gdy jest prawdziwa przezroczystość:
  - półprzezroczystość,
  - tryby mieszania,
  - maski,
  - obrazy z przezroczystym tłem.

  Sama „grupa przezroczystości” strony (Illustrator dodaje ją zawsze) się nie liczy.
- Bez przezroczystości rozdział jest zamknięty („niepotrzebne”), zostaje tylko cichy
  przycisk „Spłaszcz mimo to”.
- Przed kliknięciem program mówi, co wyjdzie, np. „jeden obraz CMYK 5994 × 11 894 px
  (150 ppi na wydruku)”.
- Rozdzielczość jak wcześniej: 300 / 200 / 150 / 120 ppi wg wielkości wydruku, sufit
  400 Mpx. Vario 600 w 1:10: 29102 × 10961 px w 8 s.

**Co się zmieniło w działaniu wobec starej wersji**

1. **Konwersja do CMYK naprawdę idzie przez FOGRA39.** Sprawdziłem stary sposób na próbniku.
   Ghostscript przy zapisie PDF-a pomija podany profil (`-sOutputICCProfile`) i przelicza
   przez swój wbudowany profil CMYK. Przykład — szarość 200/200/200:

   | Sposób | Wynik CMYK |
   |---|---|
   | stary program | 52/43/44/0 |
   | Photoshop (littleCMS, FOGRA39) | 67/48/52/0 |

   To samo opisali inni przy wersji 9.27, więc raczej nie jest to tylko przypadek wersji
   z sandboxa. Obejście:
   - kopia katalogu profili Ghostscripta z podmienionym `default_cmyk.icc`;
   - na Windowsie katalog `iccprofiles` jest obok `bin` (sprawdzone:
     `C:\Program Files\gs\gs10.07.1\iccprofiles`).

   Teraz wyniki zgadzają się z littleCMS co do ±1/255:
   - wektory: 206/0/221/17 wobec 206/0/222/18;
   - obrazy: średnio 0,15/255.

   Symulacja druku pokazuje dokładnie wynik konwersji (średnio 0,16/255).
2. **Obrazy przy konwersji nie są kompresowane od nowa stratnie.** Wcześniej Ghostscript
   zapisywał je ponownie jako JPEG i było to widać na drobnych liniach. Teraz Flate, bez strat.
3. **Symulacja kolorów nie nakłada już overprintu.** Na urządzeniu CMYK Ghostscript domyślnie
   go włącza: żółte koło na cyjanie wychodziło zielone w symulacji samych kolorów. Teraz
   overprint widać tylko w symulacji overprintu.
4. **Obraz CMYK na ekranie z kompensacją punktu czerni.** Tak samo jak symulacja: wcześniej
   obraz po konwersji wyglądał jaśniej niż jego symulacja (średnio 8,7/255, teraz 0,2/255).
5. **Ghostscript przepisuje tylko wybraną stronę.** Wynik jest wklejany w kopię pliku, więc:
   - reszta pliku i deklaracja profilu zostają bit w bit;
   - brakujący font na innej stronie nie blokuje pracy.
6. **Fakty o pliku (analiza) liczone dla wybranej strony**, nie całego PDF-a.
7. **Poprawka błędu z etapu 2.** Przy produkcie spoza listy (bez wytycznych) wektorowe ramki
   szablonu były opisywane jako „wtopione w obraz”. Teraz linie na obrazie strony sprawdzamy
   tylko wtedy, gdy nie tłumaczą ich ramki wektorowe.
8. **Obraz, którego wymiar się nie zgadza**, po „Rozumiem” ma w nagłówku „obraz bez zmian”,
   a nie „zgadza się”.

**Etap 3 — co sprawdzić**
- `PRINT_CHECKER_TEST_100x200_SZABLON_PASERY`:
  - kolory: symulacja → neonowa zieleń blednie, koło zostaje żółte;
  - overprint: symulacja → koło zielone, „BIAŁY OP” znika; naprawa przywraca wygląd z ekranu;
  - fonty → krzywe; spłaszczenie → jeden obraz.
- `fonty.pdf`: kolory i overprint zamknięte od razu, fonty → krzywe, spłaszczenie „niepotrzebne”.
- JPG: tylko rozdział Kolory, wynik to CMYK JPG.
- Cofnięcie kolorów, gdy fonty są już na krzywych → pytanie wymienia późniejsze kroki.
- Profil „bez profilu” → plik bez deklaracji; „zostaw z pliku” pojawia się tylko przy pliku z profilem.

**Poprawki po pierwszych uwagach Tomasza do etapu 3 (24.09)**

1. **Przyciski.** „Pokaż, jak wydrukuje” stoi pierwszy od lewej, potem przycisk poprawki.
   „Zostaw jak jest” (i inne pominięcia we wszystkich rozdziałach) to teraz przycisk, nie link.
2. **„Fonty na krzywe” jakby pogrubiały litery.** Przyczyną nie była poprawka, tylko podgląd.
   - Kształt liter zostaje identyczny: przy 2400 dpi krzywe/font = 0,998.
   - Ghostscript w rozdzielczości podglądu rysuje litery z FONTU niedokładnie: przy 120 ppi
     o 11 % za cienko, przy 300 ppi o 6 % za grubo.
   - Krzywe rysuje co do 0,5 %.
   - Nie pomogły opcje -dGridFitTT, -dAlignToPixels, -dNOCACHE, setcachelimit ani
     -dDisableFAPI.
   - Drukarnia rysuje w ~1200 dpi, gdzie tego problemu nie ma.

   Rozwiązanie: podgląd rysuje stronę z tekstem zamienionym na krzywe (`render.text_as_curves`).
   Tę kopię robi się tylko do podglądu, raz na wersję i stronę (~1 s), a plik się nie zmienia.
   Teraz podgląd przed i po „krzywych” różni się średnio o 0,3/255.
3. **Raster wyglądał inaczej po „fontach na krzywe”.** Ghostscript przy każdym zapisie PDF-a
   kodował obrazy bezstratne od nowa jako JPEG — stąd kolorowe obwódki na rastrze 96 px.
   Teraz wszystkie przebiegi pdfwrite mają `gs.PDFWRITE_KEEP_IMAGES`: bez zmniejszania i bez
   stratnej kompresji. Po zamianie na krzywe obrazy zostają identyczne (różnica 0).
4. **Symulacja overprintu zmieniała kolory całej strony i grubość liter.** Trzy przyczyny:
   - symulacja szła na urządzeniu RGB — Ghostscript mieszał kolory w swojej przestrzeni;
   - ekran i druk różnią się też poza overprintem: czerń K100 drukuje się jako grafit, a
     przezroczystość miesza się w CMYK;
   - przy dużej stronie symulacja szła bez wygładzania, z nadpróbkowaniem.

   Teraz:
   - obie symulacje liczą się na urządzeniu CMYK FOGRA39;
   - suwak overprintu porównuje „druk bez overprintu ↔ druk z overprintem”;
   - obie strony suwaka mają tę samą ścieżkę wygładzania.

   Na PRINT_CHECKER_TEST zmienia się wyłącznie to, co jest nadrukiem: koło, „BIAŁY OP”, linia
   (0,5 % strony).
5. Kolejność rozdziałów bez zmian. Przestawienie fontów przed overprint (propozycja Tomasza)
   nie było potrzebne — przyczyna leżała w renderze, nie w kolejności.

**Wymiar — poprawki po uwagach Tomasza (24.09, po etapie 3)**

1. Nie ma już pola „pokaż tylko to, co się wydrukuje”. Podgląd zawsze pokazuje też część
   projektu poza formatem (przyciemnioną).
2. **Przesunięcie w poziomie i pionie**
   - **Zakres.** Suwak przesuwa projekt aż do przeciwnej krawędzi formatu: prawa krawędź
     projektu może dojść do lewej krawędzi formatu i odwrotnie.
   - **Skąd było „zacinanie”.** Przesunięcie liczyło się jako ułamek wolnego miejsca
     `(format − projekt) / 2`. Gdy projekt miał prawie szerokość formatu, zakres ruchu spadał
     prawie do zera. Gdy był większy od formatu, suwak jeździł odwrotnie niż opis.
   - **Jak jest teraz.** Przesunięcie to milimetry od środka (`dx_mm` / `dy_mm`, a w
     `steps.place_rect` zakres ±(format + projekt) / 2).
   - **Przyciąganie.** Suwak przyciąga do środka i do wyrównania krawędzi projektu z krawędzią
     formatu (1,5 % zakresu). Opis nad suwakiem mówi wtedy „równo z lewą krawędzią”, a poza
     tymi miejscami podaje odległość, np. „149 mm w prawo” (w mm wydruku).
   - **Dwuklik** na suwaku ustawia środek.
   - **Opis pod suwakami.** „Przycięte” i „puste pasy” liczą się z faktycznego nakładania się
     projektu i formatu (`_span`) — w przeglądarce i na serwerze tak samo. Sprawdzone: 50 %,
     skrajnie w prawo → przycięte 490 mm, puste 1000 × 975 mm, identycznie w pliku wynikowym.

**Kolejne uwagi Tomasza (24.09, 15:47)**

1. **Tło na marginesach** to teraz trzy przyciski obok siebie, jeden aktywny: „puste / tło z
   krawędzi / odbicie lustrzane”. Wcześniej było pole zaznaczenia i lista. Widać je tylko wtedy,
   gdy projekt zostawia puste pasy.
2. **Profil kolorów** to trzy przyciski: „FOGRA39 (zalecany) / z pliku / bez profilu”, widoczne
   od razu, a nie w zwiniętej liście. „Z pliku” pojawia się tylko wtedy, gdy plik ma profil CMYK;
   jego nazwa jest w dymku.
3. **Usunięty pasek pod podglądem** („przed poprawkami ↔ po poprawkach”). Pokazywał plik, a nie
   wydruk: bez overprintu i bez kolorów z drukarki. Wróci na końcu jako symulacja wydruku przed
   i po wszystkich poprawkach, z overprintem i kolorami z drukarki. Suwaki przed/po w
   rozdziałach zostają.
4. **„Zostaw jak jest” w kolorach i overprincie przełącza podgląd na wydruk:**
   - zostawione kolory → symulacja druku kolorów (`pr`);
   - zostawiony overprint → wydruk z overprintem (`op`, na urządzeniu CMYK);
   - `main.js printFlags()` — dotyczy całego podglądu i wszystkich dalszych rozdziałów;
   - rozdział mówi to wprost („Podgląd pokazuje teraz, jak wyjdą z drukarki”);
   - „Zmień decyzję” wraca do zwykłego podglądu.

   Inaczej użytkownik mógłby myśleć, że wydruk wyjdzie tak, jak widzi na ekranie.

**Jeden suwak w panelu (24.09, 16:15).**
- Widoczny jest tylko najświeższy suwak, czyli ostatni w panelu. Gdy w Overprincie włączysz
  symulację, suwak z Kolorów znika; po naprawie overprintu zostaje tylko jego suwak przed/po.
- Porównanie z suwaka, który właśnie się schował, nie zostaje na podglądzie (`main.js`, pętla
  rysowania).

**Kolory i overprint — wybór w rzędach (24.09, 16:27).** Każdy przycisk jest biały, a wybrany
robi się niebieski. Rozdział zamyka się dopiero, gdy w każdym rzędzie coś wybrano. Ostatni rząd
to zawsze „Pokaż, jak wydrukuje” — nie da się przejść dalej bez obejrzenia wydruku.

Kolory:

| Rząd | Po wyborze „Zamień na CMYK” | Po wyborze „Zostaw jak jest” |
|---|---|---|
| 1 | Zamień na CMYK / Zostaw jak jest | Zamień na CMYK / Zostaw jak jest |
| 2 | profil: FOGRA39 (zalecany) / Z pliku / Bez profilu — wybór profilu od razu uruchamia zamianę | Pokaż, jak wydrukuje |
| 3 | Pokaż, jak wydrukuje (pojawia się, gdy zamiana gotowa) | — |

- „Z pliku” jest tylko wtedy, gdy plik miał swój profil CMYK przed zamianą.
- Inny profil po zamianie = zamiana od nowa.
- Po „Pokaż”:
  - przy zamianie: suwak ekran ↔ druk (przed/po zamianie);
  - przy zostawieniu: suwak symulacji, a cały dalszy podgląd pokazuje druk.
- Rozdział zostaje rozwinięty, żeby suwak był widoczny.

Overprint:
- Rząd 1: Wyłącz overprint / Zostaw jak jest. „Wyłącz” od razu nakłada poprawkę.
- Rząd 2: Pokaż, jak wydrukuje.
- Suwaki jak w kolorach: przy naprawie „z overprintem ↔ bez”, przy zostawieniu symulacja.

Zmiana wyboru w pierwszym rzędzie cofa poprawkę albo decyzję. Gdy po niej zrobiono coś jeszcze,
program najpierw pyta. Przycisków „Cofnij” w tych rozdziałach już nie ma — zastępuje je pierwszy
rząd.

Kod: `print.js` (`choice`, `setAct`, `setSeen`), `S.choice`, `state.settledByChoice`.

**Rozwijanie rozdziałów (24.09, 16:32).**
- Automatycznie rozwinięte są dwa rozdziały: bieżący i najbliższy wcześniejszy, w którym jest
  suwak. Reszta się zwija.
- Dzieje się to tylko przy przejściu do innego rozdziału (`main.js`, `lastAuto`), więc ręcznie
  da się rozwinąć każdy.

**Fonty i spłaszczenie — ten sam wybór w rzędach (24.09, 16:37).**
- Rząd 1: „Zamień na krzywe” / „Zostaw jak jest” (albo „Spłaszcz projekt” / „Zostaw jak jest”).
  Poprawka nakłada się od razu po kliknięciu.
- Rząd 2: „Pokaż, jak wydrukuje”.
- Suwaki:
  - po poprawce — przed ↔ po (przy spłaszczeniu z symulacją overprintu);
  - po zostawieniu — ekran ↔ pełny druk (kolory z drukarki + overprint), `S.sim = "print"`.
- Spłaszczenie bez przezroczystości: rozdział od razu zamknięty („niepotrzebne”), ale rzędy są
  i można spłaszczyć mimo to.
- Fonty bez tekstu: zamknięte, bez rzędów.
- Wszystkie cztery rozdziały mają jedną logikę (`print.js`: `choice`, `setAct`, `setSeen`,
  `rowsFor`), a `simLayers()` zwraca flagi obu warstw suwaka symulacji.

## Etap 4 — jakość wydruku, pobieranie, sprzątanie

**Pasek „pełna jakość”** (uwaga Tomasza 24.09):
- stoi zaraz na prawo od „Podgląd szablonu” i jest większy: niebieska ramka, pasek 110 px,
  pogrubiony napis;
- nie zasłania lupek, bo leży w prawej części paska narzędzi — przycisk szablonu przesuwa się
  w lewo, gdy robi się ciasno.

**Jakość wydruku** (`quality.py`, `js/quality.js`)
- Liczy ją ta sama mapa detalu co wcześniej (`detailmap.py`, metoda bez zmian):
  - każdy obraz PDF-a w natywnych pikselach, rzutowany na wszystkie swoje miejsca;
  - raster — cały plik.
- Oceniamy **ostatnią wersję przed spłaszczeniem**. Po spłaszczeniu cała strona to jeden obraz
  i jego „ppi” nic nie mówi o zdjęciach w środku. Wcześniejsze poprawki nie zmieniają pikseli
  obrazów, a dopasowanie wymiaru jest już w położeniu obrazów — więc skala to tylko skala
  wytycznych.
- Werdykt składa serwer (wcześniej robiła to przeglądarka):
  - ok — wszystko ≥ 120 ppi;
  - do obejrzenia — pikseli dość, ale brak detalu;
  - za mała rozdzielczość — za mało pikseli, trzeba wymienić obraz;
  - sam wektor.

  Dochodzą grupy do listy: ten sam obraz albo te same fakty.
- Rozdział startuje sam, z postępem w rozdziale.
- Przy problemach trzeba kliknąć „Pokaż na podglądzie (N)” — ten sam wzór co „Pokaż, jak
  wydrukuje”. Na podglądzie pojawia się pasek „Miejsce 1 z N · …” z ‹ › (też strzałki na
  klawiaturze) i ×/Esc. Każde miejsce pokazuje się w rzeczywistej wielkości wydruku, z ramką,
  która nie znika.
- „Lista miejsc” jest zwinięta pod przyciskiem.
- Przy pliku 1:10 program przypomina, że w pliku trzeba 1200 ppi.

**Pobierz plik do druku**
- Pobierasz ostatnią wersję, zawsze **jedną stronę** — z pliku wielostronicowego wycinana jest
  wybrana strona razem z profilem kolorystycznym.
- Obraz zostaje obrazem (JPG/TIFF).
- Nazwa: produkt + rola, bez wymiarów; spoza listy — „Wydruk niestandardowy”.
- Nad przyciskiem krótkie podsumowanie: co zrobiono, co zostawiono i która strona. Gdy obrazy
  są za małe, jest ostrzeżenie, ale pobrać można.

**Sprzątanie**
- `analyze.py`:
  - usunięta stara „efektywna rozdzielczość” (kafelki, okna, `_effective_*`, `analyze_svg` —
    SVG i tak jest zamieniany na PDF), 981 → 619 linii;
  - fakty o kolorach, fontach, overprincie, przezroczystości i obrazach są identyczne na
    5 plikach przykładowych;
  - analiza JPG jest szybsza (0,07 s → 0,01 s), bo nie liczy już detalu drugi raz.
- `detailmap.py`: usunięta nieużywana droga „PDF z renderu strony” (`_pdf_bands`,
  `_boxes_to_mask`, `_mask_rects`) i `block_factors`, 1010 → 895 linii. Wyniki identyczne na
  PRINT_CHECKER_TEST (3 miejsca), Vario 600 1:10 (22), Vario Light 400 (6) i JPG.

**Zamiana wersji** (`app_nowy` → `app`) — dopiero gdy Tomasz sprawdzi etap 4. Stara wersja zostaje
w `_kopia_2026-09-24`.

**Etap 4 — co sprawdzić**
- PRINT_CHECKER_TEST (produkt spoza listy 1000 × 2000):
  - jakość „za mała rozdzielczość”, 3 obrazy, najgorszy ≈ 9 ppi;
  - „Pokaż na podglądzie” → miejsca w rzeczywistej wielkości, ‹ › i Esc;
  - pobierz → „Wydruk niestandardowy.pdf”, jedna strona.
- JPG: jakość 13 ppi (cały obraz), pobierz → .jpg.
- `fonty.pdf`: „Projekt jest w wektorze”, pobieranie od razu dostępne.
- Z produktem z listy: nazwa pliku = produkt + rola.

**Przezroczystość: ekran a druk (pytanie Tomasza 24.09, 16:58).** Pytanie brzmiało: czy różnica
w symulacji przy „Zostaw jak jest” jest prawdziwa, skoro po zamianie na CMYK różnicy nie widać?

Tak, jest prawdziwa. Strona PRINT_CHECKER_TEST nie deklaruje, w jakich kolorach mieszać
przezroczystość (brak `/Group /CS`). Wtedy drukarnia miesza ją w swoich kolorach (CMYK), a ekran —
w RGB.

Zmierzone na nałożeniu czerwień × cyjan (tryb Multiply, krycie 42 %):

| Wersja pliku | Ekran | Druk |
|---|---|---|
| oryginał | 155 / 45 / 45 | 166 / 55 / 54 |
| po zamianie na CMYK | 155 / 45 / 45 | 166 / 55 / 55 |

Zamiana nic tu nie zmienia: w druku wychodzi to samo. Zwykły podgląd po zamianie pokazywał
jednak ekran, więc wyglądało, jakby różnicy nie było.

Zmiana: **od domknięcia rozdziału „Kolory” (zamiana albo „Zostaw jak jest”) cały podgląd
rysuje się jak wydruk** (`main.js printFlags`: `pr = colorSettled()`). To samo dotyczy czerni
z samej farby K: w druku to grafit, nie czysta czerń. Suwak kolorów po zamianie porównuje
ekran sprzed zamiany z wydrukiem po niej.

**Spłaszczenie pogrubiało tekst (Tomasz 24.09, 17:02).**
- Przyczyna: Ghostscript domyślnie pogrubia każdy kształt o ułamek piksela („fill adjust”). Przy
  spłaszczaniu do 150 ppi zapisywało się to na stałe w pliku.
- Zmierzone na drobnym tekście względem idealnego obrazu (1200 dpi uśrednione do 150):

  | Wariant | Farby względem ideału | Błąd na krawędziach (p99) |
  |---|---|---|
  | było | 103,6 % | 67/255 |
  | bez fill adjust | 99,9 % | 38/255 |

- JPEG q90 wobec zapisu bez strat: prawie bez różnicy (błąd na krawędziach 38 wobec 39), więc
  zostaje q90.
- Zmiana: spłaszczenie renderuje z `gs.PREVIEW_PRE` (`0 0 .setfilladjust2`), jak podgląd.
- Ostrość spłaszczonego tekstu zależy dalej od rozdzielczości (150 ppi przy wydruku 2 m) — to
  cena spłaszczenia opisana w pomocy.

**Jakość i akceptacja (Tomasz 24.09, 17:29).**
1. **„Jakość wydruku” zostaje rozwinięta do końca.** Automatyczne zwijanie (`lastAuto`) pomija ten
   rozdział.
2. **„Pokaż na podglądzie” to włącznik.** Pierwszy klik pokazuje ramki i pasek miejsc (przycisk
   niebieski), drugi je chowa (przycisk biały). Zamknięcie paska × lub Esc też zmienia przycisk
   na biały. Pierwszy klik domyka rozdział.
3. **Nowy rozdział „Akceptacja pliku”** (między jakością a pobieraniem):
   - „Pokaż wydruk przed i po” włącza suwak (`S.sim = "final"`). Porównuje wydruk bez poprawek
     od rozdziału Kolory z wydrukiem po nich — oba jako druk (kolory z drukarki + overprint).
   - „Bez poprawek” to ostatnia wersja po szablonie, spadach i wymiarze.
   - Suwak startuje od „przed”.
   - Potem pojawia się „Akceptuję plik”. Akceptacja dotyczy konkretnej wersji — każda zmiana
     pliku ją zdejmuje. Dopiero po niej jest „Pobierz plik do druku”.

**Rozwijanie rozdziałów — jedna reguła dla wszystkich (Tomasz 24.09).**
- Automatycznie rozwinięte są ZAWSZE dwa ostatnie widoczne rozdziały: bieżący i ten tuż przed nim.
  Reszta się zwija. Dotyczy wszystkich rozdziałów, od produktu po pobieranie.
- Zastępuje wcześniejsze reguły: „najbliższy wcześniejszy z suwakiem” i wyjątek „Jakość zostaje
  rozwinięta do końca”. Jakość jest teraz rozwinięta, póki jest jednym z dwóch ostatnich
  (czyli do akceptacji pliku włącznie).
- Nadal tylko przy przejściu do innego rozdziału (`main.js`, `lastAuto`), więc ręcznie da się
  rozwinąć każdy.
- Sprawdzone w przeglądarce na każdym etapie (produkt → pobieranie): rozwinięte = dwa ostatnie.

## Wersja 0.1 — adChecker (24.09)

Tomasz zaakceptował etap 4. Ten stan to **wersja 0.1**, program nazywa się **adChecker**.

- **Zamiana:** stara `app/` przeniesiona do `_kopia_2026-09-24/app_stary/`; zawartość `app_nowy/`
  skopiowana do `app/` (bez `work/`), port 5000. `app_nowy/` był zablokowany przez działający
  serwer — po jego zamknięciu przeniesiony do `_kopia_2026-09-24/app_nowy_robocza/`. Od teraz pracujemy w `app/`.
- **Kopia wersji:** `wersje/adChecker_0.1.zip` — sam kod i `data/` (bez `work/` i `__pycache__`).
- **Nazwa:** tytuł okna, nagłówek, okno `run.bat`, komunikaty w konsoli (`[adChecker]`),
  User-Agent `adChecker/0.1`. Klucze `localStorage` zostały `adcheck.*`, żeby nie zgubić
  kalibracji i ustawień.
- **Numer wersji:** `VERSION = "0.1"` w `server.py` (wypisywany przy starcie) i znaczek „v0.1”
  w nagłówku (`index.html`). Przy kolejnej wersji zmienić oba miejsca.
- **Ikona:** z sygnetu Tomasza (`sygnet.pdf`) — białe „a.” na niebieskim (#2563eb, kolor
  akcentu programu) z zaokrąglonymi rogami.
  - `static/adchecker.svg` — favicon i logo w nagłówku; `static/favicon.png` (32 px) dla
    starszych przeglądarek.
  - `adchecker.ico` (16–256 px; przy 16–32 px sygnet większy, żeby był czytelny).
  - `utworz_skrot.bat` — tworzy na pulpicie skrót „adChecker” z tą ikoną (uruchamia `run.bat`).

Następna: **wersja 0.2 — samouczek** (dymki krok po kroku, przycisk obok „Ustawienia”).
