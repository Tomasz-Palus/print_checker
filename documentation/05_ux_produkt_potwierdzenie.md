# Sekcja „2 · Produkt” — potwierdzanie wyboru, wydruk niestandardowy, wytyczne bez wymiaru

Data: 2026-09-04. Poprawki UX po testach Tomasza (po etapie 4).

## Ustalenia (Tomasz)

- Produkt trzeba **potwierdzić** — program proponuje, człowiek zatwierdza.
- „Sugerowany produkt: <nazwa>” + przycisk potwierdzenia; niżej pozostałe
  propozycje i lista rozwijana.
- Wymiar ręczny ma być **ukryty**; pojawia się dopiero, gdy nic z listy nie
  pasuje → przełącznik „wydruk niestandardowy” i tam wpisuje się wymiar.
- Sekcja ma być „miła dla oka i nie zawalać opcjami”.
- W tabeli obrazów zbędny był przycisk „Pokaż” (to samo co „100 %” u góry) —
  zostaje tylko „Słabsze fragmenty (N)”.

## Maszyna stanów sekcji (`renderProductSection()` w app.js)

| stan | co widać |
|---|---|
| **bez pliku** | wyszukiwarka + status listy + link „Nie ma na liście? Wydruk niestandardowy →” |
| **kandydat** (po wgraniu pliku z sugestią ≥ 60 %, albo po wyborze z listy) | karta z ramką w kolorze akcentu: etykieta „SUGEROWANY PRODUKT · trafność 95 %” (lub „WYBRANY PRODUKT” gdy z listy), nazwa, kod, **[✓ Potwierdź] [Inny produkt]** |
| **wybór** (po „Inny produkt” lub gdy brak sugestii) | „Inne propozycje:” (do 3 sugestii z %), wyszukiwarka, status listy, link do niestandardowego |
| **potwierdzony** | kompaktowa zielona karta „✓ nazwa / kod · zmień” + sekcja **Wytyczne** (ładowane dopiero po potwierdzeniu) + „wgraj własny PDF wytycznych” |
| **niestandardowy** | karta „Wydruk niestandardowy” z polami szerokość/wysokość [mm] + [✓ Potwierdź] [Wybierz z listy]; po potwierdzeniu zielona karta „✓ Wydruk niestandardowy · 6000 × 2270 mm · zmień” |

Zasady: nic nie wybiera się samo (poprzednio sugestia ≥ 85 % wybierała się
automatycznie — usunięte); „Sprawdź plik” jest aktywny tylko po potwierdzeniu
(produktu albo wymiaru niestandardowego); nowy plik resetuje wszystko.
`printSize()` używa wymiaru ręcznego tylko w trybie niestandardowym.

## Wytyczne bez wymiaru (produkty o zmiennym rozmiarze)

Znalezione dzięki testom u Tomasza: wytyczne dla **Wydruk adFrame LMD/LMS/LMSM
(do 3mb/medium250)** to zaślepka: strona 1 „Resolution: 0 ppi – 1:0 scale”,
szablon „1 / 0 x 0 [mm]” na umownej stronie 1060×1050 mm. Takich produktów
(„do 3mb”, „pow. 3mb”…) jest w cenniku sporo — wymiar zależy od zamówienia.

Obsługa:
- parser: `dims_missing = true` gdy w tekście jest „0 x 0 [mm]”; skala `None`.
- UI: w sekcji Wytyczne pojawia się „szablon bez wymiaru” + pola **szerokość /
  wysokość [mm]** („Wytyczne tego produktu nie podają wymiaru…”); „Sprawdź
  plik” wymaga ich wypełnienia; przycisk „Szablon” (nakładka) jest wyłączony,
  bo linie zaślepki nic nie znaczą; skala do ustawienia ręcznie (status
  „skala nieznana — ustaw”).

## Rozpoznawanie skali — poprawka

