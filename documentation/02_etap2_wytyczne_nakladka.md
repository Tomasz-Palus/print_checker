# Etap 2 — wytyczne produktu i nakładka szablonu na podgląd

Data: 2026-09-03. Kontynuacja po etapie 1 (`01_etap1_upload_produkt_podglad.md`).

## Ustalenia z tej sesji (Tomasz)

- PDF wytycznych: **strona 1 = opis** (jak przygotować plik), zawsze ze skalą
  **1:1 albo 1:10** — innych wariantów nie ma i nie będzie.
- **Strony 2+ = szablony**, jeden lub kilka zależnie od produktu; każdy ma
  napisaną **rolę pliku** (np. „Dach 1”, „Przod”, „Wrota”). Użytkownik musi móc
  wybrać, którą rolę ma sprawdzany wydruk.
- Linie szablonu mają się pokazywać na podglądzie i mieć **przycisk włącz/wyłącz**.

## Jak zbudowane są PDF-y wytycznych (sprawdzone na 4 przykładach)

| | |
|---|---|
| Strona 1 | A4 (595×842 pt). Cały tekst jest **w krzywych** — brak warstwy tekstowej. 8 obrazków: 7 małych ikon w lewej kolumnie (DPI, PDF, drukarka, …) + zdjęcie produktu. Wiersz z ikoną DPI: „Rozdzielczość: 120 ppi - skala 1:1” lub „Rozdzielczość: 1200 ppi - skala 1:10”. |
| Strony 2+ | Rozmiar strony w pt = dokładnie wymiar z tekstu „W x H [mm]” (1 mm = 72/25,4 pt), np. 369×236 mm → 1046×669 pt. **Tekst jest normalny** (SegoeUI): rola (bold, największy), wymiar, nazwa produktu. Znak `\x01` w tekście = glif spoza mapy fontu (Ø, ś) — usuwamy. |
| Rysunki | niebieski (≈ rgb 0, .68, .94) = kształt produktu; czerwony (≈ .93, .19, .18) = obszar ochronny; żółty (≈ .94, .91, .13) = obszar technologiczny (szycie/tunele). **„Linie” to najczęściej wypełnione cienkie pierścienie** (obrys zamieniony na fill, dwie zagnieżdżone ścieżki o przeciwnych kierunkach), czasem prawdziwy stroke 2 pt (1:10) / 20 pt (1:1). Trybunka ma inne odcienie (.89,.02,.07 i 0,.62,.87) — klasyfikacja po zakresach, nie po dokładnym kolorze. |

## Rozpoznawanie skali (bez OCR)

Tekst str. 1 jest w krzywych, więc mierzymy geometrię: w wierszu ikony DPI są
dwie grupy ścieżek — „Rozdzielczość:” i wartość. Szerokość grupy z wartością:
**91,9 pt → „120 ppi - skala 1:1”, 107,0 pt → „1200 ppi - skala 1:10”** (o dwa
znaki „0” więcej). Próg: 100 pt. Wynik zapisujemy z metodą i zmierzoną
szerokością (`scale_detect`), a w UI skala jest w liście rozwijanej, więc gdy
kiedyś układ strony 1 się zmieni, można ją poprawić ręcznie.

Kontrola krzyżowa na przykładach: adTent 3x3 (2358×1465 mm) → 1:1, adTent 5x5
(369×236 mm) → 1:10, Trybunka (2650×1034 mm) → 1:1, adWall 600 (600×227 mm) → 1:10.
Zgadza się z rozmiarami.

## Co zrobiono (app/)

- `guidelines.py` — pobranie PDF-a po hashu (`/file/requirements?...`),
  cache `data/guidelines/<hash>.pdf` + `<hash>.json` (z `parser_version`, więc
  zmiana parsera unieważnia stare JSON-y). Parser: skala (jw.), szablony
  (rola/wymiar/nazwa z tekstu; SVG z `page.get_drawings()` z zachowaniem
  fill/stroke, kierunku prostokątów i reguły wypełnienia — dzięki temu SVG
  wygląda dokładnie jak PDF, bez tekstu). Każda ścieżka ma `class`
  safe/shape/tech/other.
  **Zmiana 2026-09-04 (patrz 06):** przy potwierdzeniu produktu UI woła `?fresh=1`
  — PDF jest ZAWSZE pobierany ze strony; cache służy tylko awaryjnie (brak sieci)
  i jest wtedy wyraźnie oznaczony w UI jako kopia lokalna.
