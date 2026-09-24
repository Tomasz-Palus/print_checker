# 07 · Mapa detalu wydruku — jeden system oceny jakości dla każdego formatu

Data: 2026-09-04. Nowy moduł `app/detailmap.py`, endpoint `/api/jobs/<id>/detail`,
przycisk „Mapa” nad podglądem, ramka „Mapa detalu wydruku” w sekcji „Jakość rastrów”.

## Skąd się wzięło

Tomasz: „PDF też może być spłaszczony, a TIFF może mieć warstwy — czy rozszerzenie ma
znaczenie? Może lepiej jeden system?” oraz (najważniejsze): **„nie może być takiej opcji,
że przegapimy jakiś szczegół słabszej jakości — pliki muszą być sprawdzane bardzo
dokładnie”**. Dotychczasowa analiza (04) była „per obiekt obrazu w PDF” — w spłaszczonym
pliku obiektów nie ma, a kafelki 512 px uśredniały małe elementy z otoczeniem.

## Zasada

Oceniamy to, co fizycznie pójdzie na drukarkę. Rozszerzenie decyduje TYLKO o tym,
jak otworzyć plik; potem wszystko idzie tą samą drogą:

1. **Render strony pasami** w „rozdzielczości analizy”: PDF/AI/EPS/SVG — 240 ppi
   **na wydruku** (× k dla plików 1:10, czyli 2400 ppi w pliku — liczba pikseli ta sama),
   przez MuPDF albo Ghostscript (`render_region_png` z `max_px` i `gray=True`;
   gs pisze surowy PGM). Rastry (JPG/TIFF/PNG/PSD) — natywna rozdzielczość, Pillow
   (warstwowy TIFF/PSD i tak daje spłaszczoną kompozycję — to ona się drukuje).
   Wektory renderują się ostro; obraz 72 ppi wklejony do PDF-a wychodzi jako słaby
   fragment TAM, GDZIE LEŻY, niezależnie od tego, czy jest osobnym obiektem, czy tłem.
   Strona bez obrazów (sam wektor) — mapa pomijana.
2. **Bloki 64 px** (≈ 6,8 mm przy 240 ppi) — dla każdego krzywa strat E(f), f ∈ {2; 2,5;
   3; 4; 6; 8} (zmniejsz f× Lanczos, powiększ z powrotem bicubic, średni błąd²), liczona
   wektorowo na całym chunku 512 wierszy (`np.add.reduceat`), chunki w procesach
   (`ProcessPoolExecutor`, `os.cpu_count()-1`; numpy/PIL nie zwalniają GIL na tyle,
   by wątki pomagały). To samo na chunku zmniejszonym 2× (skala 2).
3. **Reguła „kolana”** (`_knee`) zamiast starego progu: obraz powiększany f× ma krzywą
   PŁASKĄ do f (E(2) ≈ E(2,5)) i dopiero potem skok; naturalny detal rośnie gładko
   (~(next/f)² na stopień). Współczynnik = pierwsze f ≥ 2, przy którym E(f) < 4,5 %·E(8)
   ORAZ następny stopień skacze > 2× naturalny wzrost. Pomiar na zdjęciu z adFrame_Smart
   (512 px, natywne 120 ppi): natywne E(2)/E(8) = 0,066 (rośnie gładko); po powiększeniu
   2,5×: E(2) = E(2,5) = 0,012, E(3) = 0,042 — skok ×3,5. Stara reguła („E(f) małe”)
   przy analizie 300 ppi dawała f = 3 dla obrazu 120 ppi (bo pasmo 100–120 ppi niesie
   mało energii) → w mapie 53 % bloków „100 ppi” na poprawnym pliku. Kolano to naprawia.
4. **Obszary, nie bloki.** Bloki z f ≥ 2 są sklejane (BFS) i każdy obszar jest
   potwierdzany krzywą CAŁEGO obszaru (średnia ważona krzywych bloków). Pojedyncze bloki
   f 2–3 to szum na natywnych zdjęciach → obszar f < 4 musi mieć ≥ 3 bloki, f ≥ 4 — ≥ 2.
   Bloki „gładkie” (E(8) < 12, ale std > 3 — jest treść, nie ma drobnego detalu) są
   sklejane osobno; ich krzywa w skali 2 mówi, czy to bardzo mocne powiększenie
   (kolano, f' → f = 2·f') czy gradient/bokeh (płasko).

