# Poprawki z 24.09 (zgłoszenia Tomasza na PRINT_CHECKER_TEST_100x200_SZABLON_PASERY.pdf)

Rozdział o szablonie z wytycznych — patrz `10_ramki_z_szablonu.md` (sekcja „Przebudowa 24.09").
Tutaj pozostałe zgłoszenia z tego dnia.

## 1. Sugestia produktu: „Air GATE ROUND" dla pliku 100×200

Plik: strona 1040 × 2040 (spady 20 mm), netto 1000 × 2000, w środku zostawiony szablon
Pop-up Lightbox 100x200 (ramka 1015 × 2014 + napis z nazwą produktu).

Przyczyna: dopasowanie po wymiarze z tolerancją 3 % dawało **wszystkim** trafieniom stały
wynik 0,9 — 12 produktów remisowało, a remis rozstrzygała długość nazwy. Air GATE ROUND
pasował tylko OBRÓCONY (szablon „Top" 1999 × 1041, 41 mm różnicy) i wygrał, bo ma krótką nazwę.

Teraz (`suggest.py`):
- **Treść pliku** (`suggest_by_content`, podpowiedzi liczy `server._content_hints`):
  napis z pełną nazwą produktu → 0,96; ramka w kolorze wytycznych o wymiarze szablonu
  produktu (±1,5 mm) → 0,90; oba naraz → 0,98. Etykieta „z szablonu w pliku".
- **Wymiar** — wynik zależy od odchyłki: 0,9 − min(0,1; 3 × odchyłka względna), obrócony
  −0,04; gdy plik ma TrimBox, trafienie po wymiarze brutto −0,02 (netto to zamierzony format).

Wynik na pliku testowym: 1. Pop-up Lightbox 100x200 (98 %), potem produkty z szablonem
1015 × 2014 (LPO, Quick, Smart, Poster — 90 %).

## 2. Rola „Base-a 1917×536"

`guessTemplateIndex` zgadywał tylko po nazwie pliku, a bez trafienia brał pierwszą rolę.
Teraz bez trafienia w nazwie wybiera rolę **po wymiarze**: ramka szablonu z pliku
(`file.ramki_szablonu`), format netto, wymiar strony; obrócony +2 %; próg 5 %.

## 3. „Cofnij" przy wymiarze wracało do szablonu

Cofnięcie wymiaru zdejmowało WSZYSTKIE poprawki. Teraz zostają poprawki sprzed wymiaru
(usunięty szablon, przycięte spady — obie idą na oryginale i nie zależą od kadru), a znikają
tylko te po nim (overprint, fonty, kolory, spłaszczenie). Pytanie pojawia się tylko wtedy,
gdy jest co zdejmować z tych późniejszych.

## 4. Overprint: „3 użycia", a przycisk wyszarzony

`preview.uses_overprint` i `fixes.remove_overprint` przeglądały tylko `pdf.objects`, czyli
obiekty POŚREDNIE. W tym pliku stany graficzne z `/OP true` są wpisane bezpośrednio w zasoby
strony — nie było ich tam. Nowe `fixes.all_dicts(pdf)` schodzi także do słowników
zagnieżdżonych. Wynik: wykryte i naprawione 3 stany (spady.pdf i ramki_w.pdf bez zmian).

## 5. Fonty: nieosadzona Helvetica blokowała zamianę na krzywe

Helvetica to jeden z 14 fontów standardowych PDF-a (Helvetica, Times, Courier — z wariantami —
Symbol, ZapfDingbats). Ich kształt i szerokości ustala specyfikacja PDF, każdy program ma je
wbudowane (Ghostscript/MuPDF: metryczne klony URW). Nieosadzony font standardowy NIE blokuje
już zamiany (`fixes.is_base14`, w UI `isBase14`); w raporcie dopisek, że krzywe powstały
z wzorcowego kroju. Porównanie renderów oryginał / po zamianie: tekst w Helvetice identyczny.

**Zmiana tego samego dnia (decyzja Tomasza):** nieosadzony font NIE blokuje już zamiany w ogóle.
Photoshop przy otwieraniu PDF-a rasteryzuje całość i przy braku fontu podstawia krój
zastępczy — i to było akceptowane. Robimy to samo: Ghostscript dostaje `-sFONTPATH` z fontami
Windowsa (`%WINDIR%\Fonts` i fonty użytkownika), więc zainstalowany font bierze z systemu;
brakujący podstawia krojem zastępczym, trzymając szerokości liter z PDF-a. Raport ma uwagę,
które fonty były nieosadzone („sprawdź suwakiem"), rozdział „Fonty" pokazuje je szarym
tagiem zamiast czerwonego. Sprawdzone na spreparowanym pliku: font zainstalowany → wzięty
z systemu; font nieistniejący → krój zastępczy, bez błędu.

## 6. Overprint na Windowsie dalej wyszarzony

Mimo poprawki z pkt 4 u Tomasza przycisk dalej był nieaktywny (zadanie wgrane już na nowym
kodzie). Nie udało się odtworzyć przyczyny poza Windowsem (pikepdf 8 i 10 działają). Zmiany:
- `fixes.all_dicts` odporne na każdy element (osobny try, `getattr(x, "is_indirect")`) plus
  drugie, jawne przejście po `/Resources /ExtGState` stron i obiektów formy,
- `preview.uses_overprint` wypisuje błąd w oknie serwera zamiast go połykać,
- UI: przycisk i symulacja w podglądzie idą też za analizą (`overprint_uses > 0`) — tym samym
  licznikiem, który pokazuje „3 użycia".


## 7. Bez kroju zastępczego (korekta pkt 5, decyzja Tomasza)

Tomasz nie chce kroju zastępczego. Zasada teraz:
- font **osadzony** — kształty z pliku (jak zawsze),
- **standardowy PDF-a** (Helvetica, Times, Courier, Symbol, ZapfDingbats) — wzorcowy krój,
- **nieosadzony, zainstalowany w systemie** — bierzemy z systemu (`-sFONTPATH`),
- **nieosadzony i niezainstalowany** — ODMOWA, zarówno przy krzywych, jak i przy spłaszczaniu.

Jak to wykrywamy: Ghostscript uruchomiony BEZ `-q` pisze „Loading font X (or substitute) from
<ścieżka>". Ścieżka w zasobach Ghostscripta (`Resource/Font`, `%rom%`) = zamiennik → przerywamy
i nie podmieniamy pliku (`fixes._gs_substituted`). Sprawdzone: font nieistniejący → odmowa
(krzywe i spłaszczanie), font zainstalowany → przechodzi.

Uwaga do dyskusji o Photoshopie: rasteryzacja nie odtworzy kształtu, którego nie ma w pliku.
PDF-y klientów zwykle MAJĄ fonty osadzone i wtedy Photoshop (i nasze krzywe) daje oryginalny
kształt bez instalowania czegokolwiek. Przy foncie naprawdę nieosadzonym Photoshop/Acrobat
podstawiają zamiennik (Acrobat pokazuje go w Właściwości dokumentu → Czcionki jako „Używana
czcionka: …").

## 8. Po wyborze produktu z projektu zostawał jeden obraz (+ spłaszczenie dawało BIAŁĄ stronę)

Błąd Ghostscripta (10.02 u nas, 10.07 u Tomasza): **symulacja overprintu
(`-dOverprint=/simulate`) + wygładzanie (`-dTextAlphaBits`/`-dGraphicsAlphaBits`) przy stronie
renderowanej pasami** (każda większa strona) gubi prawie całą treść. Wyszło na jaw dopiero teraz,
bo po poprawce z pkt 6 overprint w pliku testowym jest wreszcie wykrywany i podgląd włączył
symulację. Kafelki widoku szczegółowego (pyramid) pokazywały jeden obraz; spłaszczenie tego
pliku dawało pustą stronę.

Ustalone pomiarami:
- bez overprintu w pliku błędu nie ma (plik po „Napraw overprinty" spłaszcza się dobrze),
- bez wygładzania albo bez pasów (MaxBitmap ≥ ok. 10× rozmiaru strony) wynik jest poprawny,
- `-dOverprint=/enable` na urządzeniu CMYK NIE nakłada overprintu (identyczne jak bez niego),
  więc spłaszczanie musi zostać przy `/simulate`.

Poprawka: `preview.gs_aa_args(overprint, w_px, h_px, ncomp)` — jedno miejsce dla wszystkich
renderów Ghostscripta (podgląd, wycinki, kafelki widoku, spłaszczanie). Plik bez overprintu →
wygładzanie jak dotąd. Plik z overprintem → wygładzanie + MaxBitmap = 12 × strona, o ile
≤ 1,5 GB; powyżej — bez wygładzania (krawędzie ostrzejsze, treść kompletna). Spłaszczanie
sprawdza overprint w pliku (`uses_overprint`). Sprawdzone na pliku testowym: kafelki, wycinek
i spłaszczenie kompletne, overprint dalej symulowany.

## 9. Overprint PO kolorach (pomysł Tomasza)

Na suwaku overprintu zmieniał się zielony RGB, choć poprawka go nie dotyka. Przyczyna:
Ghostscript, symulując overprint, przelicza CAŁĄ stronę przez CMYK (FOGRA39) — RGB dostaje
wtedy kolor jak z drukarki (104,182,87). Po zdjęciu overprintu nie ma powodu przeliczać
i RGB wychodzi jak na ekranie (25,229,76). Różnica wyświetlania, nie pliku.

Rozwiązanie: rozdział „Overprint" przeniesiony ZA „Kolory" (kolejność: Fonty → Kolory →
Overprint → Spłaszcz). Przycisk „Napraw overprinty" czeka, aż kolory będą w CMYK
(`colorsDone()`: konwersja nałożona albo w pliku same CMYK/spoty). Sprawdzone: konwersja
Ghostscriptem zachowuje overprint (2 stany graficzne), a zielony po konwersji wygląda tak
samo po obu stronach suwaka (99,178,49). W potoku poprawek overprint i tak szedł po kolorach.

## 10. Rozmyty / postrzępiony tekst w powiększeniu (pliki z overprintem)

Skutek obejścia z pkt 8: widok szczegółowy tego pliku (4913 × 9638 px) przekraczał próg
pamięci i szedł bez wygładzania — litery postrzępione, rozjechane odstępy. Teraz zamiast
wyłączać wygładzanie robimy **nadpróbkowanie**: Ghostscript liczy 2× gęściej bez własnego
wygładzania (tam błędu nie ma), a my uśredniamy 2×2 (`pyramid._supersample`, `_downsample`
przez Pillow `reduce`). Pamięć: jedno pasmo więcej. Czas na tym pliku: 9,7 s zamiast 3 s
(u nas, 2 rdzenie) — tylko dla plików z overprintem, dopóki się go nie naprawi.
Spłaszczanie dużej strony z overprintem dalej idzie bez wygładzania (do zrobienia tak samo,
jeśli będzie potrzeba — typowo overprint jest naprawiony przed spłaszczeniem).

## 11. Registration (/All) po konwersji na CMYK robił się błękitny

Błąd Ghostscripta: przy `ColorConversionStrategy=/CMYK` separację o specjalnej nazwie „/All"
(Registration = 100 % wszystkich farb) zamienia na SAM cyjan 100/0/0/0. Obejście
(`fixes._rename_registration`): przed konwersją separacja dostaje zwykłą nazwę
„Registration_All" — Ghostscript przelicza ją wtedy przez przestrzeń alternatywną i wychodzi
100/100/100/100 (sprawdzone renderem CMYK). Dotyczy też DeviceN z /All.

## 12. Powiększenie zostawało rozmyte (dopóki nie ruszyło się suwakiem)

W katalogu zadania u Tomasza: widok „przed poprawkami" (`view_b0…`) miał 2 pasy z 10 — kolejna
poprawka unieważniła liczenie w trakcie i widok nigdy się nie dokończył. Przy dwóch warstwach
(przed/po) kafelki pokazują się tylko, gdy OBIE są kompletne → do końca zostawał mały podgląd
rozciągnięty w powiększeniu. Suwak spłaszczania przełączał na warstwy policzone w całości.

Poprawki:
- serwer: wpis w stanie „stale"/„err" nie blokuje — POST liczy od nowa; każdy przebieg ma
  swój znacznik (`tok`), więc stary przebieg nie pisze do nowego wpisu pod tym samym kluczem,
- przeglądarka: „stale" i „idle" (wpis unieważniony / wariant jeszcze się buduje) → ponowne
  zamówienie zamiast końca odpytywania,
- `pyramid.RENDER_VER` w kluczu widoku — po zmianie sposobu renderowania stare kafelki
  z dysku nie są używane.

Test: unieważnienie w trakcie (2/15) → ponowne zamówienie → `done 15/15`, 50/50 kafelków.

## Uwaga techniczna: zapis plików na dysk Tomasza

`device_commit_files` z tym samym plikiem pośrednim potrafił zapisać POPRZEDNIĄ wersję
(index.html, app.js, preview.py, pyramid.py były u Tomasza nieaktualne — stąd „stara kolejność
rozdziałów" i niedziałające poprawki). Od teraz: każdy zapis z nowego katalogu pośredniego
i sprawdzenie sum kontrolnych po zapisie.

## 13. Symulacja overprintu — osobny przycisk, domyślnie wyłączona

Prośba Tomasza: przed konwersją kolorów RGB ma wyglądać jak na ekranie, nie „jak po druku".
Symulacja overprintu w Ghostscripcie przelicza CAŁĄ stronę przez CMYK, więc była wyłączona
z automatu i przeniesiona do rozdziału „Overprint":

1. **„Pokaż, jak to wydrukuje (symulacja overprintu)"** — przełącznik całego podglądu.
   Pod nim suwak **bez symulacji ↔ w druku**: ten sam plik, dolna warstwa bez symulacji,
   górna z nią (`cmpMode = "opsim"`, `bottomOp()` / `topOp()`, `topVer()`; warstwa górna
   i piramida działają też wtedy, gdy nie ma jeszcze żadnej poprawki — `topOn()`).
2. **„Napraw overprinty"** — jak dotąd, ze swoim suwakiem; kliknięcie włącza symulację
   (bez niej naprawy nie widać).

Podgląd po konwersji na CMYK idzie przez Ghostscripta z profilem FOGRA39 (`gs=1` w adresie
podglądu, `render_png(force_gs=True)`), ale BEZ symulacji — wcześniej konwersja kolorów
włączała symulację na stałe tylko po to, żeby render szedł przez Ghostscripta.

Sprawdzone w przeglądarce: przed kolorami `op=0 gs=0`; po kolorach `op=0 gs=1`; symulacja
`op=1`; suwak symulacji: dół `op=0`, góra `op=1` tej samej wersji; naprawa włącza symulację;
wyłączenie wraca do `op=0`.

## 14. Po „Napraw overprinty" znika symulacja

Po naprawie przycisk symulacji i jego suwak znikają (nie są już potrzebne); po cofnięciu
naprawy wracają. Suwak samej naprawy zostaje.

## 15. Pełna jakość dalej się nie wczytywała (dopiero po ruchu suwakiem w rozdziale)

Przyczyna: zapytanie o widok w trakcie nakładania poprawki dostaje od serwera 409 („zajęty"),
a przeglądarka zapisywała to jako błąd i PRZESTAWAŁA pytać — warstwa zostawała bez pełnej
jakości, aż ruch suwaka wymusił nowe zamówienie. Na wolniejszym komputerze i większym pliku
(u Tomasza) zdarzało się to dużo częściej niż w teście.

- przeglądarka: po błędzie ponawia zamówienie (`pyrRetry`, do 30 razy dla tej wersji,
  odstęp rośnie do 4 s). Test z wymuszonymi 4 odpowiedziami 409: obie warstwy pełne.
- serwer: piramida pliku „po samym wymiarze" (warstwa „przed poprawkami") NIE jest kasowana
  przy każdej poprawce, jeśli wymiar się nie zmienił (`_drop_variants(keep_base)`). Po poprawce
  liczy się jedna piramida zamiast dwóch: pełna jakość po 4 s zamiast 16 s (u nas).
- `window.__adcheckPyr` — stan warstw podglądu do diagnostyki w konsoli przeglądarki.

## 16. Podgląd szablonu domyślnie wyłączony

Włącza się sam przy pierwszym wejściu do rozdziału „Wymiar wydruku" (raz na plik — jeśli
użytkownik go potem wyłączy, zostaje wyłączony). Nowy plik = znów schowany.

## 17. Dołożone tło na marginesach miało inny odcień

Dwie przyczyny:
- **podgląd** (przed zatwierdzeniem): tło brane z podglądu MuPDF (CMYK na ekran bez profilu),
  projekt obok z piramidy Ghostscripta (FOGRA39). Teraz główny podgląd (1600 px) zawsze idzie
  przez Ghostscripta (`gs=1`, 0,5 s zamiast 0,3 s); miniatury dalej MuPDF.
- **plik do druku**: paski tła („rozciągnij krawędź") były zapisywane jako RGB — wartości farb
  paska i projektu obok rozjeżdżały się po konwersji. Teraz pasek jest CMYK, renderowany
  z zarządzaniem kolorem (MuPDF ICC): treść CMYK przechodzi 1:1, RGB przez FOGRA39 jak
  w rozdziale „Kolory". Zmierzone: pasek 216/165/89/153 = granat projektu 216/165/89/153,
  także po konwersji kolorów. Tryb lustrzany kopiuje wektory — bez zmian.

## 18. Pełna jakość przy symulacji overprintu (Windows)

U nas działa, u Tomasza nie. Poprawki na podejrzaną przyczynę i do diagnozy:
- komunikaty Ghostscripta przy liczeniu piramidy czytane na bieżąco w osobnym wątku
  (`pyramid._popen`) — na Windowsie bufor potoku ~4 KB; po zapełnieniu Ghostscript stawał,
  a liczenie wisiało w połowie bez błędu,
- błędy liczenia pełnej jakości zapisywane do `app/work/_bledy_podgladu.log` (i do konsoli),
  z końcówką komunikatów Ghostscripta.

## 19. Usunięty przycisk „Pełny ekran" (niepotrzebny)

## 20. Symulacja druku w rozdziale „Kolory"

Przycisk „Pokaż, jak wydrukuje kolory (symulacja druku)" + suwak **ekran ↔ druk** (ten sam
plik; `cmpMode = "proof"`, `bottomPr/topPr`). Założenie (ustawień drukarki nie znamy): RGB
= sRGB, druk = Coated FOGRA39, intencja relatywna kolorymetryczna + BPC. Render: Ghostscript
do CMYK (`preview.gs_proof_args`, `tiff32nc` / w piramidzie strumień PAM `pamcmyk32`), na
ekran przez ten sam profil (`preview.proof_rgb`, Pillow ImageCms). CMYK zostaje nietknięty
(±2/255), RGB wychodzi jak po przeliczeniu przez drukarkę (zielony 25/229/76 → 104/182/88).
`-sProofProfile` Ghostscripta odrzucony — przepuszcza przez profil także CMYK.

## 21. Po konwersji na CMYK suwak (po wczytaniu pełnej jakości) wracał do RGB

Klucz widoku wersji „po poprawkach" nie zmieniał się między poprawkami, a kafelki mają
w przeglądarce pamięć podręczną 24 h — zostawały stare (RGB). Klucz zawiera teraz znacznik
zawartości pliku (czas zapisu) — każda poprawka = nowe kafelki.

## 22. Tekst po zamianie na krzywe wyglądał na grubszy (tylko podgląd)

Kształt liter się nie zmienia (przy 600–1200 dpi różnica farby 0,6 %). Grubsze było tylko
w podglądzie Ghostscripta: „fill adjust" dopełnia brzegi wypełnień o ułamek piksela, a litery
fontu rysowane są innym mechanizmem. W renderach PODGLĄDU wyłączone (`0 0 .setfilladjust2`,
`preview.GS_PREVIEW_PRE`); włosowe linie bez zmian; spłaszczanie do druku bez zmian.
Porównanie fragmentu w pełnej jakości: `Claude outputs/fonty_przed_po.png`.

## 23. Tło z krawędzi — inny odcień przy symulacji (Ghostscript)

PyMuPDF dołączał do paska tła własny profil ICC (ICCBased), a wektory projektu są DeviceCMYK —
Ghostscript (i RIP) liczyły je różnie: 20/45/68 wobec 36/50/70 przy tych samych farbach.
Pasek dostaje teraz `/ColorSpace /DeviceCMYK`. Sprawdzone we wszystkich trybach podglądu
(ekran, druk, overprint): margines = projekt.
