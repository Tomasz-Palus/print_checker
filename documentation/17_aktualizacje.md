# 17 — Aktualizacje i proces wydań (wersja 0.4, 25.09.2026)

## Proces: poprawka → test → wydanie

1. **Poprawka:** Claude zmienia kod i zapisuje go na dysku Tomasza.
2. **Test:** Tomasz sprawdza poprawkę przez `app\run.bat` (przeglądarka, bez budowania).
3. **Wysłanie:** GitHub Desktop → *Commit to main* → *Push origin*. GitHub buduje instalatory
   i sprawdza je (self-test), ok. 4 minuty.
   - **Numer wersji bez zmian** = **test**. Instalatory leżą tylko w „Artifacts” danego przebiegu
     (zakładka Actions → przebieg → Artifacts). Ludzie nic nie dostają.
   - **Nowy numer w `app/version.py`** (np. 0.4 → 0.5) = **wydanie**. GitHub tworzy wydanie
     `v<wersja>` z instalatorami i plikiem `SHA256SUMS.txt`. Programy użytkowników same je
     znajdują.

Do 0.3 każde wysłanie podmieniało pliki publicznego wydania. Nieprzetestowana zmiana mogła więc
trafić do ludzi.

## „Zaktualizuj teraz” (decyzja Tomasza: przycisk, nie instalacja bez pytania)

`app/updater.py`:
1. **Sprawdzanie:** przy starcie i co 6 h program pyta GitHuba o najnowsze wydanie
   (`version.REPO`).
2. **Pobieranie:** zainstalowany program (Windows, macOS), który znajdzie nowszą wersję, pobiera
   w tle instalator dla swojego systemu do `…\adChecker\update\`. Nagłówek pokazuje „Pobieram
   wersję X… NN %”.
   - Plik jest sprawdzany sumą SHA-256 z `SHA256SUMS.txt`. Uszkodzony albo podmieniony instalator
     nie zostanie uruchomiony; wtedy zostaje zwykły link do pobrania ręcznego.
3. **Przycisk:** potem w nagłówku jest zielony przycisk **„Zaktualizuj do wersji X”**. Kliknięcie
   pokazuje pytanie „Zaktualizować…?” (z uwagą, że otwarty plik trzeba będzie wgrać jeszcze raz),
   potem okienko „Aktualizuję adChecker…”. Program uruchamia instalację i zamyka się.
4. **Instalacja:**
   - **Windows:** instalator Inno Setup po cichu (`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`),
     jako osobny proces. Nowy wpis `[Run]` z `skipifnotsilent` uruchamia program po cichej
     instalacji.
   - **macOS:** DMG montowany w tle, nowa aplikacja kopiowana obok starej. Mały skrypt czeka na
     zamknięcie programu, podmienia aplikację i ją uruchamia. Program uruchomiony prosto z DMG
     albo bez prawa zapisu do folderu dostaje komunikat zamiast aktualizacji.
     **Niesprawdzone na prawdziwym Macu.**
5. **Sprzątanie:** przy starcie folder `update\` jest usuwany (to instalator po aktualizacji).

**Bez ostrzeżeń:** pliku pobranego przez program (a nie przeglądarkę) system nie oznacza jako
„z internetu”. Aktualizacja nie pokazuje więc ostrzeżeń SmartScreen ani Gatekeepera.

**Tryb deweloperski** (`run.bat`) niczego nie pobiera — pokazuje tylko link do wydania.

`server.py`:
- `/api/version` zwraca `updater.state()`.
- `/api/update/install` uruchamia instalację i po sekundzie kończy program (najpierw odpowiedź).

Wersja 0.3 nie ma tej funkcji. Z 0.3 na 0.4 trzeba przejść raz ręcznie (zielony link „Jest nowa
wersja”).

Test w sandboksie:
- pobieranie z lokalnego serwera (dobra suma → „ready”, zła → „error”);
- porównywanie numerów (0.4.1 > 0.4, 0.10 > 0.9);
- nagłówek z podstawionymi odpowiedziami (pobieranie → przycisk → pytanie → okienko);
- self-test zbudowanej paczki: OK.

Samej instalacji na Windowsie nie da się sprawdzić bez dwóch wydań. Test u Tomasza: zainstalować
0.4, wydać 0.4.1, kliknąć przycisk.

## Akceptacja pliku (Tomasz 25.09)

- **Plik bez poprawek od rozdziału Kolory:** „przed” było białe.
  - Przyczyna: dwie identyczne warstwy (przed = po) trafiały na jeden element podglądu, a
    przezroczystość górnej (suwak na „przed” = 0) chowała go całkiem.
  - Poprawka: `viewer.setScene` scala identyczne warstwy w jedną.
  - W rozdziale jest teraz zdanie, że plik nie potrzebował poprawek, więc przed i po wygląda tak
    samo.
- **„Pokaż wydruk przed i po”** od razu dopasowuje podgląd do okna (`viewer.zoomFit()`), jak
  przycisk „Dopasuj”.

## Indeks wymiarów w instalatorze (Tomasz 25.09)

- **Od 0.3:** `app/data/template_index.json` jest w każdym instalatorze. Przy pierwszym starcie
  trafia do folderu użytkownika, więc nikt nie zaczyna od pustego indeksu.
- **Od 0.4:** `sizeindex.load()` przy każdym starcie dokłada z indeksu instalatora produkty,
  których użytkownik nie ma (albo ma tylko nieudane próby). Nowa wersja programu przynosi więc
  też nowe wymiary. Wcześniej kopia z instalatora była brana tylko wtedy, gdy użytkownik nie miał
  żadnej.
- **Przed wydaniem** warto podmienić `app\data\template_index.json` na najpełniejszy indeks. Ten
  z zainstalowanego programu Tomasza leży w `%LOCALAPPDATA%\adChecker\data\template_index.json`
  (1016 produktów wobec 1003 w repozytorium).

## Wydanie 0.4 i test aktualizacji

- **v0.4** wydana 25.09 (build zielony, ok. 3 min). W wydaniu są instalatory Windows i macOS oraz
  `SHA256SUMS.txt`.
- **0.4.1** zmienia tylko numer wersji. Służy wyłącznie do sprawdzenia przycisku „Zaktualizuj
  teraz” na zainstalowanej 0.4.
- **Test aktualizacji:** działa. W dzienniku u Tomasza 0.4 pobrała 0.4.1 o 10:08, a o 10:09
  program wystartował już jako 0.4.1.

## 0.4.2 — błąd: drugi plik dziedziczył decyzje z pierwszego (Tomasz 25.09)

- **Objaw:** czasem przy `spady.pdf` Kolory były „✓ CMYK”, a Overprint „✓ wyłączony”, choć
  w treści było „Nie udało się wyłączyć overprintu”, a w Fontach „Nie udało się zamienić tekstu
  na krzywe”. W plikach roboczych nie było ani wersji po kolorach, ani po overprincie.
- **Przyczyna:** stan rozdziałów (`S.settle`, `S.choice`, `S.stepErr`, suwaki, akceptacja) nie
  był czyszczony przy wgraniu nowego pliku. Drugi (trzeci…) plik w tej samej sesji zastawał
  rozdziały „domknięte” decyzjami z poprzedniego pliku, choć na nim nic nie zrobiono. Stąd
  „czasem działa”: pierwszy plik po uruchomieniu zawsze był dobry.
  - Przyczynę znaleźliśmy, patrząc na żywo na pliki robocze, gdy Tomasz kilka razy wgrywał ten
    sam plik.
- **Poprawka:** `state.resetJobState()` przy każdym wgraniu pliku (`main.upload`). Sprawdzone:
  po ponownym wgraniu tego samego pliku Kolory znów czekają na decyzję, a Overprint jest schowany.

## 0.4.3 — animacje rozdziałów (Tomasz 25.09)

- **Zwijanie i rozwijanie jest płynne.** Treść rozdziału jest w `.ch-in`, owijanym w
  `initChapters`. `.ch-b` to siatka, która przechodzi z `1fr` do `0fr` w 0,35 s, razem
  z przezroczystością i odstępami.
  - Rozwijanie rusza 0,12 s po zwijaniu, więc rozdziały zmieniają się po kolei, a nie naraz.
  - Na czas ruchu rozdział dostaje klasę `anim` (`MutationObserver` na `class`/`data-st`) i treść
    jest przycinana. Poza ruchem nie jest, bo lista produktów wystaje poza rozdział.
  - Zwinięta treść ma `visibility: hidden` — klawiatura po niej nie skacze.
- **Rozdziały pojawiają się po kolei.** `revealChapters()` po każdym rysowaniu daje nowo widocznym
  rozdziałom animację wjazdu (zjazd o 10 px i rozjaśnienie, 0,45 s) z opóźnieniem 150 ms
  × numer w serii. Gdy program sam zaliczy kilka rozdziałów naraz (szablon „czysto”, spady „brak”,
  wymiar się zgadza…), wjeżdżają jeden po drugim.
  - Przy starcie programu nic nie wjeżdża (klasa `ready` na `body` po 0,4 s).
- **Ograniczony ruch:** przy ustawieniu systemowym „ogranicz ruch” (`prefers-reduced-motion`)
  animacji nie ma.
- **„Czy element widać”:** zwinięta treść nie znika już z układu (ma wysokość 0), więc
  `getClientRects`/`offsetParent` tego nie mówią. Nowe `util.shown(el)` sprawdza też, czy
  rozdział jest zwinięty. Używają go: reguła jednego suwaka w `main.js` i samouczek.
- **Sprawdzone** na `Wydruk_adWall_Vario…`: Spady i Wymiar pojawiły się 150 ms po sobie. Samouczek
  przechodzi od początku do końca.

## 0.4.3 — spłaszczenie: suwak i schodki na krawędziach (Tomasz 25.09)

- **Brak suwaka „przed / po” po spłaszczeniu.**
  - Przyczyna: reguła „rozwinięte dwa ostatnie rozdziały”. Gdy za Spłaszczeniem były już
    widoczne Jakość i Akceptacja (np. spłaszczenie było „niepotrzebne”, więc przeszło się dalej,
    a potem wróciło), rozdział zwijał się zaraz po „Pokaż, jak wydrukuje”, a razem z nim jego
    suwak. Odtworzone na `spady.pdf`.
  - Poprawka: rozdział, w którym właśnie zrobiono poprawkę albo kliknięto „Pokaż, jak wydrukuje”
    (`S.pin`), zostaje rozwinięty, nawet jeśli nie jest wśród dwóch ostatnich. Puszcza, gdy
    najświeższy suwak jest już w innym rozdziale. Dotyczy wszystkich rozdziałów z suwakiem.
- **Pikselowe wektory po spłaszczeniu.**
  - Przyczyna: obejście błędu Ghostscripta (`gs.aa_args`). Przy overprincie wygładzanie jest
    bezpieczne tylko dla strony renderowanej w całości. Duża strona (np. 5522 × 11 374 px) się nie
    mieściła, więc spłaszczenie szło bez wygładzania. Litery i linie miały schodki. Dotyczyło też
    pliku przykładowego z samouczka.
  - Poprawka: spłaszczenie liczy stronę **2× gęściej i uśrednia bloki 2 × 2**
    (`steps._flatten_supersampled`, Pillow `reduce`), jak podgląd. Wygładzanie Ghostscripta jest
    dokładane, gdy przy tej wielkości jest bezpieczne.
    - Obraz idzie strumieniem pasmami (`pamcmyk32`).
    - Wynik leży w pliku na dysku (`numpy.memmap`) i Pillow zapisuje z niego JPEG CMYK (ta sama
      konwencja Adobe co Ghostscript, `/Decode` bez zmian).
    - Od 0.4.4 (niżej) nadpróbkowanie jest ZAWSZE, nie tylko przy dużej stronie.
  - `gs.stream` zachowuje cały dziennik (`p.err_all`, do 2 MB) — potrzebny do wykrywania
    zamienionych fontów.
  - Zmierzone na pliku przykładowym (6142 × 12 047 px): kolory jak dotąd (średnia różnica
    0,19/255), krawędzie gładkie. Czas ok. 9 s zamiast 3 s; `spady.pdf` 6 s. Python ok. 500–600 MB
    (w tym plik na dysku), Ghostscript 76 MB.

## 0.4.4 — poszarpane litery, rozdziały po kolei, „Cofnij” w starszych rozdziałach (Tomasz 25.09)

- **Litery poszarpane po „Dopasuj wymiar” (`spady.pdf`).**
  - Przyczyna: napis „PACHNĄCE PRANIE” jest wypełniony gradientem przyciętym kształtem liter.
    Ghostscript nie wygładza krawędzi takiego przycięcia, nawet z `AlphaBits`. Było tak w każdej
    wersji przed zamianą na CMYK (po niej podgląd szedł już ścieżką z nadpróbkowaniem, stąd
    „znowu gładko”). Po dopasowaniu wymiaru było po prostu widać wyraźniej.
  - Poprawka: podgląd (`render._supersample`, `render.SS = 2`) i spłaszczenie liczą **zawsze** 2×
    gęściej i uśredniają. Wygładzanie Ghostscripta jest liczone dla renderu 2× (`gs.aa_args`
    z podwojonym wymiarem). Podgląd całości też.
  - Koszt zmierzony na `spady.pdf`: render 2× z wygładzaniem 1,9 s wobec 2,5 s dla 1× — czas idzie
    na wczytanie obrazów. `RENDER_VER = 7`, więc stare kafelki się nie mieszają.
- **Rozdziały pojawiają się po kolei, co 1,5 s** (`main.gateChapters`, `REVEAL_GAP`).
  - Rozdziały zaliczone same (fonty „brak tekstu”, spłaszczenie „niepotrzebne”…) nie wychodzą
    naraz. Pierwszy od razu, następne co 1,5 s; czekający jest schowany (`hidden`), ale jego
    logika już działa (np. jakość już się liczy).
  - Sprawdzone na `spady.pdf` po „Pokaż, jak wydrukuje” w Overprincie: Fonty 0,2 s, Spłaszczenie
    1,6 s, Jakość 3,1 s.
  - Nowy plik czyści kolejkę. Przy starcie programu i przy „ogranicz ruch” nic nie czeka.
- **Starszy rozdział z poprawką pokazuje tylko „Cofnij”.**
  - Rozdział Szablon, Spady, Wymiar, Kolory, Overprint, Fonty albo Spłaszczenie, w którym jest
    poprawka albo decyzja, a który nie jest jednym z dwóch ostatnich (ani przypiętym), dostaje
    klasę `past`. Znikają wybory, „Pokaż, jak wydrukuje”, suwaki i zdania o suwakach
    (`.now-only`); zostaje opis i przycisk **„Cofnij”** (przy decyzji bez poprawki: „Zmień
    decyzję”).
  - „Cofnij” cofa do tego rozdziału razem z krokami zrobionymi później — program pyta, gdy takie
    są. Potem rozdział jest znów ostatni i ma pełne wybory.
  - Sprawdzone: po cofnięciu Kolorów (z pytaniem o overprint) Kolory czekają na decyzję.
- **Przypięcie (S.pin) poprawione:** zdejmuje je rozdział dalej, który pojawia się **pierwszy
  raz** (praca poszła naprzód). Jakość i akceptacja, które tylko wracają po poprawce we
  wcześniejszym rozdziale, przypięcia nie zdejmują — suwak spłaszczenia zostaje.

## 0.4.5 — Spłaszczenie czeka na wybór, rozdziały nie znikają po poprawce (Tomasz 25.09)

- **Spłaszczenie zawsze czeka na wybór**, także bez przezroczystości. Wcześniej rozdział sam się
  zamykał („niepotrzebne”) i od razu pojawiała się Jakość.
  - Bez przezroczystości program pisze, że spłaszczać nie trzeba, i podpowiada „Zostaw jak jest”.
    Ten wybór od razu zamyka rozdział — bez „Pokaż, jak wydrukuje”, bo nic się nie zmienia.
  - „Spłaszcz projekt” działa jak dotąd (potem „Pokaż, jak wydrukuje”).
  - Pomoc („?”) poprawiona.
- **Po „Spłaszcz projekt” rozdziały od Overprintu znikały i wracały po kolei.**
  - Przyczyna: po każdej poprawce program analizuje nową wersję pliku. Do końca analizy
    Overprint, Fonty i Spłaszczenie „nie wiedziały”, czy są czyste, więc się chowały. Wcześniej
    trwało to ułamek sekundy, a od 0.4.4 wracały co 1,5 s.
  - Poprawka: `state.facts(name)` — rozdział ocenia plik w wersji sprzed swojego kroku (tak jak go
    widział, gdy był bieżący). Analizy wszystkich wersji zostają w `S.factsCache`
    (`main.loadAnalysis`). Późniejsza poprawka nie zmienia werdyktu wcześniejszego rozdziału.
- Sprawdzone na `spady.pdf`: po Overprincie pojawiają się Fonty i Spłaszczenie, a Jakość dopiero
  po wyborze. Po „Spłaszcz projekt” nic nie znika. Zmiana na „Zostaw jak jest” od razu pokazuje
  Jakość. Samouczek przechodzi.

## 0.4.6 — uwagi o granicach programu, spłaszczanie tylko w razie potrzeby (Tomasz 25.09)

Tomasz: program może błędnie zinterpretować niektóre projekty i nie zastąpi specjalisty; ocena
jakości też może się mylić; spłaszczać tylko wtedy, gdy to konieczne, bo lepiej, żeby plik
spłaszczyła drukarnia. Miejsca zaproponował Claude:

- **Na początku:**
  - Rozdział „Plik”, pod polem do wgrania — niebieska ramka (`#fileNotice`, `.box.info`):
    „adChecker pomaga przygotować plik do druku, ale nie zastępuje grafika DTP…”. Widać ją
    przed wgraniem pliku; potem rozdział się zwija.
  - Pierwszy dymek samouczka („Witaj w adCheckerze!”): jedno zdanie o tym samym.
