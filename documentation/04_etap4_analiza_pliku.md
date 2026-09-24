# Etap 4 — analiza pliku: strony, kolor, profil ICC, rozdzielczość

Data: 2026-09-03. Kontynuacja po etapie 3 (`03_etap3_podglad_100_procent.md`).

## Ustalenia z tej sesji (Tomasz)

- Program ma **zczytać z pliku**: liczbę stron, kolor (RGB / CMYK / PANTONE /
  mieszany / inne) — „dokładnie”, zawarty profil kolorystyczny oraz
  rozdzielczość (gdy całość jest wektorem — rozdzielczość nie ma znaczenia).
- Etap 4 = **fakty o pliku**, bez oceny dobrze/źle. Ocena wobec wytycznych
  (CMYK Coated FOGRA39, 120 ppi @ 1:1, bez overprintu…) to następny etap.

## Jak to działa (`app/analyze.py`, pikepdf + Pillow)

### PDF / AI
Nie patrzymy na to, co jest **zadeklarowane** w zasobach (`/Resources
/ColorSpace`) — tam Illustrator/InDesign zostawiają masę nieużywanych wpisów —
tylko na to, co jest **faktycznie użyte** w strumieniach treści. Przechodzimy
treść każdej strony i rekurencyjnie Form XObjects oraz wzorki kafelkowe,
śledząc CTM (`q`/`Q`/`cm`), i zliczamy:

| operator | co liczymy |
|---|---|
| `g`/`G`, `rg`/`RG`, `k`/`K` | DeviceGray / DeviceRGB / DeviceCMYK — wypełnienia i obrysy |
| `cs`/`CS` + `sc`/`scn`/`SC`/`SCN` | przestrzeń z zasobów: `/ICCBased` (N=1/3/4 → Gray/RGB/CMYK + nazwa profilu), `/Indexed` (→ baza), `/Separation` (spot: nazwa + przestrzeń alternatywna), `/DeviceN` (nazwy; nazwy inne niż C/M/Y/K liczone jak spoty), `/Lab`, `/CalRGB`, `/CalGray`, `/Pattern` (→ cieniowanie lub treść kafelka) |
| `sh` | `/ColorSpace` cieniowania (gradienty) |
| `Do` (Image) | przestrzeń obrazu, `/SMask`, px; **z CTM** wielkość na stronie → efektywne ppi = px / (pt/72); przy kilku umiejscowieniach bierzemy najgorsze |
| `Do` (Form) | rekurencja z `/Matrix` i własnymi `/Resources`; grupa `/Transparency` odnotowana |
| `BI` | obraz inline |
| `gs` | ExtGState: overprint (`/OP`, `/op`), krycie < 1, tryb mieszania ≠ Normal, `/SMask` |
| `Tf` | użyte fonty (nazwa, czy osadzony) — sygnał „tekst nie w krzywych” |

Profil ICC: czytamy strumień ICC i parsujemy nagłówek (przestrzeń: `RGB `/`CMYK`/`GRAY`)
oraz tag `desc` (typ `desc` lub `mluc`) → np. „Coated FOGRA39 (ISO 12647-2:2004)”,
„ISO Coated v2 (ECI)”. Output intent: `/OutputIntents` (`/S`, identyfikator,
`/Info`, profil docelowy).

Werdykt koloru = lista modeli procesowych użytych (CMYK / RGB / Gray / Lab)
+ liczba kolorów dodatkowych (z zaznaczeniem PANTONE po nazwie). Znacznik
**„mieszane”** gdy więcej niż jeden model procesowy (Gray traktujemy jako część
CMYK, nie jako „mieszane”) albo spoty obok procesu.

Uwaga techniczna: PyMuPDF `get_image_info()` zgłasza gradienty jako obrazy
(rasteryzuje je do textpage) i dekoduje obrazy (pada na >0,5 Gpx) — dlatego
obrazy liczymy z pikepdf + CTM, nie z PyMuPDF.

### Rastry (JPG/PNG/TIFF/BMP/GIF/WebP)
Pillow: tryb (RGB/RGBA/CMYK/L/P/I;16/LAB…), bity, ICC z `info['icc_profile']`
(ta sama funkcja parsująca), DPI z metadanych, liczba klatek (TIFF wielostronicowy),
kanał alfa. Rozdzielczość **na wydruku** liczona w UI: px / (rozmiar wydruku
w calach) — rozmiar wydruku z szablonu/wymiaru ręcznego/DPI (jak w etapie 3).

