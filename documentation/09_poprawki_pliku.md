# 09 · Poprawki pliku (pierwsza: overprint)

Pierwsza poprawka, którą program faktycznie **wykonuje** na pliku. Moduł jest zbudowany
jako rejestr, żeby dokładanie kolejnych było dopisaniem funkcji i wpisu, a nie
przebudową.

## Zasady (ustalone na początku projektu, tu egzekwowane w kodzie)

1. **Oryginał nigdy nie jest nadpisywany.** Poprawiona wersja to osobny plik
   (`fixed.pdf` w katalogu zadania). Serwer wybiera plik do renderu przez `?v=fix`;
   bez tego parametru zawsze idzie oryginał.
2. **Nic nie dzieje się samo.** Poprawkę uruchamia przycisk.
3. **Poprawka mówi, co zmieniła** — liczbami, nie słowem „gotowe":
   „overprint wyłączony w 1 stanach graficznych".

## `fixes.remove_overprint`

Ustawia `/OP` i `/op` na `false` we wszystkich stanach graficznych (ExtGState), które
je włączały. `/OPM` zostaje — przy `OP = false` nie ma znaczenia, a kasowanie tylko
zwiększałoby różnicę wobec oryginału.

Dlaczego to jest naprawa, a nie psucie pliku: overprint sprawia, że farba kładzie się
NA tle zamiast je wybijać, więc czerwone „D" na czarnym tle wychodzi prawie czarne —
choć projektant widział czerwone. Wytyczne Adsystem overprintu zabraniają, więc
naprawa = wyłączyć go i wydrukować to, co widać w projekcie.

Sprawdzone na `Prosta 600 Ø43`: 1 stan graficzny (używany 34 razy w treści), 0,10 s,
rozmiar pliku bez zmian (1,99 MB). Po poprawce `uses_overprint()` zwraca `False`,
a render „jak z drukarki" różni się od oryginału w **0,52 %** pikseli — dokładnie tam,
gdzie overprint działał (litera D i kwadrat RAC1).

## Suwak porównania

Pod podglądem, przenikanie przezroczystością: **0 % = przed poprawkami**, **100 % = plik po
poprawkach**. Dwie warstwy w tym samym układzie współrzędnych (bazowy render + własna
siatka kafelków każda), więc porównanie działa też w powiększeniu 100 %.

Rzecz najważniejsza dla uczciwości porównania: **obie warstwy renderujemy tak, jak
wyjdą z drukarki** (z symulacją overprintu). Gdyby oryginał renderować „ekranowo",
suwak pokazywałby różnicę renderowania, a nie skutek poprawki — i wyglądałoby na to,
że poprawka nic nie zmienia, bo obie strony byłyby czerwone.

Koszt: dwie warstwy kafelków, więc sufit kafelków na skalę dzielony przez 2
(300 zamiast 600 na warstwę). Bazowy render 1600 px: 0,39 s na wersję.

### Punktem odniesienia jest plik po dopasowaniu wymiaru (2026-09-08)

Uwaga Tomasza: po dopasowaniu wymiaru przesunięcie suwaka w lewo kasowało **dołożone tło** —
projekt wracał do starego formatu, a margines znikał. To myliło, bo tło nie jest „poprawką
do obejrzenia", tylko nowym stanem wyjściowym: **wszystko, co robimy dalej, robimy na pliku
o właściwym wymiarze**.

Dlatego poprawka wymiaru zapisuje **dwa pliki**: `base.pdf` (sam wymiar) i `fixed.pdf`
(wymiar + reszta). Lewy koniec suwaka to `?v=base`, prawy `?v=fix`, a napis brzmi
**„przed poprawkami · po dopasowaniu wymiaru"** zamiast „oryginał". Obie warstwy mają wtedy
tę samą stronę, więc leżą dokładnie na sobie (ta sama siatka kafelków, te same adresy z innym
`v=`) — wcześniej warstwa oryginału zajmowała tylko wycinek płótna.

Skutek uboczny, celowy: **przy samym wymiarze suwak w ogóle się nie pokazuje** — obie warstwy
byłyby identyczne i suwak nic by nie zmieniał. Pojawia się przy pierwszej poprawce nałożonej
na dopasowany plik. Bez poprawki wymiaru punktem odniesienia jest, jak dawniej, oryginał.

## `fixes.resize_page` — dopasowanie wymiaru

Domyślnie proponujemy **„wypełnij format"** (ustalenie Tomasza: bez pustych pasów,
nadmiar przycięty), ale użytkownik może zejść niżej. Proporcje nigdy nie są zmieniane.

### Skala liczona od WŁASNEGO rozmiaru projektu (poprawka)

Pierwsza wersja miała suwak „100–180 %", gdzie **100 % znaczyło „minimalne wypełnienie
formatu"**. Na pliku `adStand_Light_85` (850 × 2100 mm) na formacie 4030 × 2280 mm
pokazywało to „skala 100 %", choć projekt był w rzeczywistości powiększony **474 %**.
Tomasz: „to niemożliwe, projekt powinien być mniejszy od szablonu, a się dziwnie do
niego powiększył". Miał rację — liczba nie znaczyła tego, co znaczy dla człowieka.

Teraz **100 % = projekt w swoim własnym rozmiarze**. Zakres suwaka jest wyliczany
z pliku (od połowy „całego projektu" do dwukrotności „wypełnienia"), więc dla każdego
pliku da się zejść poniżej wartości domyślnej. Do tego trzy przyciski skrótu z
konkretnymi liczbami:

| przycisk | co ustawia | przykład (850×2100 na 4030×2280) |
|---|---|---|
| wypełnij format | `max(tw/sw, th/sh)` | 474 % |
| cały projekt | `min(tw/sw, th/sh)` | 109 % |
| rozmiar pliku | 1,0 | 100 % |

| suwak | znaczenie |
|---|---|
| skala projektu | wielkość projektu względem jego własnego rozmiaru |
| przesuń w poziomie / pionie | co zostaje, gdy projekt wystaje — albo gdzie leży, gdy jest mniejszy |