Rodzaje obszarów w wyniku:

| kind | co to | w UI |
|---|---|---|
| `upscaled` | kolano w skali 1, f 2–6 (pewna sygnatura powiększenia) | „Słabe obszary (N)” — decyduje o werdykcie (min ≈ 240/f ppi) |
| `upscaled-coarse` | kolano dopiero w skali 2 (brak nawet grubego detalu: mocne powiększenie ALBO mocne rozmycie — nie do odróżnienia) | razem z gładkimi, „Pokaż gładkie” |
| `soft` | gładki w każdej skali (gradient, cień, bokeh) | jw. |

Dlaczego `upscaled-coarse` nie decyduje o werdykcie: test z rozmyciem gaussowskim σ = 6
i 12 px na natywnym zdjęciu daje dokładnie taki sam obraz krzywej jak powiększenie
8–16×. Na „poprawnym” adFrame_Smart miękka krawędź pralki wychodziła jako „bardzo słaba
≈ 30 ppi” w nagłówku — fałszywy alarm. Teraz jest na liście gładkich do obejrzenia,
z opisem „program tego nie rozróżni, oceń na oko” — zgodnie z „nie przegapić”, ale bez
straszenia.

## Wynik (`/api/jobs/<id>/detail?k=1&page=0`)

Startuje w tle przy pierwszym wywołaniu (po analizie 04), kolejne zwracają
`{status: running|done|error, band, bands, result}`. `result`:
`page_px, block_px, analysis_ppi_print (240 | null dla rastra), raster_shrink, grid
{rows, cols, codes_b64}` (kody bloków: 0 jednolity, 1 pełny detal, 2…12 wg CODE_OF,
13 gładki), `share` (udział bloków z detalem wg f), `weak[]` (obszary `upscaled` i
`upscaled-coarse`: fx/fy/fw/fh w ułamkach strony, factor, blocks, kind), `soft[]`,
`blocks_total/detail/soft/uniform`, `seconds`.

ppi bloku = baza / f, gdzie baza = 240 (PDF) albo natywne ppi rastra na wydruku
(px / mm wydruku — UI liczy po wyborze produktu). Skala 1:10 → k = 10, mapa liczona
ponownie po zmianie skali (`detailOnScaleChange`).

## UI

- W „Jakość rastrów”: „Mapa detalu wydruku (cała strona, blok po bloku): pas 2 / 5…”,
  potem ramka: liczba bloków i ich rozmiar w mm, czas; „Znaleziono N obszarów o realnej
  rozdzielczości poniżej 120 ppi — najgorszy [ocena] ≈ X ppi (sygnatura powiększenia
  ~f×)” + **Słabe obszary (N)**; udział powierzchni poniżej 80 / 80–120 ppi; „Fragmenty
  gładkie … oceń na oko: N” + **Pokaż gładkie (N)**; legenda kolorów. Gdy baza < 120
  (raster o za małej rozdzielczości nominalnej): „Sama rozdzielczość pliku na wydruku
  to X ppi — poniżej 120 na całej powierzchni” + ewentualne obszary jeszcze gorsze.
- Nagłówek „min. ≈ X ppi na wydruku (z mapy detalu)” — gdy mapa znalazła coś gorszego
  niż tabela obrazów.
- Przycisk **Mapa** nad podglądem: heatmapa (canvas `#heat` na całej stronie,
  `image-rendering: pixelated`, krycie 0,55): żółty 80–120, pomarańczowy 40–80, czerwony
  < 40 ppi, fiolet = gładki (bez oceny), przezroczysty = dobra/jednolity. Włącza się sama
  przy „Słabe obszary”/„Pokaż gładkie”; nawigator (‹ › ×, strzałki) prowadzi po obszarach
  z podpisem „≈ X ppi”.
- Tabela obrazów z 04 zostaje (dla PDF pokazuje, KTÓRY obiekt wymienić); werdykt bierze
  gorsze z obu.

## Testy