### SVG
Zawsze RGB, bez ICC — tak raportujemy.

## API / UI
- `GET /api/jobs/<id>/analysis` — wynik cache'owany w jobie.
- Panel **„Informacje o pliku”** pod podglądem, ładowany zaraz po wgraniu:
  Strony/typ (wektor / wektor+raster / raster, program tworzący), Kolor
  (werdykt, znaczniki CMYK/RGB/Gray/Spot z liczbą użyć wg rodzaju, lista spotów
  z przestrzenią alternatywną), Profil kolorystyczny (profile ICC z liczbą użyć,
  output intent), Rozdzielczość (min. ppi na wydruku — przy skali 1:10 ppi w
  pliku ÷ 10 — i tabela najgorszych obrazów: px, mm na stronie, ppi, kolor,
  indeksowany, maska), Pozostałe (overprint, przezroczystość, fonty).
- Panel przelicza się przy zmianie szablonu/skali/wymiaru ręcznego.

## Testy na przykładach

| plik | wynik |
|---|---|
| `1878_…_brak_uwagi_o_spot.pdf` | CMYK (ISO Coated v2 (ECI), output intent GTS_PDFX) + spot **GOLD 2**; 92 obrazów, min. 100 ppi; overprint 2× → „mieszane” |
| `1815_czcionki.pdf` | tylko wektor, CMYK (Coated FOGRA39), font **Industry-Bold** w tekście (nie w krzywych) |
| `1824_strony_wymiar_cmyk.pdf` | CMYK (Indexed/DeviceCMYK), 1 obraz 46009×19322 px = 300 ppi, bez ICC |
| `Wydruk_adWall_Vario_Prosta_600_43…pdf` (1:10) | CMYK, 1 mały obraz 302 ppi w pliku = **30 ppi na wydruku**, overprint 34×, SMask |
| `adWall…SOFT_BAG…pdf` (poprawny) | CMYK + Gray (nie „mieszane”), 3 obrazy, najgorszy 73 ppi, przezroczystości |
| `adFrame_Smart_100x250_1.pdf` | CMYK, 1 obraz 4795×11872 = 120 ppi |
| `1788264646af029f_q1.jpg` | RGB bez ICC, 9 dpi w metadanych → 9 ppi na wydruku |

Czas analizy: 0,0–1,5 s (60 MB PDF), bez dekodowania obrazów.

## Do sprawdzenia u Tomasza
1. Plik z kolorem PANTONE (Separation „PANTONE 485 C”) — czy nazwa i znacznik PANTONE się pokazują.
2. TIFF CMYK z profilem — tryb i nazwa profilu.
3. `.ai` z Illustratora.

## Pomysły / otwarte
- Fonty: osobny etap (lista + „zamień na krzywe” jako poprawka).
- DeviceN z nazwami procesowymi (np. „All”) — na razie liczone jak spot tylko dla nazw innych niż C/M/Y/K/None/All.
- Ocena wobec wytycznych (etap 5): CMYK/FOGRA39, ppi ≥ 120 na wydruku, brak overprintu, brak spotów, brak fontów, 1 strona, wymiar vs szablon, skala.

## Uzupełnienie: „realny detal” — efektywna rozdzielczość rastra (2026-09-03)

### Skąd wzięło się pytanie
Tomasz porównał nasz wynik z Illustratorem dla `Wydruk_adWall_Vario_Prosta_600_43…pdf`:
Illustrator pokazywał obraz 661×371 px / 1501 ppi, program 133×75 px / 302 ppi.
W PDF-ie są **tylko dwa** obiekty obrazu, oba 133×75 (obraz + maska) — plik
zapisano z domyślną kompresją Illustratora (próbkowanie w dół do 300 ppi).
Illustrator otwierając PDF czyta swoje prywatne dane edycyjne
(`/PieceInfo/Illustrator` na stronie), gdzie jest oryginał 661×371; RIP plotera
czyta treść PDF → drukuje 133×75 px na 112×63 mm = **30 ppi**. Nasz wynik jest
tym „drukowym”. Wniosek do dokumentacji: **ppi liczymy z rzeczywistej liczby
pikseli obiektu i jego macierzy umiejscowienia, nigdy z metadanych.**

