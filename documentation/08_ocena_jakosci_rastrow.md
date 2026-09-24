# 08 · Ocena jakości rastrów — model docelowy (baza elementu + etykieta pewności z szumu)

Data: 2026-09-07. Zmiany w `app/detailmap.py`, `app/analyze.py`, `app/static/app.js`.
Zastępuje mechanizm z etapu 07 w części dotyczącej fragmentów.

## Problem

Na pliku 1878 program pokazywał **59–61 „słabych obszarów"**, wszystkie wewnątrz JEDNEGO
tła (11891×9055 px, 100 ppi nominalnie, powiększone ~3×). Całe zdjęcie jest jednakowo
słabe, a program pokroił je na przypadkowe prostokąty. Na poprawnym adFrame_Smart
pokazywał 41 fragmentów, których nie ma.

Przyczyna była konstrukcyjna, nie progowa: **blok był jednostką raportu**, a jego
współczynnik porównywano z progiem bezwzględnym. Obraz zły w całości rozpadał się na
tyle klastrów, ile było miejsc z kontrastem.

## Trzy pytania o różnej pewności

| pytanie | pewność | rola |
|---|---|---|
| ile jest pikseli na mm wydruku (nominalne ppi) | **fakt geometryczny** | werdykt |
| czy te piksele niosą detal (baza elementu) | pewne (mediana po całym obiekcie) | werdykt |
| czy jakiś fragment odstaje od reszty obiektu | oszacowanie | lista „do sprawdzenia" |

## Jednostka raportu: element, nie blok

Raport to lista **elementów** (obiektów rastrowych z ich użyciami), a nie kwadratów.
Fragment wewnątrz elementu trafia na listę tylko, gdy jest wyjątkiem **względem bazy
tego elementu** — nie względem progu 120 ppi.

**Baza elementu = MEDIANA** współczynników bloków z detalem. Pomiar rozkładów:

| plik | rozkład f | mediana | wynik |
|---|---|---|---|
| adFrame_Smart (natywne 120 ppi) | 90 % f=1 | 1 | 120 ppi ✓ |
| 1878 (tło powiększone 3×) | 50 % f=3, 24 % f=1, 17 % f=2 | 3 | 33 ppi ✓ |

25. percentyl (pierwsza wersja) dawał na 1878 f=2 → 50 ppi, czyli **zaniżał wadę**.
Mediana trafia w obie strony i zgadza się z niezależnym pomiarem obiektowym.

Dodatkowe zabezpieczenia: sąsiadujące bloki sklejane przez rozszerzenie maski o 1 blok
(jedna wada = jeden prostokąt); gdy „wyjątki" obejmują > 15 % bloków elementu, to nie
wyjątek tylko charakter elementu i zgłaszamy sam element.

## Szum — dlaczego i skąd

Sama baza nie wystarczyła: na poprawnym adFrame_Smart zostawało 41 fragmentów.
**Wyciągnąłem je w natywnych pikselach i obejrzałem** — to wnętrze bębna poza ostrością,
gradienty obudowy, miękkie cienie. Nie wady.

Zmierzyłem trzy sposoby odróżnienia „powiększone" od „miękkie z natury":

1. **Krzywa strat (kolano)** — nie rozdziela (to ona te fragmenty zgłasza).
2. **Szerokość najostrzejszej krawędzi** — teoretycznie idealna (obraz powiększony f× nie
   ma nigdzie krawędzi ostrzejszej niż f px). W praktyce na materiale JPEG: fragment ostry
   2,50 · fałszywki 3,00–3,24 · tło 1878 (pewne powiększenie 3×) 2,62–2,94.
   **Liczby się pokrywają — metoda odrzucona.**
3. **Poziom szumu — działa.** Rozmycie optyczne NIE usuwa szumu matrycy/JPEG-a (szum
   powstaje po rozmyciu); interpolacja przy powiększaniu wygładza go razem z obrazem.
   Pomiar w obrębie jednego zdjęcia: miękkie fragmenty 1,21–1,58, ten sam fragment
   powiększony 3× → 0,70, 4× → 0,53.

`block_noise()`: |Laplace| uśredniony po podkafelkach 16 px, z bloku brana średnia
**najspokojniejszej ćwiartki** podkafelków (miara niezależna od treści). Odniesieniem
jest mediana szumu całego elementu; `noise_ratio` = szum fragmentu / szum elementu.

### Szum jest ETYKIETĄ, nie filtrem (korekta po uwadze Tomasza)

Pierwsza wersja używała szumu jako **bramki**: fragment z zachowanym ziarnem nie trafiał
na listę. To był błąd — na adFrame_Smart wypadł w ten sposób fragment (bęben pralki),
który Tomasz uznaje za realną wadę. Decyzja „wrzucamy wszystko do jednego worka,
użytkownik sam ocenia" była wcześniej ustalona i bramka jej przeczyła.