- **Na końcu:** rozdział „Pobierz plik do druku” — „Masz wątpliwości co do pliku? Przed wysłaniem
  do druku pokaż go grafikowi.”
- **Jakość wydruku:** stała uwaga na dole rozdziału (`#quNotice`) i akapit w pomocy „?”: ocena
  jest automatyczna i orientacyjna, może się różnić od oceny grafika i nie wychwyci każdego
  problemu.
- **Spłaszczenie — nowa zasada: tylko gdy konieczne.**
  - Tekst przy przezroczystości: zwykle najlepiej zostawić ją drukarni (tekst i linie zostaną
    wektorowe). Spłaszczyć tylko, gdy drukarnia o to prosi albo „Pokaż, jak wydrukuje” pokazuje
    ślady. Wcześniej program zalecał spłaszczenie („Bezpieczniej spłaszczyć tutaj”).
  - Pomoc „?” przepisana w tym duchu.
  - Samouczek przy Spłaszczeniu każe teraz kliknąć **„Zostaw jak jest”** (wcześniej „Spłaszcz
    projekt”).
- Sprawdzone: samouczek przechodzi od początku do końca, teksty widoczne na zrzutach.

## 0.4.7 — suwak przed/po w Spadach „pokazywał tylko przed” (Tomasz 25.09)

- **Objaw:** w rozdziale Spady (plik testowy, strona 3) suwak przesunięty na „po” wyglądał jak
  „przed”.
- **Przyczyna:** „po” (strona bez spadów) jest mniejsze niż „przed” i leży na nim. Pas spadów
  ze znacznikami cięcia z „przed” wystawał więc spod „po” także przy suwaku na „po”. W środku obie
  wersje wyglądają tak samo (szablon usunięty wcześniej), więc zmiany nie było widać.
- **Poprawka:** `viewer.drawVeil` — między warstwami leży zasłona w kolorze tła podglądu,
  z otworem w miejscu „po”. Im bliżej „po”, tym mocniej przykrywa to, czego w „po” już nie ma. Na
  „po” zostaje sama strona bez spadów. Działa w każdym suwaku przed/po, w którym „przed” wystaje
  poza „po” (spady, szablon, wymiar, akceptacja). Warstwy mają teraz `z-index` 1 i 3, zasłona 2.
- Sprawdzone na stronie 3 pliku testowego: „przed” ze spadami i znacznikami, „po” bez. Samouczek
  przechodzi.

## 0.4.8 — poprawki z przeglądu kodu, część 1 (27.09)

Numery jak w `18_przeglad_kodu.md`.

- **A1 — spłaszczenie znów wykrywa podmieniony font.**
  - Przyczyna: od 0.4.3–0.4.4 spłaszczenie szło przez `gs.stream`, który dodawał `-q`. W trybie
    cichym Ghostscript nie pisze „Loading font … (or substitute)”.
  - Poprawka: `gs.stream(…, quiet=False)` puszcza pełny dziennik, a komunikaty z stdout kieruje
    na stderr (`-sstdout=%stderr`), żeby nie wmieszały się w obraz.
  - Sprawdzone: PDF z nieosadzonym fontem → „Nie spłaszczam: w pliku brakuje fontu…”. Plik
    przykładowy i `spady.pdf` spłaszczają się jak dotąd.
