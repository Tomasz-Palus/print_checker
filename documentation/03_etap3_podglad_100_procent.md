# Etap 3 — podgląd 100 % rozmiaru rzeczywistego (kontrola jakości)

Data: 2026-09-03. Kontynuacja po etapie 2 (`02_etap2_wytyczne_nakladka.md`).

## Ustalenia z tej sesji (Tomasz)

- **Zawsze drukujemy 1:1.** Projekt 1000×1000 mm w skali 1:1 → wydruk 1000×1000 mm.
  Projekt 500×500 mm w skali 1:10 → wydruk 5000×5000 mm, więc **1200 ppi w pliku
  = 120 ppi na wydruku**.
- Przycisk „100 %” ma pokazać wydruk w rzeczywistym rozmiarze (1 mm wydruku =
  1 mm na ekranie), z uwzględnieniem ppi — żeby ocenić jakość rastra.
- Kalibracja monitora: **w Ustawieniach** (nie zakładamy 96 px/cal na sztywno).
- Piksele rastra: **przełącznik** — domyślnie wygładzone (jak interpoluje RIP
  plotera), opcjonalnie surowe piksele.
- Rozmiar wydruku do widoku 100 %: **z szablonu wytycznych** (×10 przy skali
  1:10); gdy brak szablonu → wymiar ręczny; gdy i jego brak → strona pliku × skala.
- Plik w złej skali (1:1 vs 1:10) → w etapie kontroli wymiaru ma być nazwany
  wprost jako błąd (ustalone w rozmowie po etapie 2).

## Jak to działa

### Rozmiar rzeczywisty
`printSize()` w `app.js` zwraca wymiar wydruku w mm i źródło (szablon / wymiar
ręczny / strona pliku). Skala 100 % liczona po **dłuższym boku**: plik jest
mapowany na dłuższy bok wydruku (bo plik może mieć trochę inne proporcje niż
szablon, np. 616×232 vs 600×227 — wtedy wydruk i tak ma szerokość szablonu).
Ekran: `cssPxPerIn` (kalibracja) → px/mm. Zoom = (px ekranu na pt pliku) /
(px bazowego renderu na pt pliku).

Pod paskiem narzędzi jest linia **„wydruk: 6000 × 2270 mm (szablon „Przod”,
skala 1:10) · raster na wydruku: 120 ppi”** — dla plików rastrowych podaje
efektywne ppi po wydrukowaniu (px pliku / cale wydruku). Dla PDF-ów z
osadzonymi rastrami efektywne ppi każdego obrazu policzy etap kontroli.
W etykiecie strony jest bieżący zoom w % względem rozmiaru rzeczywistego.

### Wycinek w wysokiej rozdzielczości
Bazowy render ma 1600 px po dłuższym boku. Wydruk 6000 mm przy 96 px/cal to
22 677 px szerokości — całej strony nie renderujemy. Gdy zoom przekracza bazowy
render, front (po 180 ms od końca scroll/zoom) prosi o **wycinek widocznego
obszaru + 30 % marginesu** (`GET /api/jobs/<id>/region.png?page&x0&y0&x1&y1&s&smooth`,
współrzędne w pt strony, `s` = px/pt × devicePixelRatio, wynik ≤ 3200 px).
Backend: `preview.render_region_png()` → `page.get_pixmap(matrix, clip=…)`.
Wycinek jest pozycjonowany absolutnie nad bazowym obrazem (`#hires`), przy
zmianie zoomu jest przeskalowany CSS-em (chwilowo miękki), aż przyjdzie nowy.
Stare odpowiedzi są ignorowane (numer sekwencji). Zoom (+/−, Ctrl+kółko) jest
zakotwiczony w środku widoku / pod kursorem.

Dla PDF-ów z ogromnym rastrem (MuPDF „Overly large image”) wycinek robi
Ghostscript: `-dFIXEDMEDIA -dDEVICEWIDTHPOINTS/-dDEVICEHEIGHTPOINTS` = wycinek,
`-c "<</Install {tx ty translate}>> setpagedevice"` (układ PS od lewego dolnego
rogu: `tx = -x0`, `ty = -(H - y1)`). Sprawdzone na `1824_strony_wymiar_cmyk.pdf`
(~6 s na wycinek).

### Wygładzone vs surowe piksele
MuPDF skaluje obrazy **bez interpolacji** (najbliższy sąsiad), chyba że obraz w
PDF-ie ma flagę `/Interpolate true` — wtedy interpoluje. Sprawdzone testem
(szachownica 20 px renderowana ×10: bez flagi ostre krawędzie, z flagą
gradient). Dlatego `preview._set_interpolate(doc, smooth)` ustawia flagę na
wszystkich obrazach **w pamięci** (oryginał nietknięty) przed renderem.
Rastry (JPG/PNG/TIFF) i tak przechodzą przez konwersję do PDF-a, więc działa to
samo. Przycisk **„Surowe px”** przełącza tryb, przeładowuje bazowy render i
wycinek; dodatkowo CSS `image-rendering: pixelated` na czas skalowania w
przeglądarce. Ghostscript: `-dInterpolateControl=1/0`.

### Kalibracja monitora (Ustawienia)
- **Sposób A:** przekątna w calach + wykryta rozdzielczość (`screen.width ×
  devicePixelRatio`) → fizyczne ppi → CSS px/cal = ppi / devicePixelRatio.
- **Sposób B:** linijka SVG 0–100 mm (czerwone kreski początku i końca ze
  strzałkami, podziałka co 1 mm, liczby co 10 mm — na prośbę Tomasza, żeby było
  dokładnie widać skąd dokąd mierzyć); użytkownik mierzy linijką i wpisuje
  wynik → korekta proporcjonalna.
- Zapis w `localStorage` (`adcheck.cssPxPerIn`), Reset → 96. Bez kalibracji w
  linii „wydruk:” jest ostrzeżenie „monitor niekalibrowany (96 px/cal)”.
- Uwaga: kalibracja dotyczy monitora, na którym otwarta jest przeglądarka; przy
  przeniesieniu okna na inny monitor trzeba skalibrować ponownie.

## Testy (sandbox)

- `Wydruk_adWall_Vario_Prosta_600_43…pdf` + wytyczne (1:10, szablon 600×227):
  „wydruk: 6000 × 2270 mm”, 100 % → canvas 22 677 px, wycinek 1851×1157 px
  ładuje się w ~0,5 s; wektorowy tekst ostry, rastrowe logo widocznie miękkie.
- JPG 1025×880 px / 9 dpi bez szablonu → „wydruk 2892,8 × 2483,6 mm (strona
  pliku) · raster na wydruku: 9 ppi”.
- Kalibracja: wpis 27" przy 1280×720 (headless) → 54 ppi, zoom przeliczony
  (100 % → 148 % w starej skali). Bez błędów JS.

## Do sprawdzenia u Tomasza

1. Skalibrować monitor (Ustawienia) i sprawdzić linijką, czy 100 % = 1 mm/1 mm.
2. Plik z `poprawne/` w 1:10 z rastrami 1200 ppi → przy 100 % powinno wyglądać
   jak 120 ppi na wydruku; przełącznik „Surowe px”.
3. Płynność przy przewijaniu w 100 % (wycinek dogrywa się po zatrzymaniu).

## Pomysły na później

- Lupa (mały kwadrat 100 % w rogu przy widoku „Dopasuj”) — może wygodniejsza
  niż przewijanie 22 000 px.
- Efektywne ppi każdego obrazu w PDF-ie (etap kontroli) + podświetlenie
  obrazów poniżej progu na podglądzie.

## Poprawki UX po testach Tomasza (2026-09-03)

- Linijka kalibracyjna: SVG z wyraźnym początkiem/końcem (czerwone kreski ze
  strzałkami), podziałka 1/5/10 mm.
- **Zmiana pliku resetuje sekcję „2 · Produkt”**: czyści wyszukiwarkę, wybrany
  produkt, wytyczne i szablon, a potem stosuje sugestie z nazwy nowego pliku
  (≥ 85 % wybiera się samo). Wcześniej stary wybór zostawał.
