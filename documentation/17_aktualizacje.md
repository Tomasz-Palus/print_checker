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
