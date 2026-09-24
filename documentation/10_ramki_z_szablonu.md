# Rozdział „Ramki z szablonu"

Częsty błąd klientów (zgłoszony przez Tomasza): projektant robi projekt na stronie PDF-a
wytycznych i zapomina wyłączyć warstwę z szablonem. Na wydruk idzie wtedy cyjanowa ramka
formatu, czerwona ramka obszaru bezpiecznego albo napisy ze środka szablonu — a przy pliku
otwieranym w Illustratorze zwykle jeszcze artefakty po tych napisach (rozsypana mapa znaków,
w treści same `˜˜˜˜`).

## Gdzie w kolejce

Zaraz **po „Wymiar wydruku"**, przed overprintem. Trzy powody:

1. Dopiero po dopasowaniu wymiaru wiadomo, gdzie linie wytycznych *powinny* leżeć — jest co
   z czym porównywać.
2. Usunięcie ramki zmienia projekt, więc to poprawka i należy do bloku poprawek.
3. Pracujemy na tym samym kadrze, który klient dostanie z powrotem.

## Skąd pewność

Nie zgadujemy, czy coś „wygląda na ramkę" — **mamy PDF wytycznych tego produktu**. Bierzemy
z niego kształty i napisy, przeliczamy na milimetry wydruku i szukamy tego samego w pliku
klienta. Cztery poziomy dowodu, od najmocniejszego:

| poziom | co to znaczy | zaznaczone do usunięcia |
|---|---|---|
| **szablon** | kształt stoi tam, gdzie w wytycznych, i ma ten sam kolor — albo ma dokładnie ten sam rozmiar i kolor, tylko jest przesunięty (program pisze o ile) — albo jest przycięty krawędzią strony, ale leży na tej samej osi co reszta szablonu | tak |
| **kolor szablonu** | ramka przy krawędzi w kolorze, którym Adsystem rysuje wytyczne, ale nie pokrywa się z szablonem TEGO produktu (stary szablon? przeskalowany projekt? pomylony produkt?) | nie |
| **podejrzany** | cienka ramka przy krawędzi w dowolnym innym kolorze | nie |
| **raster** | linia w kolorze wytycznych wtopiona w obraz | nie da się usunąć |

Kolory są stałe w każdych wytycznych Adsystem, niezależnie od produktu i wymiaru: cyjan
(100 % C) i czerwień (0/94,7/91,2/0). To dzięki nim rozpoznajemy szablon także wtedy, gdy
nic nie pasuje geometrycznie — odpowiedź na pytanie Tomasza „co jeśli klient ma stary
szablon".

**Nic nie znika samo.** Zaznaczone są tylko trafienia z poziomu „szablon", a plik zmienia się
dopiero po kliknięciu przycisku. Każde znalezisko ma przycisk „Pokaż", który przybliża
podgląd do tego miejsca i podświetla je. Cofnięcie jest jednym kliknięciem.

## Jak to działa pod spodem (`frames.py`)

**Własny przebieg po treści strony**, a nie `page.get_drawings()` z PyMuPDF — tamten nie
wchodzi do obiektów formy, a właśnie tam ląduje treść po naszej poprawce wymiaru i tam siedzi
szablon wstawiony jako osadzona strona. Przebieg śledzi `q/Q/cm`, kolor (`k/rg/g/sc/scn`),
buduje bryłę każdej ścieżki i zapamiętuje **adres**: numer strumienia i zakres operatorów.

**Usuwanie** kasuje dokładnie te operatory (od pierwszego punktu ścieżki do operatora
malowania). Plik nie jest przerysowywany, więc niczego innego nie da się przy okazji zepsuć.

**Powtarzalność.** Poprawki liczą się zawsze od nowa, od oryginału, więc numery operatorów
mogą się zmienić. Dlatego w parametrach poprawki jedzie nie numer, tylko **klucz
geometryczny** (miejsce i rozmiar w mm) — przy nakładaniu szukamy od nowa i usuwamy to, co
pasuje do klucza.

### Trzy rzeczy, które sprawiły najwięcej kłopotu