Syntetyczne (blok 1024 px z natywnego zdjęcia 120 ppi): natywne → brak obszarów; JPEG
q20 → brak; powiększenie 2×/3×/4× → obszary `upscaled` f = 2/3/4 (poprawnie);
6× → `upscaled-coarse` 6; gradient → gładki; ostre krawędzie/szum → f = 1; rozmycie
σ = 3 → f = 3 (tak — brak detalu drobniejszego niż 3 px to fakt fizyczny);
wklejone powiększone logo 3× o boku 300/180 px w ostrym tle → wykryte w dobrym
miejscu z f = 3; logo 120 px (2 bloki) → NIE wykryte (granica ~15 mm na wydruku).

Pliki: adFrame_Smart_100x250 (1:1, natywne 120 ppi): 55 650 bloków, 73 % bloków
f = 2 → 120 ppi (dokładnie natywne), 10 obszarów `upscaled` f = 3 (panel pralki —
te same miejsca co „słabsze fragmenty” z 04), 61 gładkich; 40 s w sandboxie
(2 rdzenie; na stacji Tomasza kilka razy szybciej). 1788…q1.jpg (dpi 9 → 2893 mm):
„sama rozdzielczość pliku 9 ppi — poniżej 120 na całej powierzchni”.

## Koszt / ograniczenia

- Czas ~ liczba pikseli analizy: 1:1 6000×2270 mm przy 240 ppi = 1,2 Gpx → w sandboxie
  (2 rdzenie) kilka minut, na 8+ rdzeniach ~1 min; przy spłaszczonym JPEG-u każdy pas
  to ponowne dekodowanie przez gs. Działa w tle z postępem, nie blokuje reszty.
- Powiększenie „najbliższym sąsiadem” (klocki bez wygładzenia) nie jest wykrywane.
- Elementy < ~15 mm na wydruku giną w statystyce bloku (dla PDF łapie je nominalne ppi
  obiektu z 04).
- Mocne rozmycie i mocne powiększenie są nie do odróżnienia → „gładkie, oceń na oko”.
- Analiza tylko strony 0 (wielostronicowy PDF i tak jest błędem).

Plik 1878 (3020×2300 mm, tło 100 ppi powiększone 3×): 28535×21732 px analizy,
99 031 bloków z detalem; 53 % bloków f = 4 i 20 % f = 6 → jeden obszar `upscaled`
f = 4 na 44 606 bloków (całe tło, ≈ 60 ppi „słaba”) + gładkie; tabela obrazów z 04
mówi 33 ppi (100 nominalnie ÷ 3) i nagłówek bierze gorsze. Rozjazd 60 vs 33 wynika
z sufitu f = 6 w skali 1 przy 240 ppi analizy (100 ppi × 3 = 7,2× łącznie) — wada jest
złapana i nazwana, dokładną liczbę daje analiza obiektu. 153 s w sandboxie (2 rdzenie).

## Poprawki po pierwszym teście u Tomasza (2026-09-04, plik EDGE 4x3 Diekirch)

Uwagi: „nie widać, że coś jest sprawdzane”; przyciski „Słabe obszary”/„Pokaż gładkie”
w środku opisu; kolorowa nakładka robi podgląd nieczytelnym — wolał ramkę, która
znika; bloki 6,8 mm za małe.

- **Pasek „kontrola jakości”** (`#qc`) nad „Informacjami o pliku”: żółty w trakcie
  („⏳ Sprawdzanie jakości rastrów — cała strona blok po bloku: pas 2 / 5 · 40 %” + pasek
  postępu; wcześniej „Sprawdzanie pliku — kolory, obiekty, rozdzielczość obrazów…”),
  po zakończeniu zielony „✓ Cały plik sprawdzony — żaden fragment… poniżej 120 ppi”
  albo czerwony „⚠ Cały plik sprawdzony. N obszarów… — najgorszy ≈ 60 ppi (słaba)”.
  Plik bez rastrów: „całość w wektorze, brak rastrów do oceny”.
- Ramka „Mapa detalu” ma stały układ: nagłówek → werdykt → **rząd przycisków**
  (Słabe obszary (N) · Gładkie fragmenty (N)) → drobne szczegóły.
- Heatmapa **nie włącza się sama**; przyciski prowadzą po obszarach jak wcześniej
  (ramka + nawigator, znika po chwili). „Mapa” nad podglądem zostaje jako opcja i
  maluje tylko fragmenty poniżej 120 ppi (bez fioletu „gładkich”), krycie 0,45.