- **A14 — wykrywanie zamiennika fontu CID** (dołożone od razu, ta sama funkcja).
  `gs.substituted` rozpoznaje „Loading CIDFont X substitute from …”. Sprawdzone na PDF z
  nieosadzonym fontem CID.
- **A2 — analiza poprzedniego pliku nie trafia już do nowego.**
  - Klucz analizy ma numer zadania (`zadanie:wersja:strona`), a nie tylko `v0:strona`.
  - Wgranie pliku unieważnia analizę w toku (`anSeq`, `anBusy`).
  - Spóźniona odpowiedź dla innego pliku, wersji albo strony jest pomijana.
  - Sprawdzone: plik A wgrany i od razu zastąpiony `spady.pdf` → Kolory pokazują kolory `spady.pdf`
    (Registration), nie pliku A.
- **A4 — spóźniona poprawka albo cofnięcie nie nadpisuje zadania.** `applyStep`, `undoStep`
  i `resetSteps` sprawdzają, czy zadanie jest nadal to samo. Jeśli nie, odpowiedź jest
  pomijana, razem z błędem.
- **A3 — zmiana strony czyści decyzje.** `setPage` woła `resetJobState()`: decyzje w rozdziałach,
  wybory, akceptacja, podgląd porównań. Sprawdzone: na stronie 1 „zostaw szablon” i „zostaw
  spady”, po przejściu na stronę 3 Szablon znów czeka na decyzję.
- **A5 — bez pliku nie widać starych rozdziałów.**
  - W trakcie wgrywania i po błędzie wgrania rozdziały od Roli do Pobierania są schowane.
  - „Zatwierdź wymiar”, „zostaw szablon”, „zostaw spady”, wybory w Kolorach…Spłaszczeniu nic nie
    robią bez pliku.
- **A11 — Ghostscript nie obraca już stron.**
  - `gs.PDFWRITE_NO_ROTATE` (`-dAutoRotatePages=/None`) jest we wszystkich wywołaniach pdfwrite:
    CMYK i krzywe (`_gs_page`), EPS→PDF, krzywe do podglądu.
  - Sprawdzone: strona 400 × 800 z pionowym tekstem — bez flagi pdfwrite dodawał `/Rotate 90`,
    z flagą strona zostaje pionowa.
- **B15 — program przyjmuje zapytania tylko od siebie** (`server._only_this_computer`).
  - Host musi być 127.0.0.1, localhost albo [::1].
  - Nagłówek Origin, gdy jest, musi być tym samym adresem co program.
  - `Sec-Fetch-Site: cross-site` jest odrzucany.
  - Zapytania bez Origin przechodzą: self-test, sprawdzanie drugiego uruchomienia.
  - Sprawdzone: obca strona, `Origin: null`, inny port, podmieniony Host → 403; własne okno
    i localhost → 200.
- Samouczek przechodzi od początku do końca.

## 0.4.9 — poprawki z przeglądu kodu, część 2 (27.09)

Numery jak w `18_przeglad_kodu.md`.

- **A6 — obrazy inline.** pikepdf nazywa operator `"INLINE IMAGE"`, a kod szukał `"BI"`.
  - Teraz obraz inline liczy się do kolorów i do listy obrazów, z rozmiarem i ppi.
  - Nie ma numeru obiektu, więc ocena jakości nie mierzy jego detalu. Sprawdza tylko, czy ma dość
    pikseli (`detailmap.lowres_only`). Obrazki mniejsze niż 8 px to wypełnienia — jak dotąd
    pomijane.
  - Sprawdzone: obraz inline RGB 20 × 20 px rozciągnięty na 28 cm → „RGB” w kolorach, jakość
    „bad” (1,8 ppi). Wcześniej: brak koloru i werdykt „sam wektor”.
- **A7 — adnotacje.** Wygląd (`/AP /N`) adnotacji z flagą „drukuj” i bez „ukryta” jest
  analizowany jak treść strony (`Analyzer.annotations`, macierz z `/Rect` i `/BBox`). Sprawdzone:
  stempel z RGB, overprintem i nieosadzonym fontem → wszystko wykryte (wcześniej „czysto”).
- **A8 — obraz, którego nie da się odczytać,** nie wypada już z oceny. Sprawdzenie liczby pikseli
  (za mało ppi) działa bez dekodowania.
- **A9 — wzory (tiling pattern).** Macierz wzoru liczona względem przestrzeni strony albo formy,
  a nie macierzy w chwili `scn`. Sprawdzone: obraz we wzorze przy `cm 0.1` → 7,2 ppi i 353 mm
  (wcześniej 72 ppi i 35 mm).
- **C26 — formy rysujące same siebie** nie zawieszają już analizy. Działa ochrona przed cyklem
  i budżet 3 mln operatorów (`truncated` liczy się jako ostrzeżenie). Sprawdzone: plik z cyklem
  — ułamek sekundy (wcześniej > 60 s).
- **C27 — ocenę jakości po błędzie da się powtórzyć.** Serwer zaczyna od nowa, gdy poprzednia
  próba skończyła się błędem. W rozdziale pojawia się przycisk „Sprawdź jeszcze raz”.
- **C21:**
  - Miniatura stron zapisywana przez plik tymczasowy — po błędzie nie zostaje pusta.
  - Plik do pobrania budowany pod blokadą i przez plik tymczasowy. Sprawdzone: cztery
    równoległe pobrania — każde pełne.
- **C22 — błędy mówią prawdę:**
  - Własny wyjątek `JobNotFound` zamiast łapania każdego `LookupError`.
  - Nieprzewidziany błąd zwraca JSON z nazwą błędu, a ślad trafia do dziennika.
  - Numer strony spoza zakresu (`download`, `frames`, okno „Zapisz jako”) daje „Nie ma takiej
    strony”.
  - Plik bez stron jest odrzucany przy wgraniu.
  - Błąd propozycji produktu nie blokuje wgrania.
- **Bez regresji:**
  - Analiza pliku przykładowego (3 strony) i `spady.pdf` daje wynik identyczny ze starą wersją
    (porównanie pole po polu).
  - Self-test OK, samouczek i testy rozdziałów przechodzą.

## 0.5 — geometria strony, szablon, profil kolorów (przegląd kodu, część 3, 27.09)

Numery jak w `18_przeglad_kodu.md`.

- **A10 — strony obrócone (`/Rotate`) i z CropBoxem mniejszym od strony.**
  - **Problem:** MuPDF liczy stronę z obrotem i CropBoxem, a pikepdf, Ghostscript i nasze
    obliczenia — w surowym MediaBoxie. Skutki:
    - „Dopasuj wymiar” dawał pół białej strony;
    - spady przycinały się w poziomie zamiast w pionie;
    - szablon nie był znajdowany;
    - ocena jakości uznawała prawdziwy problem za „zakryty”;
    - podgląd był zniekształcony.
  - **Poprawka:** przy wgraniu `render.normalize_geometry` zamienia taką stronę na zwykłą:
    MediaBox od (0, 0) równy temu, co widać, bez `/Rotate`. Wygląd i wydruk się nie zmieniają.
    - Na początku treści strony jest `q <macierz> cm`, na końcu `Q`.
    - Wzory (pattern) z zasobów strony dostają kopię z przeliczoną macierzą — liczą się
      w domyślnej przestrzeni strony, nie w bieżącej macierzy.
    - Adnotacje dostają nowy `/Rect`, a ich wygląd obraca się razem ze stroną (poza `NoRotate`).
    - TrimBox, BleedBox i ArtBox są przeliczone.
    - Obrót dziedziczony po drzewie stron też jest obsłużony.
  - **Sprawdzone na 9 plikach testowych** (obroty 90/180/270, CropBox, przesunięty MediaBox
    z obrotem, obrót dziedziczony, wzór na obróconej stronie, stempel na obróconej stronie, strona
    zwykła): render MuPDF po zmianie jest identyczny piksel w piksel z oryginałem. Ghostscript
    różni się tylko wygładzaniem (średnio < 1/255).
  - **Wyniki na plikach z przeglądu:**
    - „Dopasuj wymiar” na obróconej stronie — identyczny z oryginałem.
    - Szablon na obróconej stronie znaleziony (wynik 1,0, jak na stronie zwykłej).
    - Spady na obróconej stronie przycinają się pionowo.
    - Ocena jakości: obraz 36 ppi na stronie obróconej i przyciętej wykryty jak na zwykłej.
  - **Zostaje:** UserUnit (strony większe niż 5 m zapisane w innej jednostce) — rzadkie, na razie
    bez zmian.
- **A12 — usuwanie szablonu nie kasuje już tekstu klienta.**
  - Napis blisko etykiety szablonu, o podobnej wielkości, jest usuwany tylko wtedy, gdy ma też
    podobną treść (≥ 60 %, bez ogonków i wielkości liter) albo jest nieczytelny.
    „Linia cięcia” ≈ „LINIA CIECIA”; stopka „www… tel.” zostaje.
  - Sprawdzone: 102 kombinacje prawdziwych plików i wytycznych — wykrywanie identyczne jak
    wcześniej.
- **A13 — „Dopasuj wymiar” zachowuje profil kolorów pliku (OutputIntent).**
  `steps._keep_doc_level` przenosi go do nowego pliku, w obu trybach marginesu. Sprawdzone: plik
  z profilem „ISO Coated v2” po dopasowaniu nadal go ma. Wcześniej był FOGRA39.
- Self-test OK, samouczek i testy rozdziałów przechodzą.

## 0.5.1 — jedna dokładność oceny, pływający panel podglądu (Tomasz 28.09)

- **Jedna dokładność oceny jakości — standardowa** (bloki 128 px, elementy od ok. 25 mm).
  - Wybór „wysoka” zniknął z Ustawień (`#setAcc`) i z samouczka.
  - `settings.detailBlock()` zawsze zwraca 128.
  - Część „Ustawienia” samouczka ma teraz 6 kroków: „ustawimy dwie rzeczy”.