Przy okazji: jeden obraz użyty 22 razy → tabela pokazuje „(×22 użyć)”
(`placement_count`), wcześniej pokazywała tylko 3 pierwsze umiejscowienia.

### Metoda
ppi mówi tylko, ile jest pikseli — nie, czy jest w nich detal (logo 100 px
powiększone w Photoshopie do 1000 px ma „300 ppi” i jest rozmyte). Dlatego
`analyze.effective_factor()`:

1. obraz → skala szarości, środek do 1500×1500 px;
2. dla f ∈ {1,5; 2; 3; 4; 6; 8}: zmniejsz f× (Lanczos), powiększ z powrotem
   (bicubic), policz błąd średniokwadratowy E(f);
3. normalizacja: E(f) / E(8) — metryka niezależna od kontrastu i treści;
4. **efektywny współczynnik** = największe f ≥ 2, dla którego E(f)/E(8) < 0,045
   (obraz zmniejszony f× odtwarza się praktycznie bez straty → nie ma detalu
   drobniejszego niż f px → był powiększany ~f×). Realne ppi = ppi / f.

Testy na wycinku zdjęcia z `adFrame_Smart…`: natywne → 1; powiększone
bicubic 2×/3×/4× → 2/3/4; JPEG q20 i q50 → 1 (kompresja nie jest „powiększeniem”;
reaguje tylko f=1,5, więc 1,5 jest ignorowane); obraz jednolity → „flat”.
Ograniczenie: powiększenie „najbliższym sąsiadem” (klocki) nie jest wykrywane,
bo ma ostre krawędzie — to wygląda pikselowato także w podglądzie 100 %, więc
widać gołym okiem.

Wynik na przykładach: `1878_…` — tło 11891×9055 px = 100 ppi, ale realny detal
≈ **3× mniejszy → ~33 ppi** (podgląd potwierdza: miękkie plamy bez detalu
pikselowego); małe obrazy 150 ppi — natywne. `1824_…` 46009×19322 — natywne.
`adFrame_Smart` — natywne 120 ppi.

### Implementacja
- Sprawdzane są tylko najgorsze obrazy (do 12, wg ppi). Obrazy ≤ 30 Mpx są
  dekodowane bezpośrednio (`pymupdf.Pixmap(doc, xref)`); większe — renderowany
  jest wycinek strony 1500×1500 px w natywnej rozdzielczości obrazu
  (`preview.render_region_png`, z fallbackiem Ghostscript), z prostokąta
  umiejscowienia z CTM (przeliczenie układu PDF dół-góra → MuPDF).
- Rastry (JPG/TIFF…): to samo na pliku (środek 1500 px).
- Wynik w JSON: `effective: {factor, ppi, curve, flat, source}`,
  `resolution.min_effective_ppi`; w UI kolumna **„realny detal”** („OK
  (natywny)”, „~3× powiększony ≈ 33 ppi”, „jednolity”) i ostrzeżenie nad tabelą.
- Nowa zależność: `numpy`.

## Uzupełnienie 2: opis dla laika + „pokaż na podglądzie” (2026-09-03)

Tomasz: sekcja o rozdzielczości była nieczytelna dla laika; chce prostego
opisu i przycisku, który powiększa podgląd do miejsc słabej jakości.

### Ocena słowna (`qualityGrade` w app.js) — wg **realnego** ppi na wydruku
(nominalne ppi ÷ współczynnik powiększenia, ÷10 przy skali 1:10):

| realne ppi na wydruku | etykieta | opis |
|---|---|---|
| ≥ 120 | **dobra** (zielona) | zgodne z wytycznymi, wydruk ostry |
| 80–120 | **na granicy** (żółta) | z bliska lekka miękkość, z normalnej odległości OK |
| 40–80 | **słaba** (czerwona) | krawędzie rozmyte/schodkowe, tekst i logo w rastrze nieczytelne z bliska |
| < 40 | **bardzo słaba** | pikselowaty/rozmyty nawet z daleka — do wymiany |

