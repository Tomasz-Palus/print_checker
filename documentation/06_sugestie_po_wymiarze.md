# 06 · Sugestie produktu po wymiarze pliku

Data: 2026-09-04. Rozszerzenie sekcji „2 · Produkt”.

## Cel

Gdy nazwa wgranego pliku nic nie mówi o produkcie (np. `x9.pdf`, `abc_1234.pdf`,
`1824_strony_wymiar_cmyk.pdf`), program próbuje dopasować produkt po **wymiarze
strony pliku** (mm). Bierze pod uwagę, że plik może być w **dobrej albo złej skali**:
produkt w skali 1:10 mógł dostać plik 1:1 (10× za duży) i odwrotnie.

## Kolejność (suggest.suggest_all)

1. Sugestie z nazwy pliku (jak dotąd). Jeśli najlepsza ma trafność ≥ 0,6 — koniec,
   nic się nie zmienia.
2. W przeciwnym razie: sugestie po wymiarze (pierwsze), a za nimi słabe sugestie
   z nazwy (jeśli były). Razem max 5.

Każda sugestia ma teraz pole `basis` (`name` / `size`), a sugestie po wymiarze
dodatkowo `note` (zdanie po polsku) i `scale_hint` (`ok` / `scale` / `name-dims`).

## Skąd wymiary produktów

Lista produktów ze strony nie ma wymiarów. Są dwa źródła:

**A. Indeks szablonów** `data/template_index.json` (moduł `sizeindex.py`) — z PDF-ów
wytycznych: skala (strona 1) + szablony `W × H [mm]` (strony 2+). Pewny, ze skalą.

```
{ "<hash>": {"ok": true, "scale": "1:10", "templates": [{"role":"Front","w":600,"h":227,"missing":false}]},
  "<hash>": {"ok": false, "error": "URLError: ..."} }
```

Indeks rośnie sam przy każdym pobraniu wytycznych (`/api/guidelines/<hash>` →
`sizeindex.add_from_guidelines`) i można go zbudować w całości z Ustawień
(przycisk „Zbuduj / wznów indeks”): pobiera wytyczne wszystkich ~1000 produktów
w tle **8 wątkami równolegle** (`ThreadPoolExecutor`, zapis co 20), z możliwością
zatrzymania i wznowienia (pobiera tylko brakujące; „Ponów nieudane” dodatkowo te
z błędem). Po 15 błędach z rzędu przerywa sam (brak sieci). Na dysku ~300 MB PDF-ów
w `data/guidelines/`. Pierwsza wersja pobierała po kolei z 0,15 s przerwy — Tomasz
zgłosił, że trwa to strasznie długo; test z symulowaną siecią 0,3 s/plik: 120 plików
36 s → 4,7 s. Indeks buduje się raz — plik `template_index.json` przetrwa restarty;
nowe produkty dopobiera „Zbuduj / wznów”, a wpis produktu odświeża się przy każdym
potwierdzeniu produktu (świeże wytyczne, niżej).

**B. Wymiar z nazwy produktu** (`dims_from_product_name`) — gdy produktu nie ma
w indeksie: „100x250” → 1000×2500 mm (domyślnie cm; rozpoznaje `cm`, `mm`, `m`,
przecinek dziesiętny „49,6x297,6cm”); sama liczba 30–2000 („adWall … 600”) → tylko
szerokość w cm. Pary małych liczb (namioty „3x3”, „5x5”) pomijamy — to metry i za mało
pewne. Przybliżone, bez skali, bez spadów.

## Dopasowanie i punktacja (suggest_by_size)

Plik F = W_f × H_f mm, w dowolnej orientacji. Dla produktu z indeksu, szablon T (mm
w pliku wg wytycznych), P = T × 10 przy skali 1:10 (rozmiar wydruku):