Teraz **nic nie wypada**. Każdy fragment dostaje etykietę `confidence`:

| `confidence` | warunek | co znaczy dla użytkownika |
|---|---|---|
| `confirmed` | `noise_ratio ≤ 0,70` | „pewne" — ziarno zniknęło, typowe dla powiększania |
| `soft` | `noise_ratio > 0,70` | „do obejrzenia" — ziarno zachowane, może być bokeh/rozmycie |
| `synthetic` | `noise_ratio < 0,15` | „gładka treść" — obszar bez ziarna (grafika, tło, gradient) |
| `unknown` | element bez mierzalnego ziarna | „do obejrzenia" — nie da się rozstrzygnąć |

Sortowanie na liście: najgorsze ppi na górze, `synthetic` na końcu (tam najłatwiej
o fałszywy alarm). Etykieta widoczna jako znacznik przy każdej pozycji.

## Granica metody (świadoma)

Fragment musi mieć **f ≥ 3** (≤ 40 ppi przy 120 nominalnych). Przy f = 2 (60 ppi)
ŻADEN z dwóch sygnałów nie rozdziela: krzywa strat myli to z miękką treścią, a szum
przy powiększeniu 2× jest jeszcze na poziomie tła (1,05–1,09 wobec 0,67 przy 3×).
Dotyczy to tylko plików **spłaszczonych** — w PDF-ie z obiektami taki obraz łapie
nominalne ppi, które jest faktem.

Minimalny raportowany fragment: **10 mm na wydruku** (decyzja Tomasza), liczone po
przeskalowaniu przez k (1:10).

## Jeden worek (decyzja Tomasza)

Nie ma osobnej listy „gładkich". Jest jedna lista „miejsca do sprawdzenia", posortowana
od najgorszego ppi, po której użytkownik przechodzi nawigatorem i sam ocenia okiem.
Fragmenty miękkie bez oznak powiększenia **też są na liście** — z etykietą
„do obejrzenia" / „gładka treść". Nic nie znika po cichu; jedyne, co odpada, to
fragmenty mniejsze niż 10 mm i te, które po przeliczeniu mają ≥ 120 ppi (i one też są
policzone w linijce podsumowania).

Próg 120 ppi jest **sztywny**, bez uwzględniania odległości oglądania — odległości nie
znamy i bywa różna.

## Co naprawdę idzie na druk (przycięcie do strony + widoczność)

Obraz bywa umieszczony na obszarze większym niż strona albo zasłonięty. Zgłoszenie
liczone na pikselach obrazu tego nie widzi — i tak powstał błąd na
`adWall_Vario_Prosta_Light_300`: zdjęcie 7008×4672 px rozłożone na 2780×1885 mm
zaczyna się 513 mm od góry i kończy 118 mm **poniżej dolnej krawędzi strony**.
Fragmenty z tej wystającej części dostawały `fy > 1`, a ramka lądowała pod projektem,
na tle podglądu.

Dwa zabezpieczenia, oba przed sortowaniem listy:

1. **Przycięcie do strony** (`clip_to_page`) — obszar zawsze mieści się w formacie;
   co wystaje poza stronę, nie idzie na druk i nie jest zgłaszane. Obszar w całości
   poza stroną odpada. Wymiar w mm przelicza się proporcjonalnie.
2. **Widoczność** (`page_alpha_map` + `apply_visibility`) — jeden render finalnej
   strony z kanałem alfa (≈ 1 px/mm). Gdzie nic nie jest namalowane (maska SMask,
   ścieżka przycinająca, alfa 0), tam nie ma czego oceniać: obszar odpada. Obszar
   częściowo zasłonięty przycinamy do widocznej części, żeby ramka pokazywała realną
   treść. Gdy render zawiedzie — nie odrzucamy niczego.

To jedyne dwa powody, dla których coś znika z listy „na twardo". Miękkość, gładkość,
brak ziarna — nie; te dostają etykietę i zostają (patrz wyżej).

Ramka w podglądzie jest dodatkowo obcinana do strony po stronie UI — na wypadek
danych z wcześniejszych wersji.

## Raport dla człowieka nietechnicznego (wrzesień 2026)

Raport czytają osoby bez przygotowania technicznego. Tomasz zgłosił, że stary był
nieczytelny i wewnętrznie sprzeczny: nagłówek mówił „Rastry mają wystarczająco dużo
pikseli — wydruk będzie ostry (≥ 120 ppi)", a niżej „14 miejsc, bardzo słaba, 20 ppi".