- **Lupki, „Rzeczywista wielkość”, „Dopasuj” i nawigator tylko przy „Jakości wydruku”.**
  - **Pływający panel** (`#vTools`) nad podglądem, na środku.
    - Górny wiersz: lupki, „Rzeczywista wielkość”, „Dopasuj”.
    - Dolny wiersz: nawigacja po słabych miejscach (‹ opis › ×).
  - **Stały rozmiar:** 540 px szerokości, opis miejsca zawsze na dwie linie wysokości (dłuższy
    ucięty „…”, pełny w dymku). Sprawdzone: przy przeklikiwaniu trzech miejsc panel ma cały czas
    540 × 96 px.
  - **Kiedy widać panel:** „Jakość wydruku” jest ostatnim rozdziałem albo przeglądamy słabe
    miejsca (też z listy, gdy Akceptacja jest już widoczna).
  - **Poza tym** (`viewer.setZoomAllowed(false)`) podgląd jest zawsze dopasowany do okna. Lupka
    się wyłącza, a Z i Ctrl+kółko nic nie robią — Ctrl+kółko nie powiększa też strony programu.
- **Nawigator bez przycisku.** Pokazuje się sam przy „Jakości wydruku”, gdy podgląd jest
  powiększony. Zapamiętane „wyłączony” z poprzednich wersji już nie działa.
- **Teksty:**
  - Samouczek: „Słabe miejsca” wskazuje cały panel i wspomina lupki oraz nawigator.
  - Samouczek: „Przed i po” nie odsyła już do „Dopasuj” (Akceptacja sama dopasowuje podgląd).
  - Pomoc „?” w Jakości wspomina panel.
- Samouczek przechodzi od początku do końca.
- **Szybsza ocena jakości** (w tej samej wersji 0.5.1, Tomasz 28.09: „przyspieszyć wczytywanie
  jakości”).
  - **Start w tle zaraz po wyborze roli** (`quality.prefetch`, gdy znane są strona i skala). Zanim
    użytkownik przejdzie przez Szablon…Spłaszczenie, obrazy są zwykle policzone.
  - **Pamięć wyników obrazów** (`detailmap._img_cache`). Wynik obrazu zależy tylko od jego pikseli
    i bloku, więc poprawki przed oceną go nie zmieniają. Dwa klucze:
    - skrót surowych danych obrazu;
    - „rodowód” w zadaniu: strona, wymiar w px, blok i który z kolei obraz tego wymiaru. Po zamianie
      na CMYK, overprincie i krzywych Ghostscript zapisuje obrazy od nowa, więc skrót się zmienia.
  - **Bez podwójnego liczenia:** wpis „w toku” czeka na wynik, więc ocena z tła i ocena z rozdziału
    nie liczą tego samego obrazu dwa razy. Pamięć ma 96 obrazów, najstarsze wypadają.
  - **Zmierzone na `spady.pdf`:** ocena w tle 8,3 s; po spadach, wymiarze, CMYK i overprincie
    rozdział „Jakość” gotowy w 1,0 s (od zera 8,6 s), z identycznym wynikiem.
  - **Plik przykładowy, strona 3:** po zamianie na CMYK wynik różni się od liczonego od zera, bo
    konwersja kolorów zaciera ślady powiększenia. Obraz „10 / Sztucznie powiększony” (w pliku
    testowym powiększony 4×) od zera wychodził 2×, z pamięci — 4×. Wynik z oryginalnych pikseli
    jest wierniejszy.
  - W samouczku ocena rusza po „Rola pliku”, a rozdział „Jakość” dostaje gotowy wynik po jednym-dwóch
    zapytaniach.

## 0.5.2 — pełna jakość tylko przy „Jakości wydruku”, suwak spłaszczenia, błąd profilu (Tomasz 28.09)

- **Pasek „pełna jakość” przy suwakach przed/po.** To nie ocena jakości, tylko podgląd.
  - Dla każdej pokazywanej wersji (i każdej strony suwaka: przed, po, ekran, druk) program
    budował pełną piramidę kafelków do przybliżania (120 ppi wydruku).
  - Przybliżać można już tylko w „Jakości wydruku”, więc poza nią powstaje sam podgląd całej strony
    (`views.request(full=False)`: `ov.jpg`, dłuższy bok 2048 px, klucz `…_ov`). Pełna piramida
    powstaje dopiero w trybie „Jakość” (`viewer`: warstwa `F`/`O` w kluczu, `&full=1`).
  - Pasek „pełna jakość” pokazuje się tylko dla pełnej piramidy.
  - Podgląd całości i piramida tej samej wersji nie kasują się nawzajem — przy powrocie do „Jakości”
    kafelki są od razu.
  - Sprawdzone na `spady.pdf` (spady, wymiar, CMYK, overprint, fonty, spłaszczenie, wszystkie
    suwaki): pełna piramida policzona raz, dla wersji ocenianej w „Jakości”. Reszta to podglądy
    całości.
- **Suwak spłaszczenia znikał od razu.**
  - Scenariusz: „Spłaszcz projekt” → „Pokaż, jak wydrukuje”. Jakość (sam wektor) zalicza się
    sama, pojawia się Akceptacja, a Spłaszczenie się zwijało.
  - Przyczyna: przypięcie rozdziału (`S.pin`) puszczało, gdy pojawił się nowy rozdział.
  - Teraz przypięty rozdział zostaje rozwinięty, dopóki użytkownik SAM nie kliknie czegoś w treści
    innego rozdziału. Kliknięcie w nagłówek (rozwinięcie do obejrzenia) się nie liczy.
  - Sprawdzone: suwak spłaszczenia widoczny przez cały test. Po kliknięciu „Pokaż na podglądzie”
    w Jakości Spłaszczenie się zwija.
- **„Poprawka nie powiodła się: ForeignObjectError: copy_foreign called with direct object
  handle”** (plik 1878, „Dopasuj wymiar”).
  - Przyczyna: przenoszenie profilu kolorów (0.5, A13) nie obsługiwało `/OutputIntents` zapisanego
    bezpośrednio, a nie jako osobny obiekt.
  - Ten sam błąd był od dawna w pobieraniu jednej strony z pliku wielostronicowego.
  - Poprawione w obu miejscach. Sprawdzone na odtworzonym pliku: dopasowanie (oba tryby marginesu)
    i pobieranie działają, profil zostaje.

## 0.5.3 — widać, że podgląd się wczytuje (Tomasz 28.09)

- **Pytanie Tomasza: przy suwakach przed/po ładuje się pełna jakość czy tylko podgląd?** Tylko
  podgląd całej strony (`full=0`, `…_ov`) — pełna jakość wyłącznie przy „Jakości wydruku” (0.5.2).
- **Brakowało informacji, że podgląd się wczytuje** (od 0.5.2 pasek pokazywał tylko pełną
  jakość). Teraz w tym samym miejscu jest „wczytuję podgląd…” z ruchomym paskiem
  (`viewer.progress`, `.vprog.pulse`), a przy pełnej jakości — jak dotąd „pełna jakość NN %”.
- **Biała strona zamiast poprzedniego obrazu** przy przesuwaniu suwaka (plik 1878, overprint).
  - Nowa warstwa brała zastępczy obraz tylko z warstwy leżącej wcześniej na tym samym miejscu.
  - Teraz szuka najlepszego z dotychczasowych: ta sama wersja i symulacja, potem ta sama wersja,
    potem to, co leżało na tym miejscu, potem cokolwiek o tej samej stronie i proporcjach.
  - Sprawdzone na `spady.pdf` (suwak overprintu): od pierwszej chwili obie warstwy mają obraz,
    a „wczytuję podgląd…” widać, dopóki nie przyjdzie właściwy.
- **Przycisk trzeba było klikać dwa razy** (np. „Spłaszcz projekt”, gdy wyżej był przypięty
  Overprint z suwakiem).
  - Przyczyna (z 0.5.2): przypięcie puszczało już przy WCIŚNIĘCIU myszy. Przypięty rozdział się
    zwijał, przycisk podjeżdżał do góry i zwolnienie myszy trafiało obok.
  - Teraz puszcza po kliknięciu (zdarzenie `click`, faza bąbelkowania — najpierw działa przycisk).
  - Sprawdzone „ludzkim” kliknięciem (wciśnięcie, 0,35 s, puszczenie): jedno kliknięcie spłaszcza,
    a Overprint zwija się dopiero potem.

### 0.5.3 — ciąg dalszy: ocena jakości (propozycje 1–4), plik 1824, zmiana strony (Tomasz 28.09)

- **Plik 1824: „słaba jakość” w miejscu napisów** (6 miejsc ≈ 37 ppi na literach „na rynku
  deweloperskim”).
  - Przyczyna: obraz 46009 × 19322 px (889 Mpx) jest za duży dla MuPDF-a. Liczyliśmy go więc
    z renderu STRONY pasami, razem z tym, co leży nad obrazem. Napisy w krzywych nad gładkim
    gradientem wyglądały dla metryki jak powiększony fragment obrazu.
  - Sam obraz to czysty szary gradient (104 odcienie) — nie ma w nim czego zgłaszać.
  - Teraz ogromny obraz idzie przez osobny, jednostronicowy PDF z SAMYM obrazem
    (`detailmap._image_only_pdf`), bez maski i bez niczego nad nim, renderowany 1:1 pasami.
  - Przy okazji znika założenie, że obraz leży prosto (przegląd kodu, D: ścieżka ogromnego
    obrazu przy obrocie).
  - Wynik na 1824 (oryginał): 0 miejsc (wcześniej 2 na oryginale, 6 po dopasowaniu wymiaru).
- **Fragmenty obrazu nie trafiały dokładnie w swoje bloki.** Pasy szły po 512 wierszy, a blok
  bywa np. 160 px. Fragment lądował do 32 px obok i nadpisywał sąsiedni rząd bloków. Teraz pasy
  są cięte na granicach bloków (`detailmap._feed`).
- **Propozycja 1 — górna granica rozdzielczości analizy: 300 ppi na wydruku**
  (`ANALYSIS_CAP_PPI`).
  - Obraz gęstszy (np. 600 ppi, pliki 1:10) jest przed pomiarem zmniejszany do 300 ppi.
    Współczynniki są potem przeliczane z powrotem na natywne piksele (`_unscale`).
  - Czemu 300, a nie 240: przy 300 próg 120 ppi wypada dokładnie na stopniu 2,5, a próg
    wyjątków (≥ 3×) na 100 ppi — tak samo jak dotąd dla obrazów ≤ 300 ppi. Przy 240
    fragmenty 80–100 ppi mogłyby przejść niezauważone.
  - Obrazy ≤ 300 ppi liczą się dokładnie jak wcześniej.
  - Test (zdjęcie z adFrame_Smart, 600 ppi, wklejony fragment powiększony 6× = 100 ppi):
    wcześniej nie znaleziony, teraz znaleziony jako 100 ppi, w połowie czasu.
