# Etap 1 — upload, wybór produktu, podgląd

Data: 2026-09-03. Nowy start projektu adCheck (poprzedni kod usunięty z `app/`,
budujemy funkcja po funkcji; ustalenia z poprzedniej sesji są w
`10_handoff_nowa_sesja.md` — traktujemy je jako wskazówki, nie pewnik).

## Ustalenia z tej sesji (Tomasz)

- Technologia: **Flask (Python) + przeglądarka**, uruchamiane `run.bat`, UI pod
  `http://127.0.0.1:5000/`.
- Lista produktów: **pobierana przy starcie ze strony, cache 24 h**, przycisk
  „odśwież” w UI; gdy brak sieci → ostatnia kopia; gdy brak kopii → migawka
  wbudowana w program (`app/data/products_snapshot.json`, 1003 produkty z 2026-09-03).
- Pola wymiaru ręcznego (szer./wys. mm) **zawsze widoczne**, opcjonalne.
- Etap 1 bez przełącznika „Analiza AI” i bez raportu — tylko podgląd.
- **PDF wielostronicowy = błąd** (do poprawy w kolejnych etapach: program ma
  dzielić PDF na pojedyncze strony / osobne pliki — pomysł jeszcze niedomknięty).
  Na razie podgląd pokazuje miniatury wszystkich stron i dużą wybraną stronę.

## Fakty sprawdzone o źródle produktów

- `https://noname.tey.pl/adlogo/?langs=en` to zwykły HTML generowany po stronie
  serwera (jedyny skrypt to Google Tag) — **nie trzeba przeglądarki ani JS**,
  wystarczy `urllib` + parser HTML.
- Tabela: kol. 1 = nazwa, kol. 2 = kod + link do wytycznych z logo, kol. 3 = kod +
  link bez logo (`nl=1`). 1400 wierszy, ale wiele to dokładne duplikaty (ten sam
  hash) → po deduplikacji **1003 unikalne produkty** (999 unikalnych kodów —
  kilka kodów powtarza się dla różnych nazw, więc kluczem jest `hash`).
- Link do wytycznych: `https://noname.tey.pl/file/requirements?type=product&hash=…&lang=en`.
- Uwaga: z sandboxa Claude'a strona jest zablokowana (proxy) — testy pobierania
  na żywo trzeba robić na komputerze Tomasza. Migawka posłużyła jako fallback.

## Architektura (app/)

| plik | rola |
|---|---|
| `server.py` | Flask: `/` (UI), `/api/products`, `/api/products/refresh`, `/api/upload`, `/api/jobs/<id>`, `/api/jobs/<id>/page/<n>.png?max=…`. Pliki wgrane lądują w `app/work/<job_id>/original.<ext>` (ścieżka ASCII, kasowana przy starcie). Reloader Flaska włączony — zmiany w .py przeładowują się same. |
| `products.py` | pobieranie/parsowanie listy, cache `data/products_cache.json`, fallback na snapshot. |
| `suggest.py` | dopasowanie nazwy pliku do produktu (normalizacja: małe litery, bez diakrytyków, znaki specjalne → spacja; punktacja: pokrycie tokenów produktu w nazwie pliku ważone długością, tokeny z cyframi ważniejsze, bonus za kod produktu, difflib). Synonimy `jednostronne→jednostronny` itd. Próg 0,45, top 5. |
| `preview.py` | otwieranie pliku PyMuPDF (PDF/AI/SVG/JPG/PNG/TIFF…), metadane stron (pt, mm, px, DPI dla rastra), render PNG. **Fallback Ghostscript** gdy w PDF-ie jest obraz > 400 Mpx (MuPDF: „Overly large image”) — szuka `gswin64c` w PATH lub `C:/Program Files/gs/gs*/bin/`. CDR/INDD/PSD → komunikat „wyeksportuj do PDF”. |
| `static/` | `index.html`, `app.css`, `app.js` — UI bez frameworków. |

Zależności: `flask`, `pymupdf`, `pillow` (`requirements.txt`); Ghostscript
opcjonalnie (tylko do ogromnych rastrów w PDF).

## Zachowanie UI

- Plik: drag&drop na ramkę **lub gdziekolwiek na stronie**, albo klik. Pasek
  postępu wysyłania. Po wgraniu: nazwa, rozmiar, typ (wektor/raster), liczba stron.
- Produkt: pole wyszukiwania (nazwa lub kod, wiele słów, bez diakrytyków),
  strzałki/Enter, podświetlanie trafień. Pod spodem „Sugestie na podstawie nazwy
  pliku” z procentem; **sugestia ≥ 85% wybiera się sama** (jeśli nic nie było
  wybrane). Wybrany produkt ma link do PDF-a wytycznych.
- Wymiar ręczny: dwa pola; „Sprawdź plik” aktywny gdy jest plik i (produkt lub
  oba wymiary).
- Podgląd: miniatury stron (tylko gdy >1), duża strona z zoomem (+/−/Dopasuj,
  Ctrl+kółko, przeciąganie). Render 1600 px po dłuższym boku, cache PNG per job.
- „Sprawdź plik” wypisuje na razie tylko podsumowanie wyboru (miejsce na raport).

## Wyniki testów (sandbox, przykładowe pliki)

- Sugestie trafiają w 100% dla plików z folderu `poprawne/` i `bledne/`
  z nazwami produktów (np. `adWall_Vario_Prosta_Light_300_dwustronne_tyl.pdf` →
  „Wydruk adWall Vario Prosta Light 300 dwustronny” 92%). Nazwy-hashe
  (`1788264646af029f_q1.jpg`) → brak sugestii (zgodnie z oczekiwaniem).
- `1824_strony_wymiar_cmyk.pdf` ma raster 46009×19322 px → MuPDF odmawia,
  Ghostscript renderuje (~5 s przy 1600 px).
- JPG z „9 dpi” w metadanych pokazuje 2892×2483 mm — program raportuje to, co
  jest w pliku; ocena należy do etapu kontroli.

## Do sprawdzenia u Tomasza (na Windows)

1. `run.bat` — instalacja zależności i start; czy przeglądarka otwiera się sama.
2. Czy lista pobiera się „ze strony” (status pod polem produktu) i czy
   „odśwież” działa.
3. Plik `.ai` z Illustratora (PDF-compatible) i `.tiff` CMYK — podgląd.
4. Czy Ghostscript jest znajdowany (plik `1824_strony_wymiar_cmyk.pdf`).

## Następne etapy (propozycja)

2. Wytyczne per produkt: pobranie PDF-a, wymiar szablonu z tekstu str. 2,
   wektorowa nakładka strefy (czerwona/niebieska) na podgląd.
3. Kontrole podstawowe: wymiar vs szablon, przestrzeń kolorów, spoty, overprint,
   fonty, warstwy, DPI rastrów, liczba stron.
4. Podział PDF-a wielostronicowego na osobne pliki (do ustalenia).
5. Poprawki na kliknięcie + komparator; potem AI.
