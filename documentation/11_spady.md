# 11 · Spady

Rozdział **„Spady"** wchodzi po ramkach z szablonu, a **przed** wymiarem wydruku. Znajduje
pliki przygotowane ze spadem i przycina je do formatu netto.

## Po co to w ogóle jest

Spad to margines poza linią cięcia: w poligrafii arkuszowej treść celowo wychodzi kilka
milimetrów za format, żeby po pocięciu nie było białego paska. W wielkim formacie Adsystem
spadów **się nie stosuje** — plik ma mieć dokładnie wymiar z wytycznych. Klienci jednak
przysyłają pliki ze spadem, bo tak mają ustawione w InDesignie albo tak im wychodzi
z drukarni offsetowej.

Bez tego rozdziału taki plik trafiał do rozdziału o wymiarze jako „za duży o 23 mm"
i program proponował… przeskalowanie. To najgorsze możliwe wyjście: zamiast odciąć
naddatek, ściskaliśmy cały projekt i psuliśmy wymiar treści. Dlatego spady są **przed**
wymiarem — najpierw plik ma być w formacie netto, dopiero potem sprawdzamy, czy netto
zgadza się z szablonem.

## Jak wykrywamy spady, skoro każdy program robi je inaczej

To było pytanie Tomasza i odpowiedź jest przyjemniejsza, niż się wydaje: **programy różnią
się tym, jak spad rysują, ale zapisują go tak samo** — w ramkach strony PDF-a. To część
specyfikacji PDF-a, nie wymysł jednego producenta.

Strona PDF-a ma pięć ramek:

| Ramka | Co znaczy |
|---|---|
| **MediaBox** | fizyczna strona — to, co widzimy jako „wymiar pliku" |
| **CropBox** | obszar wyświetlany (zwykle = MediaBox) |
| **BleedBox** | format netto **plus spad** |
| **TrimBox** | **format netto** — linia cięcia |
| **ArtBox** | obszar treści (bywa użyty zamiast TrimBoxa) |