Przyczyna: **dwa różne rodzaje wady były mieszane w jeden werdykt.**

| rodzaj | co to jest | pewność | co z tym robić |
|---|---|---|---|
| **za mało pikseli** (`reason: lowres`) | obraz ma mniej pikseli, niż wymaga jego rozmiar na wydruku | fakt geometryczny, pewna wada | wymienić plik na większy |
| **wygląda na powiększone** (`upscaled` / `coarse`) | pikseli jest dość, ale nie niosą szczegółu — ktoś powiększył mniejszy kawałek przed wstawieniem | ocena treści | obejrzeć i zdecydować |

Zdanie „ma dość pikseli" i „wygląda słabo" nie są sprzeczne — dotyczą różnych rzeczy.
Raport mówi to teraz wprost, jednym werdyktem:

- **Za mała rozdzielczość** (czerwony) — jest choć jeden obraz `lowres`.
- **Do obejrzenia** (żółty) — rozdzielczość OK, ale są miejsca wyglądające na powiększone.
- **Jakość w porządku** (zielony) — nic.

Zasady redakcyjne:

- Jeden werdykt na cały plik, na górze, dużą czcionką, w jednym akapicie bez żargonu.
- Liczby techniczne (ppi obrazów, tabela, pokrycie, ziarno) schodzą do „szczegółów
  technicznych" albo do dymka `title`.
- Blok „rozdzielczość" **nie wystawia już własnej oceny** — podaje same liczby.
  Tabela obrazów straciła kolumnę „jakość".
- **Werdykt pada raz.** Nagłówek sekcji podaje samą liczbę („najgorsze miejsce
  ≈ 30 ppi"); słowo oceny („za mała rozdzielczość") niesie wyłącznie kolorowy panel
  tuż pod nim. Reguła skali 1:10 też jest wyjaśniona tylko w panelu.
- **Żadna liczba nie pada dwa razy.** Zdanie „Najsłabszy obraz: 4795 × 11872 px na
  1014,9 × 2512,9 mm — 1 piksel = 0,2 mm" powtarzało co do cyfry wiersz tabeli tuż pod
  nim, a przy jednym obrazie w pliku było czystym dublem. Usunięte; zostaje tabela.
- Nagłówek sekcji powtarza **dokładnie** werdykt panelu („do obejrzenia", „za mała
  rozdzielczość", „jakość w porządku"), a nie własną ocenę literową z nominalnego ppi —
  wcześniej pisał „bardzo słaba", gdy panel mówił „do obejrzenia".