- **Propozycja 2 — pomiar na wersji przed zamianą kolorów** (`quality.version_for`, w
  przeglądarce `qualVersion`).
  - Oceniana jest ostatnia wersja po Szablonie, Spadach i Wymiarze. Położenie obrazów jest wtedy
    ostateczne, a piksele oryginalne.
  - Wynik dalej pokazuje się na końcu, w „Jakości wydruku”.
  - Zamiana na CMYK zmieniała piksele: obraz powiększony 4× wyglądał po niej na 2×.
- **Propozycja 3 — mocna kompresja JPEG.**
  - Jakość zapisu odczytywana z tablic kwantyzacji w nagłówku (bez dekodowania pikseli,
    `detailmap.jpeg_quality_tables`). Obsługuje też `[/ASCII85Decode /DCTDecode]` i pliki JPG.
  - Poniżej 50/100 — pozycja „mocna kompresja JPEG — obejrzyj”: do obejrzenia, nie pewna wada.
  - Pomiar na przykładowych plikach: eksport z InDesigna (1878) 91–93, spady/adFrame 99,
    przykładowy JPG 95. Plik testowy PRINT_CHECKER_TEST (str. 3) ma obraz ≈ 12 — teraz
    zgłoszony.
  - Grupy na liście: kompresja i „za mało pikseli” tego samego obrazu to dwie osobne pozycje.
- **Propozycja 4 — resztki z przeglądu kodu (D).**
  - 16-bitowe obrazy szare: `convert("L")` przycinał wartości > 255 (średnia jasność gradientu
    254 zamiast 127, detal znikał). Teraz skalowanie ÷ 257.
  - Raster: ppi na wydruku liczone z obu boków (słabszy wygrywa), wcześniej tylko z szerokości.
- **Spot w pliku 1878 (GOLD 2).** Program go wykrywał („kolory dodatkowe (GOLD 2)”). Dla
  jasności tekst mówi teraz „kolory **dodatkowe** (spot: GOLD 2)”.
- **Zmiana strony miniaturą psuła rozdziały** (widać było naraz „Stronę” i „Rolę pliku”). Rola
  pliku czeka teraz, aż strona zostanie znów wybrana („Wybierz tę stronę”).
- **Akceptacja: „przed poprawkami” ciemniejsze niż „po”** (strony.pdf). To nie błąd podglądu.
  - Na stronie leży półprzezroczysta (46 %) warstwa jaskrawej zieleni RGB (0,07 / 0,93 / 0) —
    poza zasięgiem CMYK.
  - Plik bez zamiany: drukarka miesza przezroczystość w RGB (tak mówi grupa przezroczystości
    strony) i dopiero wynik przelicza na CMYK. Zieleń zostaje mocna, pudełko wychodzi zielone,
    jak na ekranie.
  - Po zamianie: najpierw zieleń jest przycinana do zasięgu CMYK (dużo bledsza), potem mieszana.
    Całość wychodzi jaśniejsza, a pudełko zostaje złote.
  - Sprawdzone Ghostscriptem i MuPDF-em — oba renderują tak samo.

## 0.5.4 — rozdział „Symulacja wydruku”: od niego podgląd = wydruk (Tomasz 28.09)

- **Problem (Tomasz):** w Kolorach „przed” pokazywało plik jak na ekranie, a „po” — wydruk.
  Na ekranie kolory zawsze wyglądają lepiej, więc laik widział różnicę ekran–druk, a nie to,
  co zrobiła sama zamiana. Tak zginęła różnica z strony.pdf (półprzezroczysta zieleń RGB
  mieszana przed zamianą i po niej) — widać ją było dopiero w Akceptacji.
- **Nowy rozdział „Symulacja wydruku”** zaraz pod Wymiarem wydruku.
  - Od chwili, gdy go widać, podgląd pokazuje WYDRUK: kolory przeliczone jak w drukarni
    (FOGRA39) i overprint jak na maszynie (`main.printFlags`: `pr` = `op` = Wymiar domknięty;
    raster — bez overprintu).
  - Krótki tekst: na wydruku kolory są bledsze niż na ekranie i to normalne. Suwak
    „ekran ↔ druk” (`prSimBar`, `S.sim = "print"`).
  - Domknięcie przyciskiem **Rozumiem, dalej** (`S.settle.print`) — laik ma to przeczytać.
    Cofnięcie Szablonu, Spadów albo Wymiaru zdejmuje też to domknięcie (`steps.forgetFrom`).
- **Dalsze rozdziały porównują wydruk z wydrukiem.**
  - Kolory: „przed” = wydruk wersji sprzed zamiany, „po” = wydruk po zamianie (suwak
    `przed ↔ po`).
  - Overprint, Fonty, Spłaszczenie: tak samo — wydruk przed krokiem ↔ wydruk po nim.
  - W `main.scene` zniknęły wyjątki dla poszczególnych kroków (`CMP_WITH_OP`): obie strony
    suwaka mają te same flagi, więc widać tylko to, co zmieniła sama poprawka.
- **Bez „Pokaż, jak wydrukuje”** w Kolorach, Overprincie, Fontach i Spłaszczeniu — podgląd
  już jest wydrukiem. Zniknęły też suwaki „ekran ↔ druk” przy „Zostaw jak jest”.
  - „Zostaw jak jest” od razu domyka rozdział (`S.settle = "skip"`).
  - Poprawka domyka rozdział, gdy się nałoży (`state.settledByChoice` liczy `hasStep`).
- **Akceptacja bez zmian:** wydruk bez poprawek ↔ wydruk po wszystkich.
- Samouczek: nowy krok „Symulacja wydruku” (suwak + „Rozumiem, dalej”), krok „Wydruk przed
  i po” przy suwaku Kolorów; w Overprincie, Fontach i Spłaszczeniu jedno kliknięcie.
  Pomoc „?” — nowy wpis `print`, poprawione Kolory, Overprint, Fonty, Spłaszczenie
  (z uwagą o półprzezroczystości na jaskrawym RGB).
- Sprawdzone na strony.pdf (Playwright):
  - Symulacja wydruku: druk (stonowana zieleń) ↔ ekran (jaskrawa).
  - Kolory po zamianie: „przed” = zielone pudełko, „po” = złote — to ta różnica z Akceptacji,
    teraz widoczna od razu.
  - Kolory pojawiają się dopiero po „Rozumiem, dalej”; „Zostaw jak jest” w Spłaszczeniu
    zamyka rozdział jednym kliknięciem.

## 0.5.5 — przesunięcie w mm, czytelna skala przy wytycznych 1:10 (Tomasz 28.09)

- **Przesuń w poziomie / w pionie: pole na własną wartość.**
  - Obok suwaka pole w mm NA WYDRUKU od środka: plus = w prawo / w dół, minus = w lewo / w górę.
    Przecinek albo kropka, Enter kończy wpisywanie.
  - Wartość spoza zakresu (krawędź projektu dalej niż przeciwna krawędź formatu) przycina się
    do zakresu, jak przy suwaku.
  - Suwak z magnesem (środek, równo z krawędzią) działa jak dotąd. Opis obok pola mówi już
    tylko kierunek albo „środek” / „równo z … krawędzią” — liczba jest w polu.
- **„Skala projektu: 1:1” przy wytycznych 1:10 myliła** (laik czytał to jako „drukuję 1:1”).
  - Teraz „Przeskalowanie pliku: **bez zmian** (wytyczne w skali 1:10 — plik drukuje się 10×
    większy)”. Przyciski: ÷10 / bez zmian / ×10; podpowiedź przy złej skali mówi „po
    przeskalowaniu ×10” zamiast „w skali 10:1”.
  - Przy wytycznych 1:10 zdanie na górze rozdziału podaje najpierw wymiary NA WYDRUKU
    („Na wydruku plik ma 6160 × 2320 mm, a wytyczne wymagają 6000 × 2270 mm”), a wymiar
    pliku w nawiasie.
  - Opis pod suwakami („przycięte…”, „puste pasy…”) też w mm na wydruku — wcześniej w mm pliku.
- **Pasek wczytywania w pływającym panelu** (Tomasz 28.09).
  - „Pełna jakość NN %” jest teraz w panelu z lupkami, pod opisem miejsca („Miejsce 1 z 22…”),
    na całą szerokość panelu, większy (pasek 12 px, napis 14 px). Wcześniej był mały, na
    górnym pasku obok „Podgląd szablonu”.
  - „Wczytuję podgląd…” (suwaki przed/po, symulacja) pokazuje się w tym samym miejscu. Poza
    „Jakością” panel ma wtedy tylko pasek, bez lupek (`viewer.showTools` + `floatPanel`).
- Sprawdzone (Playwright, 1878, format 3030 × 2280): wpisane −12,5 i 999 mm → suwaki i opis
  się zgadzają. Wariantu 1:10 nie dało się odtworzyć w sandboksie (brak dostępu do wytycznych
  z sieci) — do sprawdzenia u Tomasza na adWall Vario Prosta 600.

## 0.5.6 — fałszywy „szablon wtopiony w obraz”, Akceptacja od „po” (Tomasz 29.09)

- **„Linie w kolorach wytycznych są wtopione w obraz” na pliku bez żadnego obrazu**
  (Wydruk Multiframe 250 SET3, „sam wektor”).
  - Przyczyna: `frames.in_pixels` szukał linii w kolorze wytycznych na renderze CAŁEJ strony.
    Cyjanowa kreska wektorowa pod napisem (ok. 64 % szerokości) mieściła się w tolerancji
    koloru i w progu „pół szerokości”.
  - Teraz liczą się tylko piksele wewnątrz obrazów (położenia z analizy oryginału,
    `server._image_boxes`). Strona bez obrazów — sprawdzenie od razu „nie”. Linia wektorowa
    w kolorze wytycznych to element projektu (prawdziwy wektorowy szablon i tak łapie
    `frames.find`).
  - Sprawdzone: odtworzona strona wektorowa z cyjanową kreską — wcześniej „wtopiony”, teraz nie.
    Obraz z wtopioną cyjanową linią przez całą szerokość — dalej wykryty.
- **Akceptacja: suwak startuje od „po”** — plik taki, jaki pójdzie do druku (wcześniej od
  „przed”).