- **Napisy z rozsypaną mapą znaków.** Treść to same `\x1f`, a Python uważa te znaki za białe,
  więc `strip()` zjadał cały napis. Do tego dopasowanie po treści i tak by nie zadziałało —
  napisy porównujemy więc po **położeniu i wielkości** (z uwzględnieniem przesunięcia
  szablonu), a w opisie pokazujemy czytelny tekst z wytycznych.
- **Rozmiar napisu.** Illustrator pisze `Tf /F 1` i skalę w macierzy `Tm` (np. 287,7), więc
  sam rozmiar fontu nic nie mówi — trzeba mnożyć przez skalę z `Tm`.
- **Odróżnienie łańcucha od tablicy w pikepdf.** `bytes(tablica)` nie rzuca błędu, tylko
  zwraca puste bajty — przy złej kolejności prób gubiliśmy CAŁY tekst. Tablice da się
  iterować, łańcuchy rzucają `TypeError` i tylko tak można je rozróżnić.

## Raster: wykrywamy, ale nie usuwamy

Gdy ramki są wtopione w obraz (plik Tomasza `ramki_r.pdf` ma zero obiektów wektorowych),
renderujemy stronę do ok. 2400 px i szukamy wierszy i kolumn, w których niemal każdy piksel
ma kolor wytycznych. Dwie krawędzie tej samej linii scalamy w jedno znalezisko, pola grubsze
niż 14 mm pomijamy.

Wynik na pliku Tomasza: **8 z 8 linii** (4 cyjanowe i 4 czerwone) rozpoznanych jako „dokładnie
tam, gdzie rysuje je szablon", w 1,5 s. Rozdział mówi wprost, że usunąć się ich nie da, i
podpowiada półśrodek: jeśli linia leży przy samej krawędzi, można ją **zakryć** tłem
z krawędzi w rozdziale o wymiarze (to zakrycie, nie usunięcie).

## Sprawdzone na plikach Tomasza