- **Bloki domyślnie 128 px ≈ 13,5 mm** (Ustawienia → „dokładność mapy detalu”:
  standardowa 13,5 mm / wysoka 6,8 mm, zapis w localStorage `adcheck.dmBlock`,
  `?block=` w API, klucz zadania zawiera blok). Przy 128 px obszar f 2–3 wymaga
  2 bloków (`MIN_BLOCKS_MILD = {64: 3, 128: 2}`). Test z wklejonym powiększonym logo
  (źródło z teksturą): 128 px wykrywa logo 3× o boku 300 i 180 px oraz 4× 400 px,
  nie wykrywa 2× 200 px (jeden pełny blok) → „elementy od ok. 25 mm”; 64 px wykrywa
  wszystkie cztery → „od ok. 15 mm”. Natywne zdjęcie: brak fałszywych obszarów przy
  obu rozmiarach. Czas przy 128 px ~ten sam co przy 64 (koszt to resize całego pasa,
  nie liczba bloków) — różnica to skala 2 (mniej pikseli), więc ~10–20 % szybciej.
- Gdy mapa daje gorszy werdykt niż tabela obiektów, opis dla laika dostaje na
  początku zdanie „Mapa detalu: … Dotyczy N fragmentów strony (nie całego obrazu)”.

## Zmiana zasadnicza (2026-09-04, po teście na Prosta 600 Ø43): PDF liczony z NATYWNYCH pikseli obrazów

Tomasz: „gładkie i słabe obszary są błędnie identyfikowane — plik to prawie w całości
wektor plus jeden obraz powielony 22 razy”. Oraz: „sprawdzanie jakości rastrów nie może
się odbywać przed potwierdzeniem produktu”.

Diagnoza (zrzuty + test renderu):
1. „Słabe obszary” leżały na miękkich krawędziach wektorowej „1” (cień/gradient),
   „gładkie” na płaskich wypełnieniach — wektor nie ma rozdzielczości, a metryka widzi
   w nim „miękkość”.
2. Render logo 133×75 px na 2400 ppi: MuPDF powiększa je **najbliższym sąsiadem**
   (kroki co 8 px) mimo flagi /Interpolate (obraz z SMask). Dla metryki to ostre
   krawędzie → logo 30 ppi „przechodziło” jako dobre. Sprawdziłem detektor okresowości
   (autokorelacja profilu |dx|): wykrywa siatkę przepróbkowania (NN i bicubic), ale
   artefakty JPEG (bloki 8 px) dają ten sam obraz nawet przy q75 → za dużo fałszywych
   trafień, porzucone.

Wniosek: dla PDF-a renderowanie strony jako podstawa oceny jest zawodne z obu stron.
**Mapa dla PDF-podobnych liczy się teraz obiekt po obiekcie z natywnych pikseli**
(`detailmap.build_pdf_objects`): każdy obraz (poza maskami) zdekodowany w całości
(ogromne — pasami w natywnej rozdzielczości, bez przepróbkowania), bloki w pikselach
obrazu o rozmiarze odpowiadającym `block` px przy 240 ppi na wydruku (≈ 13,5 mm; dla
logo 30 ppi to 32 px, dla zdjęcia 300 ppi — 160 px), reguła kolana + potwierdzanie
obszarów jak dotąd, a obszary rzutowane na **wszystkie umiejscowienia** obrazu na stronie
(`analyze` daje pełne rekordy `_images` z xref i listą użyć — server trzyma je poza
JSON-em dla UI). Dodatkowy rodzaj obszaru `lowres`: użycie obrazu, które nominalnie ma
< 120 ppi na wydruku (całe użycie jako słaby obszar, ppi = nominalne). Wektor jest
automatycznie poza oceną, renderer nie ma znaczenia, a k (1:10) wchodzi przez ppi
umiejscowienia. Rastry (JPG/TIFF) bez zmian — cały plik w natywnej rozdzielczości.
Tryb renderu strony z maską obrazów (`build(..., boxes=)`) zostaje w kodzie jako opcja,
ale nie jest używany.

Skutki: Prosta 600 Ø43 — 22 obszary „za mało pikseli: 133×75 px” ≈ 30 ppi, 0 fałszywych,
0,1 s (było: 29 fałszywych + 2 gładkie, 57 s). adFrame_Smart — obszary 3–4× na panelu
pralki (jak wcześniej), 8,5 s. 1878 — całe tło ≈ 33 ppi (3×, zgodnie z tabelą obiektów),
25 s w sandboxie.