- **Spłaszczenie „szarpie” krawędzie** (1815 / Multiframe CAD/CAM, Photoshop przy ~450 %).
  - Główna przyczyna: kompresja JPEG q90. Na ostrej krawędzi białego napisu na granacie
    dawała kwadraciki 8×8 i wcięcia wzdłuż krawędzi. Zmierzone na wycinku 1815, w pasie ±4 px
    wokół krawędzi: q90 — średnio 1,8/255, 99. percentyl 9, maks. 19; q98 — 0,4 / 2 / 4.
    Najpierw q98, a na prośbę Tomasza (chce bezstratnie; JPEG 100 też nie jest bezstratny —
    do 2/255) **zapis bezstratny ZIP (Flate) z predyktorem PNG „Sub”** (`_flatten_supersampled`
    pisze strumień pasmami, `step_flatten` wstawia go jako /FlateDecode, Predictor 15).
    Pomiary: 1815 (grafika wektorowa) — 9 MB (JPEG q90: 17 MB), 25 s; 1878 (zdjęcia,
    14268 × 10867 px) — 288 MB, 107 s w sandboksie. Poziom zlib 3 (`FLATTEN_ZLIB_LEVEL`).
  - Overprint przy spłaszczaniu liczy się tylko wtedy, gdy STRONA naprawdę go używa
    (`overprint_uses` z analizy). Wcześniej wystarczył nieużywany stan graficzny z /OP w pliku —
    wtedy przy dużej stronie gs wyłączał wygładzanie krawędzi (obejście błędu gs, `gs.aa_args`).
  - Gdy wygładzania gs naprawdę nie da się włączyć (overprint na dużej stronie), nadpróbkowanie
    4× zamiast 2× (16 próbek na piksel, jak AlphaBits=4); przy stronie ponad 4000 Mpx
    renderu — 3×.
  - Porównanie wycinka ukośnej krawędzi „/”: q98 wygląda jak render MuPDF-a z pliku
    wektorowego. Rozdzielczość zostaje (150 ppi przy wydruku 1,5–3 m), więc w dużym
    powiększeniu dalej widać piksele — ale równe, bez wcięć.

## 0.5.7 — spłaszczenie zawsze w 120 ppi (Tomasz 29.09)

- **„Poszarpane” krawędzie po spłaszczeniu — wyjaśnione.** Photoshop otwierał spłaszczony PDF
  w 120 ppi (okno „Import PDF”), a spłaszczenie było w 150 ppi. Przeskalowanie 1,25 : 1 robiło
  nierówne schodki. Oryginał wektorowy Photoshop rysował od zera w 120 ppi — stąd różnica. Samo
  spłaszczenie jest równe: ukośna krawędź „/” w 1815 odchyla się od prostej średnio o 0,009 px
  (MuPDF: 0,003). Kolory CMYK — co do wartości jak w pliku (Tomasz sprawdził w panelu Info).
- **Decyzja Tomasza: „wszystko drukujemy w 120 ppi — takie są ustalenia z drukarnią”.**
  Spłaszczenie zawsze w 120 ppi na wydruku (`steps.FLATTEN_PPI`, `flatten_ppi_for`; w przeglądarce
  `state.flattenPlan`). Wcześniej: 300 ppi do 80 cm, 200 do 1,5 m, 150 do 3 m, 120 wyżej.
  Obraz w innej rozdzielczości i tak był przeliczany do 120 ppi — w RIP-ie albo w Photoshopie.
- Pomoc „?” przy Spłaszczeniu: „zawsze 120 ppi na wydruku”.

- **Fonty nieosadzone — pytanie Tomasza: „co, gdy fontu nie ma na komputerze?”**
  - Liczy się font w PLIKU, nie na komputerze. Osadzony — kształty liter są w pliku. Nieosadzony —
    przy zamianie na krzywe / spłaszczeniu: tekst niewidoczny pomijany → Google Fonts → fonty
    systemu → odmowa z prośbą o PDF z osadzonymi fontami (krój zastępczy — nigdy).
  - **Nowe:** nieosadzonego, WIDOCZNEGO fontu nie da się zostawić — w rozdziale Fonty „Zostaw jak
    jest” jest nieaktywne, a notatka mówi dlaczego i co zrobić. Analiza strony ma nowe pole
    `fonts_missing` [{name, visible}] (`analyze._fonts_missing` → `fontfix.missing(path, page)`).
  - **Nowe:** nad podglądem ostrzeżenie „⚠ brak fontu X — litery w podglądzie zastępcze”
    (Ghostscript i MuPDF rysują wtedy litery zamiennikiem). Znika po zamianie na krzywe.
  - **Błąd:** `fontfix` działał na CAŁYM pliku, nie na stronie. Brak fontu na innej stronie
    blokował zamianę na krzywe (tekst niewidoczny tutaj, widoczny tam), a opis kroku wymieniał
    fonty z innych stron. Teraz `text_usage` / `missing` / `embed` przyjmują stronę
    (`steps._prepare_fonts(src, dst, page)`).
- **Plik testowy fontów** `przykladowe projekty/bledne/Test_fonty_adChecker.pdf` (7 stron
  1000 × 500 mm, na każdej opis oczekiwanego zachowania): 1 osadzony, 2 nieosadzony z Google Fonts
  (Roboto Bold), 3 nieosadzony z Windowsa (Arial Bold), 4 nieosadzony nigdzie (FooBar Pro),
  5 nieosadzony, ale niewidoczny (Tr 3), 6 Helvetica (standardowy PDF), 7 wszystko naraz,
  8 nieosadzony font Identity-H (CID, typowy dla Worda / PowerPointa / Canvy) z Google Fonts
  (Lora Italic), 9 nieosadzony Identity-H, którego nie ma nigdzie (FooBar Sans).
  - Tomasz 29.09: w Photoshopie widać było wszystkie fonty ze stron 1–7 — Adobe podstawia
    nieosadzonym fontom prostym (TrueType/Type1 z szerokościami) swój krój Adobe Sans MM, a Arial /
    Roboto bierze z systemu. Strony 8–9 to przypadek, którego Photoshop nie umie pokazać (same
    numery znaków, bez kształtów — kropki albo nic). Str. 8 po zamianie na krzywe: prawdziwa Lora
    Italic; str. 9: odmowa.
  - Sprawdzone w sandboksie (zamiana na krzywe): 1, 2, 5, 6 — udane; 4 i 7 — odmowa (FooBar Pro);
    3 — odmowa tylko dlatego, że sandbox nie ma Ariala (na Windowsie / Macu jest).
  - Interfejs (Playwright, str. 2): ostrzeżenie nad podglądem, „Zostaw jak jest” nieaktywne.

## 0.5.8 — zamiana kolorów nie utrwala już krojów zastępczych (Tomasz 29.09)

- **Błąd znaleziony na pliku testowym fontów (jedna strona 1000 × 2000 mm).** Po „Zamień na CMYK”
  ostrzeżenie o brakujących fontach znikało, „Zostaw jak jest” w Fontach wracało, a „Zamień na
  krzywe” się udawało — z krzaczkami w przypadkach 7 i 8.
  - Przyczyna: zamiana kolorów to Ghostscript (pdfwrite), który przepisuje stronę i brakujący font
    OSADZA — swoim zamiennikiem. Dla fontu Identity-H (same numery znaków) zamiennik rysuje zupełnie
    inne znaki. Od tej chwili plik „miał” font, więc dalsze sprawdzenia nic nie widziały.
  - Teraz `step_cmyk` najpierw szuka prawdziwego fontu (Google Fonts — `_prepare_fonts`, potem
    fonty systemu — `-sFONTPATH`). Gdy Ghostscript i tak sięga po zamiennik (`gs.substituted`),
    zamiana idzie drugi raz z `NeverEmbed` dla tych fontów: kolory są zamienione, a brakujące fonty
    ZOSTAJĄ nieosadzone (jak w oryginale) — program dalej o nich wie i ostrzega. Opis kroku:
    „UWAGA: brak fontu … — zostaje nieosadzony, drukarnia podstawi swój krój”.
    (`_gs_page(..., pre=[...])` — parametry pdfwrite wstawiane tuż przed plikiem.)
  - **Decyzja Tomasza: „wolałbym, żeby dało się przejść dalej i to wydrukować, po prostu info”.**
    „Zostaw jak jest” w Fontach znów aktywne; przy braku fontu notatka mówi, co się stanie
    (drukarnia podstawi krój, przy tekście z Worda / Canvy nawet krzaczki), a po wyborze rozdział
    pokazuje ostrzeżenie. W „Pobierz plik do druku” — pozycja „Brak fontu w pliku: … — drukarnia
    podstawi swój krój”. Ostrzeżenie nad podglądem — jak dotąd.
  - Zamiana na krzywe i spłaszczenie przy brakującym foncie dalej odmawiają (utrwaliłyby krój
    zastępczy na stałe); komunikat dopowiada, że można wybrać „Zostaw jak jest” i iść dalej.
  - Sprawdzone: strona 1000 × 2000 — kolory zamienione; Roboto i Lora osadzone prawdziwe
    (Google Fonts), FooBar Pro, FooBar Sans (i w sandboksie Arial) zostały nieosadzone, analiza
    dalej je zgłasza; krzywe — odmowa z podpowiedzią „Zostaw jak jest”.
- **Dlaczego przypadki 7 i 8 wyglądały inaczej w Wymiarze i po Symulacji wydruku.** Do Symulacji
  podgląd rysuje MuPDF (ekran), potem Ghostscript (druk). Font Identity-H bez osadzenia ma w pliku
  tylko numery znaków. MuPDF odczytuje z ToUnicode, jakie to litery, i rysuje je swoim zapasowym
  krojem — tekst da się przeczytać. Ghostscript bierze numery wprost do kroju zastępczego —
  wychodzą krzaczki (tak jak w Photoshopie kropki). Żaden z nich nie pokazuje prawdziwego fontu —
  dlatego ostrzeżenie nad podglądem.

## 0.5.9 — krzywe i spłaszczenie mimo brakującego fontu, z ostrzeżeniem na podglądzie (Tomasz 29.09)