Suwak przesuwania jest nieaktywny („dokładnie pasuje"), gdy na danej osi nie ma ani
nadmiaru, ani luzu.

### Wstawianie bez zniekształceń w obie strony

`place_rect()` liczy prostokąt, w który trafia **cała** strona źródłowa, i
`show_pdf_page()` dostaje ten prostokąt bez parametru `clip`. PyMuPDF przycina to, co
wystaje poza stronę (sprawdzone). Dzięki temu ta sama funkcja obsługuje wypełnienie
(projekt większy, nadmiar odcięty) i zmieszczenie całości (projekt mniejszy, puste pasy)
— i **w żadnym przypadku nie zmienia proporcji**.

Poprzednia wersja liczyła okno pliku i mapowała je na cały format przez `clip`. Przy
skali poniżej wypełnienia okno wychodziło poza plik, było przycinane do jego krawędzi,
a mapowanie na pełny format **rozciągało obraz**. Błąd nigdy się nie ujawnił, bo suwak
zaczynał się dokładnie na wypełnieniu — ale czekał.

### Jak to wygląda w podglądzie (poprawione po uwadze Tomasza)

Pierwsza wersja rysowała **ramkę wycinka na pliku**: plik stał w miejscu, a ramka
„co zostanie" jeździła po nim przy ruchu suwaka. Tomasz: „kompletnie nie rozumiem".
Słusznie — to jest odwrotność tego, co człowiek robi w głowie.

Teraz jest tak, jak on to opisał:

- **obszar wydruku stoi w miejscu** — jasny prostokąt to szablon z wytycznych
  (niebieska linia), podgląd przełącza się w tryb, w którym płótno *jest* obszarem
  wydruku,
- **projekt skaluje się i przesuwa pod nim** (suwak „skala projektu" 100–180 %),
- **wszystko poza obszarem wydruku jest przyciemnione** — to zostanie odcięte.

`cover_window()` liczy okno pliku trafiające na format; **ta sama arytmetyka jest
w Pythonie i w JS** — dzięki temu podgląd pokazuje dokładnie to, co potem wytnie
serwer. Podgląd jest natychmiastowy (przeliczany lokalnie), plik liczy się dopiero po
kliknięciu.

W trybie dopasowania kafelki pełnej jakości są wyłączone: tu liczy się układ, nie
piksele, a kafelki i tak trzeba by przeliczyć po każdym ruchu suwaka. Nawigator też
znika — jego miniatura pokazuje stronę pliku, a płótno jest teraz kompozycją
„format + projekt", więc ramka widoku kłamałaby.

### Trzy warstwy podglądu

| warstwa | co pokazuje | kolejność |
|---|---|---|
| projekt | plik, skalowany suwakiem | na dole |
| **zielona linia przerywana** | **dokładny format z wytycznych** (600 × 227 mm, z podpisem także w mm wydruku) | nad projektem |
| szablon (czerwony/niebieski) | obszar ochronny i kształt produktu | na górze |

Zielona linia była potrzebna, bo granicę formatu wyznaczało dotąd tylko przejście
między jasnym a przyciemnionym tłem — czytelne przy dużym kontraście, gubiące się na
ciemnym projekcie. Teraz format ma własną, jednoznaczną linię z wymiarem.

### Płótno obejmuje format ORAZ projekt

Pierwsza wersja robiła płótno wielkości samego formatu, a projekt wystawał poza nie.
Przeglądarka rozszerza obszar przewijania **tylko w prawo i w dół**, więc przy
powiększaniu projektu podgląd uciekał w prawy dolny róg, a format w lewy górny.

Teraz płótno to **suma prostokątów** (format ∪ projekt), a `fitBox` pamięta, gdzie
wewnątrz płótna leży format. Po każdym przeliczeniu widok jest przewijany tak, żeby
**środek formatu był na środku okna**. Do tego `fitScale()` w tym trybie mierzy
*obszar wydruku*, nie stronę pliku — dzięki temu format ma stale tę samą wielkość na
ekranie niezależnie od skali projektu, a suwak przesuwa tylko projekt pod nim.

### Dokładanie tła na marginesach („dilation")

Gdy projekt jest mniejszy od formatu, zostaje biel — drukarka wypluje białą ramkę.
Rozwiązanie z eksportu tekstur (Substance Painter): **piksele z krawędzi rozciągnięte
na zewnątrz**, żeby nie było pustych przestrzeni.

`_fill_edges()` robi to samo, tylko wektorowo: **osiem wstawień tej samej strony**
(4 boki + 4 narożniki), każde przycięte do paska **3 mm** przy odpowiedniej krawędzi
i rozciągnięte na margines. Wektor zostaje wektorem, rastry rastrami — nic nie jest
rasteryzowane, bo to nadal `show_pdf_page(clip=…)`.

| wstawienie | wycinek źródła | gdzie ląduje |
|---|---|---|
| lewy bok | pasek 3 mm przy lewej krawędzi, pełna wysokość | lewy margines, wysokość projektu |
| prawy / górny / dolny | analogicznie | odpowiedni margines |
| 4 narożniki | kwadracik 3 × 3 mm z narożnika | narożnik marginesu |

Kolejność rysowania: **najpierw tło, potem projekt** — inaczej paski zakryłyby brzeg
projektu.

**`keep_proportion=False` jest tu kluczowe.** Domyślnie `show_pdf_page` zachowuje
proporcje wycinka: wąski pasek 3 mm × 232 mm wpasowywał się w szeroki margines jako
cienka kreska pośrodku, a reszta zostawała biała. Efekt na pliku Tomasza: biała strona
z czterema czarnymi kwadratami w narożnikach i dwiema poziomymi kreskami — czyli
dokładnie „wpasowane z zachowaniem proporcji" osiem wycinków. Chcemy rozciągnięcia,
więc proporcje trzeba wyłączyć.

**Pasek liczymy od 1 mm w głąb, nie od samej krawędzi** (`EDGE_SKIP_MM`). Ostatnie
piksele przy krawędzi strony bywają jaśniejsze od wygładzania krawędzi renderu i po
rozciągnięciu dawały widoczny jasny pas wzdłuż całego marginesu.

Sprawdzone na 1878 (zdjęcie dochodzące do krawędzi): niebo, drzewa i bruk przechodzą
płynnie na margines. Na pliku, który ma własną białą ramkę w środku strony, dilation
powiela tę ramkę — to poprawne zachowanie (rozciągamy to, co jest przy krawędzi), ale
warto o tym wiedzieć.

Podgląd na żywo robi **dokładnie tę samą konstrukcję ośmiu pasków w CSS** (z tym samym
odsunięciem od krawędzi), więc pokazuje to, co naprawdę wyjdzie, a nie przybliżenie.
Przełącznik „dołóż tło na marginesach" w panelu wymiaru; domyślnie włączony.

### Tryb kadrowania tylko przy „Dopasuj"

Tryb kadrowania (płótno = obszar wydruku, kafelki wyłączone) był włączony **na stałe**
dla każdego pliku o innym wymiarze. Skutek: kliknięcie „100 %" przed sprawdzeniem
jakości dawało rozmazany podgląd, który nigdy się nie doładowywał — kafelki pełnej
jakości były zablokowane.

Teraz kadrowanie działa **tylko przy powiększeniu „Dopasuj"**. Po kliknięciu 100 %, +
albo kółkiem wraca zwykły podgląd pliku z kafelkami. Panel mówi to wprost.

### Ostrzeżenie o zupełnie innych proporcjach

Gdy wypełnienie formatu odcięłoby **ponad 25 %** projektu, panel mówi to wprost:
proporcje pliku, proporcje formatu, ile procent zniknie i zdanie *„sprawdź, czy to na
pewno plik do tego produktu"*. Bo najczęściej to właśnie znaczy — plik 850 × 2100 mm na
formacie 4030 × 2280 mm traci 77 % treści; automatyczne przycięcie w takiej sytuacji
byłoby ciche i szkodliwe. Dla pliku, który prawie pasuje (4030 × 2270), strata to 0,4 %
i ostrzeżenia nie ma.

Sama zamiana: nowa strona o wymiarze docelowym, treść wstawiona przez
`show_pdf_page(clip=…)` jako **obiekt formy** — wektor zostaje wektorem, rastry
rastrami, nic nie jest rasteryzowane.

Sprawdzone: `Prosta 600 Ø43` 616×232 mm → 600×227 mm, powiększenie 112 %, przesunięcie
w lewo: proporcje wyniku 2,645 wobec oczekiwanych 2,643 (różnica z zaokrąglenia punktów).

### Kolejność poprawek ma znaczenie

**Najpierw wymiar** (PyMuPDF, przebudowa strony), potem poprawki **na obiektach**
(overprint, pikepdf). `apply_fixes` wymusza tę kolejność niezależnie od tego, w jakiej
użytkownik włączy poprawki.

Do 2026-09-08 było odwrotnie, z obawy, że po przebudowie strony overprint schowa się
w zagnieżdżonym obiekcie formy. Obawa okazała się nieuzasadniona: `remove_overprint`
chodzi po **wszystkich obiektach dokumentu** (`pdf.objects`), więc zagnieżdżenie nic nie
zmienia — sprawdzone na `Wydruk_adWall_Vario_Prosta_600_43`: „overprint wyłączony w 1
stanach graficznych" przed zmianą kolejności i po niej.

Zyskujemy za to dwie rzeczy naraz: plik po samym wymiarze (`base.pdf`) jako punkt
odniesienia suwaka i zgodność z zasadą „najpierw wymiar" — poprawki naprawdę liczą się
na pliku o docelowym formacie, a nie na oryginale, który dopiero potem zostanie przeskalowany.

## Interfejs

Kolejność w panelu: **wymiar → jakość → overprint**. Wymiar jest pierwszy, bo zmienia
rozmiar wydruku, a od niego zależy każde ppi w ocenie jakości.

- Panel **„Wymiar wydruku"** nad „Sprawdź jakość": porównanie wymiarów, suwaki i
  informacja, ile zostanie przycięte. Znika, gdy wymiar się zgadza.
- Przycisk **„Napraw overprinty"** pod „Sprawdź jakość"; nieaktywny dla plików bez
  overprintu (z podpowiedzią dlaczego).
- **Przyciski nie zmieniają nazw.** Po zastosowaniu poprawki przycisk dostaje dopisek
  **„· cofnij"** i zielone obramowanie; kolejne kliknięcie ją zdejmuje. Wcześniejsze
  „Napraw ponownie" / „Sprawdź jakość ponownie" myliło — sugerowało, że trzeba coś
  powtórzyć. Cofnięcie jest tanie i bezpieczne: poprawiona wersja to osobny plik,
  więc `DELETE /fix` po prostu go kasuje.
- Poprawki **sumują się**: włączenie drugiej przelicza plik od oryginału z obiema.
- Notka pod przyciskami wypisuje, co zmieniła każda poprawka, i daje **link do pobrania
  poprawionego PDF-a** (`/api/jobs/<id>/fixed.pdf`, nazwa `<oryginał>_poprawiony.pdf`).
- Górny przełącznik „Overprint" **usunięty** — porównanie „przed/po" robi suwak, a nie
  wyłączanie symulacji. Symulacja jest zawsze włączona dla plików, które overprintu
  używają, bo podgląd ma pokazywać wydruk, nie plik.
- Postęp wczytywania kafelków nazywa się teraz wprost **„wczytuję pełną jakość
  podglądu — 24 %"** i ma pasek. Samo „jakość: 24 %" myliło się z oceną jakości pliku.
- **2026-09-08:** z panelu wymiaru zniknął opis pod suwakami („Jasny obszar na
  podglądzie to wydruk, przyciemnione zostanie odcięte…"). Podgląd pokazuje to
  wprost — jasne pole w zielonej ramce, reszta przyciemniona — więc zdanie tylko
  opisywało to, co i tak widać.

## Pułapka: ta sama nazwa, inna zawartość

Objaw: cofam „Dopasuj wymiar", ustawiam inne kadrowanie, klikam ponownie — a podgląd
pokazuje **poprzednie** dopasowanie.

Przyczyna nie leżała w poprawce: serwer poprawnie generował nowy plik (rendery dwóch
różnych skal różniły się w 30 % pikseli). Winne było to, że poprawiona wersja zawsze
mieszka pod tym samym adresem `…/page/0.png?…&v=fix`, a rendery są wysyłane z
`Cache-Control: public, max-age=3600`. Przeglądarka nie miała powodu pytać serwera
o nic — pokazywała obrazek sprzed poprawki.

Dwa zabezpieczenia, żeby to nie wróciło innym wejściem:

1. **Znacznik wersji w adresie.** `state.fixVer` rośnie przy każdym zastosowaniu
   poprawki i jest dopisywany jako `&r=` do renderów wersji „po poprawkach" (oraz do
   linku pobierania). Inny adres = pewne pobranie.
2. **Krótkie `max-age` dla wersji po poprawkach** (30 s zamiast 3600 s dla strony
   i 86400 s dla kafelków; plik do pobrania: `no-store`). Nawet gdyby ktoś kiedyś
   zbudował adres bez znacznika, nieaktualność potrwa chwilę, a nie godzinę.

Do tego `fixShow()` czyści kafelki warstwy „po poprawkach" — one też były z poprzedniej
wersji pliku.

Zasada: **jeśli pod tym samym adresem może pojawić się inna zawartość, adres musi mieć
znacznik wersji.** Sam nagłówek pamięci podręcznej to za mało.

## Pułapka: po poprawce wymiaru podgląd pokazuje INNĄ stronę

Objaw (`1815_czcionki.pdf`, plik 2870 × 2460 mm, format 2496 × 4357 mm): po kliknięciu
„Dopasuj wymiar" projekt **spłaszczał się na wysokość**, znikała zielona ramka formatu,
a nagłówek podawał dziwny rozmiar.

Przyczyna: cały podgląd był zbudowany na założeniu, że canvas = **strona pliku
źródłowego**. Rozmiar canvasu brał się z `stageImg.naturalWidth`, a warstwa „po
poprawkach" leżała *wewnątrz* warstwy oryginału z `width:100%; height:100%`. Po zmianie
wymiaru poprawiona strona ma inny format niż plik — więc była rozciągana do proporcji
starej strony. Zielona ramka znikała, bo rysowała się tylko w trybie dopasowania,
a ten wyłącza się po nałożeniu poprawki.

Rozwiązanie: **podgląd wie, którą stronę pokazuje.**

- `POST /fix` zwraca `geom`: `page_mm` (format strony wynikowej) oraz — dla poprawki
  wymiaru — `art_mm` (gdzie na nowej stronie wylądował projekt, w mm). Liczy to
  `fixes.resize_page` tą samą arytmetyką, którą wstawia treść, więc podgląd nie zgaduje.
- W przeglądarce: `viewMm()` / `viewNat()` podają wymiar **strony pokazywanej**
  (po poprawce = nowy format), a `artBox()` — gdzie w canvasie leży **strona źródłowa**.
  Od tego liczą się: rozmiar canvasu, „100 % rozmiaru wydruku", wysokość okna, nakładka
  szablonu, ramka formatu i pozycje wyników analizy.
- W HTML `#fixLayer` przestał być dzieckiem `#art` — jest jego **siostrą**, więc każda
  warstwa ma własne miejsce na płótnie i obie leżą w rejestrze.
- Kafelki pełnej jakości liczą siatkę **osobno dla każdej warstwy** (każda może mieć własną
  stronę i własne miejsce w canvasie).
- Od 2026-09-08 warstwa dolna po poprawce wymiaru pokazuje **plik po samym wymiarze**
  (`?v=base`), więc obie warstwy mają tę samą stronę i obie wypełniają płótno. `artBox()`
  liczy wtedy miejsce **strony źródłowej** z `art_mm` (a nie z pozycji elementu) — tam dalej
  lądują wyniki analizy, które są w milimetrach pliku źródłowego. Bez poprawki wymiaru nic
  się nie zmienia: dolna warstwa to oryginał, `artBox()` to po prostu element `#art`.
- To, co poprawka odcięła, zostaje widoczne, ale **przyciemnione** — tak samo jak przed
  kliknięciem. Zielona ramka obrysowuje teraz całą stronę wynikową (ona *jest* formatem),
  a nagłówek pisze `2496 × 4357 mm po dopasowaniu`.
- `#heat` (mapa jakości) przeniesiona do `#art` — dotyczy oryginału, więc ma się skalować
  razem z nim; przy okazji naprawia się jej pozycja w trybie dopasowania.

Przy okazji: `confirmCustom()` nie wołało `updateSizeBox()`, więc dla **wydruku
niestandardowego** panel wymiaru w ogóle się nie pokazywał (przy produkcie z listy
wołał go `selectTemplate`). Dopisane.

Zasada: **jeśli poprawka zmienia geometrię strony, podgląd nie może dalej mierzyć
oryginałem.** Wymiar wynikowy przychodzi z serwera razem z poprawką, a nie jest
odtwarzany z ustawień suwaków — te użytkownik może zmienić po zastosowaniu.

## Kadrowanie trzyma się przy powiększeniu

Przez chwilę tryb kadrowania (jasny obszar wydruku + przyciemniony nadmiar + zielona ramka)
wyłączał się po kliknięciu „100 %" / „+" — był to obchód wcześniejszego błędu: kafelki
pełnej jakości liczyły siatkę z canvasu, a w kadrowaniu canvas nie jest stroną, więc
kafelki nigdy się nie wczytywały i podgląd w 100 % zostawał rozmazany. Dla Tomasza
wyglądało to jak zniknięcie kadru („jak klikam powiększenie to wraca do normalnego
wymiaru").

Po przejściu kafelków na **siatkę liczoną osobno dla każdej warstwy** (patrz wyżej) nie ma
czego wyłączać: warstwa oryginału ma swoje miejsce w canvasie i swoją stronę, więc kafelki
działają też w kadrowaniu. Zostały dwa drobiazgi:

- środkowanie obszaru wydruku dzieje się **tylko przy „Dopasuj"** — po ręcznym powiększeniu
  to użytkownik decyduje, na co patrzy;
- nawigator liczy ramkę widoku względem **strony**, a nie canvasu (w kadrowaniu canvas jest
  większy od strony), i pokazuje stronę po poprawce, gdy jakaś jest nałożona.

## Jasna kreska na styku dołożonego tła i projektu

Objaw: przy włączonym „dołóż tło na marginesach" wzdłuż krawędzi projektu biegła jasna
kreska (zgłoszone przez Tomasza na `Wydruk_adWall_Vario_Prosta_600_43`). W wynikowym
PDF-ie jej nie było — czysto podglądowa.

Zmierzone przyczyny były dwie i obie leżały poza samą poprawką:

1. **Render z Ghostscripta ma częściowo pokryty skrajny wiersz.** Strona 657,6 pt przy
   66 dpi to 602,5 px — Ghostscript oddaje 603 wiersze, a ten ostatni jest zmieszany
   z białym tłem strony. Na ciemnym projekcie to jasna kreska (zmierzone: średnia wiersza
   103 przy 32 w reszcie obrazu). Naprawa w `preview._fix_gs_edges`: jeżeli skrajny
   wiersz/kolumna jest jaśniejszy od sąsiedniego i **nigdzie od niego ciemniejszy** (czyli
   wygląda dokładnie jak zmieszanie z bielą), zastępujemy go sąsiednim. Dotyczy tylko
   renderów z Ghostscripta — MuPDF tego nie robi. Przy okazji znikają takie kreski na
   stykach kafelków.
2. **Cień strony kładł się na dołożonym tle** (`box-shadow` z `.canvas img`) ciemną smugą
   wzdłuż wszystkich czterech krawędzi. Gdy tło jest dołożone, strona nie ma widocznego
   brzegu, więc cień jest zdejmowany (`.canvas.filled img`).

Do tego paski tła wchodzą teraz 2 px **pod projekt** i pod siebie nawzajem — przy
ułamkowych pozycjach elementów inaczej zostawała włosowa szczelina, przez którą prześwitywało
jasne tło okna.

## Znalezione przy okazji (przegląd automatyczny)

Przebieg całej ścieżki (wgranie → produkt → zoom 100 %/+/−/dopasuj → poprawka wymiaru
i jej cofnięcie → overprint → pełny ekran → nawigator → szablon) na sześciu przykładowych
plikach wyłapał jeszcze:

- **Poprawka wymiaru gubiła strony.** `resize_page` budowało dokument z **jedną** stroną,
  więc w pliku wielostronicowym reszta znikała. Teraz pozostałe strony są przepisywane
  bez zmian, a przebudowywana jest tylko ta wybrana.
- **Przycisk „Dopasuj wymiar" działał na JPG/PNG** i kończył się czerwonym komunikatem
  z serwera (400 — poprawki działają na PDF-ach). Teraz jest wyłączony, a panel mówi
  wprost, że taki plik trzeba przeskalować w programie graficznym. SVG i EPS działają,
  bo przy wgraniu są zamieniane na PDF.
- **Zmiana formatu przy nałożonej poprawce.** Po wybraniu innego szablonu (albo innego
  wymiaru ręcznego) poprawka zrobiona pod poprzedni format zostawała nałożona, a panel
  dalej pisał „dopasowany". Teraz zdejmuje się sama.
- **Panel wymiaru nie pojawiał się dla wydruku niestandardowego** — `confirmCustom()` nie
  wołało `updateSizeBox()`.

## Zasada: najpierw wymiar, potem reszta

Ustalenie Tomasza (2026-09-08): **plik najpierw sprawdzamy i, jeśli trzeba, poprawiamy pod
kątem wymiaru — dopiero potem dostępne są kolejne opcje.** Powód jest rachunkowy, nie
kosmetyczny: ppi na wydruku liczy się z rozmiaru, w jakim projekt naprawdę pójdzie na druk.
Plik 2870 × 2460 mm wstawiony w format 2496 × 4357 mm musi być przeskalowany do 43 %, więc
każdy raster drukuje się **2,3 × mniejszy**, niż wynikałoby z samego pliku. Ocena zrobiona
przed dopasowaniem opisywałaby rozmiar, w którym ten plik nigdy nie pójdzie na maszynę.

W praktyce:

- „Sprawdź jakość" i „Napraw overprinty" są **nieaktywne**, dopóki wymiar pliku nie zgadza
  się z formatem z wytycznych albo nie zostanie dopasowany. Nad przyciskiem stoi wtedy
  jednozdaniowe wyjaśnienie, a podpowiedź przycisku mówi to samo.
- Wyjątek: pliki rastrowe (JPG/PNG) — tam wymiaru nie poprawimy, więc blokada nie ma sensu.
- Ocena jakości liczy się **z oryginału**, ale ze skalą dopasowania w rachunku:
  `k = skala wytycznych (1 albo 10) × skala wstawienia projektu`. Serwer przyjmuje `k`
  jako liczbę zmiennoprzecinkową. Nałożenie albo cofnięcie dopasowania zmienia `k`, więc
  policzona wcześniej ocena sama się unieważnia i trzeba kliknąć „Sprawdź jakość" jeszcze raz.
- **Dlaczego nie liczyć jakości z poprawionego pliku** (choć `/analysis?v=fix` to potrafi):
  w poprawionej wersji margines to rozciągnięty pasek z krawędzi — z definicji rozmyty.
  Każda ocena rozdzielczości zgłosiłaby go jako fatalny raster (zmierzone: 8 ppi) i przykryła
  to, co naprawdę jest do sprawdzenia. Oceniamy więc materiał, który dostarczył grafik,
  tylko w rozmiarze, w jakim wyjdzie z drukarki.

## Dołożone tło: dlaczego jest rastrem

Objaw zgłoszony przez Tomasza na `1815_czcionki` (projekt w 43 %, margines 1262 × 3299 mm):
po dopasowaniu wymiaru na prawym marginesie pojawiły się **białe pasy**, a w powiększeniu
było widać, że rozciągnięte tło **nie schodzi się** z projektem.

Zmierzone przyczyny — obie po stronie sposobu wstawiania paska:

1. **`show_pdf_page(clip=…)` gubi przycięcie przy dużym rozciągnięciu.** PyMuPDF wstawia
   CAŁĄ stronę jako obiekt formy i ogranicza ją dopiero ramką (BBox) równą wycinkowi.
   Przy rozciągnięciu paska 3 mm na metrowy margines (×70 i więcej) współrzędne treści idą
   w setki tysięcy punktów i rasteryzator MuPDF-a przestaje trzymać przycięcie: na marginesie
   lądowały elementy ze **środka** projektu. Zmierzone: pasek z prawej krawędzi nie zawiera
   ani jednego białego piksela (render z `clip` w 4×), a to samo wstawione przez
   `show_pdf_page` dawało cztery białe wiersze przez całą szerokość. Przy ×35 problemu nie
   było — to kwestia skali, nie logiki.
2. **Odsunięcie 1 mm było liczone na obu osiach.** Dla pasów bocznych oznaczało to, że
   wycinek o wysokości „strona minus 2 mm" trafiał na pełną wysokość projektu — tło było
   minimalnie przeskalowane i linie rozjeżdżały się tym bardziej, im dalej od środka.

Rozwiązanie:

- Pasek jest **renderowany do wąskiej bitmapy** (`get_pixmap(clip=…)` przycina uczciwie)
  i wstawiany jako obraz. W poprzek 24 px — i tak jest rozciągany; wzdłuż krawędzi
  **120 ppi na wydruku** (stąd `k` w parametrach poprawki), z sufitem 30 000 px na bok.
  Rozciągnięty pasek jest rozmyty z definicji, więc raster nic tu nie psuje, a plik
  przestaje zależeć od tego, jak RIP poradzi sobie z ekstremalną macierzą.
- Odsunięcie w poprzek osi rozciągania **zniknęło** — pasek obejmuje całą krawędź, więc
  trafia dokładnie na wymiar projektu.
- Odsunięcia nie ma też na osi rozciągania: pasek zaczyna się **dokładnie na krawędzi**,
  a częściowo pokryty skrajny piksel obcinamy w `_strip_pix` (renderujemy o jeden szerzej
  i odcinamy). Wcześniejsze odsunięcie 1 mm w głąb sprawiało, że przy projekcie lądowała
  treść z 1 mm środka — przy stromych liniach robił się widoczny **uskok** (uwaga Tomasza:
  „dalej jest to przesunięcie"). Zmierzone na `1815_czcionki`: dopasowanie tła do prawdziwej
  krawędzi wzrosło z 0,37 do 0,68 (korelacja profili), przesunięcie pionowe 0 px z 1500.
  To samo dotyczy podglądu (`EDGE_SKIP_MM = 0` w JS) — jasny brzeg renderu naprawia teraz
  `preview._fix_gs_edges`, stosowany też do renderów MuPDF-a, nie tylko Ghostscripta.

- Pasek próbkujemy w poprzek **96 pikselami** (było 24). Nie chodzi o ostrość — pasek i tak
  jest rozciągany — tylko o styk: pierwsza kolumna tła bierze się z (szerokość paska / 96)
  przy krawędzi, czyli z 0,03 mm zamiast 0,12 mm w głąb.

  Zmierzony uskok na szwie (plik testowy z liniami o nachyleniu 0 / 0,3 / 1,0, wynik
  w mm strony): **0,003 / 0,04 / 0,09**. Na `1815_czcionki` różnica wartości bezpośrednio
  na szwie: średnia 0,32 na 255, p99 = 0. Innymi słowy **wartości się zgadzają** — tego
  nie da się już poprawić sensowniej.

### Odcinamy brzeg, potem rozciągamy albo odbijamy

Po testach Tomasz odrzucił pasek liczony do marginesu (1/10) — wciągał w margines za dużo
struktury projektu. Wróciliśmy do wąskiego paska, ale z dwiema zmianami, które załatwiają
oba objawy naraz (**ustalenie Tomasza:** „obcinać kilka pikseli przy krawędzi i dopiero
rozciągać / robić odbicie lustrzane"):

1. **Przycięcie.** Skrajne piksele projektu bywają JAŚNIEJSZE — tak wychodzi z eksportu
   wektora do rastra (wygładzona krawędź) i tak samo zachowuje się render strony.
   Rozciągnięte na cały margines dawały jasny pas. Odcinamy więc `EDGE_TRIM_PX = 3` piksele
   wydruku i dopiero to, co zostało, rozciągamy albo odbijamy.
2. **Tło wchodzi POD projekt** o dokładnie tyle samo. Odcięte, jaśniejsze piksele są
   zakryte, a treść na styku zgadza się co do miejsca — nie ma ani jasnego pasa, ani uskoku.
   Dlatego kolejność rysowania jest teraz odwrotna niż wcześniej: **najpierw projekt, potem
   tło** (wcześniej tło było pod spodem i jasna krawędź zostawała na wierzchu).

**Rozciągnięcie to POWIELENIE jednej linii pikseli, nie rozciągnięcie paska.** Pasek
2 mm rozciągany na metrowy margines uśredniał treść: linia dochodząca do krawędzi bladła
i rozmywała się w poziomą smugę. Tomasz pokazał w Photoshopie, o co chodzi — tam bierze się
JEDEN rząd pikseli i powiela go w bok, więc linia idzie dalej **ostra i w pełnym kolorze**.
Robimy dokładnie to: renderujemy `EDGE_TRIM_PX + 1` pikseli przy krawędzi, odcinamy te
przy samym brzegu i zostawiamy jedną kolumnę (albo wiersz) — ta jedna linia jest rozciągana
na cały margines. Narożniki to pojedynczy piksel, czyli jednolity kolor.

W podglądzie ten sam rząd wycinamy do maleńkiego `<canvas>` (1 × wysokość renderu)
i rozciągamy go stylami. Wersja z ogromnym `<img>` (szerokość × liczba pikseli strony)
zjadałaby pamięć przeglądarki.

### Drugi tryb: odbicie lustrzane

Przełącznik **metoda: rozciągnij krawędź / odbij lustrzanie** pod „dołóż tło na
marginesach". Odbicie kafelkuje margines lustrzanymi kopiami PRZYCIĘTEGO projektu
(parzysty indeks = przesunięcie, nieparzysty = odbicie), więc linia biegnąca pod kątem
idzie dalej pod tym samym kątem, tylko w drugą stronę, a styk jest ciągły z definicji.

Technicznie: projekt leży już na stronie jako obiekt formy, więc odbicie to narysowanie go
jeszcze raz z macierzą o ujemnej skali. PyMuPDF nie ma na to API (żadna kombinacja `rotate`
nie da odbicia — obroty mają wyznacznik +1), więc operatory `q … re W n … cm /Fm Do Q`
dopisujemy do strumienia treści przez **pikepdf**, już po zapisaniu pliku. Zostaje wektor:
margines jest tak ostry jak projekt, nic nie jest rasteryzowane. Podgląd rysuje tę samą
siatkę transformacjami CSS, więc przed kliknięciem widać dokładnie to, co wyjdzie.

Kiedy co: **rozciąganie** daje spokojne, jednolite tło (dobre dla zdjęć i gładkich teł),
**odbicie** zachowuje strukturę i ostrość (dobre dla grafiki geometrycznej), ale przy
marginesie szerszym od projektu widać powtórzenia.

### Cofnięcie wymiaru zdejmuje wszystkie poprawki (bezpiecznik)

Skoro poprawki liczą się na pliku o właściwym wymiarze, to cofnięcie wymiaru unieważnia je
wszystkie — inaczej zostałby plik poprawiany pod jeden kadr, a wymiar miałby inny.
„Dopasuj wymiar · cofnij" pyta więc najpierw w oknie programu (`#askModal`, nie okienko
przeglądarki — w naszym da się wytłumaczyć, o co chodzi):

> **Cofnąć dopasowanie wymiaru?** Razem z wymiarem zostaną cofnięte pozostałe poprawki:
> *Napraw overprinty*. Poprawki robimy zawsze na pliku o **właściwym wymiarze** — po zmianie
> kadru trzeba je nałożyć jeszcze raz. Oryginał jest nietknięty, nic nie przepada.

Po potwierdzeniu leci jedno `DELETE /fix`: znikają `fixed.pdf`, `base.pdf` i rendery obu
wersji. Ustawienia suwaków kadru zostają, więc ponowne dopasowanie to jedno kliknięcie.
To samo dzieje się bez pytania, gdy poprawka wymiaru unieważnia się sama (zmiana szablonu,
skali albo wymiaru ręcznego) — tam pytanie nie miałoby sensu, bo poprawka pod poprzedni
format i tak przestała cokolwiek znaczyć.

## Układ: menu i fakty po lewej, podgląd na całą prawą stronę

Zmiana na życzenie Tomasza (2026-09-08): okno pracuje na **całej szerokości ekranu**.
Lewa kolumna (300–400 px, dociągnięta do krawędzi) zbiera wszystko, co się czyta —
plik, produkt, wytyczne, wymiar, przyciski **oraz „Informacje o pliku"** (kolory, jakość,
fonty, ppi), które wcześniej leżały pod podglądem. Prawa kolumna to sam podgląd,
dociągnięty do prawej krawędzi i **przyklejony** (sticky) do góry, więc zostaje w polu
widzenia, kiedy przewijamy raport w lewej kolumnie. Pod podglądem nie ma już nic,
co odciągałoby wzrok od pliku.

`fi-grid` jest teraz jednokolumnowy (wąska kolumna), a poniżej 900 px szerokości okna
układ wraca do jednej kolumny.

### Porządki w pasku podglądu (2026-09-08)

- **Pełny ekran to po prostu ZNIKNIĘCIE LEWEJ KOLUMNY.** Wcześniej scena szła na
  `position: fixed` przez całe okno: znikał górny pasek z nazwą i Ustawieniami, nagłówek
  „Podgląd" i opis strony lądowały gdzie indziej, dochodził przycisk „✕ Zamknij pełny ekran",
  a „Pełny ekran" zmieniał nazwę na „Normalny widok". Teraz nie rusza się nic poza szerokością
  podglądu: `body.fs` chowa lewą kolumnę i zwęża siatkę do jednej kolumny. Przycisk tylko się
  podświetla (jak „Szablon" i „Nawigator"), Esc dalej wychodzi.
- **Pasek „pełna jakość — 51 %" ma stałe miejsce** po lewej od „Szablon" i stałą szerokość
  (176 px); gdy nic się nie wczytuje, jest niewidoczny, ale zajmuje swoje miejsce. Zmierzone:
  przyciski i opis strony mają te same współrzędne przed i w trakcie wczytywania. Pełny opis
  przeniesiony do podpowiedzi, bo w rzędzie przycisków musi być krótko.
- **Legenda „obszar ochronny / kształt produktu" usunięta** — kolory linii same się tłumaczą,
  a legenda zajmowała pół paska.
- **Kolejność powiększenia:** `Dopasuj · − · 100 % · +` (minus po lewej od 100 %).
- **Zniknęło „7 % rozmiaru wydruku"** — sam procent nic nie mówi; liczy się, czy widać
  rozmiar rzeczywisty, a to pokazuje podświetlony przycisk „100 %".
- **„szablon „Door"" → „rola pliku: Door"** — tak samo nazywa się to w panelu wytycznych.
- **Ekran renderowania**: pełna zasłona z kręcącym się kółkiem zamiast półprzezroczystej
  mgiełki, spod której wystawał róg wczytywanego arkusza. Na czas renderu czyścimy też
  rozmiar sceny i przewinięcie — inaczej kółko lądowało poza widokiem, bo canvas
  po poprzednim powiększeniu bywa ogromny.

## Drobne z UI (2026-09-08)

- „rozmiar pliku (100 %)" jako pierwszy w rzędzie skrótów skali — najczęściej się z niego korzysta.
- Checkbox **„pokazuj tylko to, co się wydrukuje"**: canvas staje się samym obszarem wydruku,
  nadmiar jest ucinany (`.canvas.clipped { overflow: hidden }`) zamiast przyciemniany.
- Duży przycisk **„Pobierz poprawiony plik"** zamiast odnośnika w notce. Nazwa pliku to
  **produkt + rola** (bez wymiarów), a przy pliku wielostronicowym pobiera się **tylko strona
  z podglądu** — serwer wycina ją do osobnego PDF-a (`/fixed.pdf?page=N&name=…`).
- Opis, co zmieniła poprawka, przeniesiony **pod suwak** porównania (`#cmpWhat`) — w opisie
  końca suwaka rozpychał cały pasek.

### Jasna kreska przy odbiciu lustrzanym (2026-09-08)

Tomasz: „przy odbiciu lustrzanym widzę taką jasną linię poziomą, gdy podgląd jest dopasowany
do okna; jak przybliżę, ona znika". Zmierzone na renderze strony 1600 px: w wierszu na granicy
projektu **66,0 przy tle 32,0**, i tak samo przy dolnej krawędzi (50,0). Ta sama kreska przy
każdej szerokości renderu, więc nie chodziło o jeden pechowy piksel.

Przyczyna: sąsiednie komórki odbicia stykały się **dokładnie krawędź w krawędź**.
Rasteryzator wygładza obie krawędzie, więc piksel na styku dostawał od każdej z nich po
około połowie krycia — a 0,5 „na 0,5" to nie 1,0, tylko 0,75: przez brakującą ćwiartkę
przebijała biel strony. Przy powiększeniu piksel renderu jest dużo mniejszy niż zakładka,
więc kreska znikała — stąd „znika, jak przybliżę".

Odcięty pasek `ov` na zakładkę nie wystarczał: przy skali 1:10 to ułamek punktu, a piksel
renderu dopasowanego do okna ma ich ponad jeden. Rozwiązanie: każdą komórkę rysujemy
**odrobinę większą** (o `MIRROR_SLACK_PT = 1,5 pt` z każdej strony, czyli ~0,3 % rozmiaru)
i przycinamy do pola powiększonego o to samo. Sąsiedzi zachodzą na siebie o `2s` — zawsze
więcej niż piksel renderu — a rozciągnięcie tła o 0,3 % jest niewidoczne. Przycięcie zostaje,
bo to ono odcina jasną krawędź projektu; **usunięcie samego przycięcia nic nie dało**
(sprawdzone: kreska została), co potwierdziło, że problemem jest brak zakładki, a nie clip.

Sprawdzenie po zmianie — średnia jasność wierszy na granicy projektu wobec sąsiadów:

| szerokość renderu | górna krawędź | dolna krawędź |
|---|---|---|
| przed: 1600 px | 66,0 wobec 32,0 | 50,0 wobec 32,0 |
| po: 1600 / 1200 / 900 / 600 px | 32,0 = 32,0 | 32,0 = 32,0 |
| po: 400 px (piksel = 4,3 pt) | 32,1 = 32,1 | 37,4 wobec 32,0 |

Przy 400 px na całą stronę piksel renderu jest szerszy niż zakładka i ślad wraca — ale to
skala miniatury, nie podglądu (dopasowanie do okna to ~1500 px).

### Etykieta formatu przy górnej krawędzi

Zielony napis „format z wytycznych …" wisiał 21 px **nad** ramką. Po dopasowaniu wymiaru
ramka pokrywa się z całą stroną, więc napis wychodził poza płótno i obcinała go krawędź okna.
Teraz, gdy ramka jest wyżej niż 22 px od góry, napis wjeżdża **do środka** ramki
(`.fmtframe.inside span`).

## Windows: „cannot remove file … Permission denied" (2026-09-08)

Tomasz przy drugiej poprawce (overprint po dopasowaniu wymiaru) dostał:

> Poprawka nie powiodła się: FzErrorSystem: code=2: cannot remove file
> 'C:\…\app\work\…' Permission denied

Przyczyna jest w całości windowsowa: **kafelki podglądu trzymają PDF-y otwarte** (to one
dają szybkość — patrz `preview._cached_doc`), a otwartego pliku nie da się na Windowsie
nadpisać ani skasować. Druga poprawka liczyła plik po wymiarze od nowa i próbowała zapisać
go pod tą samą nazwą — pod którą sama przed chwilą renderowała kafelki. Na Linuksie to
przechodzi (stąd nie było widać tego w sandboksie), na Windowsie nie.

Trzy zmiany, każda potrzebna:

1. **`preview.forget_doc` woła się PRZED poprawką**, nie po niej — i zamyka dokument pod
   zamkiem wpisu, żeby nie wyrwać go spod trwającego renderu. To samo przy cofaniu poprawek
   (`DELETE /fix`), bo tam pliki się kasuje.
2. **Nigdy nie zapisujemy prosto na plik docelowy.** Każdy zapis idzie do pliku roboczego
   o losowej nazwie (`_tmp`) i dopiero `os.replace` wstawia go na miejsce (`_swap`),
   z kilkoma podejściami co 150 ms — na wypadek, gdyby plik przytrzymał antywirus albo
   Eksplorator.
3. **Plik po wymiarze nie jest liczony drugi raz.** Jeśli ustawienia kadru się nie zmieniły
   (serwer porównuje `params["resize"]`), kolejna poprawka bierze gotowy `base.pdf`
   i nakłada na niego tylko poprawki na obiektach. Zmierzone na `Wydruk_adWall_Vario_Prosta`:
   dopasowanie wymiaru 17 s, overprint po nim **2,1 s** (wcześniej liczyłby wymiar od nowa).
   Przy okazji nie przeładowuje się warstwa „przed poprawkami" ani jej kafelki.

## Wielostronicowy plik: najpierw wybór strony (2026-09-08)

Poprawki, ocena jakości i pobieranie dotyczą **jednej strony**. Dlatego przy pliku z wieloma
stronami nad panelem wymiaru pojawia się panel **„Strona pliku"**: lista stron + przycisk
„Wybierz tę stronę". Póki strona nie jest zatwierdzona, panel wymiaru jest schowany,
a „Sprawdź jakość" i „Napraw overprinty" są nieaktywne (podpowiedź: „Najpierw wybierz
stronę"). Po zatwierdzeniu przycisk zmienia się w „Wybierz inną stronę", a lista jest
zablokowana — to ten sam bezpiecznik co przy wymiarze: **zmiana strony zdejmuje wszystkie
poprawki**, po pytaniu w oknie. Miniatury stron chodzą przez tę samą bramkę.

### Przycisk pobierania: zawsze widoczny, aktywny gdy jest co pobierać

Ustalenie Tomasza: przycisk **nie znika** — stoi na swoim miejscu wyszarzony i włącza się,
gdy w pliku coś zmieniamy. „Zmiana" to każda poprawka, a przy pliku wielostronicowym
**także sam wybór strony**, bo pobiera się wtedy wyłącznie ta jedna strona (PDF-a z kilkoma
stronami nie pobieramy nigdy). Napis idzie za tym: „Pobierz wybraną stronę ↓" zanim
pojawią się poprawki, „Pobierz poprawiony plik ↓" po nich.

Serwer: `/fixed.pdf` bez poprawionej wersji podaje **oryginał** (a przy `?page=` — jego jedną
stronę), zamiast odpowiadać 404. Sprawdzone: plik dwustronicowy, wybrana strona 2, bez
poprawek → pobrany PDF ma 1 stronę i nazwę „produkt - rola".

Przy okazji naprawiony błąd zgłoszony przez Tomasza: po wgraniu **kolejnego** pliku zostawał
zielony przycisk „Pobierz poprawiony plik" z adresem POPRZEDNIEGO zadania — klik kończył się
pobraniem błędu jako `fixed.json` („Plik nie był dostępny w witrynie"). Reset po wgraniu
wołał tylko ukrycie notki; teraz woła `fixSummary()`, które chowa notkę **i** przycisk.
Adres pobierania odświeża się też przy zmianie strony (siedzi w nim `?page=`).

## Fonty na krzywe (2026-09-08)

Pytanie Tomasza: *co się stanie, jak w projekcie będzie font, którego nie mamy
zainstalowanego?* — bo Illustrator przy otwarciu takiego PDF-a krzyczy o brak fontu
i podmienia go na losowy, a Photoshop (który od razu rastruje) pokazuje dobrze.

**Odpowiedź: font zainstalowany w systemie nie jest do niczego potrzebny — pod warunkiem,
że jest OSADZONY w pliku.** Kształty liter siedzą wtedy w samym PDF-ie (podzbiór fontu),
więc bierzemy je stamtąd. Illustrator marudzi dlatego, że do EDYCJI tekstu potrzebuje
prawdziwego fontu w systemie; osadzony podzbiór mu nie wystarcza. My nie edytujemy — my
tylko zamieniamy litery na krzywe, dokładnie z tych obrysów, które są w pliku.

Robi to **Ghostscript z `-dNoOutputFonts`** (ten sam Ghostscript, którym symulujemy overprint).
Obrazy zostają nietknięte: `-dPassThroughJPEGImages`, bez zmniejszania, bez zmiany kolorów.

Zmierzone (render oryginału kontra render po zamianie, ten sam wycinek, ta sama skala):

| plik | fonty | render: piksele różne | maks. różnica | czas |
|---|---|---|---|---|
| `1815_czcionki` (Industry-Bold, osadzony) | 1 → 0 | 0,0037 % | 25/255 | 0,2 s |
| `adWall_…_Light_300` (74 MB, obraz 5989×4497) | 1 → 0 | 0,0020 % | 19/255 | 4,9 s |
| `Wydruk_adWall_Vario_Prosta_600_43` | 0 → 0 | 0,0694 % | 21/255 | 0,5 s |

Same litery w powiększeniu ×8: **maks. różnica 1/255** — czyli identyczne, a te ułamki
procenta na całej stronie to wygładzanie krawędzi.

Plik po zamianie bywa dużo mniejszy (74 → 13,4 MB), bo Ghostscript wyrzuca obiekty, których
nikt nie rysuje. Sprawdzone, że **rysowane** obrazy zostają co do jednego: te same rozmiary
w pikselach i te same miejsca na stronie (7008×4672 i 2000×2000, które „zniknęły", nie były
nigdzie użyte).

### Font nieosadzony — nie ruszamy

Spreparowany plik z dwoma nieosadzonymi fontami pokazuje, dlaczego to musi być twardy warunek:

| strona | oryginał (MuPDF) | po krzywych (Ghostscript) | piksele różne |
|---|---|---|---|
| Helvetica | podstawiony bezszeryfowy | inny bezszeryfowy | 0,82 % |
| Industry-Bold | podstawiony **szeryfowy** | **bezszeryfowy**, inna szerokość tekstu | 5,41 % (do 255) |

Kształtów tego fontu nie ma w pliku, więc każdy program podstawia swój — krzywe utrwaliłyby
przypadkowy krój **na zawsze**. Dlatego przycisk jest wtedy nieaktywny, a w podpowiedzi stoi,
których fontów brakuje i że trzeba poprosić o plik z osadzonymi fontami. To samo sprawdzenie
jest po stronie serwera (`fixes.outline_fonts` odmawia), żeby nie dało się tego obejść.

Kolejność w potoku: **wymiar → krzywe → overprint**. Ghostscript pisze plik od nowa, więc idzie
przed poprawkami na obiektach — overprint (pikepdf) nakłada się na gotowy wynik i na pewno
w nim zostaje. Po zamianie sprawdzamy jeszcze, czy w pliku naprawdę nie ma już fontów; jeśli
któryś został, plik nie jest podmieniany (lepiej nic nie zrobić niż zrobić gorzej).

## Sprzątanie interfejsu (2026-09-08, wieczór)

Zasada Tomasza: **im mniej na ekranie, tym czytelniej** — pokazujemy to, czym trzeba się
zająć teraz.

- **Na starcie widać tylko „1 · Plik".** Sekcja „2 · Produkt" pojawia się po wgraniu pliku,
  a przyciski poprawek (jakość, overprint, krzywe, pobieranie) dopiero, gdy wiadomo, na jaki
  wydruk patrzymy — czyli po potwierdzeniu produktu albo podaniu wymiaru ręcznie.
  Wytyczne, wybór strony i panel wymiaru miały już swoje warunki.
- **Nagłówek „Podgląd" i opis strony („Strona 1 / 1 · 980 × 2050 mm") usunięte**, tak samo
  linia „wydruk: … (rola pliku: …)". Te same liczby stoją w lewej kolumnie, w panelu wymiaru,
  a nad podglądem tylko rozbijały wzrok. Nad podglądem została **nazwa pliku i liczba stron**
  (bez wymiaru — też był powtórzony) oraz rząd przycisków, który dzięki temu ma cały pasek.
- Jedyne ostrzeżenie z usuniętej linii, które naprawdę dotyczy podglądu — **niekalibrowany
  monitor** — siedzi teraz w przycisku „100 %": obwódka na pomarańczowo i wyjaśnienie
  w podpowiedzi. Bez kalibracji „rozmiar rzeczywisty" nie jest rzeczywisty, więc informacja
  jest przy przycisku, którego dotyczy.

## Rozdziały: jeden krok = jedno zadanie = swój kawałek raportu (2026-09-08)

Program prowadzi teraz przez plik krok po kroku, a **raport nie jest jedną listą na dole** —
każdy jego kawałek stoi w rozdziale, którego dotyczy (ustalenie Tomasza):

| rozdział | co w nim jest | kiedy się pojawia |
|---|---|---|
| **1 · Plik** | wgranie pliku + fakty o nim: strony/typ, kolor, profil, przezroczystość | zawsze |
| **2 · Produkt** | sugerowany produkt, `Potwierdź` · `Inny produkt` · `Niestandard` | po wgraniu pliku |
| **3 · Szablon / rola pliku** | wybór roli z wytycznych + `Zatwierdź rolę`; skala jest POKAZYWANA, nie ustawiana | po potwierdzeniu produktu |
| **4 · Strona pliku** | wybór strony + zatwierdzenie | po zatwierdzeniu roli, tylko gdy stron jest kilka |
| **5 · Wymiar wydruku** | porównanie z wytycznymi, suwaki kadru, `Dopasuj wymiar` | po wybraniu strony |
| **6 · Jakość wydruku** | ppi obrazów, tabela, mapa detalu, `Sprawdź jakość (experimental)` | po dopasowaniu wymiaru |
| **7 · Overprint** | ile użyć i co to zmienia, `Napraw overprinty` | jw. |
| **8 · Fonty** | lista fontów (osadzony / nieosadzony), `Zamień fonty na krzywe` | jw. |
| **9 · Kolory** | rodziny kolorów, spoty, profil; `Zamień kolory na CMYK` i wybór profilu | jw. |

Numery liczą się same: przy pliku jednostronicowym rozdziału „Strona pliku" nie ma i dalsze
numery przesuwają się w dół (wymiar = 4, jakość = 5…); przy wydruku niestandardowym nie ma
też rozdziału z rolą.

**Rola idzie do zatwierdzenia tak samo jak strona i wymiar**: od niej zależy docelowy wymiar,
więc dopóki nie jest wskazana, dalsze rozdziały się nie pokazują. Po zatwierdzeniu lista ról
jest zablokowana, a `Zmień rolę` — jak każde cofnięcie wcześniejszego kroku — zdejmuje
nałożone poprawki (po pytaniu). **Skala wytycznych przestała być polem wyboru** — jest
odczytana z wytycznych produktu i tylko pokazana; ustawianie jej ręcznie kusiło do pomyłki,
a mylna skala psuje każde ppi. Kolejny w planie: **rozdział o kolorach
i profilach** — dziś te fakty siedzą w „1 · Plik", przeniosą się, gdy dojdzie poprawka.

Zmiany przy okazji:
- „Nie ma na liście? Wydruk niestandardowy →" zniknęło; **„Niestandard"** jest trzecim
  przyciskiem przy sugerowanym produkcie (i drugim wejściem w wyszukiwarce).
- **Wymiar można poprawiać także wtedy, gdy się zgadza.** Panel z suwakami zostaje otwarty,
  bo tym samym mechanizmem naprawia się mankament przy krawędzi — np. biały pasek z jednej
  strony (minimalne powiększenie albo dołożenie tła na marginesie). Wcześniej panel się zwijał
  i nie dało się tego zrobić.
- Przyciski kolejnych kroków są **ukryte**, a nie wyszarzone — dopóki poprzedni krok nie jest
  domknięty. Zamiast nich stoi jedno zdanie, co jest teraz do zrobienia.
- Pasek stanu przy jakości pokazuje tylko to, co dzieje się TERAZ (postęp, wynik,
  nieaktualność). Wcześniej w stanie spoczynku dublował kartę obok.

## Jasny pasek przy krawędzi: obcinamy, potem dokładamy (2026-09-08)

Tomasz na `fonty.pdf` (980 × 2050 mm, pionowy): po zmniejszeniu skali **cały prawy margines
miał inny róż niż projekt**, a przy odbiciu lustrzanym w tym samym miejscu szedł pasek.

Zmierzone: skrajna kolumna renderu to **(237, 14, 145)** zamiast **(236, 0, 139)** — piksel
z samej krawędzi jest zawsze wymieszany z bielą strony. To ten sam mechanizm, o którym mówił
Tomasz: „często przy eksportach zostaje kilkupikselowy biały pasek na krawędzi".

Dlaczego akurat tu, skoro odcinamy 3 piksele wydruku? Bo podgląd renderuje **1600 px na
DŁUŻSZYM boku**: przy stronie 980 × 2050 mm to tylko 765 px szerokości, czyli 0,78 px/mm.
Odcięcie 0,635 mm wychodziło wtedy **0,5 piksela → zaokrąglane do zera** i tło brało kolor
właśnie z tej wymieszanej kolumny. Przy poziomych plikach (600 × 227 mm) wychodziło 1 piksel
i problemu nie było widać — stąd ujawnił się dopiero na pionowym pliku.

Dwie zmiany:

1. **Wynikowy PDF: krawędzie są OBCINANE, nie tylko pomijane przy próbkowaniu** (decyzja
   Tomasza). Przy dołożeniu tła projekt wstawiamy jako WYCINEK strony bez skrajnych
   3 pikseli wydruku (0,635 mm), w to samo miejsce i o tym samym rozmiarze — projekt jest
   przez to większy o ~0,06 %, czyli tyle co nic, a format wypełnia się co do kreski.
   Tło dokładamy już z obciętej krawędzi. Sprawdzone na `fonty.pdf` (skala 80 %, margines
   216 × 400 mm): w całym marginesie **(236, 0, 139)** — dokładnie kolor projektu.
2. **Podgląd: odcięcie ma co najmniej 1,5 piksela bazowego renderu.** Sprawdzone na tym samym
   pliku: kolor tła w podglądzie = (236, 0, 139) przy projekcie, w połowie marginesu i przy
   krawędzi formatu.

## Plik w złej skali: skala osobno, wielkość osobno (2026-09-08)

Uwaga Tomasza: suwakiem skali nie dało się naprawić pliku zapisanego w złej skali (1:1 zamiast
1:10 — trzeba dojechać do 1000 %). Pierwsza próba to był jeden suwak logarytmiczny 2–5000 %;
Tomasz słusznie zauważył, że **procenty to zły język dla skali** — drukarz myśli „1:10", nie
„1000 %". Zostały więc dwa poziomy, każdy ze swoim pytaniem:

| suwak | pytanie | jednostka |
|---|---|---|
| **Zmień skalę projektu** (schowany pod strzałką) | w jakiej skali jest ten plik? | `1:50 … 1:1 … 50:1` |
| **Dostosuj wielkość projektu** | ile z tego formatu ma zająć? | procent, gdzie **100 % = dokładnie to, co ustawia górny suwak** |

Skala końcowa = mnożnik z górnego × procent z dolnego. Górny rusza się rzadko, więc domyślnie
jest zwinięty i pokazuje bieżącą wartość w podsumowaniu („Zmień skalę projektu — teraz 10:1").
Skróty pod nim (`1:10` · `1:1` · `10:1`) ustawiają skalę i zerują procent do 100.

Podpisy skrótów wielkości liczą się **względem ustawionej skali**: przy 10:1 „rozmiar pliku"
to 10 %, a „wypełnij format" 100 % — czyli dokładnie to, co pokazuje dolny suwak.

**Wykrycie złej skali**: jeśli plik po pomnożeniu ×10 albo ÷10 trafia w wymiar z wytycznych
z dokładnością do 1 mm, program pisze o tym wprost, podświetla właściwy skrót i sam rozwija
sekcję (raz, żeby nie zamykać jej użytkownikowi pod palcami). Przy powiększaniu dopisuje, że
rastry nie zyskają pikseli i ppi na wydruku spadnie 10× — rozdział jakości policzy to potem
uczciwie, bo skala poprawki wchodzi do `qualityK`.

Sprawdzone na pliku 98 × 205 mm przy formacie 980 × 2050 mm: program sam ustawia **10:1** i
**100 %**, podpowiedź się pokazuje, a skrót `1:1` wraca do pliku w jego własnym rozmiarze.

## 9 · Kolory: konwersja na CMYK i profil (2026-09-08)

Dwie osobne poprawki, bo to dwie różne rzeczy: **konwersja** zmienia barwy, **profil** tylko
deklaruje, na jaką maszynę plik jest przygotowany.

### Zamień kolory na CMYK — przez profil, tak jak Photoshop

Wymóg Tomasza: „żeby kolory nie były wyblakłe albo jakieś dziwne — użyj tego samego konwertera
co Photoshop". Robi to Ghostscript, ale z **jawnie podanymi profilami i intencją**:

```
-dColorConversionStrategy=/CMYK -dProcessColorModel=/DeviceCMYK
-sOutputICCProfile=<Coated FOGRA39>  -sDefaultRGBProfile=<sRGB>
-dRenderIntent=1 -dBlackPtComp=1        # relatywna kolorymetryczna + kompensacja punktu czerni
```

To dokładnie te ustawienia, których Photoshop używa domyślnie w „Convert to Profile". Bez nich
(samo `ColorConversionStrategy=CMYK`) Ghostscript bierze swój domyślny profil CMYK i barwy
wychodzą inne — zwykle bardziej matowe.

Sprawdzenie na próbniku pięciu pól RGB, wobec **littleCMS** z tymi samymi profilami i intencją
(to ta sama biblioteka, na której opiera się większość świata poligrafii):

| RGB | nasz wynik (CMYK) | littleCMS |
|---|---|---|
| 255 0 0 | 0 · 0,996 · 1 · 0 | 0 · 0,969 · 0,984 · 0 |
| 0 102 255 | 0,804 · 0,612 · 0 · 0 | 0,792 · 0,584 · 0 · 0 |
| 51 179 77 | 0,757 · 0,008 · 0,984 · 0 | 0,741 · 0 · 0,882 · 0 |

W gamucie różnice sięgają 0,03 na kanał; poza gamutem (czysta zieleń RGB) do 0,1 na żółtym —
tam każdy silnik przycina po swojemu. Kierunek różnicy jest bezpieczny: **odrobinę więcej
farby, nie mniej**, więc nic nie blaknie.

Profil bierzemy w kolejności: **profil Adobe z komputera** (`CoatedFOGRA39.icc` z Common Files
albo z katalogu profili Windows) — wtedy liczby są identyczne jak w Photoshopie na tej maszynie
— a jak go nie ma, nasza kopia w `app/data/icc/CoatedFOGRA39.icc` (FOGRA39L Coated, profil
oznaczony „free of known copyright restrictions").

**Podgląd musi iść przez Ghostscripta.** MuPDF przelicza CMYK na ekran wzorem bez profilu
i wszystko wygląda wtedy wyblakle — porównanie „przed / po" pokazywałoby nieprawdę o samej
poprawce. Dlatego po włączeniu tej poprawki podgląd przełącza się na render Ghostscriptem
(ten sam, którym symulujemy overprint). Zmierzone na próbniku, suwak 0 % → 100 %:
czerwień `255,0,0` → `237,30,36`, błękit `0,102,255` → `66,105,178` (kolor spoza gamutu CMYK,
i tak właśnie wyjdzie na druku), zieleń i żółty prawie bez zmian.

**Kolory dodatkowe (spot / PANTONE)**: Ghostscript zamienia ich przestrzeń ALTERNATYWNĄ na CMYK
— czyli na wydruk idą jako proces — ale nazwana separacja zostaje w pliku i program pisze o tym
wprost w opisie poprawki. Pełne spłaszczenie separacji (przepisanie operatorów `scn` na `k`)
jest w „Do zrobienia".

### Profil kolorystyczny: FOGRA39 albo żaden — w tym samym przycisku

Lista z dwiema pozycjami (**Coated FOGRA39 (ISO 12647-2:2004)** albo **bez profilu**) stoi
**nad** przyciskiem i decyduje, co ten przycisk zrobi; napis na nim mówi to wprost:
„Zamień kolory na CMYK **i ustaw profil FOGRA39**" albo „…**i usuń profil**". Osobnego
przycisku „Ustaw profil" nie ma — to jedna decyzja („na jaki druk przygotowujemy plik"),
więc jedno kliknięcie (ustalenie Tomasza).

Pod spodem są dalej dwie poprawki, nakładane razem: konwersja barw (Ghostscript) i deklaracja
profilu, czyli `/OutputIntents` w katalogu dokumentu — wpis `GTS_PDFX` z osadzonym profilem
ICC (`/N 4`) albo usunięcie klucza. Sama deklaracja **nie zmienia żadnego koloru**.

## Wyjaśnienia pod „?" (2026-09-08)

Rozdziały pokazują **stan i liczby**, a całe tłumaczenie „co to jest i po co" chowa się pod
małym przyciskiem **„?"** w rogu rozdziału (uwaga Tomasza: opisy zajmowały pół panelu, a czyta
się je raz). Teksty siedzą w jednym miejscu w `app.js` (stała `HELP`), po jednym na rozdział:
rola, strona, wymiar, jakość, overprint, fonty, kolory. Kliknięcie rozwija, ponowne zwija,
przycisk podświetla się na czarno, gdy pomoc jest otwarta.

Przy okazji z rozdziałów zniknęły zdania, które i tak były wykładem: „Wskaż, którą rolę…",
„Wybierz stronę, którą sprawdzamy…", „Podgląd pokazuje już plik w docelowym formacie…",
opis mechanizmu overprintu i uwaga o fontach nieosadzonych. Zostały same znaczniki stanu
(`do wyboru`, `2 strony`, `wybrana`, `dopasowany`) i konkrety z liczbami.

## Windows: Ghostscript nie przyjmował ścieżki do profilu

U Tomasza konwersja kolorów kończyła się „GPL Ghostscript 10.07.1: Unrecoverable error,
exit code 1". Powód: Ghostscript czyta wartości parametrów jak łańcuchy PostScriptu, a profil
Adobe leży w `C:\Program Files (x86)\Common Files\…` — backslash jest tam znakiem ucieczki,
a nawiasy domykają łańcuch. Teraz profil jest **kopiowany do katalogu zadania pod bezpieczną
nazwą** i podawany ze zwykłymi ukośnikami; tak samo normalizujemy ścieżki wejścia i wyjścia.

Gdyby mimo to nie dało się użyć profilu, program **nie zatrzymuje się**: robi drugie podejście
bez profilu (żeby wiedzieć, czy zawodzi profil, czy sam plik) i — jeśli to pomaga — kończy
konwersję domyślnym profilem CMYK Ghostscripta, **pisząc o tym wprost w opisie poprawki**
razem z komunikatem Ghostscripta. Lepsze to niż cicha podmiana profilu albo ślepy błąd.

## Dlaczego kolory rozjeżdżały się z Photoshopem (2026-09-09)

Tomasz: „kolory się mocno różnią między Photoshopem a naszym programem". Złożyły się na to
dwie rzeczy — obie znalezione po komunikacie z jego maszyny (`Last OS error: Permission denied`).

**1. Ghostscript w ogóle nie czytał profilu.** W trybie `-dSAFER` czyta tylko to, na co dostał
zgodę, a profil to plik spoza pliku wejściowego i wyjściowego. Na Windowsie kończyło się to
„Unrecoverable error" i cichym zejściem na domyślny profil CMYK Ghostscripta (SWOP-owaty) —
czyli dokładnie na inne kolory. Teraz do każdego wywołania idzie
`--permit-file-read=<profil>`, a gdyby to nie wystarczyło, jest jeszcze podejście bez
`-dSAFER` (profil to nasz plik, nie cudzy) i dopiero na końcu — z komunikatem — konwersja
domyślnym profilem.

**2. Podgląd renderował CMYK bez profilu.** Nawet z dobrą konwersją ekran pokazywał barwy
przeliczone domyślnym profilem Ghostscripta, więc różnica wobec Photoshopa była większa niż
sama poprawka. Render dostał `-sDefaultCMYKProfile=<FOGRA39>`, czyli robi to samo, co soft
proof w Photoshopie.

Sprawdzenie: pięć pól z próbnika, kolory odczytane **ze zrzutu ekranu programu** wobec
przeliczenia tych samych wartości CMYK przez littleCMS (FOGRA39 → sRGB, relatywna
kolorymetryczna + BPC — tak liczy soft proof):

| pole | podgląd w programie | wzorzec (soft proof) | różnica |
|---|---|---|---|
| czerwień | 228, 11, 22 | 228, 11, 22 | 0 |
| błękit | 68, 99, 172 | 68, 99, 172 | 0 |
| zieleń | 57, 169, 58 | 55, 169, 58 | 2 |
| żółty | 248, 218, 0 | 248, 218, 0 | 0 |
| fiolet | 128, 34, 130 | 129, 34, 130 | 1 |

Czyli różnice na poziomie zaokrągleń (≤ 2 z 255).

## Start od 100 % i koniec z migotaniem rozdziałów (2026-09-09)

- **Plik otwiera się w swoim własnym rozmiarze.** Panel wymiaru startował od „wypełnij format"
  (np. 97,8 %), więc plik od razu był przeskalowany. Teraz zawsze zaczyna od **100 %** —
  najpierw widać, co przyszło, a dopiero potem decyduje się o kadrze. Skróty „wypełnij format"
  i „cały projekt" są tuż obok, jednym kliknięciem.
- **Rozdziały nie pojawiają się „na chwilę".** W trakcie wczytywania pliku i pobierania
  wytycznych program przez moment nie znał formatu, a wtedy `sizeSettled()` mówiło „wszystko
  gra" i wyskakiwały wszystkie rozdziały, żeby sekundę później zniknąć. Teraz stan „ustalony"
  wymaga, żeby **wiadomo było, czy w ogóle jest co ustalać**: dopóki lecą wytyczne (albo
  produkt jest potwierdzony, a wytycznych jeszcze nie ma), dalsze rozdziały są schowane.
- **Przyciski czekają na swoją treść.** „Zatwierdź rolę" wyskakiwał, zanim wczytała się lista
  ról. Teraz przycisk stoi na swoim miejscu, ale jest **wyszarzony** i pisze „Wczytuję
  wytyczne…", a lista ról jest zablokowana. Ta sama zasada obowiązuje wszędzie: dopóki program
  się zastanawia (wczytywanie pliku, pobieranie wytycznych), żaden przycisk rozdziału nie jest
  klikalny — wyszarzenie liczy się na samym końcu `updateCheckButton()`, po tym jak każdy
  przycisk policzy swój własny stan. Zmierzone: przycisk roli jest ukryty → szary (przez czas
  pobierania wytycznych) → aktywny dokładnie w chwili, gdy pojawia się lista.
- **Rozdział 2 czeka na rozdział 1.** „2 · Produkt" pojawia się dopiero, gdy plik jest
  przeczytany (strony, typ, kolory) — wcześniej wyskakiwał od razu po wgraniu, a fakty o pliku
  doskakiwały nad nim sekundę później. Zmierzone na pliku 74 MB: podgląd 6,7 s, a rozdział 2
  i fakty o pliku **w tej samej chwili** (8,2 s).

## Suwak w rozdziale: co zmienia TA JEDNA poprawka (2026-09-09)

Pod przyciskiem każdej nałożonej poprawki jest teraz mały suwak **przed / po**. Suwak główny
pod podglądem zostaje i dalej pokazuje całość (plik po wymiarze ↔ plik po wszystkich
poprawkach); suwak w rozdziale pokazuje **wyłącznie skutek tej jednej poprawki**.

Kluczowe jest, co jest po lewej stronie takiego suwaka. Nie „stan do tego kroku", tylko
**wszystko, co już zrobiliśmy, OPRÓCZ tej jednej poprawki** — dokładnie tak, jak chciał Tomasz:
„jak poprawię overprinty i potem wejdę w rozdział o kolorach, to lewy koniec suwaka ma już mieć
poprawione overprinty". Dzięki temu kolejność nakładania poprawek nie ma znaczenia, a suwak
zawsze odpowiada na jedno pytanie: *co ten przycisk zmienia w moim pliku teraz*.

Serwer liczy taki wariant **leniwie** — dopiero przy pierwszym ruchu suwaka — i trzyma obok
jako `wo_<nazwa>.pdf` (`?v=wo:<nazwa>` w adresach renderów i kafelków). Plik po samym wymiarze
jest przy tym używany ponownie, więc powstanie wariantu to zwykle jeden przebieg poprawek
na obiektach, nie liczenie wymiaru od nowa. Każda zmiana zestawu poprawek kasuje warianty
i ich rendery.

Sprawdzone na `Wydruk_adWall_Vario_Prosta_600_43` (wymiar + overprint + kolory):

| plik | obiekty z overprintem | profil w pliku |
|---|---|---|
| `base.pdf` (sam wymiar) | 1 | nie |
| `wo_overprint.pdf` | 2 (poprawka pominięta) | tak |
| `wo_cmyk.pdf` | 0 (overprint poprawiony) | tak |
| `fixed.pdf` | 0 | tak |

Czyli w rozdziale o kolorach lewy koniec suwaka ma już naprawione overprinty — o to chodziło.

Wymiar jest wyjątkiem: bez niego strona ma inny format i warstwy nie leżałyby na sobie,
więc w tym rozdziale suwaka nie ma (od tego jest suwak główny).

## Do zrobienia

- Kolejne poprawki w tym samym rejestrze (RGB→CMYK, spot→CMYK, spłaszczenie,
  znaczniki drukarskie).
- Wybór, które poprawki zastosować, gdy będzie ich więcej niż jedna.
- Lista miejsc, w których overprint zmienia wygląd (mamy oba rendery — wystarczy je
  porównać i pokazać obszary nawigatorem, tak jak przy jakości).
- **Przycisk „pobierz podgląd"** — zapis tego, co widać na ekranie (z ramkami formatu
  i szablonu albo bez), do wysłania klientowi jako obrazek.
- **Spłaszczenie kolorów dodatkowych** — dziś po konwersji zostaje nazwana separacja
  z alternatywą CMYK (drukuje się procesowo, ale w pliku widać spot). Do zrobienia:
  przepisanie operatorów `scn` na `k` z wyliczeniem funkcji tint transform (najpewniej przez
  sondę renderowaną Ghostscriptem, bo to jedyny pewny sposób na funkcje typu 4).
- **Plik w złej skali** — do przemyślenia, jak to naprawiać. Dziś program wykrywa, że plik
  1:1 trafił na produkt w 1:10 (albo odwrotnie), i podpowiada produkt po wymiarze, ale sam
  nie przelicza pliku. Do rozstrzygnięcia: czy przeskalować stronę (i co wtedy z ppi rastrów,
  bo one się nie zmienią), czy tylko ostrzec i kazać poprawić plik u źródła.

### Dokładanie tła domyślnie WYŁĄCZONE

`dołóż tło na marginesach` startuje odznaczone (ustalenie Tomasza). Dokładanie tła to
ingerencja w projekt — włącza się je świadomie, a nie znajduje po fakcie w gotowym pliku.
Opis pod suwakami mówi wtedy wprost: „PUSTE PASY 55,0×40,0 mm".

Przy okazji: z wyłączonym tłem przycisk „Dopasuj wymiar" **nic nie robił**. `resize_page`
ustawiała zmienną `filled` wyłącznie w gałęziach dokładających tło, więc bez tła `return`
wywracał się na `NameError` i poprawka kończyła się błędem. Teraz `filled = 0` stoi przed
pętlą.

### Zamiana na CMYK: szybka ścieżka dla plików, które już są w CMYK

Konwersja pliku 60 MB trwała **43 s**. Pomiar pokazał, że cały ten czas to rozpakowywanie
i pakowanie z powrotem obrazu 11891×9055 px — obrazu, który **już był w CMYK**. Robota do
wyrzucenia, i to nie darmowa: Ghostscript przy okazji przebudowuje separacje.

Próbnik: 4010 pól CMYK z profilem ISO Coated v2 (takim, jaki siedzi w pliku Tomasza),
przeliczonych na Coated FOGRA39, porównanie **wyglądu** (przez oba profile do sRGB),
realne separacje do 320 % farby:

| co robimy z wartościami CMYK | różnica wyglądu wobec oryginału |
|---|---|
| littleCMS z ustawieniami Photoshopa (wzorzec) | średnio **1,0** / 255 |
| zostawiamy je nietknięte (szybka ścieżka) | średnio **1,3** / 255 |
| przeliczamy Ghostscriptem (stara droga) | średnio **9,0** / 255, p95 13, max 34 |

Same liczby CMYK zmieniają się przy konwersji średnio o 30/255 na kanale — to inny rozkład
farb (czerń zamiast trzech kolorów), przy tym samym wyglądzie. Czyli przeliczanie CMYK-u,
który jest już CMYK-iem, **oddala plik od Photoshopa**, zamiast go do niego zbliżać.

Dlatego `to_cmyk` sprawdza teraz rodziny kolorów w pliku:

- **tylko CMYK i kolory dodatkowe** → `-dColorConversionStrategy=/LeaveColorUnchanged`
  z `-dProcessColorModel=/DeviceCMYK`. Ghostscript nie rusza wartości, tylko liczy przejście
  tonalne spotów na ich przestrzeń alternatywną. Sprawdzone na próbniku spotu: alternatywa
  0,15/0,35/0,85/0,05 przy krycia 100 % daje 0,149/0,349/0,847/0,047, a przy 50 % dokładnie
  połowę — dokładnie to, co robi Photoshop przy zamianie na farby procesowe.
- **cokolwiek w RGB/Gray/Lab** → stara, pełna konwersja (tam przeliczyć trzeba, a dla
  RGB→CMYK Ghostscript był już wcześniej sprawdzony wobec littleCMS: ≤0,03 na kanał).

Wynik na pliku `1878…` (60 MB): **43 s → 2,8 s**, wygląd wobec oryginału średnio **0,33**/255
zamiast 7,67, a kolor dodatkowy GOLD 2 zniknął z pliku naprawdę (stara droga zostawiała go
jako nazwaną separację). W programie: 50 s → 5 s.

### Profil kolorystyczny: trzecia opcja — „zostaw profil z pliku"

Wybór profilu ma teraz trzy pozycje: **Coated FOGRA39**, **zostaw profil z pliku**, **bez
profilu**. Powód jest ten sam co przy szybkiej ścieżce: plik zwykle jest już przygotowany pod
konkretną maszynę (u nas najczęściej ISO Coated v2, czyli ta sama norma FOGRA39), więc
przestawianie go na inny profil tej samej normy to zmiana bez powodu.

Przy „zostaw profil z pliku":

- konwersja bierze za profil docelowy **profil z pliku** (OutputIntent, a jak go nie ma —
  pierwszy osadzony profil CMYK; gdy nie ma żadnego, wraca Coated FOGRA39),
- deklaracji profilu w ogóle nie ruszamy — poprawka `intent` się nie wykonuje,
- OutputIntent jest po konwersji **odtwarzany**, bo Ghostscript przepisując plik i tak go
  wyrzuca; sprawdzone: przed i po jest `ISO Coated v2 (ECI)`.

Przycisk mówi, co zrobi: „Zamień kolory na CMYK, profil bez zmian".

## Rozdział „Spłaszcz projekt"

Spłaszczanie w rozumieniu Photoshopa (wybór Tomasza spośród trzech wariantów): **cała strona
idzie jako jeden obraz CMYK**, w **120 ppi na wydruku** — tym samym progu, którym mierzymy
jakość rastrów w rozdziale o jakości.

Po co: żywa przezroczystość (maski, cienie, tryby mieszania) jest spłaszczana dopiero w RIP-ie.
Zwykle wychodzi dobrze, ale tam, gdzie przezroczystość spotyka się z kolorem dodatkowym albo
overprintem, potrafi zostawić szew, jasną obwódkę albo przesunięcie koloru — i widać to
dopiero na wydruku. Jak spłaszczymy sami, podgląd pokazuje dokładnie to, co pójdzie na maszynę.

Cena, powiedziana wprost w rozdziale: **tekst i wektory tracą ostrość** (dostają rozdzielczość
rastra), a plik rośnie — wydruk 3 m to ok. 110 MB.

Rozdział jest widoczny zawsze (jak „Fonty"). Gdy plik nie ma przezroczystości, przycisk jest
wyszarzony z wyjaśnieniem — zamiana ostrych wektorów na raster „na wszelki wypadek" byłaby
stratą, nie poprawką. Cały raport o przezroczystości (dawne „Pozostałe: przezroczystość…")
przeniósł się tutaj i jest napisany po ludzku: „obraz z własną przezroczystością (wycięte
logo, miękki cień, plik z alfą)" zamiast „obraz z maską (SMask) (1)".

### Jak to jest zrobione

`fixes.flatten_page`: Ghostscript rysuje stronę prosto do **CMYK-owego JPEG-a**
(`-sDEVICE=jpegcmyk`, `-dOverprint=/simulate` — na urządzeniu CMYK to nie symulacja, tylko
realne zachowanie farby), a my pakujemy ten obraz w stronę o tym samym wymiarze.

Trzy rzeczy, które musiały się zgadzać:

- **Rozdzielczość liczy się NA WYDRUKU.** Przy pliku w skali 1:10 render idzie w 1200 dpi
  pliku, żeby na wydruku wyszło 120 ppi.
- **Profil.** Domyślnie ten z pliku (jak w rozdziale o kolorach), bo przeliczanie CMYK-u,
  który już jest CMYK-iem, tylko oddala plik od oryginału. `-sOutputICCProfile`
  i `-sDefaultCMYKProfile` dostają ten sam profil, więc wartości nie są ruszane.
- **`/Decode [1 0 1 0 1 0 1 0]`.** CMYK-owy JPEG spod Ghostscripta idzie w konwencji Adobe
  (wartości odwrócone) — bez tego strona wychodzi jak negatyw. Zmierzone: różnica 138/255
  bez `/Decode`, 6,9/255 z nim (a te 6,9 to wyłącznie krawędzie liter, bo wektor stał się
  rastrem — na płaskich polach różnicy nie ma).

Jakość JPEG-a: 90. Zmierzone alternatywy — q95 daje poprawę wyglądu o 0,07/255 i plik
155 MB zamiast 110 MB, q98 poprawę o 0,12/255 i 207 MB. Nie warto.

Poprawka idzie **na samym końcu** kolejki (wymiar → krzywe → kolory → profil → overprint →
spłaszczenie), bo zapieka wszystko, co zrobiliśmy wcześniej. Przy stronie, która przy 120 ppi
przekroczyłaby 260 megapikseli, program schodzi z rozdzielczości i pisze o tym w raporcie.

Zmierzone: strona 3075 × 2340 mm → obraz 14 528 × 11 055 px, 3,5 s (plik 2 MB) i 21 s
(plik 60 MB), wynik ok. 110 MB.

## Przycięcie spadów (`trim`)

Poprawka `trim` opisana jest w osobnym rozdziale — `11_spady.md`. Tutaj tylko to, co dotyczy
potoku: jest to poprawka typu `page`, idzie **pierwsza** (przed ramkami i wymiarem), zmienia
wyłącznie ramki strony (`MediaBox`/`CropBox`/`TrimBox`, kasuje `BleedBox`/`ArtBox`), więc nie
rusza treści i nie kosztuje jakości. Pełna kolejność potoku:

```
spady → ramki z szablonu → wymiar → kolory (CMYK) → fonty na krzywe → overprint/intent
→ spłaszczenie
```

`fileMm()` po nałożeniu `trim` (a przed `resize`) podaje wymiar **netto**, żeby rozdział
o wymiarze porównywał się z tym, co faktycznie pójdzie na maszynę.

## „WinError 5: Odmowa dostępu" przy podmianie pliku

Zgłoszone przez Tomasza: poprawka kończyła się błędem
`PermissionError: [WinError 5] ... fixed.pdf.14b1c817.tmp -> fixed.pdf`.

Windows nie pozwala nadpisać pliku, który ktokolwiek trzyma otwarty. Serwer zamykał otwarte
kopie **przed** poprawką (`preview.forget_doc`), ale poprawka trwa kilka–kilkanaście sekund,
a podgląd przez cały ten czas prosi o kafelki poprzedniej wersji (warstwa „po" pod suwakiem
porównania) — i każdy taki render otwierał dokument z powrotem. Wystarczyło, żeby trafił
w moment podmiany.

Trzy zabezpieczenia, od najważniejszego:

- **Na czas poprawki serwer nie renderuje wersji poprawionych.** Zadanie ląduje w rejestrze
  `_fixing`, a zapytania o `?v=fix`, `?v=base` i `?v=wo:…` dostają 409. Przeglądarka po
  prostu poprosi jeszcze raz, gdy poprawka się skończy — kafelki i tak umieją to obsłużyć.
- **`_swap` zamyka otwarte kopie przy KAŻDEJ próbie**, nie tylko raz przed. Prób jest 24,
  z narastającą przerwą.
- `trim_page` (nowa poprawka „spady") woła `forget_doc` przed podmianą, tak jak reszta.

### Dlaczego po spłaszczeniu litery są poszarpane

Pytanie Tomasza po obejrzeniu spłaszczonego pliku w dużym powiększeniu. Odpowiedź jest
wpisana w samą poprawkę: **spłaszczenie zamienia wektory na piksele**. Przed nią litera była
krzywą — ostrą przy każdym powiększeniu. Po niej cała strona to jeden raster 120 ppi
na wydruku, więc powyżej rozmiaru rzeczywistego widać pojedyncze piksele wydruku.

Sprawdzone na `Wydruk_adWall_Vario_Prosta_600_43_jednostronny_przod.pdf` (616 × 232 mm,
napis „premis" jest wektorem — plik ma 2599 obiektów wektorowych i ani jednego znaku tekstu):
ten sam wycinek renderowany przy ok. 600 % rozmiaru rzeczywistego wychodzi gładko
z oryginału i schodkowo ze spłaszczonego. Przy 100 % (rozmiar rzeczywisty) różnicy nie widać.

Dwie rzeczy dokładają się do wrażenia „schodków":

- **120 ppi to nasze minimum dla wielkiego formatu**, a nie wartość dobrana do tego pliku.
  Przy 616 mm szerokości i oglądaniu z pół metra krawędź litery przeskakuje co 0,21 mm —
  na banerze 3 m z odległości 2 m to niewidoczne, na tabliczce 60 cm już nie.
- **Ghostscript nie wygładza obrazu, który nie ma flagi `/Interpolate`** — a nasz spłaszczony
  obraz jej nie ma. Powiększenie powiela więc piksele zamiast je mieszać. Świadomie tego nie
  zmieniamy: podgląd ma pokazywać to, co jest w pliku, a nie ładniejszą wersję.

### Rozdzielczość spłaszczenia zależy teraz od formatu

Tomasz porównał to z Photoshopem: *„gdy spłaszczam w Photoshopie, litery nie są tak
poszarpane"*. I ma rację — tyle że Photoshop nie jest mądrzejszy, on po prostu pracuje na
dokumencie w 300 dpi, a my rasterowaliśmy w 120.

Zmierzone na `Wydruk_adWall_Vario_Prosta_600_43` (616 mm, napis „FIATC" jest wektorem),
ten sam wycinek w powiększeniu ok. 600 %:

| ppi | wygląd krawędzi | plik | czas |
|---|---|---|---|
| 120 | wyraźne schodki | 0,9 MB | 0,5 s |
| 200 | ledwo widoczne | 1,7 MB | 0,6 s |
| 300 | praktycznie jak wektor | 2,8 MB | 1,1 s |

Anti-aliasing działał cały czas (`-dTextAlphaBits=4 -dGraphicsAlphaBits=4`; zmierzone 4,3 %
pikseli o wartości pośredniej na krawędziach) — problemem była sama liczba pikseli.

Reguła (`fixes.flatten_ppi_for`), dobrana wg tego, z jakiej odległości patrzy się na wydruk
danej wielkości:

```
dłuższy bok wydruku ≤ 0,8 m   → 300 ppi
                    ≤ 1,5 m   → 200 ppi
                    ≤ 3 m     → 150 ppi
                    powyżej   → 120 ppi   (próg z wytycznych; z 3 m schodków nie widać)
```

Sufit 260 megapikseli zostaje — przy stronie, która by go przekroczyła, program schodzi
z ppi i pisze o tym w raporcie.

Zmierzone po zmianie:

```
adWall 616 × 232 mm      300 ppi   7276 × 2740 px    3 MB    1,4 s   (było 120 ppi, 0,9 MB)
adFrame 1015 × 2513 mm   150 ppi   5994 × 14840 px  18 MB    5,4 s
strona 3020 × 2300 mm    120 ppi  14268 × 10866 px 111 MB   22,9 s   (bez zmian)
```

Klient wysyła teraz `ppi: 0` („dobierz sam"), a rozdzielczość liczy się z wymiaru wydruku
(strona × skala), więc plik w skali 1:10 dostaje ją tak samo poprawnie. Podpowiedź przy
przycisku mówi, ile ppi dostanie TEN wydruk, a raport — ile faktycznie dostał.

Wniosek praktyczny bez zmian: spłaszczać tylko wtedy, gdy jest po co (przezroczystość,
overprint na przezroczystości), bo ostry wektor zawsze bije raster.


## Dwa miejsca, w których program pokazywał stan SPRZED poprawki (2026-09-10)

Dwa zgłoszenia Tomasza, jedna przyczyna: coś czytało wersję pliku sprzed poprawek,
choć na ekranie była już wersja po nich.

### 1. Dołożone tło wciągało spady z krawędzi

*„Gdy ucinam spady i dokładam tło, to widać te spady. W jaki sposób spady są przycinane?
Wydaje mi się, że trzeba je trochę bardziej przyciąć."*

Przycinanie jest w porządku i nie trzeba ciąć więcej. `trim_page()` ustawia `MediaBox`,
`CropBox` i `TrimBox` na ramkę `TrimBox` z pliku (u `spady.pdf`: 11,64 mm z każdej strony),
więc wszystko, co leżało na spadzie, wychodzi poza stronę i żaden renderer tego nie pokaże.
Sprawdzone na `spady.pdf`: w oryginale przy lewej krawędzi siedzi pasek kontrolny CMYK
(x 2,0–7,2 mm) i znaczniki drukarskie (y 2,2–7,0 mm) — **wszystkie poza `TrimBoxem`**;
po przycięciu render 15-milimetrowego pasa przy każdej krawędzi nie zawiera ani jednego
takiego piksela. Także gotowy plik po „Dopasuj wymiar" z dołożonym tłem jest czysty —
`_fill_edges()` próbkuje krawędź z pliku PO przycięciu.

Nieprawdę pokazywał **podgląd**. `edgeFillDraw()` wycinał rząd pikseli z `stageImg`, czyli
z DOLNEJ warstwy porównania — a ta pokazuje wersję „przed poprawkami", więc wciąż ze spadami.
Rozciągnięty na margines rząd z paskiem kontrolnym dawał dokładnie to, co Tomasz widział:
poziome paski cyan/magenta/żółty/czarny przy krawędzi i czarny prostokąt przy górnym rogu.
Teraz piksele bierzemy z warstwy „po poprawkach" (`stageImgFix`, gdy jakakolwiek poprawka
jest nałożona), a po jej doczytaniu tło rysujemy jeszcze raz. To samo dotyczy trybu
„odbicie lustrzane".

### 2. Rozdziały opisywały plik sprzed poprawki

*„Jak na ramkach z szablonu są fonty i usunę je przez nasz program, to w rozdziale Fonty
te fonty i tak są wykrywane."*

Analiza pliku (`/api/jobs/<id>/analysis`) była pobierana **raz, przy wgraniu, i zawsze
dla oryginału**. Serwer od dawna umie policzyć ją dla wersji po poprawkach (`?v=fix`,
osobny slot `analysis_fix`, unieważniany przy każdej nowej poprawce) — tylko klient o to
nie prosił. Skutek: po każdej poprawce zmieniającej treść rozdziały „Fonty", „Kolory",
„Overprint" i „Spłaszcz" opisywały plik sprzed niej. Najbardziej rzucało się to w oczy
po usunięciu ramek z szablonu i po zamianie tekstu na krzywe.

Teraz po każdej nałożonej i cofniętej poprawce klient dociąga analizę TEJ wersji
(`refreshAnalysis()`). Sprawdzone na `fonty.pdf`: przed zamianą na krzywe rozdział pokazuje
„3 fonty", po zamianie — „brak — wszystko w krzywych" (wcześniej dalej wisiały trzy).
Mapy detalu to nie dotyczy: ona liczy się z oryginału i skali `k`, więc poprawki treści
jej nie unieważniają, a wynik „Sprawdź jakość" nie znika po każdym kliknięciu.

**Co z tego zostaje otwarte.** Usunięcie ramki kasuje operatory rysujące SAM KSZTAŁT.
Jeśli szablon dopisał przy ramce OPIS (tekst w kolorze wytycznych), to ten tekst zostaje
w pliku — i rozdział „Fonty" słusznie nadal pokaże jego font. Rozszerzenie usuwania
o teksty w kolorze szablonu jest do zrobienia; potrzebny plik, na którym to widać.


## Po przycięciu spadów: biały pasek przy krawędzi i rozdział wymiaru, który nie wracał (2026-09-10)

### 3. „Zostaje pusty pasek na dole, widoczny nawet jak dokładam tło"

To nie był plik. Zmierzone: przycięta strona jest w dolnych 400 mm jednolicie granatowa,
bez jednego jasnego piksela; jasny pas w oryginale (ostatnie **1,8 mm** przed krawędzią
mediów) leży w obszarze spadu i przycięcie go usuwa.

Pasek rysował **podgląd**. Piramida każdej warstwy jest planowana z wymiaru NA WYDRUKU,
a ten klient liczył z wymiaru strony ORYGINAŁU — także dla warstwy „po poprawkach".
Po przycięciu spadów ta warstwa pokazuje stronę 950 × 1950 mm, a jej piramida była
policzona dla 973,3 × 1973,3 mm. Proporcje różnią się o 1,2 %, więc kafelki, wpasowane
szerokością w prostokąt projektu, kończyły się **~6 px nad jego dolną krawędzią** —
i w tej szczelinie prześwitywało białe tło strony. Dołożone tło zaczyna się dokładnie
przy krawędzi projektu, więc paska nie zakrywało.

Teraz warstwa pyta o wymiar SWOJEJ wersji pliku (`pyrPageMm()`): po przycięciu spadów
bierze `fixGeom.page_mm`, a wersja „wszystko oprócz jednej poprawki" ma spady przycięte,
chyba że to właśnie ich dotyczy (`wo:trim`). Sprawdzone na `spady.pdf` przy skali 85 %
z dołożonym tłem: przed poprawką biały pas ~5 px przy dolnej krawędzi, po poprawce
granat dochodzi do samej ramki formatu.

### 4. Ustawienia rozdziału „Wymiar wydruku" nie wracały do wyjściowych

*„Jak bawię się suwakami od wymiaru i potem kliknę np. przytnij spady, to mimo że nie
zaakceptowałem wymiaru, wymiar nie cofa się do oryginalnego."*

Rozdział resetował się tylko wtedy, gdy przy OTWARTYM rozdziale zmienił się klucz
(plik × format). Cofnięcie wcześniejszego kroku rozdział **zamyka** — a wtedy funkcja
kończyła się przed resetem i w polach zostawała skala, przesunięcie i „dołóż tło"
ustawione dla strony, której już nie ma. Samo dokładanie tła nie było resetowane nigdy.

Teraz zamknięcie rozdziału czyści ustawienia (`sizeClear()`), a reset przy zmianie klucza
obejmuje też „dołóż tło" i metodę — to ustawienia KADRU, nie preferencje użytkownika.
Zmierzone na `spady.pdf` (985 × 1926 mm z wytycznych), cykl przycięcie → suwaki → cofnięcie
→ przycięcie: skala 88 % / przesunięcie 30 / tło włączone wracają do 100 % / środek /
wyłączone, a opis rozdziału mówi o wymiarze tej strony, która jest teraz.