- `server.py` — `GET /api/guidelines/<hash>` (`?fresh=1` zawsze aktualne, `?refresh=1` wymusza),
  `POST /api/guidelines/upload` (własny PDF wytycznych, np. do wydruku
  niestandardowego lub gdy nie ma sieci).
- UI (lewy panel, sekcja „Wytyczne”): lista **Szablon / rola pliku**
  („rola — W×H mm”; przy powtarzających się rolach dopisany numer strony),
  **Skala wytycznych** (rozpoznana, do zmiany ręcznej) i przycisk **Otwórz PDF
  wytycznych**. Rola jest **podpowiadana z nazwy pliku** (tokeny:
  przod/tyl/dach/nogi/wrota/owijka/…).

  **Uproszczenie 2026-09-08 (Tomasz).** Z panelu wypadły dwie rzeczy:
  opis szablonu pod listą („szablon 600 × 227 mm (skala 1:10 → 6000 × 2270 mm
  na wydruku)” + nazwa produktu) i potwierdzenie **„✓ aktualne — pobrano ze
  strony <data>”**. Pierwsze było trzecim powtórzeniem tej samej liczby (jest
  w pozycji listy, w pasku nad podglądem i w panelu wymiaru); drugie nie niosło
  informacji, bo wytyczne pobieramy przy każdym wyborze produktu, więc świeże
  są **zawsze**. Ostrzeżenie o **kopii lokalnej** zostaje — ono pojawia się tylko
  wtedy, gdy coś poszło nie tak, i wtedy trzeba je przeczytać. Zasada: komunikat,
  który zawsze mówi to samo, przestaje być czytany; zostawiamy tylko ten, który
  informuje o odstępstwie. Link do PDF-a wygląda teraz jak zwykły przycisk —
  odnośnik w tekście ginął pod listami.
- UI (podgląd): przycisk **Szablon** (wł./wył.), legenda kolorów, tryb nałożenia:
  **„szablon 1:1 (środek)”** — szablon w mm na środku strony pliku (gdy plik ma
  inny wymiar, od razu to widać, np. 616×232 vs 600×227), albo **„dopasowany do
  strony”** (rozciągnięty). Nakładka to SVG pozycjonowany nad obrazem — zoom i
  przesuwanie trzymają wyrównanie, linie zostają ostre.
- Podgląd przepisany na jawne wymiary w px (canvas + img + overlay), zamiast
  CSS max-width — potrzebne, żeby nakładka liczyła się z tej samej skali.

## Testy (sandbox, migawka produktów + lokalne PDF-y wytycznych)

- Parser: 4/4 pliki, 18 szablonów, wszystkie role i wymiary z tekstu; skala jw.
- UI: plik `Wydruk_adWall_Vario_Prosta_600_43_jednostronny_przod.pdf` → produkt
  wybrany automatycznie (95 %), wytyczne wczytane, rola „Przod”, skala 1:10,
  nakładka pokazuje różnicę wymiaru. AdTent 5x5 → 8 szablonów, wybór „Wrota (str. 8)”.
- Pobieranie wytycznych z noname.tey.pl **nie było testowane** (sandbox nie ma
  dostępu) — do sprawdzenia u Tomasza. W razie problemu działa „wgraj własny PDF”.

## Do sprawdzenia u Tomasza

1. Wybór produktu → czy status w sekcji „Wytyczne” pokazuje liczbę szablonów i skalę.
2. Czy linie nakładają się dokładnie na poprawnych plikach z `poprawne/`.
3. Czy nazwa roli z nazwy pliku podpowiada się sensownie (np. `_przod`, `_tyl`).

## Otwarte pytania / pomysły na później

- Jak traktować pliki 1:1 sprawdzane wobec wytycznych 1:10 (i odwrotnie) — na
  razie w trybie „1:1 (środek)” szablon będzie 10× za mały/duży, co jest
  informacją; kontrola wymiaru w etapie 3 powinna to nazwać wprost.
- Przy skali 1:10 obszar technologiczny (żółte kreski) jest bardzo cienki na
  małym zoomie — ewentualnie opcja pogrubienia linii nakładki.
- Szablony o tej samej roli (np. 3× „Wrota” — warianty) — może dodać miniaturę
  szablonu w liście, żeby łatwiej wybrać.