- Zabezpieczenie przed wyścigiem: nowy upload przerywa poprzedni (`xhr.abort()`),
  a spóźniona odpowiedź starego uploadu jest ignorowana (numer sekwencji) —
  inaczej po szybkim wgraniu dużego i małego pliku produkt ustawiał się z tego
  pierwszego.

## Poprawka kalibracji linijką (po testach Tomasza, 2026-09-03)

Problem: „Zastosuj” z tą samą wartością (103 mm) za każdym razem zmniejszało
linijkę i dawało inną kalibrację. Przyczyna: metoda była **względna** — pasek
był rysowany wg bieżącej kalibracji i każde „Zastosuj” mnożyło ją przez 100/103,
więc powtórne kliknięcie z tą samą liczbą kumulowało korektę.

Rozwiązanie: **pasek wzorcowy o stałej długości 400 CSS px** (nie zmienia się po
kalibracji). Użytkownik mierzy go linijką i wpisuje mm; px/cal = 400 / mm × 25,4
— wynik absolutny, wielokrotne „Zastosuj” z tą samą wartością daje ten sam
wynik. Pod spodem osobny pasek **„Sprawdzenie”** rysowany wg bieżącej
kalibracji, który powinien mieć dokładnie 100 mm.

## Pełny ekran, nawigator, kafelki (2026-09-07)

Trzy rzeczy z prośby Tomasza: ręczne sprawdzanie jakości na całym ekranie, szybkie
przesuwanie widoku jak w Photoshopie i koniec czekania „aż jakość się dostosuje" po
przewinięciu.

### Kafelki zamiast wycinka „to, co widać"

Dotąd po każdym przewinięciu podgląd renderował od nowa jeden wycinek widocznego
obszaru (+30 % marginesu) — z 180 ms opóźnienia i czasem serwera; stąd chwila miękkiego
obrazu po każdym ruchu. Teraz jest **stała siatka kafelków 1024 px** w bieżącej skali:

- widoczne kafelki (z marginesem jednego) ładują się od razu, potem reszta strony
  **doładowuje się w tle** od środka widoku na zewnątrz — po chwili cała strona jest
  w pełnej jakości i przewijanie niczego nie czeka; postęp widać w pasku narzędzi
  („jakość: 63 %"),
- stałe adresy (`tile.jpg?page&s&T&tx&ty`) = pamięć podręczna przeglądarki i dysku
  serwera działa — powrót do 100 % nie renderuje nic drugi raz,
- 4 pobrania naraz (serwer renderuje na CPU), sufit 600 kafelków na jedną skalę
  (1:10 przy 100 % to ~400), JPEG q92 bez podpróbkowania chromy (30–50 KB na kafelek;
  PNG byłby 10× większy — przy 100+ kafelkach to jest różnica między „chwila" a
  „minuta"),
- zmiana powiększenia czyści siatkę i buduje ją od nowa — kafelek z innej skali
  byłby po przeskalowaniu miękki i rysował szew (patrz „szwy na podglądzie" w 08).

Pomiar (adFrame_Smart, 100 %): kafelek 0,2–0,4 s renderu, 30–50 KB; z pamięci
podręcznej 4 ms.

### Pełny ekran

Przycisk **„Pełny ekran"** w pasku narzędzi podglądu; wraca **„✕ Zamknij pełny ekran"**
w prawym górnym rogu albo **Esc**. To ten sam DOM z klasą `body.fs` (podgląd
`position: fixed; inset: 0`), więc powiększanie, kafelki, ramki i nawigator działają
identycznie — nic nie jest duplikowane.

### Nawigator

Miniatura całej strony (ten sam obraz co bazowy podgląd) w prawym dolnym rogu, z
czerwoną ramką bieżącego widoku. Kliknięcie albo przeciągnięcie ustawia środek widoku
w tym punkcie. Pokazuje się tylko wtedy, gdy strona jest większa od okna (przy
„Dopasuj" nie ma czego przesuwać). W pełnym ekranie jest większy (300 px).

Włączanie/wyłączanie: przycisk **„Nawigator"** w pasku narzędzi (podświetlony = włączony)
i mały **×** w rogu samego nawigatora. Wybór pamiętany w `localStorage`
(`adcheck.navi`), więc wyłączony zostaje wyłączony także po ponownym otwarciu.

## Symulacja overprintu (2026-09-07)

Tomasz: w podglądzie litera „D" w logo DRAC jest **czerwona**, a na wydruku (podgląd
separacji w Photoshopie) wychodzi **prawie czarna**. Plik: `Prosta 600 Ø43`,
34 użycia overprintu.

Overprint zmienia to, co wyjdzie z drukarki: farba **nie wybija tła**, tylko kładzie się
na nim. Czerwone „D" (M+Y) z włączonym overprintem na czarnym tle drukuje się jako
czerń + czerwień, czyli prawie czarne. MuPDF — jak każdy render „ekranowy" — pokazuje
je jako czerwone. To najgorszy możliwy rodzaj błędu podglądu: **użytkownik akceptuje
plik, który wydrukuje się inaczej, niż zobaczył.**

Rozwiązanie: render przez Ghostscript z `-dOverprint=/simulate`. Sprawdzone na tym
pliku — wynik zgodny z Photoshopem (D i kwadrat RAC1 ciemnieją); 9,3 % pikseli strony
różni się od renderu bez symulacji, największa różnica 207/255.

Jak to działa w programie:

- `preview.uses_overprint(path)` — skan po obiektach PDF-a za `/OP` albo `/op` = true
  w ExtGState. Bez wchodzenia w strumienie treści: 0,07–1,3 s nawet dla 70 MB.
- Plik z overprintem → **wszystkie** rendery (strona, kafelki, wycinki) idą przez
  Ghostscripta z symulacją; MuPDF zostaje dla reszty, bo jest szybszy.
- Przełącznik **„Overprint"** nad podglądem (widoczny tylko dla plików, które go
  używają, domyślnie włączony) — pozwala porównać „co wyjdzie z drukarki" z „co jest
  w pliku". Przełączenie czyści kafelki i pobiera bazowy render na nowo.
- W „Pozostałe" informacja mówi wprost, że overprint **zmienia wygląd wydruku**, i czy
  podgląd go aktualnie symuluje.

Koszt: strona 1600 px przez Ghostscripta 0,51 s wobec 0,21 s przez MuPDF — dla plików
z overprintem to uczciwa cena za pokazywanie prawdy.

Zasada: **podgląd pokazuje WYDRUK, nie plik.**

## Szybkość podglądu w pełnej jakości (2026-09-08)

Tomasz: „czy jest szansa przyspieszyć ten podgląd pełnej jakości?". Zmierzone i poprawione
w dwóch miejscach.

**1. Serwer: kafelek z listy wyświetlania, prosto do JPEG-a.** Każdy kafelek otwierał plik
od nowa i renderował wycinek ze strony — czyli za każdym razem od zera interpretował treść
strony i dekodował obrazy, a wynik szedł jeszcze przez PNG (render → PNG → Pillow → JPEG).
Teraz `preview.render_tile_jpeg` trzyma otwarty dokument i **listę wyświetlania** strony
(`page.get_displaylist()`), a kafelek to rasteryzacja gotowej listy prosto do JPEG-a.
Podręczna pamięć: najwyżej 4 dokumenty, każdy z własnym zamkiem (dokumenty MuPDF-a nie są
bezpieczne wątkowo), unieważniana po każdej poprawce pliku.

Zmierzone (jeden kafelek 1024 px):

| plik | było | jest |
|---|---|---|
| adWall 1,9 MB | 0,09–0,13 s | 0,03 s |
| 1878 70 MB | 3,2 s (pierwszy) / 0,19 s | 0,21 s (pierwszy) / 0,035 s |

**2. Przeglądarka: kafelki tylko na widok.** To była właściwa przyczyna. Dociągaliśmy w tle
CAŁĄ stronę — przy wydruku 6 m to ~200 kafelków 1024×1024, czyli ponad 800 MB zdekodowanych
bitmap, a użytkownik i tak patrzył na jeden fragment. Teraz pobieramy widok plus margines
jednego kafelka (do 24 na porcję), trzymamy w pamięci 30 najbliższych, resztę wyrzucamy;
przy przewijaniu dociągają się kolejne.

Efekt na przykładzie (wydruk 6000 × 2270 mm, okno 1700 px): **62 s → 7 s**, 198 kafelków → 20.

Uwaga do pomiarów: w kontenerze testowym są 2 rdzenie, więc przeglądarka rasteryzująca
wielki obszar i serwer renderujący kafelki biją się o CPU — pojedyncze żądanie potrafi tam
trwać 1,9 s zamiast 0,03 s (to samo żądanie z bezczynnej strony: 33 ms). Na maszynie
z kilkoma rdzeniami różnica powinna być jeszcze wyraźniejsza.

## Lupki i zaznaczanie obszaru (2026-09-08)

Zamiast przycisków „+" i „−" w pasku są **dwie lupki** (ikonki), które działają jak
narzędzia w programach graficznych: przycisk WŁĄCZA lupkę (podświetla się jak „Szablon"
czy „Nawigator"), a potem klika się w podglądzie. Póki lupka jest włączona:

- **klik** — skok powiększenia w miejscu kliknięcia (×1,25 lupką +, ×0,8 lupką −),
- **przeciągnięcie** — prostokąt zaznaczenia; po puszczeniu podgląd powiększa się tak,
  żeby zaznaczony obszar wypełnił okno, **najwyżej do 100 % rozmiaru rzeczywistego**
  (ustalenie Tomasza: wyżej ogląda się piksele ekranu, nie wydruk). Sprawdzone: maleńkie
  zaznaczenie kończy się dokładnie na skali przycisku „100 %" (płótno 22 223 px w obu
  przypadkach, przycisk „100 %" podświetlony).
- **Esc** albo ponowne kliknięcie ikonki wyłącza lupkę i wraca „łapka" (przeciąganie
  przesuwa widok).

Kursor mówi, co się stanie (`zoom-in` / `zoom-out`), a prostokąt zaznaczenia to zwykły
`div` w układzie płótna, więc trzyma się treści przy przewijaniu.

### Miejsce na zieloną etykietę formatu

Etykieta „format z wytycznych …" wisi 21 px NAD ramką. Po dopasowaniu wymiaru ramka pokrywa
się z całą stroną, więc etykieta wychodziła poza płótno i obcinała ją krawędź okna. Pierwsza
próba (etykieta do środka ramki) Tomaszowi się nie spodobała — zasłaniała projekt. Teraz
zapas wokół strony jest w pionie większy niż w poziomie (`PAD_Y = 48`, `PAD_X = 24`), więc
nad stroną zawsze zostaje ~24 px i etykieta mieści się na zewnątrz.

### Kafelki znikają natychmiast przy zmianie skali

Siatka kafelków przebudowywała się dopiero w `tilesUpdate` (60 ms po zmianie). Do tego czasu
stare kafelki leżały na stronie w SWOICH starych rozmiarach — przy przesuwaniu suwaka skali
projektu wyglądało to jak duch poprzedniego powiększenia wklejony w róg podglądu (zgłoszone
przez Tomasza). Teraz `applyZoom` czyści kafelki od razu, gdy zmienił się rozmiar płótna.

### Czekanie widać na środku podglądu (nie w rzędzie przycisków)

Postęp wczytywania pełnej jakości był wąskim paskiem obok przycisków skali. Tomasz zgłosił,
że „pełna jakość przestała się wczytywać" — a ona się wczytywała, tylko wskaźnik ginął.
Teraz **wszystko, na co trzeba poczekać, mówi jedno miejsce**: plakietka z kręcącym się
kółkiem na środku podglądu, taka sama jak przy renderowaniu strony (`#stageBusy`).

Pokazuje po kolei (ważniejsze wypiera mniej ważne):

| źródło | napis |
|---|---|
| `fixrun` | „nakładam poprawkę na plik" / „cofam poprawki" |
| `fiximg` | „renderuję wersję po poprawkach" |
| `base`   | „liczę wersję do porównania" |
| `tiles`  | „wczytuję pełną jakość — 42 %" (z paskiem) |

Kafelki dostają **450 ms opóźnienia** — przy przewijaniu doczytują się ułamek sekundy i
plakietka mrugająca po każdym ruchu myszki byłaby gorsza niż jej brak. Pod zasłoną renderu
strony plakietki nie ma (byłyby dwa kółka).

### Kafelek nigdy nie liczy wariantu porównawczego

Wariant „wszystko oprócz jednej poprawki" (`wo_*.pdf`, lewy koniec suwaka w rozdziale) liczy
Ghostscript i przy dużym pliku trwa to kilkanaście sekund. Budowanie siedziało w
`_src_path`, więc robiło je **każde** zapytanie, które o ten plik poprosiło — a kafelków leci
sześć naraz. Kilkanaście renderów naraz zajeżdżało procesor i pisało po tym samym pliku;
z zewnątrz wyglądało to tak, jakby pełna jakość w ogóle się nie wczytywała.

Teraz:

- `_wo_path(..., build=False)` — kafelek **nie buduje niczego**. Jak wariantu jeszcze nie ma,
  dostaje **409** i próbuje ponownie, kiedy dolna warstwa podglądu się doczyta
  (`baseReload` → `tilesSchedule`). Renderowanie w tym czasie oryginału byłoby gorsze niż
  brak kafelka: trafiłby do pamięci podręcznej pod adresem wariantu i pokazywał nieprawdę.
- budowanie chroni zamek per (zadanie, poprawka) — liczy je jeden wątek, reszta czeka na gotowe.
- po każdej poprawce wracamy do taniego punktu odniesienia (`cmpMode = null`); wariant policzy
  się dopiero, gdy ktoś znów ruszy suwakiem w rozdziale.

### Nie pokazujemy nieaktualnej warstwy „po poprawkach"

Po kliknięciu poprawki przeglądarka trzyma stary obraz górnej warstwy, dopóki nie doczyta
nowego — Tomasz zobaczył przez kilkanaście sekund POPRZEDNI stan pliku i odebrał to jako
„wczytał mi się poprzedni projekt". Teraz na czas renderu górna warstwa ma `opacity: 0`
(widać poprawne „przed"), a plakietka mówi, że pracujemy.

### Biała kreska u dołu strony z dołożonym tłem

Pasek „rozciągnij krawędź" rysujemy na `<canvas>`. Canvas jest elementem **wierszowym** —
siadał na linii bazowej tekstu i zaczynał się 3,4 px niżej niż jego ramka, więc u dołu
zostawał prześwit, przez który widać było wygładzony brzeg renderu projektu: jasna kreska,
znikająca po powiększeniu (zgłoszenie Tomasza). `.edgefill > div > canvas` ma teraz
`position: absolute; inset 0`. Zmierzone na `1878_wymiar_strony…` (3020×2300 → 3075×2340 mm):
przed poprawką wiersz 983 miał kolor tła okna (243,243,245), po poprawce tło dołożone z
krawędzi idzie bez przerwy aż do zielonej ramki formatu.

### Typ pliku w górnym pasku, nie w lewej kolumnie

„Strony / typ" (liczba stron, `PDF — wektor + raster`, program, w którym plik powstał)
siedziało w lewej kolumnie pod „1 · Plik". Tomasz: „bez sensu, żeby to było w tym miejscu" —
to fakty o pliku jako całości, a nie krok do zrobienia. Teraz stoją w pasku nad podglądem,
przy nazwie pliku: pierwsza linijka `nazwa · 1 strona · PDF — wektor + raster`, druga,
ciszej, `Adobe InDesign 17.0 (Macintosh) · Adobe PDF Library 16.0.3`. Tam też ląduje napis
„analizuję plik…", więc lewa kolumna nie pokazuje ramki, która za chwilę zniknie — blok
„fakty o pliku" chowa się, gdy nie ma w nim nic poza tym.

### Cała strona wczytuje się raz, a nie „po kawałku"

Kafelki dociągały się tylko dla tego, co widać, więc każde przesunięcie w powiększeniu
oznaczało czekanie (uwaga Tomasza: „wolałbym aby wczytywało raz i móc szybko przesuwać po
całym obszarze"). Teraz kolejka obejmuje **całą stronę**, uporządkowaną od środka widoku na
zewnątrz, z jednym harmonogramem na obie warstwy:

1. widoczne kafelki warstwy, na którą się patrzy (tej spod suwaka porównania),
2. widoczne kafelki drugiej warstwy,
3. reszta strony — dopiero gdy widok jest gotowy, i tylko dwoma naraz.

Bez punktu 3 tło zabierało serwer temu, co widać. Sufit to 200 kafelków na warstwę (strona
ok. 14 500 × 14 500 px, czyli więcej niż wydruk 3 m w skali 1:1); w pamięci trzymamy 220,
więc powrót w to samo miejsce jest natychmiastowy.

Kółko na środku mówi tylko o kafelkach WIDOCZNYCH — doładowywanie reszty leci po cichu.

Pomiar na `1878…` (60 MB, wydruk 3075 × 2340 mm, podgląd 1:1 = płótno 11414 × 8696 px,
108 kafelków, plik z overprintem, czyli każdy kafelek przez Ghostscripta):

| | przed | po |
|---|---|---|
| komplet widocznych kafelków (zimny cache) | ~25 s, dociągane po kilka | **8,6 s** (jeden render bloku) |
| przewinięcie o ekran w bok | kolejne czekanie | kafelek już jest, 0 s |

Bok bloku podniesiony z 3 na 4 kafelki — zmierzone sekundy na kafelek: 1×1 → 3,06;
2×2 → 0,63; 3×3 → 0,39; **4×4 → 0,27**; 5×5 → 0,28; 6×6 → 0,29. Powyżej 4×4 nic już nie
zyskujemy, a rośnie czas pierwszego bloku (na który się czeka).

### Całość mieści się w oknie

Suwak porównania pod podglądem wychodził poza ekran i trzeba było zjechać stroną w dół
(zgłoszone przez Tomasza). Teraz **strona nie przewija się w ogóle**: układ ma wysokość okna,
lewa kolumna z rozdziałami ma własny pasek przewijania, a podgląd dostaje resztę miejsca.
Sprawdzone na 1920×975, 1600×820 i 1366×700 — w każdym przypadku suwak jest w całości
widoczny, a strona nie ma paska po prawej.

### Pełna jakość: jeden przebieg, jak wczytanie obrazu w Photoshopie

Tomasz: „w Photoshopie obraz się wczytuje i potem nawigatorem sprawdzam każde miejsce bez
czekania". Poprzednia wersja liczyła kafelki blokami, na żądanie — czyli w kółko od nowa.
Problem jest w tym, że **Ghostscript nie ma pamięci między uruchomieniami**: przy każdym
wywołaniu od nowa rozpakowuje wielkie obrazy ze strony, a to 95 % kosztu (render 400 px
i 2400 px trwa tyle samo).

Więc zamiast wielu przebiegów robimy JEDEN. Zaraz po wgraniu pliku serwer renderuje całą
stronę w skali 1:1 jednym uruchomieniem Ghostscripta, który pisze surowy obraz na wyjście,
a my czytamy go **pasmami po 1024 wiersze** i od razu zapisujemy gotowe kafelki
(`preview.render_page_tiles`). W pamięci siedzi jedno pasmo — przy stronie 11 400 px to
ok. 35 MB, nigdy cała strona (byłoby 300 MB).

Zmierzone na `1878…` (60 MB, wydruk 3020 × 2300 mm, 108 kafelków 1024²):

| | kafelki na żądanie | jeden przebieg |
|---|---|---|
| policzenie całej strony | ~90 s | **56 s** |
| wejście w 100 % po przebiegu | 8,6 s | **1,6 s** (komplet 108 kafelków) |
| skok nawigatorem w inne miejsce | 8,6 s | **bez czekania** (kafelek z dysku, 0,02 s) |

Dwie rzeczy, które trzeba było przy tym uzgodnić:

- **Skala musi się zgadzać CO DO CZWARTEGO MIEJSCA po przecinku.** Adres kafelka zawiera
  `s` (piksele na punkt), więc 1,3339 zamiast 1,3333 to inny plik — cały przebieg szedł
  w las. Plan liczy teraz przelicznik z ZAOKRĄGLONYCH szerokości płótna, dokładnie tak jak
  `applyZoom`.
- **Starsze zamówienia poddają się same.** Każde nowe dostaje numer; gdy użytkownik wgra
  inny plik albo zmieni skalę, poprzedni przebieg przerywa się między pasmami i oddaje
  procesor. Bez tego kolejkowały się i blokowały to, na co ktoś właśnie patrzył.

Pasek nad podglądem pulsuje, dopóki Ghostscript nie odda pierwszego pasma (wcześniej nie ma
czego liczyć w procentach — rysuje całą stronę, zanim cokolwiek wyśle), potem pokazuje
procenty. Kółko na środku zostaje dla tego, na co czekamy tu i teraz.

Ceny tego rozwiązania: komputer pracuje ok. minuty na plik, nawet jeśli nikt nie powiększy;
liczymy konkretnie skalę 1:1 (inne powiększenia dalej liczą się na żądanie, blokami); każda
poprawka unieważnia kafelki poprawionej wersji, więc przebieg startuje od nowa; a komplet
kafelków siedzi potem w pamięci przeglądarki (na wydruku 3 m to ok. 100 kafelków).

### Rozdział „Jakość wydruku" na końcu

Sprawdzanie jakości liczy się długo, a poprawka wymiaru i tak unieważnia wynik (zmienia się
ppi na wydruku). Dlatego rozdział wędruje na sam koniec: najpierw wymiar, overprint, fonty
i kolory, a jakość sprawdza się na pliku już poprawionym — raz.

## Skala rastra oderwana od powiększenia („wczytaj raz, potem nawiguj")

Uwaga Tomasza, powtórzona: *„chcę żeby to się działo raz jak w Photoshopie i żebym potem
mógł przybliżać i oddalać i nawigować do woli po całym projekcie bez kolejnych wczytywań"*.

Przebieg w tle liczył całą stronę w rozmiarze rzeczywistym — i to działało — ale **adres
kafelka zawierał skalę wyświetlania**. Każde kliknięcie lupki zmieniało `s` w adresie, więc
siatka kasowała się i cała strona szła do Ghostscripta od nowa. Wystarczyło oddalić o jeden
krok, żeby zmarnować całą wcześniejszą robotę.

Teraz **skala rastra jest niezależna od powiększenia**:

- kafelki liczymy w **rozmiarze rzeczywistym (100 %)** — dokładnie w tej skali, którą liczy
  przebieg w tle,
- przy innym powiększeniu tylko **zmieniamy ich wielkość na ekranie** (`t.kd` — ile pikseli
  CSS przypada na piksel rastra); przeglądarka skaluje gotowe obrazki, serwer nie robi nic,
- powyżej 100 % wchodzą **szczeble 2× i 4×**, żeby lupka pokazywała prawdziwy detal pliku,
  a nie rozmyty piksel. Szczeble są trzy, więc adresy się powtarzają — drugie wejście w to
  samo powiększenie leci z cache przeglądarki.

Siatka liczy się teraz w pikselach **rastra**, nie ekranu: `Wr = own.w · k100 · szczebel`,
a widoczne kafelki wyznacza widok przeliczony przez `kd`. Kafelki kasujemy tylko wtedy, gdy
zmieni się skala rastra (inny szczebel, inna strona, inny plik) — przy samym powiększeniu
`tilesReposition()` przestawia to, co już wisi.

Współczynnik `k100` liczony jest z **zaokrąglonych** szerokości canvasu, tak samo jak
w `applyZoom()` i `warmPlan()`. To nie kosmetyka: ze zwykłego ilorazu skal wychodziła różnica
na czwartym miejscu po przecinku (1,3339 zamiast 1,3333), a to już inny adres kafelka i cały
przebieg w tle szedł w las.

### Zmierzone (`spady.pdf`, 30 MB, 973 × 1973 mm, okno 1600 × 950)

```
pierwsze wejście w 100 %          0,4 s   (32 kafelki, wszystkie z przebiegu w tle)
oddalenie o 4 kroki               0 żądań do serwera   (wcześniej: pełne przeładowanie siatki)
zbliżenie o 8 kroków (szczebel 2×) 11 żądań — tylko to, co widać
powrót do 100 %                   0,1 s   (z cache przeglądarki)
```

Minus, świadomy: przy powiększeniu **poniżej** 100 % ściągamy kafelki w pełnej rozdzielczości
i pomniejszamy je w przeglądarce, czyli przesyłamy więcej danych, niż widać. W zamian
zoom nie kosztuje ani jednego renderu. Przy dopasowaniu do okna kafelków i tak nie ma —
tam wystarcza podgląd bazowy.

## Przyspieszenie: koniec z liczeniem tego samego dwa razy

Pytanie Tomasza po tym, jak wczytywanie zaczęło działać: *„czy możemy to przyspieszyć?"*.
Zmierzone i poprawione po kolei.

### 1. Kafelek czeka na przebieg w tle, zamiast liczyć to samo obok niego

Największa strata — i najmniej oczywista. Gdy podgląd prosił o kafelek, którego przebieg
w tle jeszcze nie zdążył zapisać, serwer liczył go **osobno** blokiem 4 × 4. Wygląda to na
sprytne, a jest kosztowne: rozpakowanie wielkiego obrazu to praktycznie cały koszt renderu,
więc jeden blok kosztuje mniej więcej tyle, co CAŁA strona jednym przebiegiem — i jeszcze
odbiera procesor temu przebiegowi. Przy dwóch warstwach (suwak przed/po) ten sam obraz
rozpakowywał się trzy razy naraz.

Teraz zapytanie o kafelek najpierw sprawdza, czy przebieg w tle liczy **dokładnie to samo**
(ta sama strona, skala, wersja pliku), i jeśli tak — czeka na niego (`_wait_for_prerender`).
Czeka do 25 s, a gdy z tempa przebiegu wynika, że dany wiersz jest tuż-tuż, przedłuża
czekanie. Dopiero potem liczy kafelek sam.

```
wejście w 100 % zaraz po poprawce (spady.pdf, warstwa „po")
   przed:  14,4 s      po: 4,2 s
```

### 2. Kodowanie JPEG-ów obok Ghostscripta, nie po nim

Przebieg czytał pasmo, pakował z niego 12 kafelków, potem czytał następne. Przez ten czas
Ghostscript stał (bufor rury pełny). Teraz pakowanie idzie w wątkach obok — Pillow puszcza
GIL na czas kompresji, więc gdy my pakujemy jedno pasmo, GS liczy następne.

```
plik 60 MB, cała strona (108 kafelków)
   przed: 17,1 s      po: 14,1 s      (sam Ghostscript: 13,3 s — czyli jesteśmy już przy nim)
```

Kafelki wychodzą **bajt w bajt takie same** — sprawdzone na 108 z 108.

### 3. Warstwa zakryta suwakiem nie zabiera kolejki

Przy suwaku przed/po na „po" dolna warstwa jest niewidoczna, a jej kafelki i tak wchodziły
do kolejki jako „widoczne" i konkurowały z tym, na co użytkownik patrzy. Teraz warstwa
całkowicie zakryta ma kafelki tylko w tle.

### 4. Wątki Ghostscripta wg liczby rdzeni

`-dNumRenderingThreads` było zaszyte na 4; teraz tyle, ile rdzeni (do 8). Na maszynie
testowej (2 rdzenie) bez różnicy — wielki obraz i tak rozpakowuje się jednowątkowo.

### Co zmierzone i ODRZUCONE

- **`-dUseFastColor=true`** — kusząco szybkie: 13,2 s → 8,2 s (−38 %). Ale to zamiana
  przeliczania przez profil ICC na wzorki, a wynik różni się średnio o **25,8/255 na 70 %
  powierzchni**. Podgląd, który kłamie o kolorze, jest w tym programie bez wartości.
- **MuPDF zamiast Ghostscripta na cały przebieg** — 19,4 s pasmami i 21,9 s jednym
  pixmapem (przy 1,5 GB pamięci) wobec 13,3 s Ghostscripta. Odpada.
- **Render prosto do CMYK-a zamiast symulacji overprintu w RGB** — o tym niżej, bo to
  jedyna rzecz, która może dać jeszcze duży skok, ale wymaga decyzji o kolorze.

### Gdzie teraz idzie czas i co dalej

Po tych zmianach przebieg to praktycznie sam Ghostscript, a w nim: rozpakowanie wielkiego
obrazu, przeliczenie kolorów przez profil i — gdy plik używa overprintu — jego symulacja.
Ta symulacja bywa droga:

```
plik 60 MB, cała strona:   bez overprintu 14,5 s      z symulacją 51,1 s   (×3,5)
spady.pdf, cała strona:    bez overprintu  3,4 s      z symulacją  4,1 s   (×1,2)
```

Symulacja overprintu włącza się **sama** dla plików, które overprintu używają (a to
większość plików do druku) — bo bez niej podgląd nie pokazuje tego, co wyjdzie z maszyny.

Droga na skróty istnieje: renderować od razu na urządzenie **CMYK-owe** (`pamcmyk32`), gdzie
overprint jest zachowaniem naturalnym, a nie symulacją, i przeliczyć CMYK → sRGB naszym
własnym profilem. Zmierzone: **51,5 s → 16,9 s** plus ok. 0,5 s na 4 Mpx przeliczania ICC.

Ale to zmienia obraz: na pliku RGB różnica wychodzi 17,4/255 (bo dochodzi podróż RGB → CMYK
→ RGB), a nawet na pliku w całości CMYK-owym — 5,9/255. Zanim to wejdzie, trzeba porównać
oba warianty z Photoshopem na plikach Tomasza i zdecydować, który jest bliżej prawdy.
Do zrobienia, nie do zrobienia po cichu.

## Przebudowa: „wczytuje się raz, potem nawigacja bez doczytywania"

Uwaga Tomasza, po której cały mechanizm poszedł do przebudowy: *„jak przybliżam, to dalej
się ładuje; jak zmieniam obszar w nawigatorze, to znowu. Rozdział 9 — kolory — działa
w starej wersji. Wywal to i zrób raz a dobrze"*.

Diagnoza była nieprzyjemnie prosta: **trzy różne rzeczy kasowały policzoną stronę**.

1. `applyZoom()` wołało `tilesClear()` przy KAŻDEJ zmianie szerokości canvasu. Czyli każde
   drgnięcie lupki wyrzucało całą policzoną stronę i zaczynało od zera. (Ta linijka miała
   sens w starej wersji, gdy adres kafelka zawierał powiększenie — została po niej.)
2. Wejście na wyższy szczebel jakości (lupka powyżej 100 %) **kasowało szczebel niższy**,
   więc na czas doostrzania nie było czego pokazać: dziura i kółko „wczytuję".
3. Przebieg w tle był **jeden na zadanie**, a wersji pliku na ekranie bywa kilka: oryginał,
   plik po poprawkach i — przy suwaku w rozdziale — „wszystko oprócz tej jednej poprawki"
   (`wo:…`). Wejście w rozdział z suwakiem podmieniało dolną warstwę na wersję, której nikt
   nie policzył, więc doczytywała się kafelek po kafelku. Stąd „rozdział 9 działa w starej
   wersji" — bo faktycznie działał inaczej niż reszta.

### Jak jest teraz

**Jedna warstwa = jedna wersja pliku. Jedna wersja = jeden przebieg w tle.**

- Zaraz po wgraniu pliku serwer liczy CAŁĄ stronę w rozmiarze rzeczywistym jednym przebiegiem
  Ghostscripta. Robi to dla każdej wersji, która jest na ekranie — a przebiegi stoją
  w kolejce i idą pojedynczo (`_pre` trzyma teraz wpis na wersję, nie jeden na zadanie).
- Gdy przebieg się skończy, przeglądarka wciąga **całą stronę** (kafelki leżą gotowe na
  dysku, idą po kilkanaście na sekundę). Od tej chwili nawigator i przewijanie nie proszą
  serwera o nic.
- **Powiększenie nie kasuje niczego.** Tożsamość siatki (`key`) to wersja + strona + numer
  poprawki + szerokość przy 100 % — powiększenia w niej nie ma. Zmiana zoomu to tylko zmiana
  wielkości kafelków na ekranie (`kd`), robiona od razu, w tym samym rysowaniu co canvas.
- **Szczeble się nakładają, nie zastępują.** Szczebel 1 to cała strona w rozmiarze
  rzeczywistym; szczebel 2 (lupka) dokłada się NA WIERZCH tego, co już widać. Nic nie znika,
  obraz tylko się doostrza. Powyżej 200 % powiększamy szczebel 2 — tak jak Photoshop powyżej
  100 % powiększa piksele, zamiast kazać czekać na render 16× większy.
- **Kółko „wczytuję" pokazuje się tylko wtedy, gdy nie ma czym zastąpić** — czyli przy
  brakujących kafelkach szczebla 1 w widoku. Doostrzanie i doładowywanie reszty strony leci
  po obrazie, który już jest, więc nie ma o czym krzyczeć.

### Zmierzone (`spady.pdf`, 30 MB, 973 × 1973 mm, okno 1600 × 950)

```
wejście w 100 % po przebiegu w tle          0,3 s   (32 kafelki)
nawigacja po CAŁEJ stronie w 100 %          0 żądań do serwera
przybliżenie do ~230 % (szczebel 2×)        6 żądań, 0 klatek bez obrazu, 0× kółko
powrót do 100 %                             0 żądań
nawigacja po całej stronie w ~180 %         9 żądań, 0 klatek bez obrazu
```

Rozdział z suwakiem („Kolory", wersja `wo:cmyk`):

```
zamówione przebiegi: oryginał → base → fix → wo:cmyk   (wcześniej: tylko jeden)
wejście w wersję „wszystko oprócz kolorów"   6,8 s
nawigacja po całej stronie w tej wersji      0 żądań
```

Plik 60 MB (3020 × 2300 mm, 108 kafelków): przebieg w tle 68 s na maszynie testowej
(2 rdzenie), wejście w 100 % po nim — **0,4 s**.

### Czego NIE zrobiliśmy, żeby było szybciej

Tomasz postawił warunek: przyspieszać, ale nie tracąc danych. Symulacja overprintu zostaje
włączona (bez niej podgląd nie pokazuje tego, co wyjdzie z maszyny), kolory dalej idą przez
profil ICC. Odrzucone wcześniej `-dUseFastColor` i render do CMYK-a bez porównania
z Photoshopem — patrz rozdział wyżej. Cały zysk pochodzi z tego, że program **przestał
liczyć to samo po kilka razy**, a nie z liczenia gorzej.

### Pasek „pełna jakość" — dłuższy i nad podglądem

Pasek stał w rzędzie przycisków i miał sztywne 176 px: tekst się w nim nie mieścił, a po
poszerzeniu zderzał się z wyśrodkowanym przyciskiem „Podgląd szablonu" (uwaga Tomasza).
Przeniósł się więc **nad podgląd**, do prawego górnego rogu tuż pod rzędem przycisków:
szerokość dobiera się do treści, pasek postępu ma 130 px, tekst jest półgruby, a plakietka
dostała obwódkę i cień, żeby było ją widać na każdym projekcie. Kółko na środku podglądu
zostaje bez zmian — mówi o tym, na co czekamy tu i teraz.

---

## 2026-09-10: cały mechanizm pełnej jakości USUNIĘTY

Decyzja Tomasza: *„wczytywanie pełnej jakości jest mocno skopane. Proponuję, żebyśmy je
zrobili od nowa, ale najpierw usuń wszystko, co jest z tym związane — paski ładowania,
wczytywanie pełnej jakości — tak aby po użyciu lupki nie wczytywała się pełna jakość."*

Wszystko powyżej w tym rozdziale opisuje mechanizm, którego **już nie ma w kodzie**.
Zostaje jako zapis tego, co było zrobione i czego się nauczyliśmy — przy pisaniu nowego
warto tu zajrzeć, żeby nie wdepnąć drugi raz w te same rzeczy (skala w adresie kafelka,
kasowanie siatki przy zoomie, jeden przebieg na zadanie zamiast na wersję pliku, liczenie
tego samego dwa razy).

### Co konkretnie zniknęło

**Przeglądarka** (`app/static/app.js`, `index.html`, `app.css`)
- silnik kafelków: `makeTiles`, `lvGet`/`lvDrop`, `tilesUpdate`, `tilesRun`, `tileStart`,
  `tilesReposition`, `tilesProgress`, stałe `TILE_*`, szczeble jakości,
- przebieg w tle: `warmSync`, `warmPoll`, `warmPlan`, `warmProg`, `warmReady`, `layerW100`,
- pasek „pełna jakość" (`#tileProg` + style `.tile-prog`, `.tp-bar`, `.tp-txt`),
- warstwy kafelków `#tiles` i `#tilesFix` (razem ze stylami `.tiles`),
- pozycja `tiles` w kółku „na co czekamy" (zostają `fixrun`, `fiximg`, `base`).

**Serwer** (`app/server.py`)
- `GET /api/jobs/<id>/tile.jpg` i `GET|POST /api/jobs/<id>/prerender`,
- `_pre`, `_pre_worker`, `_pre_drop`, `_wait_for_prerender`, `_tile_cluster`,
  `_cluster_locks`, `_write_atomic`, `PRE_WAIT_MAX`.

**Render** (`app/preview.py`)
- `render_page_tiles`, `render_tile_cluster`, `render_tile_jpeg`, `cluster_side`,
  `needs_gs`, `page_px`, `_edge_lighter`, `TILE_CLUSTER*`, podręczna pamięć list
  wyświetlania (`_cached_doc`, `TILE_DOC_CACHE`).

### Druga tura sprzątania (po pytaniu „na pewno nic nie zostało?")

- **`GET /api/jobs/<id>/region.png`** — trasa renderu wycinka w wysokiej rozdzielczości.
  Była poprzedniczką kafelków (podgląd 100 % przed nimi) i po ich usunięciu nikt jej już nie
  wołał. Sama funkcja `preview.render_region_png` **zostaje** — z niej czytają analiza
  rastrów i mapa detalu, tam render wycinka jest narzędziem pomiarowym, nie podglądem.
- **Podręczna pamięć list wyświetlania** (`_cached_doc`, `TILE_DOC_CACHE`) — obsługiwała
  wyłącznie kafelki. Został sam rejestr otwartych dokumentów, którego potrzebuje `forget_doc`.
- **Przedrostki plików pamięci podręcznej** w katalogu zadania: sprzątanie wymieniało `tf`,
  `rf`, `tb`, `rb`, `tw`, `rw` (kafelki i wycinki). Dziś powstają tylko rendery stron, więc
  lista to `pf`, `pb`, `pw` i `wo_`.

Sprawdzone na całym projekcie (`grep` po `*.py`, `*.js`, `*.html`, `*.css`, `*.bat`):
zero trafień na `prerender`, `tile.jpg`, `tileProg`, `warmSync`, `render_page_tiles`,
`render_tile_*`, `cluster_side`, `needs_gs`, `TILE_*`, `_cached_doc`, `layerW100`.
Zostały tylko `TILE_MAX_DECODE_PX` i `BAND_MAX_PX` w `analyze.py` — to **inna rzecz**:
analiza realnego detalu przegląda obraz kafelek po kafelku i nie ma nic wspólnego z podglądem.

Pełny przebieg w przeglądarce (wgranie → produkt → spady → wymiar → overprint → suwaki →
lupka → nawigacja → „Dopasuj") woła dziś wyłącznie:

```
/api/upload · /api/jobs/<id>/analysis · /api/jobs/<id>/frames
/api/jobs/<id>/fix · /api/jobs/<id>/page/<n>.png · /api/products · /api/sizeindex/status
```

Zero błędów w konsoli (poza brakiem `favicon.ico`, który był zawsze).

### Co zostało

- `render_png` — render strony do 1600 px (podgląd bazowy) i `render_region_png` — render
  wycinka (mapa jakości, „Pokaż"),
- `forget_doc` — zamyka otwarte dokumenty przed nadpisaniem pliku (na Windowsie warunek
  konieczny, żeby poprawka mogła podmienić `fixed.pdf`),
- kółko „na co czekamy" — dla renderu strony, poprawek i wersji porównawczej.

Podgląd pokazuje więc teraz **tylko render bazowy**, skalowany przez przeglądarkę. Lupka
nic nie dociąga: powiększenie jest miękkie, ale natychmiastowe i nic się nie liczy w tle.

Sprawdzone po usunięciu (`spady.pdf`): po wgraniu, po „100 %", po sześciu krokach lupki
i po przewinięciu przez całą stronę — **zero zapytań `tile.jpg` i `prerender`**, brak
paska, brak kółka, zero błędów w konsoli. Rozdziały (ramki, spady, wymiar, poprawki)
działają bez zmian.

---

## 2026-09-10: nowy mechanizm — PIRAMIDA

Prośba Tomasza po usunięciu starego: *„chciałbym, żeby to wczytywanie pełnej jakości działo
się tak jak w Photoshopie — obraz wczytuje się raz, a potem operacje i przemieszczanie się
nawigatorem nie każą czekać. Pasek postępu zostaw jeden, w widocznym miejscu, ale nie na
środku podglądu."*

### Skąd wzięła się ta konstrukcja

Photoshop nie ma czego przeliczać: przy imporcie rasteryzuje PDF-a RAZ i od tej chwili
dokument to piksele. My mamy PDF-a i każda poprawka robi nowy PDF, więc uczciwy podgląd
wymaga renderu. Robimy więc to samo świadomie: **jeden przebieg Ghostscripta na wersję
pliku**, wynik pokrojony na kafelki i zapisany na dysku. Przeglądarka już tylko **czyta
gotowe pliki** — trasa kafelka (`/px/…`) nic nie renderuje, nigdy. Dlatego przewijanie
i nawigator nie mają na co czekać.

Rozdzielczość: **120 ppi na wydruku** (decyzja Tomasza — „żeby przy 100 % było widać mniej
więcej to samo co po wydruku"). To ten sam próg, którym mierzymy jakość rastrów, więc jeden
piksel podglądu = jeden piksel wydruku na granicy tego, co uznajemy za ostre. Sufit 400 Mpx;
powyżej schodzimy z ppi i piszemy o tym w planie (`plan.uwaga`).

### Piramida, a nie jedna bitmapa

Poziom 0 to pełna rozdzielczość, każdy następny o połowę mniejszy, aż strona zmieści się
w ~1400 px. Dwie rzeczy dają wrażenie „nic się nie wczytuje":

1. **Podkład.** Największy poziom mieszczący się w ok. 6 Mpx (kilka kafelków) ładuje się
   w całości i wisi pod spodem zawsze. Przy każdym powiększeniu JEST więc co pokazać w tej
   samej chwili — obraz najwyżej się doostrza, nigdy nie ma pustego miejsca.
2. **Nic nie znika przy zmianie wersji.** Po poprawce nowa piramida liczy się w tle, a na
   ekranie zostają kafelki poprzedniej — podmieniamy je dopiero, gdy nowa jest gotowa
   w CAŁOŚCI (wybór Tomasza: „trzymaj stary obraz do końca"). Zmierzone: zero klatek
   z pustym podglądem.

Poziomy 1..n budujemy z gotowych kafelków poziomu wyżej (cztery → jeden), a nie kolejnymi
przebiegami Ghostscripta: kilka sekund zamiast kilku minut, a wynik nie do odróżnienia od
uśrednienia pikseli.

### Gdzie co siedzi

| Miejsce | Co robi |
|---|---|
| `app/pyramid.py` | `plan()` — ile pikseli i poziomów; `build_quick()` — szybki podkład całej strony; `build_level0()` — jeden przebieg GS, krojenie w locie; `build_levels()` — poziomy niżej z dysku; `dirty_tiles()` — które kafelki dotyka zmiana (pod przyszłe poprawki miejscowe) |
| `POST/GET /api/jobs/<id>/view` | zamawia piramidę dla TEJ wersji pliku i mówi, jak idzie |
| `GET /api/jobs/<id>/px/<key>/L<p>_<x>_<y>.jpg` | kafelek — **czysty odczyt z dysku**, brak pliku = 404 i klient pokazuje niższy poziom (`Q…` = ten sam kafelek z szybkiego podkładu) |
| `app/static/app.js` | `pyrSync` (zamawianie + odpytywanie), `pyrDraw` (podkład + poziom pod powiększenie), `pyrProg` (jeden pasek) |

Klucz piramidy to wersja + strona + numer poprawki + szerokość rastra. **Powiększenia w nim
nie ma** — zoom nie unieważnia niczego. Wymiar wydruku owszem: potwierdzenie produktu w skali
1:10 to inny wydruk (10× większy), więc inna rozdzielczość — stary przebieg jest wtedy
przerywany, żeby nie zajmował procesora nowemu.

### Zmierzone

Pierwszy przebieg (maszyna testowa, 2 rdzenie — u Tomasza szybciej):

| Plik | Wydruk | Piramida | Czas | Kafelki | Dysk |
|---|---|---|---|---|---|
| `spady.pdf` (30 MB) | 973 × 1973 mm | 4598 × 9323 px (43 Mpx) | 5–7 s | 73 | 10,7 MB |
| `ramki_w.pdf` (115 MB) | 1015 × 2513 mm | 4795 × 11872 px (57 Mpx) | 7,3 s | 87 | 10 MB |
| `1878` (60 MB) | 3020 × 2300 mm | 14268 × 10866 px (155 Mpx) | 27–29 s | 213 | 61 MB |
| `adWall` 1:10 | 6160 × 2320 mm | 29102 × 10961 px (319 Mpx) | 18 s | 444 | 24 MB |

Po przebiegu (`spady.pdf`, okno 1600 × 950):

```
wejście w 100 %                    12 kafelków z dysku, natychmiast
nawigacja po CAŁEJ stronie w 100 % 34 odczyty z dysku, ani jednej pustej klatki
przybliżanie i oddalanie           0 zapytań
poprawka (spady)                   0 klatek z pustym podglądem, nowa piramida w tle
rozdział „Kolory" (wersja wo:cmyk) własna piramida 8,9 s, potem nawigacja = same odczyty
```

Pasek postępu: **jeden**, w górnym pasku obok nazwy pliku. Nazwa ustępuje mu miejsca
(wielokropek), a lewa grupa nigdy nie dochodzi do środka, gdzie stoi „Podgląd szablonu".

### Co jeszcze przed nami

Dziś każda poprawka to nowa piramida — jeden przebieg w tle, bez migania, ale jednak
przeliczenie. Następny krok to **poprawki miejscowe**: `fonty na krzywe` nie zmieniają obrazu
(zmierzone: 0,32/255 średnio, tylko 0,78 % powierzchni na krawędziach liter), `spady` to samo
przycięcie, a `ramki` i `overprint` zmieniają wyłącznie te miejsca, gdzie stały te obiekty —
`pyramid.dirty_tiles()` i tryb `only=` w `build_level0()` już na to czekają. Wtedy zostanie
jeden przypadek, w którym naprawdę trzeba przeliczyć wszystko: konwersja kolorów.

### Trzy błędy zgłoszone zaraz po włączeniu piramidy

**1. Suwak porównania działał skokowo — 0 i 50 % wyglądały tak samo, dopiero 100 % pokazywało
wersję „po".** Winne było układanie warstw w CSS. `.art` (oryginał) nie tworzył własnego
kontekstu układania, więc `z-index` kafelków piramidy uciekał do canvasu i kafelki oryginału
zasłaniały CAŁĄ warstwę „po poprawkach". Przy `opacity: 1` warstwa „po" wygrywała kolejnością
w DOM-ie (stąd działające 100 %), a przy każdej innej przezroczystości przegrywała z-indeksem.
Obie warstwy dostały `z-index` i `isolation: isolate`, więc numery kafelków zostają w środku.
Zmierzone po poprawce: 0 → 50 to różnica 0,79/255, 50 → 100 to 0,76 — czyli suwak miesza
liniowo, tak jak powinien.

**2. Suwak w rozdziale pokazywał NIE TEN rozdział.** Po wejściu w suwak „Kolory" dolna warstwa
ma pokazywać plik ze wszystkimi poprawkami OPRÓCZ kolorów (`wo:cmyk`). Piramida dolnej warstwy
była jeszcze poprzedniej wersji, a zasada „trzymaj stary obraz do końca" kazała ją pokazywać —
więc suwak porównywał overprinty zamiast kolorów. Teraz każda warstwa pamięta, DLA JAKIEJ
wersji są jej kafelki (`pyrFresh`); gdy wersja się zmieni, piramida znika, a warstwa wraca na
podgląd bazowy — miękki, ale **właściwej wersji**. Sprawdzone: po ruszeniu suwaka rozdziału
dolna warstwa pokazuje `wo:cmyk` od razu, a piramida wraca, gdy się doliczy.

**3. „Naprawa overprintu zmienia lekko kolory całego projektu."** Nie zmienia — zmierzone na
`spady.pdf`: sama poprawka rusza 0,1 % powierzchni. Zmieniał się **renderer**. Podgląd bazowy
liczy MuPDF (szybko, ale CMYK przelicza wzorem, bez profilu), a piramida — Ghostscript
z FOGRA39. Gdy jedna warstwa pokazywała piramidę, a druga podgląd bazowy, cały projekt zmieniał
odcień. Zmierzone: **7,4/255 średnio na 60 % powierzchni** (`ramki_w`) i **8,9/255 na 80 %**
(`fonty.pdf`). Teraz obie warstwy są zawsze w tym samym stanie: albo obie z piramidy, albo
obie z podglądu bazowego. Przy okazji, gdy piramida jest widoczna, podgląd bazowy pod nią jest
chowany — nie ma jak przebić się na krawędziach.

Zostaje jedna różnica, świadoma: **kilka sekund po wgraniu, gdy piramida wchodzi, kolory
lekko się poprawiają**. To nie błąd — to moment, w którym podgląd przestaje pokazywać
przybliżenie MuPDF-a, a zaczyna prawdę Ghostscripta z profilem. Można to usunąć, licząc też
podgląd bazowy Ghostscriptem, ale wtedy pierwszy obraz po wgraniu pojawia się o kilka sekund
później (zmierzone: 3,4 s zamiast ~1 s na `spady.pdf`, 13 s na pliku 60 MB) — do decyzji.


## 2026-09-10: „czemu tak długo? w Photoshopie i w Readerze jest szybciej"

Pytanie Tomasza po włączeniu piramidy. Zmierzone, a nie zgadywane — plik `1878…` (60 MB),
wydruk 3020 × 2300 mm, maszyna testowa z **dwoma rdzeniami** (u Tomasza jest ich więcej).

### Gdzie idzie czas

Cały czas to Ghostscript. Nasze krojenie i zapis JPEG-ów to pojedyncze procenty.
A w samym Ghostscripcie czas dzieli się na dwie zupełnie różne rzeczy:

| Co | Ile |
|---|---|
| render podkładu 1783 × 1358 px (2,4 Mpx) | 7,24 s |
| ten sam render w **połowie** tej rozdzielczości | 6,89 s |
| ten sam render w **ćwiartce** | 6,74 s |

Czyli: **rozdzielczość prawie nic tu nie kosztuje**. 6,7 s idzie na otwarcie pliku,
rozpakowanie obrazów, wczytanie fontów, rozłożenie przezroczystości i przeliczenie kolorów
przez profil — to trzeba zrobić raz, choćby dla jednego piksela. Dopiero potem dochodzi
malowanie pikseli, i ono skaluje się z powierzchnią: połowa powierzchni to 48 % czasu,
ćwiartka 28 %.

Do tego dochodzą dwie rzeczy, które sami sobie dokładamy świadomie:

* **symulacja nadruku** (overprint) — 2,92× (19,9 s zamiast 6,8 s na `spady.pdf`). Adobe
  Reader jej domyślnie nie robi. My musimy: bez niej nie widać, co naprawdę wyjdzie z maszyny.
* **cała strona zamiast tego, co widać** — 155 Mpx zamiast 2 Mpx okna.

### Dlaczego Reader i Photoshop wydają się szybsze

Bo robią **co innego**:

* **Adobe Reader** rasteryzuje wyłącznie to, co masz na ekranie — jakieś 2 Mpx. Przewiniesz
  albo przybliżysz — liczy od nowa ten kawałek. Dlatego otwiera się w sekundę i dlatego przy
  szybkim przewijaniu po dużym pliku widać, jak dociąga. My poszliśmy w drugą stronę,
  bo tego chciałeś: policzyć raz **wszystko**, żeby potem nawigacja nigdy nie czekała.
* **Photoshop** przy imporcie PDF-a robi dokładnie to co my — rasteryzuje całość w zadanej
  rozdzielczości. Na Twoim zrzucie było 6159,92 × 2320,08 mm przy 120 ppi, czyli 319 Mpx.
  Ten import też trwa; różnica jest taka, że tam czekanie jest w okienku „Import PDF"
  i wygląda na część otwierania pliku, a u nas działo się po wgraniu.

### Co z tym zrobiliśmy: szybki podkład

Skoro rozdzielczość prawie nic nie kosztuje, a otwarcie pliku kosztuje wszystko, to **jeden
krótki przebieg daje cały projekt na ekran za ułamek ceny**. Więc: równolegle z poziomem 0
leci drugi, mały przebieg Ghostscripta w rozdzielczości poziomu podkładowego (ok. 2–5 Mpx).
Kończy się po kilku sekundach i od tej chwili **widać cały projekt** — już z Ghostscripta,
z profilem i z symulacją nadruku, więc kolory się potem nie przeskakują. Ostre kafelki
dochodzą na wierzch pasmami, w miarę jak leci poziom 0.

Równolegle, a nie po kolei — bo koszt tego przebiegu to prawie wyłącznie wczytanie PDF-a,
czyli praca, która i tak czeka na dysk i na pojedynczy rdzeń. Zmierzone:

| | pierwszy obraz na ekranie | cała piramida |
|---|---|---|
| przed zmianą | 31,2 s | 31,2 s |
| podkład **po kolei** z poziomem 0 | 7,9 s | 35,7 s |
| podkład **równolegle** (tak zostało) | **7,9 s** | **30,7 s** |

Czyli obraz jest **cztery razy wcześniej**, a całość ani trochę nie zwolniła (dwa rdzenie;
na maszynie z większą liczbą rdzeni różnica będzie jeszcze mniejsza).

Przy okazji dwie rzeczy w kliencie:

* dopóki nie ma czym zasłonić podglądu bazowego, warstwa piramidy w ogóle nie wchodzi —
  wcześniej potrafiła zasłonić obraz pustką na czas liczenia;
* nie prosimy o kafelki, których jeszcze nie ma (klient wie z paska postępu, ile pasm poziomu 0
  jest gotowych). Zmierzone: **517 pustych zapytań → 0**.

Kafelki podkładu mają własne nazwy (`Q…`), a nie nadpisują docelowych (`L…`), z dwóch
powodów: przeglądarka trzyma kafelki pod adresem, więc nadpisany plik i tak by do niej nie
dotarł, a podkład liczony wprost w małej rozdzielczości potrafi zgubić włosową linię.
Gdy piramida jest gotowa, klient przechodzi na `L…` (te powstają z uśrednienia poziomu 0,
więc nie gubią nic) — i robi to **bez mrugnięcia**: stary kafelek znika dopiero, gdy nowy
się wczyta. Zmierzone na tej podmianie: średnia różnica na kolorach 0,2 / 0,7 / 2,4 na 255
(R/G/B), czyli obraz się „ustawia", a nie zmienia barwę.

### Co jeszcze można ugrać (i czego nie warto)

* **Poprawki miejscowe** — największa rzecz przed nami. Dziś każda poprawka to nowa piramida
  (u Tomasza kilkanaście sekund). `dirty_tiles()` i `only=` czekają gotowe.
* **Poziomy niżej** — już zrównoleglone: 4,2 s → 2,2 s.
* **Wątki Ghostscripta** — już włączone, ale to nie jest złoty strzał: 1 wątek 4,3 s,
  2 wątki 3,1 s (1,39×), bo wczytywanie pliku zrównoleglić się nie da.
* **Ręczny podział strony na pasy i kilka Ghostscriptów naraz** — sprawdzone i odrzucone:
  tyle samo czasu (bo każdy proces musi wczytać plik od nowa), a do tego rozjeżdżało się
  próbkowanie na styku pasów (różnica 5,3/255 wobec jednego przebiegu).