`adFrame_Smart_100x250_ramki_w.pdf` (115 MB, wektor): znalezione i usunięte 3 elementy —
ramka 1012 × 2513 mm („przycięta przez krawędź strony"), ramka 915 × 2413 mm („ten sam
kształt co w wytycznych, przesunięty o 3,1 mm") i blok napisów ze środka. Po usunięciu
ponowne sprawdzenie nie znajduje już nic, a projekt jest nietknięty.

Warto zauważyć, że ten plik JEST przypadkiem, o który pytał Tomasz: nic w nim nie pokrywa się
z wytycznymi co do milimetra (szablon przesunięty o 3,1 mm, zewnętrzna ramka przycięta) —
i mimo to obie ramki wylądowały na poziomie „szablon".

## Poprawki po pierwszym teście u Tomasza

- **Rozdział pojawia się dopiero wtedy, co reszta poprawek.** Wcześniej wchodził od razu po
  wgraniu pliku (wystarczyło, że wymiar się zgadzał), więc wyskakiwał nad rozdziałem o
  produkcie. Teraz siedzi wewnątrz sekcji z poprawkami i brama jest ta sama co dla niej:
  produkt → strona → wymiar. Przy okazji znika przypadek, w którym szukaliśmy ramek **bez
  wytycznych** (bo produkt nie był jeszcze potwierdzony) i wszystko lądowało na słabszym
  poziomie „w kolorze wytycznych" zamiast „z szablonu".
- **Przycisk cofa poprawkę.** Zacinał się na „Pracuję…" z dwóch powodów: `fixButtons()`
  odświeżał napis tylko wtedy, gdy poprawki NIE było, a przeszukanie pliku po poprawce
  („czysto") wyszarzało przycisk na twardo. Teraz napis ustawia ten sam mechanizm co przy
  pozostałych poprawkach (`· cofnij`), a stan przycisku pilnuje jedno miejsce — nawet gdy
  lista jest pusta, przycisk zostaje aktywny, żeby dało się wrócić.
- Na czas nakładania poprawki przeszukiwanie ramek nie rusza przycisku (blokada `fixBusy`).

Zmierzone po poprawkach na `ramki_w.pdf`: usunięcie 6 s, cofnięcie 1 s, ponowne wykrycie
3 elementów natychmiast po cofnięciu.

## Klucze zapamiętane z chwili usunięcia

Błąd zgłoszony przez Tomasza: po usunięciu ramek wystarczyło kliknąć „Zamień fonty na krzywe"
i **ramki wracały**. Powód: poprawki liczą się zawsze od nowa, od oryginału, a lista kluczy
do usunięcia była brana z bieżącego rozdziału — który po usunięciu ramek pokazuje już „czysto",
czyli pustą listę. Kolejna poprawka wysyłała więc „usuń nic".

Teraz klucze zapamiętujemy w chwili nałożenia poprawki i jadą z **każdą** kolejną, dopóki
poprawka jest włączona. Sprawdzone: po „usuń ramki" + „fonty na krzywe" raport ma obie
pozycje, a rozdział dalej pokazuje „czysto".

## Fałszywka: „Ramka 973 × 1973 mm", której nie widać

Zgłoszone przez Tomasza na `spady.pdf`: rozdział pokazywał **dwie podejrzane ramki wielkości
całej strony**, choć na projekcie nie ma żadnej ramki.

To były **znaczniki cięcia**. Illustrator rysuje je jako jedną ścieżkę złożoną z kilkunastu
krótkich odcinków w rogach strony — obrys takiej ścieżki obejmuje całą stronę, więc
`_edge_frame()` (kształt sięgający całej szerokości albo wysokości i leżący przy krawędzi)
uznawał ją za pas przy krawędzi. Dwie, bo znaczniki są rysowane dwa razy: biała podkładka
(obrys 0,44 mm) i czarne kreski na wierzchu (0,09 mm), po 16 odcinków każda.

Reguła jest teraz taka: **kształt wielkości całej strony to nie ramka z szablonu.** Tak
wygląda tło projektu, ramka przycięcia wstawionego obrazu i właśnie znaczniki cięcia.
Odrzucamy go, gdy zajmuje ≥ 98 % szerokości i wysokości strony oraz:

- ma **wypełnienie** — czyli jest tłem, albo
- ma **więcej niż 6 odcinków** — czyli nie jest prostokątem.

Filtr działa **tylko na najsłabszym poziomie („podejrzany")**. Kształt, który pokrywa się
z wytycznymi albo jest w kolorze wytycznych, zostaje znaleziskiem niezależnie od wielkości —
i tak być musi, bo prawdziwa ramka szablonu w pliku bez spadów ma dokładnie wymiar strony.

Sprawdzone po zmianie: `spady.pdf` → „czysto" (0 znalezisk ze 162 kształtów),
`ramki_w.pdf` → dalej 3 znaleziska na poziomie „szablon" (ramka cyan 1011,8 × 2512,9 przycięta
krawędzią, ramka czerwona 915 × 2413 przesunięta o 3,1 mm, napis z wytycznych).

---

## Przebudowa 24.09: jeden szablon, jeden przycisk, suwak przed/po

Uwaga Tomasza: rozdział pokazywał za dużo — na `PRINT_CHECKER_TEST_100x200_SZABLON_PASERY.pdf`
(produkt adFrame CTF 100x200) wyszło 2 ramki „w kolorze wytycznych", 4 „podejrzane" pasy
(zwykłe panele projektu) i 4 „linie w obrazie" (te same ramki złapane drugi raz przez skan
rastra). Nic nie było zaznaczone do usunięcia.

Powód: w pliku siedział szablon **Pop-up Lightbox** (1015 × 2014, bezpieczny 915 × 1914),
a wytyczne CTF mają 1012 × 2010 / 912 × 1910. Ten sam układ, te same kolory, różnica 3–4 mm —
a stare porównanie wymagało zgodności rozmiaru co do 0,5 mm.

### Jak jest teraz (`frames.match_template`)

- Porównujemy **cały szablon** z wytycznych: linie w kolorach wytycznych (cyjan, czerwień)
  i ich wzajemne położenie. Każda para „linia w pliku ↔ linia w szablonie" tego samego koloru
  i proporcji wyznacza ułożenie szablonu (przesunięcie środka, ewentualnie skala — różnica
  do 2 % to nie skala). Dla każdego ułożenia liczymy, ile linii szablonu stoi w pliku.
- Tolerancja krawędzi: **0,6 % większego boku szablonu** (12 mm na 2 m). Szablon uznajemy za
  znaleziony, gdy w pliku jest **≥ 60 % szablonu** (ważone obwodem linii).
- Napisy z szablonu: ta sama treść ALBO ta sama wysokość na stronie (±tolerancja / 2× wielkość
  liter), podobna wielkość liter (±25 %) i położenie w obrębie szablonu. Treść bywa inna
  (inny produkt) albo nieczytelna (rozsypana mapa znaków).
- Współrzędne w mm wydruku; wytyczne przeliczamy tym samym współczynnikiem co plik
  (`page_mm` / wymiar strony w mm), więc skala 1:10 liczy się sama. Wcześniej szablon był
  rozciągany do wymiaru strony pliku — przy pliku ze spadami to przesuwało wszystkie linie.

### Interfejs

Zamiast listy z checkboxami — jedno zdanie i jeden przycisk:

- **szablon w projekcie** — „Zgadza się z wytycznymi tego produktu: cały szablon + 1 napis —
  krawędzie odjeżdżają najwyżej o 2 mm." · „Pokaż" · **Usuń szablon** · „zostaw jak jest".
- **usunięty** — przycisk „Usuń szablon · cofnij" i suwak przed/po (ta sama mechanika co
  w innych rozdziałach: lewy koniec = wszystkie poprawki oprócz tej).