Wytyczne pobierane z `lang=en` mają tekst angielski („120 ppi - scale 1:1”),
a szerokości grup różnią się od polskich (EN 1:1 = 98,5 pt — o włos od progu
100!). Zamiast szerokości liczymy teraz **podścieżki glifów** w grupie z
wartością (nowa podścieżka = start ≠ koniec poprzedniej; „0”, „p”, „a” mają
po 2): **22 → 1:1, 26 → 1:10, 21 → zaślepka „0 ppi – 1:0”** — niezależnie od
języka (sprawdzone PL i EN, 9 plików). Inna liczba → zapasowo po szerokości.
`PARSER_VERSION = 4` (stare JSON-y w cache przeliczą się same).

## Testy (sandbox + 5 PDF-ów wytycznych pobranych u Tomasza)
- Przepływ: sugestia → Potwierdź → wytyczne; „zmień” → wybór; „Inny produkt” →
  lista; klik w propozycję → karta „Wybrany produkt”; niestandardowy 6000×2270 →
  „wydruk: 6000 × 2270 mm (wydruk niestandardowy)”, przycisk aktywny.
- LMD (zaślepka): po potwierdzeniu przycisk nieaktywny do wpisania wymiaru;
  po wpisaniu 3000×2500 → „wydruk: 3000 × 2500 mm (wymiar podany ręcznie…)”.

## Dopisek: przycisk „Pokaż” wraca — ale tylko tam, gdzie ma sens

Po usunięciu „Pokaż” zniknęła jedyna droga do małego logo 133×75 px (przycisk
„100 %” pokazuje środek strony, nie ten element; „Słabsze fragmenty” nie
istnieje dla obrazów mniejszych niż 4 kafelki). Reguła: **„Pokaż (×N)”**
pojawia się, gdy obraz zajmuje < 50 % powierzchni strony (czyli jest
elementem do odszukania); dla obrazu-tła jest zbędny i go nie ma. Kolumna
nazywa się „na podglądzie” i może mieć oba przyciski: „Pokaż” i „Słabsze
fragmenty (N)”.
- Przyciski „Pokaż (×N)” i „Słabsze fragmenty (N)” są czarne (klasa
  `btn-dark`, jak „Szablon”), żeby były widoczne. Zdanie w ramce oceny odsyła
  do „Pokaż” w tabeli, a gdy obraz jest tłem (bez „Pokaż”) — do „100 %”.

## Rozdziały wchodzą pojedynczo, także po wymiarze

Po zatwierdzeniu roli pojawiały się od razu WSZYSTKIE kolejne rozdziały, bo `sizeSettled()`
zwracało prawdę już wtedy, gdy wymiar pliku po prostu się zgadzał. Tomasz chce inaczej:
po roli ma wejść **tylko** rozdział o wymiarze, a reszta dopiero po jego domknięciu.

Dlatego rozdział o wymiarze domyka się tak samo jak rozdział o roli — świadomą decyzją:

W rozdziale jest **jeden przycisk**, a jego napis mówi, co się stanie (pierwsza wersja miała
dwa i to myliło — uwaga Tomasza):

- wymiar się **nie zgadza** albo ktoś ruszył suwaki (skala, wielkość, przesunięcie, tło na
  marginesach) → **„Dopasuj wymiar"**, czyli przebudowa pliku,
- wymiar się **zgadza** i nikt niczego nie ruszał → **„Zatwierdź wymiar"**, czyli samo
  domknięcie kroku, bez dotykania pliku; po kliknięciu zostaje notka „zatwierdzony —
  wydruk 1015 × 2513 mm · zmień".

Napis przelicza się przy każdej zmianie suwaków, więc ruszenie czegokolwiek natychmiast
zamienia „Zatwierdź" w „Dopasuj" — i odwrotnie, powrót do 100 % wraca do „Zatwierdź".

`sizeSettled()` rozpadło się przy tym na dwie rzeczy: `sizeMatches()` (fakt: czy wymiar się
zgadza) i `sizeSettled()` (decyzja: czy rozdział jest domknięty). Zatwierdzenie zeruje się
przy zmianie pliku, strony, produktu i roli — czyli zawsze wtedy, gdy zmienia się docelowy
format.

## Przycisk „Podgląd szablonu" nad podglądem

