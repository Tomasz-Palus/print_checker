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