- **Decyzja Tomasza: „chciałbym, aby fonty dało się zamienić na krzywe — niech zostanie ostrzeżenie
  o tych, co się zmienią w artefakty, i żeby to było widoczne na podglądzie. To samo przy
  spłaszczeniu”.** Zmienia to, co było w 0.5.8 (tam krzywe i spłaszczenie odmawiały).
  - `step_outline` i `step_flatten` nie odmawiają już przy brakującym foncie. Kolejność szukania
    jak dotąd: font z pliku → Google Fonts → fonty systemu. Dopiero gdy nigdzie go nie ma,
    Ghostscript bierze krój zastępczy. Krok zwraca wtedy `fonts_subst`: [{name, boxes}], a opis
    dostaje „UWAGA: … te litery mają kształt kroju zastępczego”. Wynik trafia do wersji
    (`jobs.Version.to_json`), bo w pliku po zamianie fontu już nie ma i analiza nic by nie widziała.
    Usunięte: `_font_refusal`.
  - `analyze.font_boxes(path, page, names)` — gdzie na stronie stoi tekst danym fontem: jedna ramka
    na wiersz, w ułamkach strony (PyMuPDF `get_text("dict")`, tekst niewidoczny pominięty).
    `fonts_missing` z analizy ma teraz też `boxes`.
  - `state.fontWarnings()` łączy oba źródła: fonty utrwalone krojem zastępczym (z kroków,
    `baked`) i fonty, których dalej brakuje (analiza ostatniej wersji).
  - **Podgląd:** każde takie miejsce ma przerywaną pomarańczową ramkę z etykietą „⚠ <font> — krój
    zastępczy” (`scene.marks`, warstwa `.fmarks` w `viewer.js`). Widać je od razu po wczytaniu —
    przed decyzją, po „Zostaw jak jest”, po krzywych i po spłaszczeniu.
  - **Fonty:** notatka przed wyborem mówi, że zamiana się uda, ale czego program nie znajdzie,
    wyjdzie krojem zastępczym. Po zamianie z brakami: pomarańczowy komunikat „Tekst zamieniony na
    krzywe, ale fontów … nie było w pliku ani w sieci — te litery wyszły krojem zastępczym albo
    zniknęły (pomarańczowe ramki na podglądzie). Najlepiej poproś klienta o PDF z osadzonymi
    fontami”.
  - **Spłaszczenie:** przed spłaszczeniem ostrzeżenie o brakujących fontach (poszuka w Google Fonts
    i w systemie, czego nie znajdzie — zostanie na stałe krojem zastępczym); po spłaszczeniu —
    pomarańczowy komunikat jak w Fontach.
  - **Pobierz plik do druku:** osobne pozycje „Brak fontu w pliku” (drukarnia podstawi krój)
    i „Krój zastępczy utrwalony (krzywe / spłaszczenie)”.
  - Pomoc (?) w Fontach i Spłaszczeniu opisuje nowe zachowanie; komentarze w `fontfix.py`,
    `gs.py`, `steps.py` poprawione.
- Sprawdzone w sandboksie na stronie 1000 × 2000 (`Test_fonty_1strona_1000x2000.pdf`):
  - krzywe i spłaszczenie udane; Roboto i Lora pobrane i osadzone prawdziwe;
  - FooBar Pro, FooBar Sans (i w sandboksie Arial) zgłoszone w `fonts_subst` z ramkami;
  - Playwright: ramki na podglądzie przy przypadkach 3, 4 i 8; komunikaty w Fontach
    i Spłaszczeniu jak wyżej.
  - Przypadek 8 (Identity-H bez fontu) po krzywych jest pusty — litery znikają. Dlatego komunikat
    mówi „albo zniknęły”, a ramka zostaje w tym miejscu.
- **„Usuń szablon” zostawiał napisy ze środka** (Tomasz 29.09, `adFrame_Smart_100x250_ramki_w3.pdf`):
  po usunięciu ramek zostawało „1 / 1015 x 2513 [mm] / Wydruk adFrame Smart 100x250”.
  - Przyczyna: napis jest w foncie Identity-H (SegoeUI, dwubajtowe numery znaków). `frames.py`
    czytał bajty jak zwykły tekst (latin1) i wychodziły śmieci, więc napis nie przypominał napisu
    z szablonu i nie trafiał na listę do usunięcia.
  - Teraz `_Walker.decoder` czyta tekst przez ToUnicode fontu (ten sam parser co `fontfix`).
    Obsługuje fonty dwubajtowe (Type0) i znaki „symboliczne” U+F020–F0FF („” = „1”).
    Font dwubajtowy bez ToUnicode = tekst nieczytelny, więc liczy się tylko położenie i wielkość
    (tak, jak opisuje `_text_like`).
  - Sprawdzone: napis odczytany jako „11015 x 2513 [mm]Wydruk adFrame Smart 100x250”
    (w szablonie „…Print adFrame…” — podobieństwo wystarcza), usunięte 2 ramki + napis, na
    stronie nie zostaje żaden tekst.
- **Przypadki brzegowe (Tomasz 29.09: „warto wszystkie te punkty zrobić”)** — pierwsza piątka:
  - **Ukryte warstwy (OCG) i adnotacje** — nowy `prepare.py`, `bake_print_state` przy wgraniu
    (po `normalize_geometry`).
    - Stan do druku: /D (BaseState, ON, OFF) + `/Usage /Print /PrintState`; OCMD (AnyOn, AllOn,
      AnyOff, AllOff).
    - Treść niedrukowanych warstw jest wycinana: `BDC /OC … EMC`, `Do` z /OC, także w formach.
      Znaczniki drukowanych warstw zamieniane na `/OC BMC`, `/OCProperties` usunięte.
    - Adnotacje z flagą „Print” (i nie „Hidden”) — ich wygląd /AP /N wpisany w treść strony
      (macierz jak `analyze._annot_ctm`). Pozostałe usunięte razem z /Popup i /AcroForm; linki zostają.
    - Powód: RIP-y różnie traktują warstwy i adnotacje (starsze drukują wszystko), a MuPDF rysuje
      wszystkie adnotacje. Teraz podgląd = wydruk, a analiza nie liczy tego, co się nie drukuje.
      To domyka „Ukryte warstwy” z przeglądu kodu i A7.
  - **UserUnit** (strony ponad 200 cali, np. z Illustratora) — `normalize_geometry` wpisuje go
    w treść: MediaBox × U, `cm` z U, bez /UserUnit.
    - MuPDF i Ghostscript go uwzględniały, a pikepdf i nasze obliczenia nie — wymiar wychodził
      U razy za mały.
    - Przy pobieraniu strona ponad 14 400 pt dostaje UserUnit z powrotem
      (`prepare.with_user_unit`, najmniejsza całkowita jednostka).
  - **PDF z hasłem / uszkodzony** — `prepare.check_open`, przed wszystkim innym. Jasne komunikaty
    (błąd 415):
    - hasło do otwarcia;
    - plik pusty albo niepełny;
    - „to nie jest PDF” (brak nagłówka);
    - PDF zniszczony.
    Hasło tylko do uprawnień jest zdejmowane. Plik naprawiony przez qpdf (ostrzeżenia) daje
    notatkę „obejrzyj dokładnie podgląd”.
  - **Rozdział Plik:** nowa ramka „Przygotowane przy wczytaniu” (`#filePrep`, `info.prepared`)
    — lista zmian: warstwy, adnotacje, hasło, UserUnit, naprawa.
  - **Biel z overprintem** — `analyze.py` śledzi stan overprintu (/OP, /op, /OPM, dziedziczony
    przez formy), kolor wypełnienia i obrysu oraz obrys ścieżki i napisu.
    - Biel, która znika: szarość 1; RGB 1/1/1 (znika po zamianie na CMYK); CMYK 0/0/0/0 przy OPM 1.
      Kolor dodatkowy „White” nie jest liczony — jest celowy.
    - Wynik: `white_overprint` = ramki (ułamki strony).
    - Overprint: ostrzeżenie „biel z overprintem (N miejsc) w druku zniknie” przed decyzją
      i po „Zostaw jak jest”; pomarańczowe ramki na podglądzie znikają po „Wyłącz overprint”.
  - **Za dużo farby (TAC)** — nowy `ink.py` i `/api/jobs/<id>/ink`: render CMYK FOGRA39 z symulacją
    overprintu (1500 px), suma C+M+Y+K, limit 330 % (limit profilu).
    - Czerń RGB po zamianie daje ok. 316 %, więc nie ma fałszywych alarmów.
    - Skupiska ponad limit → czerwone ramki „farba 400 %”.
    - Kolory: ramka „Za dużo farby…” (przy ≥ 390 % podpowiada czerń 4 × 100 % albo „Registration”).
    - Tylko informacja — poprawić musi grafik albo klient.
    - Liczone od Symulacji wydruku, dla ostatniej wersji (`S.ink`, `inkNow()`).
  - **Wspólne:**
    - `state.printRisks()` zbiera ramki bieli z overprintem i farby do podglądu (`.fmarks`,
      czerwone: klasa `red`).
    - W „Pobierz plik do druku” są nowe pozycje: biel z overprintem, za dużo farby.
    - Pomoc (?) w rozdziałach Plik, Overprint i Kolory uzupełniona.
  - **Sprawdzone:**
    - Testy na sztucznych plikach: warstwy (ukryta, „nie drukuj”, widoczna); stempel, pole
      tekstowe, komentarz; UserUnit 10 (render przed i po identyczny, po pobraniu UserUnit 2 i ten
      sam wygląd); hasło do otwarcia, hasło do uprawnień, obcięty plik, śmieci, „nie PDF”; biel
      CMYK, szara i bez overprintu; TAC: czerń RGB 316 %, 4 × 100 % i Registration = 400 %.
    - Playwright na `Test_edge_1strona_1000x1500.pdf`: ramka w rozdziale Plik, ostrzeżenie
      o farbie w Kolorach, ostrzeżenie o bieli w Overprincie, 4 ramki na podglądzie; po „Wyłącz
      overprint” zostają 2 (farba). Bez błędów JS.
  - **Pliki testowe** (`przykladowe projekty/bledne/edge/`):
    - `Test_edge_1strona_1000x1500.pdf` (warstwy, adnotacje, biel z overprintem, farba);
    - `Test_edge_UserUnit_7000x1760.pdf`;
    - `Test_edge_haslo_do_otwarcia_abc.pdf`;
    - `Test_edge_haslo_uprawnien.pdf`;
    - `Test_edge_uszkodzony_naprawialny.pdf`;
    - `Test_edge_nie_pdf.pdf`.
- **„Różnice po spłaszczeniu” w `adFrame_Smart_100x250_1.pdf`** (Tomasz 29.09, zrzuty z Photoshopa):
  - Oryginał to JEDEN obraz CMYK JPEG 4795 × 11872 px, dokładnie 120 ppi, bez żadnego wektora.
  - Spłaszczenie odtwarza go 1:1 — porównane wszystkie 56,9 mln pikseli z dekodowanym JPEG-iem:
    różnica 0.
  - Różnica widoczna w Photoshopie wynika więc z tego, jak Photoshop otwiera (rasteryzuje) każdy
    z PDF-ów, a nie z danych do druku.

