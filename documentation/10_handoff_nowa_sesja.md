# Handoff — ustalenia do nowej sesji (start od zera, funkcja po funkcji)

Ten plik zbiera to, co w tej sesji było trudne do ustalenia. Nowa sesja może
zacząć od czystego kodu, ale NIE musi odkrywać tych rzeczy ponownie.

## Fakty o danych wejściowych (sprawdzone)

- **Lista produktów**: https://noname.tey.pl/adlogo/?langs=en — 1002 unikalne
  produkty. Kolumna 2 = kod produktu. Każdy wiersz ma link do PDF-a wytycznych
  tego produktu (`/file/requirements?type=product&hash=…`). Uwaga: odczyt tekstu
  strony ucina się na 50 000 znaków (dało tylko 470 z 1002) — tabelę trzeba
  pobrać przez JavaScript z DOM (`querySelectorAll('table tr')`). Gotowa lista
  z linkami: `app/data/products.json`.
- **Wytyczne (PDF)**: strona 1 = wymagania, ale w KRZYWYCH (brak tekstu — skali
  1:1/1:10 nie da się wyczytać tekstowo; ewentualnie OCR). Strona 2 = szablon:
  czerwony kształt = obszar ochronny, niebieski = kształt produktu — to WYPEŁNIONE
  ścieżki wektorowe (fill ≈ rgb(0.93,0.19,0.18) i rgb(0,0.68,0.94)), często z
  zaokrągleniami. Tekst na str. 2 podaje wymiar szablonu „W x H [mm]".
- **Reguły druku** (jednakowe dla wszystkich produktów): CMYK Coated FOGRA39,
  120 ppi @ 1:1, PDF, spłaszczony, bez paserów/overprintu/spadów, fonty na krzywe,
  nie zmieniać wielkości szablonu; ważne elementy w czerwonej strefie, tło może
  wychodzić.
- **Sidecary JSON** w `poprawne/` pokazują model danych istniejącego pipeline'u
  (hasCMYK/hasRGB/hasSeparation/hasOverPrints/withLayers/hasEmbeddedFont/images/
  mediaBox/width/height w mm).

## Pułapki techniczne (kosztowały czas)

- **DPI**: pliki wektorowe z drobnymi logotypami rastrowymi dawały mylące „302 ppi".
  Liczyć DPI tylko dla rastrów o istotnym pokryciu (>15% powierzchni); inaczej „wektor".
- **Ghostscript na Windows**: nie podawać mu JPG (błąd `/undefined`); ścieżki
  robocze ASCII, ukośniki `/`; auto-wykrywanie `gswin64c.exe` w Program Files.
- **Konwersja CMYK obrazów**: naiwne Pillow `convert('CMYK')` daje wyblakłe kolory
  w Photoshopie — używać ICC (littleCMS), profil FOGRA39 z instalacji Adobe
  (`C:\Program Files\Common Files\Adobe\Color\Profiles\...`), osadzać profil w pliku.
- **Dopasowanie wymiaru**: skalować z WYPEŁNIENIEM (cover) — bez pustych pasków.
- **Nakładka wytycznych**: wyciągać ścieżki czerwone/niebieskie z PDF jako SVG
  (wektor), NIE rysować własnego prostokąta i nie rasteryzować.
- **Ostry zoom**: podgląd 1 raster = pikseloza przy „rozmiarze wydruku"; renderować
  na żądanie tylko widoczny fragment z wektora (PyMuPDF `get_pixmap(clip=…)`).
- **Flask nie przeładowuje kodu** — po zmianach trzeba zrestartować serwer
  (zamknąć czarne okno konsoli i odpalić `run.bat`). Zmiany w HTML wystarczy F5.
- **CSS**: reguła `display:flex` nadpisuje atrybut `hidden` — dodać
  `[hidden]{display:none!important}`.
- **AI (Claude subskrypcja, Agent SDK)**: działa po `claude login`, ale bywa błąd
  „Reached maximum number of turns" przy analizie obrazu; pomaga większy limit tur,
  bardzo dyrektywny prompt (Read raz → od razu JSON), zbieranie odpowiedzi mimo
  błędu. Tryb Klucz API jest stabilniejszy dla obrazów. ChatGPT Plus / Gemini
  Advanced NIE działają programowo — tylko klucze API (Gemini ma darmowy limit).
- **Cache**: wersjonować wpisy cache (zmiana schematu = nowa wersja), bo starych
  plików w folderze zmontowanym nie da się nadpisać z tej sesji.

## Decyzje produktowe (od Tomasza)

- Program RAPORTUJE wszystko; poprawki tylko na kliknięcie; oryginał nietykalny.
- Panel „Opcje" minimalny: suwak + „Analiza AI"; szczegóły trybu AI w Ustawieniach.
- Komparator (oryginał ↔ po poprawce) z suwakiem na głównym podglądzie + pełny ekran
  z suwakiem na dole, zoom/panorama, „Rozmiar wydruku" wg skali 1:1/1:10.
- Jeden przycisk „Pobierz poprawiony plik".
- Pliki wielostronicowe: podział na strony i praca na każdej osobno.
- NA RAZIE bez kontroli „ważne elementy poza strefą" (usunięte na życzenie).
- Obsługiwane formaty: PDF/AI pełne; JPG/PNG/TIFF rastrowo; SVG wstępnie;
  CDR/INDD → prośba o eksport do PDF.

## Co jest w tym folderze (do wykorzystania lub skasowania)

- `app/` — działający MVP (Flask + PyMuPDF + pikepdf + Pillow + Ghostscript):
  silnik kontroli, poprawki, wytyczne per produkt, komparator, pełny ekran,
  wielu dostawców AI. Można go użyć jako źródło gotowych fragmentów (np.
  `guidelines.py`, `render.py`, `fixes/`), nawet jeśli nowa sesja zaczyna od zera.
- `documentation/` — wymagania, katalog kontroli, model danych, dziennik zmian.

## Sugestia kolejności w nowej sesji (funkcja po funkcji, każda przetestowana)

1. Upload + wybór produktu (lista 1002) + surowy podgląd.
2. Wytyczne per produkt: pobranie PDF, wektorowa nakładka linii (SVG), wymiar z tekstu.
3. Kontrole podstawowe (kolor, warstwy, overprint, fonty, wymiar, DPI dla rastrów).
4. Poprawki na kliknięcie (jedna naraz, z komparatorem i jednym przyciskiem pobrania).
5. Pełny ekran + ostry zoom wektorowy + „rozmiar wydruku" ze skalą.
6. Dopiero potem AI (najpierw tryb klucz API jako najstabilniejszy).