| przypadek | trafność | scale_hint | komunikat |
|---|---|---|---|
| F ≈ T (tolerancja 3 % / 3 mm) | 0,90 | ok | „wymiar 616×232 mm = szablon „Front” 600×227 mm (skala 1:10 → 6000×2270 mm na wydruku)” |
| produkt 1:10, F ≈ P | 0,75 | scale | „… = rozmiar wydruku 6000×2270 mm, ale plik powinien być w skali 1:10 (600×227 mm)” |
| produkt 1:1, F ≈ P/10 | 0,75 | scale | „… = 1/10 szablonu 1015×2513 mm, ale ten produkt jest w skali 1:1” |
| z nazwy produktu W×H (8 % / 8 mm) | 0,70 | name-dims | „… pasuje do 4000×2500 mm z nazwy produktu” |
| z nazwy, F ≈ (W×H)/10 | 0,60 | name-dims | „… = 1/10 z 6000×2500 mm z nazwy produktu (plik w skali 1:10?)” |
| z nazwy, sama szerokość (4 %) | 0,50 / 0,40 | name-dims | „… pasuje do 2200 (szer.) mm z nazwy produktu” |

Tolerancja 3 % obejmuje różnice typu 616 vs 600 mm (plik ze spadem). Szablony
`0 × 0` (wydruk o zmiennym rozmiarze) są pomijane.

Sugestia ≥ 0,6 trafia na kartę „Sugerowany produkt” (nadal **wymaga potwierdzenia**);
słabsze tylko na listę propozycji.

## UI

- Karta kandydata: etykieta „SUGEROWANY PRODUKT · PO WYMIARZE” (lub „· Z NAZWY PLIKU”)
  i pod kodem produktu ramka z uzasadnieniem (`note`). Gdy skala się nie zgadza —
  żółta ramka z „⚠”.
- Lista propozycji: po prawej mała plakietka „nazwa” / „wymiar” / „wymiar · zła
  skala?” + trafność; pełne uzasadnienie w podpowiedzi (title).
- Pod wyszukiwarką podpowiedź „Sugestie po wymiarze pliku obejmują N z 1003
  produktów. Zbuduj indeks w Ustawieniach →” — gdy indeks niepełny i nazwa nic nie
  dała. Klik otwiera Ustawienia i od razu startuje budowanie.
- Ustawienia → sekcja „Sugestie produktu po wymiarze”: licznik, pasek postępu,
  „Zbuduj / wznów indeks”, „Ponów nieudane”, „Zatrzymaj”, ostatni błąd. Odświeżanie
  co 1,5 s w trakcie budowania.

## API

- `GET /api/sizeindex/status` → `{running, done, total, errors, last_error, indexed, failed, total_products}`
- `POST /api/sizeindex/build[?retry=1]` → start (retry=1: także nieudane)
- `POST /api/sizeindex/stop`
- `/api/upload` zwraca w `suggestions[]` dodatkowo `basis`, `note`, `scale_hint`.

## Testy (sandbox, indeks z 5 wytycznych)

| plik (nazwa bez sensu) | wymiar | wynik |
|---|---|---|
| x9.pdf (Prosta 600 Ø43) | 616×232 | adWall Vario Prosta 600 Ø43 — 90 %, „= szablon Front 600×227 (1:10 → 6000×2270)” |
| abc_1234.pdf (adFrame Smart) | 1014,9×2512,9 | adFrame Smart 100x250 — 90 %, „= szablon 1015×2513”; niżej Foldable/DTF/Quick 100x250 z nazwy (70 %) |
| 1824_strony_wymiar_cmyk.pdf | 4090×2300 | Foldable / Adframe GO / DTF 400x250 — 70 % z nazwy (plik ma celowo zły wymiar; komunikat pokazuje oba wymiary) |
| syntetyczny 6000×2270 | — | Prosta 600 Ø43 — 75 %, ⚠ „plik powinien być w skali 1:10 (600×227 mm)” |
| syntetyczny 101,5×251,3 | — | adFrame Smart — 75 %, ⚠ „1/10 szablonu 1015×2513, ale ten produkt jest w skali 1:1” |

Budowanie indeksu w sandboxie bez sieci: 15 błędów z rzędu → automatyczne przerwanie,
komunikat w Ustawieniach; „Zatrzymaj” działa.

## Aktualność wytycznych (wymaganie Tomasza, 2026-09-04)

„Jak potwierdzę produkt, to ma się pobrać AKTUALNY szablon, a nie z cache.”