Do opisu dodana orientacyjna odległość, z której wydruk wygląda ostro:
`d [cm] ≈ 7500 / ppi` (300 ppi → 25 cm, 120 ppi → 60 cm, 30 ppi → 2,5 m) —
reguła kciuka, nie norma. Nagłówek sekcji: „Jakość rastrów (rozdzielczość)”,
w ramce: co to znaczy, najsłabszy element (px → mm na wydruku, ile razy użyty,
ile mm ma 1 piksel) i przycisk **„🔍 pokaż na podglądzie”**. Tabela: obraz [px],
na wydruku [mm] (już po ×10), ppi na wydruku, jakość (z dopiskiem
„nominalnie X ppi, ale obraz był powiększany ~N×”), kolor, 🔍.

### „Pokaż na podglądzie”
- Backend: każde umiejscowienie obrazu ma teraz `x_mm, y_mm, bw_mm, bh_mm, page`
  (od lewego-górnego rogu strony; z prostokąta CTM i `/MediaBox`). W `worst`
  zapisywane do 24 umiejscowień.
- Front: `zoomToPrintRect()` — przełącza stronę, jeśli trzeba; dobiera zoom tak,
  by obraz zajął ~70 % okna, **ale nie mniej niż 100 % rozmiaru rzeczywistego**
  (żeby było widać, jak to wyjdzie z plotera); przewija na środek; rysuje
  czerwoną przerywaną ramkę z etykietą „użycie n / N” (znika po 4 s, przy zoomie
  jest przeliczana). Kolejne kliknięcia 🔍 przy tym samym obrazie przechodzą
  po kolejnych użyciach (logo ×22). Dla plików rastrowych przycisk „pokaż w 100 %”.
- Sekcja rozdzielczości zajmuje pełną szerokość siatki (tabela nie nachodziła na
  sąsiednią kolumnę i blokowała kliknięcia).

## Poprawki UX po testach Tomasza (2026-09-03, po południu)

- Usunięta lista „szablon 1:1 (środek) / dopasowany do strony” — nakładka jest
  **zawsze 1:1, wyśrodkowana** (tryb „dopasowany” zostaje w kodzie jako
  `state.overlayMode`, ale bez UI).
- Usunięty przycisk „Surowe px” — podgląd zawsze wygładza jak RIP (backend nadal
  obsługuje `smooth=0`, gdyby kiedyś było potrzebne).
- **Okno podglądu dopasowuje wysokość do proporcji pliku** (`fitStageHeight()`
  w trybie „Dopasuj”: wysokość = szerokość × proporcje strony + margines,
  min 320 px, max wysokość ekranu − 175 px). Dla szerokich plików (banery)
  panel „Informacje o pliku” jest widoczny bez przewijania. Po powiększeniu
  wysokość zostaje taka, jaka była w „Dopasuj”.
- Jedna lupa zamiast dwóch: tylko 🔍 w wierszu tabeli obrazów; opis w ramce
  odsyła do niej.
- **Nawigator użyć obrazu**: po kliknięciu 🔍 nad podglądem pojawia się pływający
  ciemny pasek „obraz 133×75 px · użycie 2 / 22 ‹ › ×”. Strzałki (także
  klawisze ← →) przechodzą po kolejnych użyciach, × (lub Esc) zamyka. Ramka
  podświetlenia dalej znika po 4 s (Tomasz chciał to zostawić).

## Uzupełnienie 3: analiza fragmentów w spłaszczonych plikach (2026-09-03)

Pytanie Tomasza: jak to działa na spłaszczonych plikach (cała strona = jeden
raster)? Do tej pory: nie działało regionalnie — ocena „realnego detalu” była
liczona na środkowym wycinku 1500 px całego obrazu, więc wklejone powiększone
logo w ostrym tle nie było wykrywane.

Teraz `analyze.tile_analysis()`: obraz (do 120 Mpx, dekodowany w całości)
dzielony na kafelki ~512 px; dla każdego liczona jest ta sama metryka (skale
2/3/8 — mniej niż globalnie, żeby było szybciej). Kafelki jednolite
(E(8) < 12) są pomijane. Kafelki z detalem ≥ 3× mniejszym niż ich własny
„pełny” detal są flagowane, a sąsiednie sklejane w obszary (BFS po siatce) →
lista do 8 obszarów z bbox w px i w mm strony. Dla rastrów (JPG/TIFF) to samo,
bbox w ułamkach szerokości/wysokości (mm liczone w UI).