Blokada: ocena jakości rastrów (sekcja „Jakość rastrów” i mapa) pojawia się dopiero po
**potwierdzeniu produktu** (`productConfirmed()`): wcześniej szary pasek „◌ Jakość
rastrów zostanie sprawdzona po potwierdzeniu produktu — od produktu zależy skala
i rozmiar wydruku” i w sekcji tag „po potwierdzeniu produktu”. Cofnięcie („zmień”)
anuluje mapę i wraca do tego stanu. Analiza faktów (kolory, fonty, profile) nadal
liczy się od razu po wgraniu.

W trybie obiektowym nie ma heatmapy (przycisk „Mapa” ukryty) — obszary pokazuje
nawigator ramką; ppi każdego obszaru jest policzone po stronie serwera.

## Niezależność od formatu — postać kanoniczna (2026-09-04)

Tomasz: „a co z AI, SVG, PNG? To nie powinno zależeć od rozszerzenia, tylko od tego, co
w pliku jest — PDF może być w całości rastrem, AI i SVG też; może być mieszany, z
nachodzącymi na siebie wektorami i rastrami”.

Rozwiązanie: **rozszerzenie decyduje tylko o tym, jak plik otworzyć; ocena zależy od
treści**. Przy wgraniu (`preview.canonicalize`) każdy plik jest sprowadzany do postaci
kanonicznej, na której działa wszystko dalej (podgląd, analiza, mapa):

| wejście | postać kanoniczna | jak |
|---|---|---|
| PDF, AI (zgodne z PDF) | ten sam plik | — |
| SVG | `canon.pdf` | MuPDF `convert_to_pdf()` — obrazy osadzone w SVG zostają obiektami obrazów z pełną geometrią (transformacje, rozciągnięcia), tekst zostaje tekstem |
| EPS | `canon.pdf` | Ghostscript `pdfwrite -dEPSCrop` |
| JPG/PNG/TIFF/BMP/WebP/GIF | ten sam plik | plik = jeden raster (TIFF/PSD z warstwami → spłaszczona kompozycja, bo to ona się drukuje) |
| CDR, INDD, PSD | — | prośba o eksport do PDF (jak dotąd) |

`analyze.analyze()` nie patrzy już na rozszerzenie: co da się otworzyć jako PDF, idzie
przez analizę obiektów (każdy raster w środku oceniany w natywnych pikselach, wszystkie
jego użycia; wektor nie ma rozdzielczości), reszta = jeden raster. Stąd:

- PDF/AI/SVG **w całości raster** = jeden obiekt obrazu na całą stronę → oceniany w całości
  (pasami, gdy ogromny) — dokładnie jak JPG.
- **mieszany**, wektory i rastry nachodzące na siebie → każdy raster oceniany osobno
  w swoim położeniu; wektor nad rastrem nie zmienia oceny rastra (nie ma rozdzielczości),
  raster nad rastrem — oba osobno. Nominalne ppi każdego użycia z macierzy CTM (także
  w Form XObject i wzorkach).
- „PDF — tylko wektor” → brak rastrów do oceny (pasek zielony).

Test (syntetyczny `mix.svg`: prostokąt, koło, tekst, raster 60×40 px rozciągnięty na
300×200 pt, raster 300×200 px w `transform="scale(0.5)"`): SVG, EPS (z niego przez
eps2write) i PDF dają identyczny wynik — 2 obrazy, 14,4 ppi i 144 ppi, tekst
Times-Roman, mapa: 1 obszar `lowres` 14,4 ppi. UI pokazuje „(SVG → PDF (MuPDF))” przy
typie pliku i „PDF — w całości raster”, gdy jeden obraz pokrywa > 90 % strony.

Znane ograniczenie (do zrobienia): obraz przycięty ścieżką (clip) jest oceniany w całym
swoim prostokącie, także w części niewidocznej — może dać obszar słaby w miejscu, którego
nie widać. Analizator śledzi CTM, ale nie ścieżki przycięcia; dopisać śledzenie bbox
clipu (`W n`) w `Analyzer.walk` i przycinać `placements`.