Zapisuje je każdy porządny eksport: InDesign („Marks and Bleeds"), Illustrator, Acrobat
Distiller, PDF/X (w PDF/X TrimBox jest **wymagany**). Dlatego pierwszym i najpewniejszym
sygnałem jest **TrimBox mniejszy od strony**, a gdy go nie ma — **ArtBox**.

Sprawdzone na `spady.pdf`:

```
MediaBox 973,3 × 1973,3 mm
BleedBox 970,0 × 1970,0 mm
TrimBox   950,0 × 1950,0 mm   ← format netto
ArtBox    950,0 × 1950,0 mm
```

Program czyta z tego wprost: format netto 950 × 1950, spad 11,6 mm z każdej strony.
Nie zgaduje i nie mierzy pikseli.

**Pułapka, o którą łatwo się potknąć.** Według specyfikacji brak TrimBoxa nie znaczy „nie
wiem" — znaczy „TrimBox = CropBox". Biblioteki (PyMuPDF też) zwracają wtedy TrimBox równy
stronie. Gdybyśmy czytali samą wartość, **każdy** plik wyglądałby jak plik ze spadem zerowym
albo — po odjęciu — jak plik bez spadu. Dlatego warunek brzmi: ramka musi być **mniejsza od
strony o co najmniej 0,5 mm**. Sprawdzone na wszystkich plikach testowych: tylko `spady.pdf`
przechodzi ten warunek, reszta ma wszystkie ramki równe stronie.

### Drugi poziom: plik równomiernie większy od formatu

Zostają pliki **bez ramek** — spad „dorobiony na oko" przez powiększenie obszaru roboczego,
eksport z programu, który ramek nie zapisuje, plik przepuszczony przez konwerter, który je
zgubił. Tu nie ma czego czytać, więc porównujemy z formatem z wytycznych:

```
dx = (szerokość pliku − szerokość szablonu) / 2
dy = (wysokość pliku − wysokość szablonu) / 2
spad, jeśli:  dx, dy > 0,4 mm   i   dx, dy < 30 mm   i   |dx − dy| < 0,6 mm
```

Czyli: plik musi być większy **z obu stron**, po tyle samo w poziomie i w pionie, i o wartość
z sensownego zakresu spadu. Trzy warunki naraz, bo każdy z osobna łapałby fałszywki:

- bez `|dx − dy| < 0,6` łapalibyśmy pliki po prostu **źle przygotowane** (np. 1014,9 × 2512,9
  przy szablonie 1000 × 2500 — 7,5 mm w poziomie, 6,5 w pionie: to nie spad, to bałagan, i tym
  ma się zająć rozdział o wymiarze),
- bez `< 30 mm` łapalibyśmy plik zrobiony pod zupełnie inny produkt,
- bez `> 0,4 mm` łapalibyśmy zaokrąglenia (0,1 mm różnicy przy przeliczaniu punktów na mm).

Ten poziom działa tylko wtedy, gdy produkt jest już potwierdzony — bez formatu docelowego nie
ma z czym porównywać. I działa w jednostkach pliku, więc przy skali 1:10 próg 0,4 mm to
4 mm na wydruku.

### Czego jeszcze nie robimy

**Znaczniki cięcia (crop marks).** Zdarza się plik bez ramek, za to z narysowanymi krzyżykami
i paskami kontrolnymi na spadzie. Technicznie da się je znaleźć (cienkie czarne linie
w rogach, w stałej odległości od treści) i z ich położenia odczytać linię cięcia — ale nie
mamy takiego pliku na testy, a wykrywanie „na oko" bez próbki to proszenie się o fałszywki.
Zostawiam do zrobienia, gdy taki plik się pojawi. Na razie plik z samymi znacznikami wpadnie
w poziom drugi (jeśli naddatek jest równomierny) albo trafi do rozdziału o wymiarze.

**Rastry.** JPG/TIFF/PNG nie mają ramek PDF-a, więc zostaje wyłącznie poziom drugi. Przycisk
przycinania jest przy rastrze wyłączony — przycięcie rastra to już przerysowanie pliku,
a nie zmiana metadanych.

## Co robi poprawka

Nic nie przerysowujemy. Poprawka zmienia **tylko ramki strony**:

- `MediaBox`, `CropBox` i `TrimBox` dostają prostokąt formatu netto,
- `BleedBox` i `ArtBox` znikają (nie ma już spadu, więc nie ma czego opisywać).

Treść zostaje bit w bit taka sama — to, co było na spadzie, po prostu wychodzi poza stronę
i nie drukuje się. Stąd dwie miłe konsekwencje: **zero straty jakości** i **natychmiast**
(0,4 s na pliku 30 MB, bo to przepisanie kilku liczb, a nie render).

Kolejność w potoku poprawek: **spady → ramki z szablonu → wymiar → kolory → krzywe →
overprint → spłaszczenie**. Spady idą pierwsze, bo każda następna poprawka ma już pracować
na właściwym formacie.

## Jak to wygląda w rozdziale

```
4 · SPADY
[spady 11,6 mm]  strona 973,3 × 1973,3 mm, format netto 950 × 1950 mm
Format netto wzięty z ramki TrimBox zapisanej w pliku.
Po przycięciu wymiar będzie się zgadzał z szablonem.
[Przytnij spady]        zostaw spady, idę dalej
```

- Rozdział **mówi, skąd wie** — „z ramki TrimBox" albo „z wytycznych" — żeby dało się to
  zweryfikować, a nie tylko uwierzyć.
- Mówi też **z góry**, czy po przycięciu wymiar się zgodzi. Jeśli nie, pisze wprost, że
  zajmie się tym następny rozdział — zamiast zostawiać wrażenie, że coś poszło nie tak.
- Spad liczony jest **osobno z każdej strony** (`trim_bleed_mm` = lewo / góra / prawo / dół).
  Przy równym spadzie pokazujemy jedną liczbę, przy nierównym wszystkie cztery z podpisem —
  bo nierówny spad zwykle znaczy, że treść jest przesunięta i warto na to spojrzeć.
- Gdy spadów nie ma: „**brak** — plik nie ma spadów, strona to od razu format netto",
  przycisk wyszarzony.
- Nic nie dzieje się samo. Rozdział można domknąć również świadomym **„zostaw spady, idę
  dalej"** — np. gdy klient wie, co robi, albo gdy to my się mylimy.
- Ponowne kliknięcie przycisku **cofa** poprawkę, jak w pozostałych rozdziałach.

## Zmierzone

`spady.pdf` (30 MB, 973,3 × 1973,3 mm, produkt niestandardowy 950 × 1950):

```
wykrycie          natychmiast (z ramek, bez renderowania)
przycięcie        strona 973,3 × 1973,3  →  950,0 × 1950,0 mm
spad              11,6 / 11,6 / 11,6 / 11,6 mm
źródło            TrimBox
rozdział 5        „wymiar się zgadza — plik 950 × 1950, szablon wymaga 950 × 1950"
```

Ramki strony w plikach testowych (potwierdzenie, że nie ma fałszywych trafień):

| Plik | MediaBox | TrimBox | wykryty spad |
|---|---|---|---|
| `spady.pdf` | 973,3 × 1973,3 | 950 × 1950 | **tak** |
| `fonty.pdf` | 980 × 2050 | = strona | nie |
| `strony.pdf` | 2650 × 1034 | = strona | nie |
| `1815_czcionki.pdf` | 2870 × 2460 | = strona | nie |
| `1824_strony_wymiar_cmyk.pdf` | 4090 × 2300 | = strona | nie |
| `ramki_w.pdf` | 1014,9 × 2512,9 | = strona | nie (naddatek nierównomierny) |

## Kolejność rozdziałów

Przy okazji zmieniła się kolejność całej sekcji poprawek (uwaga Tomasza: usunięcie wytycznych
ma być przed wymiarem):

```
1 · Plik → 2 · Produkt → 3 · Ramki z szablonu → 4 · Spady → 5 · Wymiar wydruku
→ 6 · Overprint → 7 · Fonty → 8 · Kolory → 9 · Spłaszcz projekt → 10 · Jakość wydruku
```

Rozdziały dalej wchodzą **pojedynczo**: spady czekają na domknięcie ramek, wymiar czeka na
domknięcie spadów (`updateSizeBox` sprawdza `framesSettled() && trimSettled()`), a reszta
poprawek na domknięcie wymiaru.

Dwie rzeczy, które trzeba było przy tym zabezpieczyć:

- Po zakończeniu szukania ramek trzeba **odświeżyć rozdział o spadach** — inaczej zostawał
  schowany do końca sesji, bo w chwili pierwszego rysowania ramki jeszcze się liczyły.
- Gdy szukanie ramek **padnie** (błąd zapytania), rozdział o ramkach pisze o błędzie, ale
  **przepuszcza dalej** (`framesErr`). Inaczej jeden błąd blokowałby cały program.

## Znaczniki cięcia a rozdział o ramkach

`spady.pdf` ma nie tylko spad, ale i **znaczniki cięcia** — i to one wywołały fałszywkę
w rozdziale o ramkach („Ramka 973 × 1973 mm" ×2, opisane w `10_ramki_z_szablonu.md`).
Po przycięciu spadów znaczniki wychodzą poza stronę i znikają z wydruku same z siebie,
więc rozdział o ramkach nie ma się nimi czym zajmować.

Przy okazji potwierdziło się, że znaczniki **da się** rozpoznać (ścieżka z kilkunastu
krótkich odcinków w rogach, rysowana podwójnie: biała podkładka + czarne kreski). Gdy
trafi się plik ze znacznikami, ale **bez ramek PDF-a**, będzie z czego odczytać linię
cięcia — to naturalny trzeci poziom wykrywania spadów, do zrobienia na takim pliku.


## Spady a sugestia produktu (2026-09-10)

Plik ze spadami jest większy od formatu o szerokość spadu z każdej strony i o tyle właśnie
mija się z każdym szablonem w wytycznych. `spady.pdf` (973,28 × 1973,28 mm strony wobec
950 × 1950 mm netto) nie dostawał **żadnej** sugestii produktu. Od teraz wymiar netto
z tego rozdziału (`trim_mm`) idzie razem z wymiarem strony do `suggest.suggest_all()`,
a trafienie po netcie jest oznaczone w opisie: „— po odjęciu spadów".
Szczegóły i pomiary: `06_sugestie_po_wymiarze.md`.