Włączanie linii wytycznych ginęło wśród lupek (uwaga Tomasza). Przycisk nazywa się teraz
wprost **„Podgląd szablonu"**, stoi **pośrodku paska** nad podglądem, jest większy i w kolorze
akcentu: obrys i tekst na czerwono, a po włączeniu całe wypełnienie na czerwono. Ma też
ikonkę ramki, żeby dało się go znaleźć wzrokiem bez czytania.

Wyśrodkowanie jest bezwzględne (`position: absolute; left: 50 %`), więc długość napisu nie
przesuwa reszty przycisków. Poniżej 1350 px szerokości okna przycisk wraca do rzędu, żeby nie
wchodził na przyciski skali.


## Górny pasek w jednym rzędzie

Nazwa pliku stała w osobnym rzędzie nad paskiem z przyciskami — dwa rzędy zjadały ~30 px
wysokości podglądu bez powodu (uwaga Tomasza). Teraz wszystko jest w jednym rzędzie: nazwa
i program po lewej, „Podgląd szablonu" pośrodku, skala i widok po prawej. Podgląd urósł
z 765 do 818 px przy oknie 1920 × 975.

Nazwa nigdy nie dochodzi do środka paska (`max-width: calc(50 % - 140px)`), a to, co się nie
mieści, obcina wielokropek — całość zostaje w podpowiedzi pod kursorem.

## Kolejność rozdziałów po dołożeniu ramek i spadów

Sekcja poprawek zaczyna się teraz od dwóch rozdziałów, które muszą pójść **przed** wymiarem:

```
1 · Plik → 2 · Produkt → 3 · Ramki z szablonu → 4 · Spady → 5 · Wymiar wydruku → …
```

Powód jest ten sam w obu przypadkach: wymiar liczy się na **czystym pliku w formacie netto**.
Gdyby spady zostały, dopasowywalibyśmy format brutto (i skalowali projekt zamiast obciąć
naddatek), a gdyby zostały ramki szablonu, liczylibyśmy wymiar razem z nimi.

Zasada „rozdziały wchodzą pojedynczo" obowiązuje na całej długości: `updateSizeBox()` trzyma
rozdział o wymiarze schowany, dopóki `framesSettled() && trimSettled()`, a `sizeSettled()`
dalej otwiera resztę poprawek. Szczegóły wykrywania spadów: `11_spady.md`.

### Rozdziały 3 i 4 wchodziły przed potwierdzeniem produktu

Zgłoszone przez Tomasza: zaraz po wgraniu pliku widać było „Ramki z szablonu" i „Spady",
choć rozdział 2 (produkt) czekał jeszcze na „Potwierdź".

Powód: bramą dla wszystkiego dalej jest `roleSettled()`, a ono przy **niewybranym** produkcie
zwracało prawdę — nie ma szablonu, więc „rola jest ustalona". Przy pliku jednostronicowym
`pageSettled()` też było prawdą i oba nowe rozdziały wchodziły od razu. Teraz `roleSettled()`
zaczyna od `productConfirmed()`: bez potwierdzonego produktu nie ma formatu docelowego, więc
nie ma z czym porównywać ramek ani spadów.

Przy okazji wyszły dwie rzeczy, które ta zmiana odsłoniła:

- **Rozdział o stronie nie odrysowywał się po potwierdzeniu produktu.** `updatePageBox()`
  wołane było tylko przy zmianie strony, więc plik wielostronicowy po potwierdzeniu produktu
  nie miał czego pokazać i program stawał. Teraz odrysowuje się na końcu `updateRoleBox()`,
  czyli przy każdej zmianie stanu roli.
- **Przycisk „Wybierz tę stronę" zostawał wyszarzony na zawsze.** Globalne wyszarzanie
  („póki program liczy, nic nie jest klikalne") wyłączało go, ale nikt go potem nie włączał.
  Warunek wyjechał do `busyWaiting()` i pyta o niego zarówno globalne wyszarzanie, jak i sam
  rozdział o stronie.

Kolejność jest więc pilnowana w jednym łańcuchu: **produkt → rola → strona → ramki → spady →
wymiar → reszta poprawek**.