- **Jeden przycisk.** Panel ma dokładnie jedną akcję („Pokaż miejsca na podglądzie"),
  która zaczyna od najgorszego i strzałkami prowadzi dalej — plus zdanie, że lista jest
  posortowana od najgorszego. Wcześniej były trzy wejścia w to samo (przycisk w pasku,
  „pokaż najgorsze" i „przejrzyj wszystkie" w panelu) i trzeba było wybierać bez potrzeby.
- **Lista jest zwinięta.** Pełne pozycje siedzą w `<details>` „szczegóły techniczne";
  domyślnie widać sam werdykt i przycisk. Czternaście pozycji z powtarzającym się
  zdaniem wyjaśnienia przykrywało to, po co użytkownik tu przyszedł.
- Pozycje listy mają tytuł do kliknięcia („tło 40 × 81 mm — jak przy 20 ppi")
  i jedno zdanie wyjaśnienia pod spodem.
- **Każda liczba, która pada w tekście, musi mieć obok siebie sposób jej zobaczenia.**
  Pasek u góry mówił „najgorsze ≈ 20 ppi" i na tym kończył — nie dało się do tego
  miejsca dojść. Teraz zarówno pasek, jak i panel mają przycisk „Pokaż najgorsze",
  a „Przejrzyj wszystkie" jest dopiero drugie.
- Etykieta pewności pokazuje się tylko wtedy, gdy coś wnosi: „na pewno powiększone"
  albo „gładkie tło — pewnie nic złego". Przy 14 pozycjach z tą samą etykietą
  „do obejrzenia" jest to szum.

## Sprawdzanie na żądanie

Jakość liczy się **dopiero po kliknięciu „Sprawdź jakość"** (przycisk zastąpił dawny
„Sprawdź plik"). Powód: analiza obiektowa dużego pliku trwa kilkanaście sekund,
a wcześniej startowała sama zaraz po potwierdzeniu produktu — zanim użytkownik zdążył
cokolwiek przeczytać.

Zmiana produktu albo skali **unieważnia** wynik (bo od nich zależy rozmiar wydruku,
a więc wszystkie ppi) i pokazuje „Wynik jest nieaktualny — kliknij Sprawdź jakość
jeszcze raz". **Nie przelicza go sama.**

Pierwsza wersja przeliczała automatycznie i miała błąd: przy potwierdzaniu produktu
`detailOnScaleChange()` wołane jest dwa razy — raz po samym produkcie, raz po wczytaniu
szablonu (wtedy dopiero znane jest `k`). Pierwsze wywołanie startowało liczenie, drugie
podbijało `dmSeq` i je anulowało. Zasada: **liczenie startuje wyłącznie z przycisku**,
wszystko inne co najwyżej unieważnia wynik.

### Drugie źródło tego samego objawu (i ono było właściwe)

Objaw „po potwierdzeniu produktu przez chwilę idzie sprawdzanie i się anuluje" utrzymał
się po powyższej poprawce, bo miał **inną przyczynę**: to nie było sprawdzanie jakości,
tylko **analiza pliku** (kolory, fonty, obiekty), która startuje po wgraniu i przy
60-megowym PDF-ie trwa kilkanaście sekund. Użytkownik potwierdza produkt właśnie w tym
oknie czasu.

Potwierdzenie wołało `renderDetail()`, a ta — nie mając jeszcze `state.analysis` —
robiła `renderQc(null)`, czyli **gasiła pasek postępu trwającej analizy**. Stąd „ruszyło
i się urwało".

Poprawka: flaga `state.analysisRunning`; dopóki jest ustawiona, `renderDetail()` nie
dotyka paska. Do tego komunikat analizy mówi wprost, czym jest: *„Czytam plik — kolory,
fonty, obiekty, liczba pikseli. To jeszcze nie jest ocena jakości."*

Morał na przyszłość: pasek postępu ma **jednego właściciela naraz**. Jeśli dwie operacje
piszą do tego samego elementu, ta wolniejsza zawsze przegra i będzie wyglądać na
przerwaną.

### Trzecia odsłona: pasek, który nie gasł

Po tej poprawce pasek „Czytam plik" potrafił zostać na ekranie *na stałe*, mimo że
kolory i fonty były już wypisane niżej. Przyczyna: przy niepotwierdzonym produkcie
sekcja „Jakość wydruku" renderuje się **bez** `<div id="dmBox">`, a `renderDetail()`
zaczynała od `if (!box) return` — czyli wychodziła, zanim zdążyła zaktualizować pasek.
Pasek należał do niej, a ona się nie wykonywała.

Poprawka: `renderDetail()` nie zależy już od istnienia `dmBox` (pomocnik `setBox()`
zapisuje treść tylko wtedy, gdy element jest) i **zawsze** ustawia pasek.

Stany paska po zmianie:

| kiedy | wygląd |
|---|---|
| trwa czytanie pliku | żółty, „Czytam plik — kolory, fonty, obiekty, liczba pikseli", pasek **animowany** |
| plik wczytany, brak produktu | zielony, „Plik wczytany… Ocena jakości — po potwierdzeniu produktu" |
| plik wczytany, produkt jest | zielony, „Plik wczytany… Teraz kliknij Sprawdź jakość" |
| trwa ocena jakości | żółty, z realnym postępem (pasma / obrazy) |
| ocena gotowa | zielony albo pomarańczowy — werdykt |

Pasek postępu bez znanego postępu jest **animowany**, nie zamrożony na 5 % — zamrożony
wygląda jak zawieszony program.

## Schodek — czy niską rozdzielczość w ogóle WIDAĆ (wrzesień 2026)

Tomasz: na 1878 program zgłaszał kawałek jednolitego nieba jako „38 ppi". Rozdzielczość
faktycznie jest tam niska — ale nie ma tego jak zobaczyć.

Fizyka: obraz powiększony f× drukuje się jako **grube piksele f×f**. Widać je tylko tam,
gdzie **sąsiednie grube piksele różnią się tonem** (schodek). Jednolite niebo powiększone
4× jest nadal jednolitym niebem. Gradient powiększony 4× jest nadal gradientem. Tam nie
ma schodków, więc nie ma wady — choć liczba ppi jest niska.

Miara: 95. percentyl |różnicy| między sąsiednimi grubymi pikselami (obraz zmniejszony f×,
czyli to, co się wydrukuje), liczony **per blok**; dla fragmentu **maksimum** po blokach —
konserwatywnie, żeby mały ostry element w dużym gładkim obszarze nie zginął.
Próg `STEP_MIN = 4` (≈ 1,6 % tonu): poniżej ani drukarka nie odda różnicy, ani oko jej
nie zobaczy z żadnej odległości.

Pomiar (wartości z potoku, skala 0–255):

| miejsce | schodek | los |
|---|---|---|
| 1878 — jednolite niebo | 3 | pominięte |
| Prosta_Light_300 — ciemne gradienty | 2–6 (część), reszta 14–47 | część pominięta |
| adFrame_Smart — bęben (wskazany przez Tomasza jako wada) | 14 | **zostaje** |
| adFrame_Smart — pozostałe 13 fragmentów | 34–71 | zostają |
| Prosta 600 — logo 30 ppi (fakt geometryczny) | nie dotyczy | zostaje (lowres nigdy nie podlega) |

Czym to się różni od odrzuconego filtra kontrastu: kontrast (odchylenie std całego
bloku) mierzył, ile jest treści; schodek mierzy, czy **różnice między grubymi pikselami**
są dostrzegalne — to jest dokładnie ta wielkość, która decyduje o widoczności
pikselozy. Filtr kontrastu topił małą literę w medianie bloków; schodek bierze maksimum
i literę zachowuje.

Zasady bezpieczeństwa:

- **`lowres` (za mało pikseli) nigdy nie podlega schodkowi** — to fakt geometryczny.
- Schodek dotyczy fragmentów i „całego obrazu bez detalu" (`upscaled`) — tam, gdzie
  wada jest oceną treści.
- Pominięte miejsca są **policzone** w linijce pokrycia („pominięto N miejsc o niskiej
  rozdzielczości, której nie widać"). Nic nie znika po cichu.
- Liczone z tego samego obrazu zmniejszonego f×, który służy krzywej strat — bez
  drugiego resize'u. Koszt: ok. +30 % czasu na największych obrazach.

Co zostaje na 1878 po tej zmianie: cały obraz tła (33 ppi, fakt) + 3 wąskie paski na
lewej krawędzi zdjęcia nieba z miękkimi liśćmi (schodek 10–16, etykieta „gładkie tło") —
do oceny okiem, tak jak ustalono.

## Odbite obrazy — ramka w lustrzanym miejscu (znaleziony przy okazji)

Diagnozując niebo okazało się, że obraz nieba na 1878 ma CTM z **a < 0** (odbicie
w poziomie). Fragment z wnętrza obrazu (ułamki w pikselach obrazu) był rzutowany na
stronę bez uwzględnienia odbicia — ramka lądowała w lustrzanym miejscu: analiza patrzyła
na liście, ramka pokazywała niebo obok. To samo dotyczyłoby obrazów odbitych w pionie
i obróconych o 90°.

Poprawka: `analyze.py` zapisuje w każdym umiejscowieniu pełną macierz `ctm` i `rect_pdf`;
`detailmap.region_on_placement()` przepuszcza cztery rogi fragmentu przez CTM i bierze
obwiednię. Efekt uboczny: na Prosta_Light_300 liczba obszarów „poza formatem" spadła
z 10 do 5 — połowa z nich była poza stroną tylko dlatego, że była odbita.

## Jedna wada, wiele miejsc (grupowanie)

`Prosta 600 Ø43`: jedno logo 133×75 px wstawione **22 razy**. Lista pokazywała 22
pozycje — a to jedna wada w 22 miejscach, nie 22 wady.

W PDF-ie z obiektami rozstrzyga to `xref`: wszystkie umiejscowienia tego samego obiektu
obrazu to jedna pozycja z licznikiem („w 22 miejscach"). Nawigacja nadal chodzi po
wszystkich 22 wystąpieniach — grupowanie dotyczy tylko **listy i liczników**, nigdy
podglądu. Fragmenty (kawałki wnętrza jednego zdjęcia) nie są grupowane: każdy jest innym
miejscem tego samego obrazu.

Rozdzielenie liczb w komunikatach:

- **pozycje** = ile jest wad (grupy) → to liczy werdykt,
- **miejsca** = ile jest wystąpień na stronie → to liczy przycisk i nawigator.

### Czego to NIE rozwiązuje: pliki spłaszczone

W spłaszczonym rastrze (albo spłaszczonym PDF-ie) nie ma obiektów — powtórzone logo to
po prostu piksele w różnych miejscach. `xref` nie istnieje, więc tą metodą nie da się
tego wykryć.

### Grupowanie po treści — ZMIERZONE I ODRZUCONE

Propozycja brzmiała: policzyć dla każdego zgłoszonego obszaru mały deskryptor (wycinek
32×32 w skali szarości, znormalizowany do średniej i kontrastu) i skleić obszary
o bliskich deskryptorach. Zamiast ją zaimplementować — zmierzono ją na pliku
`Prosta 600 Ø43`, gdzie z PDF-a znamy prawdę: 22 umiejscowienia jednego obiektu to
klasa „to samo", a strona pełna innych logo podobnej wielkości to klasa „różne".
Miara odległości: `1 − korelacja` (0 = identyczne).

| warunki (JPEG q80) | max „to samo" | min „to samo × inne" | wynik |
|---|---|---|---|
| kadr idealnie na krawędziach logo | 0,088 | 0,764 | **rozdziela** (margines ~8×) |
| kadr przesunięty ±10 % | 1,090 | 0,643 | **nie rozdziela** |
| kadr przesunięty ±25 % | 1,134 | 0,623 | **nie rozdziela** |
| ±10 % + dopasowanie 27 wariantów kadru (3×3 przesunięcia × 3 skale) | 0,796 | 0,587 | **nie rozdziela** |
| ±25 % + dopasowanie 27 wariantów | 1,055 | 0,417 | **nie rozdziela** |

Wniosek: metoda działa **tylko wtedy, gdy znamy dokładne krawędzie powtarzanego
elementu** — a w pliku spłaszczonym właśnie ich nie znamy. Obszar wyznacza siatka
bloków (blok ≈ 13,5 mm na wydruku, logo ≈ 112 mm), więc kadr jest przesunięty
o kilkanaście procent i to wystarcza, żeby klasy się zlały. Dopasowywanie kadru
sytuacji nie ratuje.

Kierunek błędu jest tu **groźny**: fałszywe sklejenie chowa realną wadę z listy, a to
łamie regułę nadrzędną („nigdy nie przegapić słabszego szczegółu"). Fałszywy podział
jest niegroźny — lista jest dłuższa i tyle. Przy takiej asymetrii metoda bez marginesu
nie nadaje się do użycia.

**Nie implementujemy.** Zapis zostaje, żeby pomysł nie wrócił bez nowych dowodów.

### Co zamiast tego (zaimplementowane)

Grupujemy nie po tym, **jak wyglądają**, tylko po tym, **co zmierzyliśmy**. Dwa
niezależne klucze:

| klucz | warunek | co mówi komunikat |
|---|---|---|
| `image` | ten sam obiekt obrazu (`xref`) | „ten sam obraz w 22 miejscach" — to fakt z PDF-a |
| `facts` | ten sam rodzaj wady, to samo ppi (po zaokrągleniu) i oba wymiary na wydruku zgodne w ±5 % | „5 takich samych miejsc" — bez twierdzenia, że to ta sama grafika |

Porównujemy z **reprezentantem grupy**, nie z kubełkiem wielkości: kubełki mają
krawędzie i rozdzielały 39,6 mm od 40,6 mm (różnica 2,5 %). Grup jest mało, więc
liniowe szukanie wystarcza.

`reason` (`coarse` / `upscaled`) **nie** dzieli grup — to nazwa mechanizmu, nie fakt
widoczny dla użytkownika; oba dają identyczny opis. Dzieli tylko `lowres`, bo to inna
wada.

Fałszywe sklejenie jest tu nieszkodliwe: skoro fakty są identyczne, jeden wiersz opisuje
wszystkie te miejsca poprawnie, a nawigator i tak odwiedza każde z osobna. To ta sama
asymetria co wyżej, tylko odwrócona na naszą korzyść.

Efekt na plikach Tomasza: `Prosta 600` 22 miejsca → **1 pozycja**;
`adFrame_Smart` 14 miejsc → **9 pozycji**.

## Szwy na podglądzie (nie są wadą pliku)

Na podglądzie pojawiały się ciemne prostokątne linie, znikające po chwili — łatwo je
wziąć za wadę projektu. To był podgląd, nie plik. Dwie przyczyny:

1. **Cień.** Nakładka hi-res (`.hires`) jest elementem `<img>` wewnątrz `.canvas`,
   więc łapała regułę `.canvas img { box-shadow: … }` — cień rysował się po obwodzie
   doładowywanego wycinka. Poprawka: `.hires { box-shadow: none; background: none; }`.
2. **Nieaktualny wycinek.** Po zmianie powiększenia stary wycinek zostawał na ekranie
   i był przeskalowywany, więc był miększy od obrazu pod spodem — jego krawędź rysowała
   się jako szew. Poprawka: przy zmianie powiększenia `hideHires()` od razu; przy samym
   przewijaniu wycinek zostaje (skala się zgadza, szwu nie ma).

Zasada: podgląd nie ma prawa dorysowywać niczego, co da się pomylić z zawartością pliku.
Jedyne, co program rysuje na projekcie, to czerwona ramka znalezionego miejsca.

## Znikające pierwsze kliknięcie (wyścig ze skalą)

Objaw: klikam „Sprawdź jakość", pasek przez chwilę idzie, po czym nic — i dopiero drugie
kliknięcie działa.

Przyczyna: **wytyczne dojeżdżają asynchronicznie i dopiero one ustawiają skalę**
(`state.scale`, a z niej `k` = 1 albo 10). Kliknięcie przed ich przyjściem startowało
liczenie z `k = 1`; gdy odpowiedź dojechała ze skalą 1:10, `detailOnScaleChange()`
wykrywało zmianę `k` i **cicho anulowało** trwające sprawdzanie (`dmSeq++`), bo taka
była reguła „zmiana ustawień unieważnia wynik". Nic o tym nie mówiło.

Dwie poprawki, obie potrzebne:

1. **Nie anulujemy po cichu.** Gdy parametry zmienią się w trakcie liczenia,
   `startDetail(true)` przelicza z nowymi. Użytkownik już poprosił o sprawdzenie —
   zmiana `k` pod spodem nie unieważnia jego decyzji, tylko dane wejściowe. Reguła
   „start wyłącznie z przycisku" zostaje zachowana: to nadal jest to samo kliknięcie.
2. **Nie pozwalamy kliknąć za wcześnie.** Flaga `state.glLoading` blokuje przycisk na
   czas pobierania wytycznych, z podpowiedzią „Trwa pobieranie wytycznych (stąd skala
   wydruku)…". Flagę czyści też `clearGuidelines()`, żeby porzucone żądanie (zmiana
   produktu w locie) nie zostawiło przycisku zablokowanego na stałe.

Zasada ogólna: **żadna operacja uruchomiona przez użytkownika nie może zniknąć bez
śladu.** Albo się kończy, albo restartuje, albo mówi, dlaczego przerwała.

## Próg 120 ppi i skala pliku

Próg jest sztywny: **120 ppi NA WYDRUKU**, dla każdego produktu, bez uwzględniania
odległości oglądania (potwierdzone przez Tomasza, wrzesień 2026).

Ale plik może być w skali 1:10, a drukuje się zawsze 1:1 — czyli 10× większy. Wtedy
ppi z pliku dzieli się przez 10:

| skala pliku | ppi wymagane w pliku | ppi na wydruku |
|---|---|---|
| 1:1 | 120 | 120 |
| 1:10 | **1200** | 120 |

W kodzie: `nominal = p["ppi"] / k` (k = 10 dla 1:10), a wymiary obszarów mnożone przez
k, żeby mm były zawsze wymiarem NA WYDRUKU. Każde `ppi`, `nominal_ppi` i `mm` w wyniku
`detailmap` jest już przeliczone na wydruk — nigdy nie są to liczby „z pliku".
Sprawdzone: adFrame_Smart (obraz 120 ppi) przy k=1 nie łapie progu jako element, przy
k=10 daje element 12 ppi i obszary 10× większe w mm.

Dlatego opis w UI mówi „z liczby pikseli wychodzi N ppi", nie „w pliku jest N ppi" —
przy 1:10 to zupełnie inne liczby. Przy skali 1:10 pasek jakości dopisuje wprost:
„w pliku musi być 1200 ppi".

## Podgląd zawsze w skali 1:1 wydruku

Nawigator jakości ustawia podgląd **zawsze na 100 %** (rozmiar rzeczywisty wydruku) —
nigdy więcej. Wcześniej dopasowywał się do okna, przez co mały fragment wyskakiwał na
402 % i piksele wyglądały drastyczniej niż na druku. Ocena „czy to widać" ma sens tylko
w skali druku.

Ta sama zasada obowiązuje pozostałe nawigatory (użycia obrazu, fragmenty): mogą
**pomniejszyć**, żeby duży obiekt zmieścił się w oknie, ale nigdy nie powiększają ponad
100 %.

## Obszar na (prawie) całą stronę — prezentacja

Na 1878 zgłoszenie dotyczy **całego zdjęcia tła**. Ramka wokół całej strony nic nie
pokazuje, a napis „jakość · ≈ 33 ppi" nie tłumaczy, co jest nie tak, skoro cały projekt
to to samo zdjęcie.

Reguła: gdy obszar zajmuje **≥ 50 % powierzchni strony**, program:

- **nie rysuje ramki** (byłaby wokół wszystkiego),
- ustawia podgląd w **skali 1:1 wydruku** na środku obszaru, żeby było widać piksele,
- pisze wprost, co jest nie tak, np. *„to zdjęcie zajmuje całą stronę — ≈ 33 ppi
  (w pliku 100 ppi, ale detal jak przy 33 ppi — obraz był powiększany), wymagane 120"*.

Dla mniejszych obszarów zostaje ramka, która po chwili znika (jak wcześniej).

## Czym są pliki testowe (ważne dla kalibracji)

**Folder `poprawne/` NIE znaczy „plik jest poprawny".** Znaczy: ten plik poszedł na
druk — klient zaakceptował pewne mankamenty (ustalenie Tomasza, wrzesień 2026).

To zmienia sposób oceniania metody. Zero zgłoszeń na pliku z `poprawne/` **nie jest**
kryterium sukcesu, a niezerowa liczba **nie jest** dowodem fałszywego alarmu. Program
ma zgłaszać fakty (ppi na wydruku, realny detal) — czy dana wada jest do przyjęcia,
decyduje człowiek, tak jak zdecydował klient. Nie wolno dobierać progów tak, żeby
pliki z `poprawne/` wychodziły czyste; tak właśnie powstała błędna bramka szumowa.

Kryterium poprawności metody jest inne: **czy zgłoszony obszar faktycznie zawiera to,
co program twierdzi** (obejrzany wycinek w 100 % skali) i czy nic realnego nie wypada.

## Wyniki (regresja na plikach Tomasza)

| plik | folder | przedtem | teraz |
|---|---|---|---|
| adFrame_Smart 100x250 | wydrukowany | 41 fragmentów | 14 fragmentów „do obejrzenia" — w tym bęben wskazany przez Tomasza ✓ |
| adFrame LMD/LMS/LMSM | wydrukowany | — | 0 |
| adWall Prosta Light 300 | wydrukowany | ramka pod projektem (fy = 1,04) | 34 obszary, wszystkie ramki na stronie ✓; obraz 48,6 ppi na całą stronę, raster ~16 ppi ze schodkami na literach |
| 1815 czcionki | błędny (fonty) | — | 0 (wada nie dotyczy rastrów) ✓ |
| 1878 | błędny | 59–61 obszarów | **1 element: 100 ppi nominalnie → 33 ppi realnie** + 5 drobnych fragmentów ✓ |
| Prosta 600 Ø43 | błędny | 22 | 22 użycia logo 133×75 px → 30 ppi ✓ |
| Prosta Light 400 SOFT | wydrukowany | — | 6 obrazów po 73 ppi (50×58 mm) |
| Presto Light 150 | wydrukowany | — | 2 obrazy 34 ppi + 3 fragmenty |

Wiersze z 73, 48,6, 34 i 16 ppi to fakty geometryczne, nie statystyka — te pliki
naprawdę są poniżej 120 ppi i poszły na druk mimo to.

## Odrzucone: filtr kontrastu (wrzesień 2026)

Część zgłoszeń na Prosta Light 300 to prawie czarne gradienty, gdzie 12 ppi i tak
niczego nie zmienia. Próba odsiania ich miarą kontrastu bloku (odchylenie standardowe
luminancji) **odrzucona**: ta sama miara wywala literę „U" wyrenderowaną w rastrze
~16 ppi z wyraźnymi schodkami (kontrast 2,5 — bo blok jest w większości czarny,
a litera zajmuje jego skrawek). Mediana zaniża jeszcze bardziej niż maksimum.
Bez metody, która nie gubi takich przypadków, nie filtrujemy — powtórka błędu bramki
szumowej byłaby gorsza niż nadmiar pozycji na liście.

## Uporządkowanie: jeden system, jeden werdykt

Stary przebieg „efektywnej rozdzielczości" per obraz w `analyze.py`
(`_effective_for_images`, kafelki 512 px) **nie jest już wywoływany**: dublował ocenę,
kosztował 7–11 s na plik i potrafił przeczyć nowemu wynikowi („Słabsze fragmenty (2)"
obok „wszystkie obrazy ≥ 120 ppi"). Tabela obrazów podaje teraz same fakty (px, mm na
wydruku, nominalne ppi, kolor), a ocenę realnego detalu ma wyłącznie `detailmap`.
Kod funkcji zostaje jako referencja.

## Cztery przypadki Tomasza w tym modelu

1. **Całość w wektorze** — brak rastrów, brak oceny ppi. Do zrobienia: wykrywanie
   image trace po stałym kroku schodków konturu (krok = piksel źródłowego bitmapu,
   daje liczbę „prześledzony z ok. N ppi").
2. **Całość w rastrze** — jeden element: nominalne ppi + mediana; fragmenty przy
   dwóch zgodnych sygnałach.
3. **Raster z warstwami** — ocena na kompozycji (tylko ona się drukuje); warstwy
   najwyżej do wskazania, co wymienić.
4. **Mieszany** — każdy obiekt osobno, wektor poza oceną. Do zrobienia: ścieżki
   przycięcia, przykrycie nieprzezroczystym obiektem, alfa 0.

Spłaszczone pliki: grupowanie powtórzeń po treści **zmierzone i odrzucone**;
działa grupowanie po zmierzonych faktach (patrz wyżej).