- `guidelines.get_guidelines_fresh(hash)` — zawsze pobiera PDF ze strony
  (`download_pdf`). Jeśli pobrany plik jest bajt w bajt taki sam jak w cache, nie
  parsuje ponownie (`unchanged: true`), tylko odświeża `fetched_at`. Jeśli inny —
  nadpisuje cache i parsuje. Gdy sieć nie działa — zwraca kopię lokalną (JSON, a gdy
  go nie ma, parsuje PDF z cache) z `stale: true` i `stale_error`; gdy nie ma nic —
  błąd 502.
- `GET /api/guidelines/<hash>?fresh=1` — tego używa UI po potwierdzeniu produktu.
  Zwykłe `get_guidelines` (cache-first) zostało tylko dla indeksu wymiarów.
- UI pod szablonem: zielone „✓ aktualne — pobrano ze strony 4.09.2026 08:11 (bez
  zmian)” albo żółta ramka „⚠ Nie udało się pobrać aktualnych wytycznych ze strony —
  użyto kopii lokalnej z … · spróbuj ponownie”.
- Koszt: jedno pobranie ~300 KB przy każdym potwierdzeniu (ułamek sekundy).

## Uwagi / do zrobienia

- Na komputerze Tomasza indeks trzeba zbudować raz (Ustawienia). Do tego czasu
  sugestie po wymiarze opierają się głównie na wymiarach z nazw produktów.
- Produkty o tym samym wymiarze (Foldable / adFrame DTF / Quick 100x250) są
  nierozróżnialne po wymiarze — zawsze lista + potwierdzenie.
- Ostrzeżenie o złej skali pojawia się tu tylko jako podpowiedź; właściwy błąd
  „zła skala” będzie w etapie oceny wobec wytycznych (Sprawdź plik).


## Plik ze spadami nie dostawał żadnej sugestii (2026-09-10)

Zgłoszenie Tomasza: *„dlaczego pliku `spady.pdf` program nie jest w stanie dopasować
do jakichś wytycznych?"*

**Przyczyna.** Sugestie po wymiarze brały wyłącznie wymiar STRONY. `spady.pdf` ma spady:
strona 973,28 × 1973,28 mm, format netto (TrimBox) 950 × 1950 mm — czyli 11,64 mm spadu
z każdej strony, razem +23,3 mm na każdym boku. Tolerancja dopasowania to 3 % (albo 3 mm),
więc przy metrowym pliku mieści się ok. 29 mm — a najbliższy szablon leżał 38 mm dalej.
Zabrakło kilku milimetrów i produkt nie miał prawa się pokazać. Zmierzone: **0 sugestii**
dla strony, **2 sugestie** dla formatu netto.

**Poprawka.** `suggest_all()` przyjmuje teraz `trim_mm` (format netto z rozdziału o spadach)
i gdy plik ma spady, szuka po OBU wymiarach — po stronie i po netcie. Trafienie „po odjęciu
spadów" ma wynik o 0,02 niższy niż trafienie wprost (żeby przy remisie wygrywało to
oczywiste) i mówi o tym wprost w opisie. Ten sam produkt z obu list pokazujemy raz.

Efekt na `spady.pdf`: *„SUGEROWANY PRODUKT · PO WYMIARZE · trafność 88 % — Wydruk adFrame
Lumina RGB 100x200 — wymiar 950 × 1950 mm = szablon „1" 935 × 1926 mm — po odjęciu spadów"*.

**Uwaga merytoryczna.** Nawet po poprawce to jest dopasowanie „w tolerancji", nie co do
milimetra: w całych wytycznych (1003 produkty) **nie ma szablonu 950 × 1950 mm**. Najbliższe
to 935 × 1926 (adFrame Lumina RGB 100×200) i 1012 × 2010 (adFrame CTF 100×200). Czyli ten
konkretny plik nie jest zrobiony pod żaden nasz szablon — i dobrze, że program mówi
„trafność 88 %", a nie udaje pewności.

Sprawdzone na 14 plikach przykładowych: zmienił się wynik **wyłącznie** dla `spady.pdf`
(jedynego z TrimBoksem mniejszym od strony), reszta bez zmian.