**Ważne zastrzeżenie (jest też w UI):** tak samo jak powiększony element
wychodzą obszary celowo rozmyte — tło zdjęcia, bokeh, miękkie gradienty.
To wskazówka „gdzie spojrzeć”, nie wyrok. Dlatego przycisk „Słabsze
fragmenty (N)” prowadzi przez nie w nawigatorze (fragment 1 / N), a ocena
należy do człowieka.

Test na `adFrame_Smart_100x250_1.pdf` (plik „poprawny”, 120 ppi): 207 kafelków,
145 z detalem, 12 oflagowanych → 2 obszary; największy (11 kafelków, ok.
450×440 mm na wydruku) to panel pralki — w 100 % widać, że zdjęcie produktu było
powiększane ~3× (miękkie napisy). `1878_…`: 288/321 kafelków → całe tło
powiększane. `Wydruk_adFrame_LMD…`: 0 obszarów.

Czas: adFrame_Smart (57 Mpx) ~6 s (3 s dekodowanie + 2 s kafelki), 1878
(107 Mpx) ~25 s. Obrazy > 120 Mpx: tylko globalna ocena z wycinka (bez
kafelków).

UI: ikona 🔍 zastąpiona zwykłymi przyciskami „Pokaż” / „Pokaż w 100 %” /
„Słabsze fragmenty (N)” w stylu reszty paska. Nawigator jest wspólny dla użyć
obrazu i fragmentów (licznik „użycie n / N” albo „fragment n / N”).

## Uzupełnienie 4 (2026-09-04): cały plik, nie próbki; tabela tylko z tym, co wymaga uwagi

Pytanie Tomasza: „czy program sprawdza dokładnie cały plik, czy losowe
fragmenty? Chcę cały plik” oraz „po co w tabeli obrazy z dobrą jakością?”.

**Jak było:** nominalne ppi — wszystkie obrazy; realny detal — tylko 12
obrazów o najniższym nominalnym ppi, z tego współczynnik globalny liczony na
środkowym wycinku 1500 px (kafelki całego obrazu tylko do „słabszych
fragmentów”); obrazy > 120 Mpx — jeden wycinek ze środka. Czyli NIE cały plik.

**Jak jest:**
- realny detal liczony dla **wszystkich** obrazów (poza maskami), każdy
  dekodowany w całości i badany kafelek po kafelku (`tile_analysis`, kafelki
  512 px, skale 2/3/4/8, 4 wątki). Współczynnik całego obrazu = **25. percentyl**
  współczynników kafelków z detalem (najostrzejsza ćwiartka decyduje: obraz
  powiększany ma obniżony detal wszędzie, zdjęcie z rozmytym tłem ma ostry motyw).
  Dodatkowo `share_low` = udział kafelków z detalem obniżonym ≥ 3× — UI pisze
  „brak drobnego detalu na ok. 90 % powierzchni (jak po powiększeniu ~3×)”.
- „Słabsze fragmenty” są teraz **względem obrazu**: kafelek musi mieć ≥ 3 i
  ≥ 2× współczynnik całego obrazu. Tło powiększone 3× w całości nie ma więc
  „fragmentów” (jest po prostu całe słabe — i tak to mówi wiersz tabeli), a
  wklejone logo w ostrym zdjęciu nadal wychodzi.
- obrazy > 120 Mpx (nie da się zdekodować w całości): siatka do 4×3 okien po
  1500 px renderowanych ze strony w natywnej rozdzielczości, równomiernie po
  obrazie; UI pisze wprost „zbadany w 12 oknach — za duży, by zdekodować w
  całości”. To jedyne miejsce, gdzie analiza jest próbką.
- limit czasu 150 s na etap realnego detalu (`EFF_TIME_BUDGET_S`); po nim reszta
  obrazów dostaje `skipped` i UI to pokazuje jako ostrzeżenie (nie ciche
  pominięcie). Pod tabelą zdanie o pokryciu: „Realny detal: sprawdzono 92 obrazy
  w całości (piksel po pikselu, kafelkami) — 23,5 s”.