## 0.6.0 — po kolei z listy „co jeszcze do zrobienia” (Tomasz 29.09: „leć dalej po kolei”)

- **C28 — klawiatura:**
  - Okno pytania (`util.ask`): Enter i spacja działają na zaznaczony przycisk. Dawniej Enter zawsze
    potwierdzał, nawet przy zaznaczonym „Zostaw” — można było tak stracić poprawki. Tab krąży
    między dwoma przyciskami, Escape = „Zostaw”.
  - Spacja na przycisku, linku, nagłówku rozdziału i w oknie pytania klika, a nie przełącza
    przesuwania podglądu (`viewer.js`).
  - Nagłówek rozdziału ma fokus (Tab) i rozwija się / zwija Enterem albo spacją; widoczna
    obwódka fokusu.
  - Sprawdzone (Playwright): Enter → Tak, Tab+Enter → Zostaw, Tab+spacja → Zostaw, Escape →
    Zostaw, Enter na nagłówku rozwija rozdział.
- **C20 — Ghostscript po zamknięciu okna:** każdy proces Ghostscripta trafia do rejestru
  (`gs._track`), a przed `os._exit` `desktop._shutdown` zabija je (`gs.kill_all`) i procesy oceny
  jakości. Na Windowsie procesy są też w „zadaniu” systemu (Job Object, KILL_ON_JOB_CLOSE) —
  Windows zabija je sam, nawet gdy program padnie. `gs.run` przepisane na Popen (rejestr).
  Sprawdzone: render w toku → `kill_all` → proces zakończony.
- **C19 — jeden program naraz:** decyduje blokada pliku `adchecker.lock` w folderze użytkownika
  (`instance.py`: `msvcrt.locking` / `fcntl.flock`, system zdejmuje ją sam po zakończeniu procesu),
  a nie odpowiedź serwera w 1,5 s.
  - Drugie uruchomienie otwiera działający program (port z `adchecker.port`) i niczego nie czyści.
  - `python server.py` (run.bat) odmawia startu, gdy inny działa.
  - Sprawdzone: drugi `server.py` → „już działa w innym oknie”, `work/` nietknięte.
- **B18 (część):**
  - Odinstalowanie usuwa `%LOCALAPPDATA%\adChecker` — pliki klientów z ostatniej sesji, pobrane
    fonty i wytyczne, pamięć okna, dziennik (`adchecker.iss`, [UninstallDelete]). Aktualizacja nie
    odinstalowuje, więc ustawienia przy aktualizacji zostają.
  - `.gitignore`: `app/webview/`, `app/adchecker.lock`, `.port`, `.log*`.
- **Cienkie linie i obszar bezpieczny** (rozdział Jakość wydruku, ramka `#quRisk`):
  - `analyze.py` zbiera kreski cieńsze niż 0,25 mm w pliku (grubość × skala macierzy; „hairline”
    0 zawsze) — `thin_lines`. Kreski w kolorach linii wytycznych są pomijane. Interfejs liczy
    grubość na wydruku (× skala 1:10) i ostrzega poniżej 0,25 mm (`THIN_PRINT_MM`).
  - Obszar bezpieczny: `guidelines.parse_template_page` zapisuje czerwone ramki (`safe_mm`,
    PARSER_VERSION 5 — wytyczne parsują się na nowo). `analyze._text_boxes` daje wiersze
    widocznego tekstu. `state.layoutRisks` sprawdza, czy każdy wiersz leży w obszarze bezpiecznym
    (szablon na środku strony, jak na podglądzie). Liczone na wersji z ostateczną geometrią
    (po Wymiarze, przed krzywymi i spłaszczeniem) — `geoVersion`, `loadGeoFacts`.
  - Ramki na podglądzie („linia 0,10 mm”, „poza obszarem bezpiecznym”) i pozycje w „Pobierz”.
    Tylko informacja — poprawia się w Wymiarze albo u klienta.
  - Sprawdzone (Playwright, `Test_edge_linie_i_krawedz_adFrame_Smart_100x250.pdf`): 2 cienkie
    linie (0,1 mm i hairline; 1 mm i 0,3 mm bez ostrzeżenia), 2 wiersze poza obszarem
    bezpiecznym (15 mm od lewej, 20 mm od dołu), wiersze w środku bez ostrzeżenia.
- **B16 — podpis aktualizacji:**
  - `ed25519.py`: Ed25519 w czystym Pythonie, bez nowych bibliotek; zgodny z wektorem RFC 8032
    i z biblioteką `cryptography`; weryfikacja ok. 5 ms.
  - GitHub (`build.yml`) podpisuje SHA256SUMS.txt sekretem `ADCHECKER_SIGN_KEY` →
    `SHA256SUMS.txt.sig`.
  - Program z kluczem publicznym (`app/update_key.py`) instaluje tylko wydanie z poprawnym
    podpisem. Klucz pusty = jak dotąd (tylko SHA-256).
  - Zabezpieczenie przed zablokowaniem aktualizacji: gdy program ma klucz, a GitHub nie ma
    sekretu (albo sekret nie pasuje) — wydanie się przerywa.
  - Klucz tworzy Tomasz sam: `py packaging\klucz_aktualizacji.py` (klucz prywatny tylko na
    ekranie → sekret na GitHubie + menedżer haseł). Na razie klucz jest PUSTY — podpis zadziała
    od wersji, w której Tomasz go wpisze.
  - Sprawdzone: podpis poprawny → przechodzi; podmieniony plik sum → „podpis się nie zgadza”;
    brak podpisu → „nie jest podpisane”.
- **B17 / C24 (część):**
  - `build.yml`: domyślnie `contents: read`, zapis tylko w zadaniu „wydanie”;
    `persist-credentials: false`.
  - `concurrency` — dwa szybkie wypchnięcia czekają na siebie.
  - Numer wersji z literami przerywa wydanie.
  - Cicha instalacja aktualizacji pisze dziennik: `%LOCALAPPDATA%\adChecker\instalacja.log`
    (`/LOG`).
  - Zostaje: sumy kontrolne Ghostscripta i zależności, wersja Inno Setup.
- **Rozdział Plik bez listy „Przygotowane przy wczytaniu”** (Tomasz 29.09: „ten tekst w rozdziale 1
  jest niepotrzebny”). Warstwy, adnotacje, hasło do uprawnień i UserUnit program ustawia po cichu
  (opis jest pod „?”). Zostaje tylko ostrzeżenie o pliku uszkodzonym i naprawionym przy otwarciu —
  wtedy trzeba obejrzeć podgląd. `info.prepared` z serwera zostaje (do dziennika i na przyszłość).
- **Ramki na podglądzie tylko w swoim rozdziale** (Tomasz 29.09: „ramki informacyjne powinny się
  pojawiać tylko w danej kategorii … po przejściu do kolejnego rozdziału powinny znikać, a jak wracam
  do danego rozdziału, mogą się znowu pojawiać”).
  - `state.riskMarks(rozdział)`: fonty → Fonty i Spłaszczenie; biel z overprintem → Overprint;
    za dużo farby → Kolory; cienkie linie i obszar bezpieczny → Jakość wydruku.
  - `main.currentChapter()`: rozdział ręcznie rozwinięty nagłówkiem (`S.viewCh`, myszą albo
    klawiaturą), przypięty (`S.pin`) albo ostatni widoczny. Nowy rozdział na końcu zeruje `S.viewCh`.
  - Biel z overprintem: „może zniknąć” zamiast „zniknie”. Biel CMYK 0/0/0/0 znika na podglądzie;
    biel w skali szarości Ghostscript drukuje, choć część RIP-ów kładzie ją tylko na kanał K —
    pewne jest tylko „Wyłącz overprint”.
  - Sprawdzone (Playwright): Kolory → „farba 400 %”, Overprint → tylko biel, Fonty → nic,
    rozwinięcie Kolorów nagłówkiem → znowu farba, zwinięcie → nic.

## 0.6.1 — poprawa czerni w Kolorach, biel z overprintem tylko CMYK (Tomasz 29.09)

- **Biel z overprintem — tylko CMYK 0/0/0/0** (Tomasz 29.09: w Acrobacie, Podgląd wyjściowy
  z symulacją nadruku, biel w skali szarości z overprintem NIE znika — tak samo jak u nas).
  `analyze._white` liczy już tylko CMYK 0/0/0/0 przy OPM 1. Biel RGB po zamianie na CMYK staje się
  0/0/0/0 i wtedy wyłapie ją analiza nowej wersji. Plik testowy ma poprawione opisy.
- **„Popraw czerń” w rozdziale Kolory** (Tomasz 29.09: „niech się pojawi taki button, gdy jest to
  zalecane … czerń C78 M85 Y90 K100 … tylko gdy warstwa ma jednolity kolor czarny, jak plik jest
  rastrowy, to nie poprawimy”).
  - Nowa poprawka `black` (steps.ORDER: … cmyk, black, overprint …), `steps.step_black` /
    `_fix_black`. W treści strony i form podmienia jednolite czernie z za dużą ilością farby na
    C78 M85 Y90 K100:
    - `k` / `K` i `sc` / `scn` w CMYK (urządzenia albo ICC z 4 kanałami), gdy suma > 360 % i K ≥ 85 %;
    - kolor „Registration” (separacja /All): `cs` → DeviceCMYK, odcień t → t × zalecana czerń.
  - Obrazów i przejść tonalnych nie rusza.
  - `analyze.heavy_black` — ile takich pól, napisów i linii jest na stronie. Przycisk pokazuje się,
    gdy suma farb przekracza limit (`ink.py`), jest co poprawić, decyzja o kolorach już zapadła
    i nie ma późniejszych poprawek. Po poprawie: „Czerń poprawiona …” + „Cofnij poprawę czerni”.
    Gdy nadmiar farby zostaje (obraz) — informacja, że tego program nie poprawi.
  - `ink.TAC_LIMIT` 330 → **360 %**, żeby zalecana czerń (353 %) nie dawała ostrzeżenia. Czerń
    z RGB po zamianie ma ok. 316 %.
  - Sprawdzone: plik testowy (czerń 4 × 100 % i „Registration”) → 2 miejsca poprawione, suma farb
    400 % → 353 %, bez ostrzeżenia. Czerń 60/50/50/100 nietknięta. Playwright: przycisk
    dopiero po wyborze w rzędzie Kolory, po poprawie ramki znikają, błędów JS brak.