- **do obejrzenia** — ramki w kolorach wytycznych, które nie układają się w szablon tego
  produktu; jedno zdanie + „Pokaż", nic nie usuwamy.
- **w pikselach** — szablon wtopiony w obraz; jedno zdanie + „Pokaż (N)" (kolejne linie).
- **czysto**.

Znikły „podejrzane" pasy przy krawędzi w dowolnym kolorze — to były panele projektu.

### Trzy błędy naprawione przy okazji

1. **Szablon wracał po „Przytnij spady"** — usuwanie szło PO przycięciu i szukało po
   położeniu w mm; po przycięciu strona zaczyna się gdzie indziej. Do tego „klucz miękki"
   w `apply` był zbudowany źle (zawsze równy pełnemu kluczowi). Teraz usuwanie szablonu idzie
   **jako pierwsza poprawka, na oryginale**, i usuwa wszystko, co `find` uznał za szablon —
   ten sam plik i ten sam wymiar co w rozdziale, więc wynik jest identyczny. Klucze przestały
   być potrzebne (`framesApplied`, `framesKeys` usunięte).
2. **Rozdział zmieniał zdanie po kolejnych poprawkach** — był skanowany od nowa na każdej
   poprawionej wersji. Teraz skan idzie raz, na oryginale (`/frames` ignoruje `v`), a po
   poprawkach tylko przerysowujemy stan.
3. **„Dopasuj wymiar" wracało do spadów** — `fileMm()` po przycięciu brał wymiar netto tylko
   wtedy, gdy wymiar NIE był jeszcze dopasowany. Po dopasowaniu wracał wymiar brutto
   (1040 × 2040), `updateSizeBox` uznawał, że „zmienił się format", i sam cofał wymiar —
   a cofnięcie wymiaru zdejmuje wszystkie poprawki. Teraz format netto bierzemy z `trimInfo()`
   (to samo źródło co przycięcie).

### Sprawdzone

- `PRINT_CHECKER_TEST_100x200_SZABLON_PASERY.pdf` + CTF 100x200: 2/2 linie + napis „Przod /
  1015 x 2014 [mm] / Wydruk Pop-up Lightbox…", odchyłka 2 mm. Pełna ścieżka w przeglądarce:
  usuń szablon → przytnij spady → dopasuj wymiar — wszystkie trzy poprawki zostają, rozdziały
  się nie zamykają, szablon nie wraca (render po poprawkach bez cyjanowych/czerwonych linii).
- `adFrame_Smart_100x250_ramki_w.pdf` + Smart 100x250: te same 3 elementy co wcześniej
  (odchyłka 1,6 mm).
- `spady.pdf`: czysto. `ramki_r.pdf`: 8 linii w pikselach (bez zmian).