- API: `resolution.worst` zawiera teraz wszystkie obrazy (do 400, od
  najsłabszego wg realnego ppi), `resolution.coverage = {full, windows, skipped,
  error, seconds}`, `effective.coverage = "full" | "windows"`, `effective.tiles.share_low`.
- rastry (JPG/TIFF): to samo — całość kafelkami, > 120 Mpx w oknach.

**Tabela w UI:** domyślnie tylko obrazy wymagające uwagi (realne ppi < 120,
słabsze fragmenty, niesprawdzone). Reszta jedną linią: „Pozostałe 91 obrazów:
dobra jakość (≥ 150 ppi na wydruku, realny detal sprawdzony) — nie wymagają
uwagi · pokaż wszystkie”. Obrazy jednolite („ostrość bez znaczenia”) też są
w tej reszcie.

Wynik na `1878_…`: 92 obrazy w całości, 23,5 s (13 s to samo dekodowanie
107-Mpx tła CMYK→Gray); tło: 288/321 kafelków ≥ 3× → współczynnik 3, realnie
33 ppi, 90 % powierzchni; 0 „fragmentów” (całe słabe). `adFrame_Smart`: 7,4 s,
współczynnik 1, 2 fragmenty (pralka) — jak wcześniej.

## Uzupełnienie 5 (2026-09-04): spłaszczony plik = jeden ogromny raster

Pytanie Tomasza: „a jak jest to rozwiązane, gdy cały plik to jeden obraz rastrowy
bez warstw?” — to najczęstszy przypadek w druku (baner 6000×2270 mm 1:1 przy
120–300 ppi to 300–900 Mpx), a właśnie tam uzupełnienie 4 zostawiało próbkę
(12 okien). Teraz:

- **PDF z obrazem > 120 Mpx** (nie mieści się w pamięci po dekodowaniu):
  obraz jest renderowany ze strony **pasami** w natywnej rozdzielczości
  (`render_region_png(..., max_px=…, gray=True)` — limit 3200 px zniesiony dla
  analizy, wynik w skali szarości; Ghostscript pisze surowy PGM zamiast PNG),
  pas = wielokrotność kafelka 512 px, ok. 150 Mpx na pas. Każdy pas jest
  kafelkowany w całości, kafelki wszystkich pasów składają się w jedną siatkę
  → współczynnik obrazu, „słabsze fragmenty” w mm strony, `coverage: "bands"`.
  **Pokrycie 100 %.** Potok: następny pas renderuje się w tle, gdy bieżący jest
  kafelkowany. Szybka ścieżka dla kafelków jednolitych (std < 1,5 → „flat” bez
  krzywej strat) — w banerach większość powierzchni to tło.
- **Rastry (JPG/TIFF)** do 400 Mpx dekodowane w całości i kafelkowane
  (`RASTER_MAX_DECODE_PX`); powyżej — siatka do 6×4 okien (jedyny pozostały
  przypadek próbkowania, UI pisze o tym wprost). Pillow i tak dekoduje całość,
  więc próg to kwestia RAM-u (400 Mpx RGB ≈ 1,2 GB).
- limit czasu etapu podniesiony do 300 s (`EFF_TIME_BUDGET_S`).

Test `1824_strony_wymiar_cmyk.pdf` (46009×19322 px = 889 Mpx, JPEG CMYK, przez
Ghostscript): 7 pasów, 3420 kafelków, 881 z detalem (reszta tło), wszystkie
współczynnik 1 → realnie 300 ppi, 0 fragmentów; **69 s** (z tego ~50 s to
7 dekodowań JPEG-a przez gs — nie da się zdekodować raz i trzymać: 3,5 GB).
Wcześniej 12 okien: 60 s i tylko 4 okna z detalem — czyli wolniej i próbka.
1878 (107 Mpx, całość w pamięci): 21 s; adFrame_Smart: 6 s — bez zmian wyników.

UI: „Realny detal: sprawdzono 0 obrazów w całości, 1 ogromny(e) też w całości —
pasami renderowanymi ze strony — 68,8 s”; w wierszu tabeli „(sprawdzony w
całości, w 7 pasach)”.
