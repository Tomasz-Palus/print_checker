# Nieosadzone fonty — bez grafika DTP i bez kroju zastępczego

Cel (Tomasz, 24.09): osoba nietechniczna ma przygotować plik do druku sama. Dotąd grafik DTP
przy brakujących fontach otwierał PDF w Photoshopie (rasteryzacja zachowywała kształt liter).

## Co ustaliliśmy testem w Photoshopie

Pliki `Claude outputs/Test_font_OSADZONY.pdf` i `Test_font_NIEOSADZONY.pdf` (Lora Italic,
niezainstalowany u Tomasza):
- **osadzony** — Photoshop pokazał prawdziwy Lora Italic. Kształty liter są w pliku.
- **nieosadzony** — Photoshop pokazał same kropki. Nie ma skąd wziąć kształtów.

Czyli „Photoshop zachowuje kształt" = font osadzony. Ten przypadek program obsługuje od zawsze
tak samo (krzywe / spłaszczenie biorą kształty z pliku, nic nie trzeba instalować).

## Font osadzony, a uznawany za nieosadzony — Type 3

Fonty **Type 3** (kształty liter jako rysunki w `/CharProcs`, bez pliku fontu — częste
w eksportach z CorelDRAW) były liczone jako nieosadzone. Poprawione w `analyze.py`
i `fixes.fonts_in`.

## Font naprawdę nieosadzony — `fontfix.py`

Wywoływane przez `fixes._prepare_fonts` przed Ghostscriptem przy **zamianie na krzywe**
i przy **spłaszczaniu**. Po kolei:

1. **Czy tekst się drukuje** (`text_usage`) — tryb tekstu Tr 3 / Tr 7 (niewidoczny, np.
   warstwa OCR) → font niepotrzebny, brak nie blokuje.
2. **Google Fonts** (`fetch`) — nazwa z PDF-a → rodzina / grubość / kursywa
   (`parse_name`: „ABCDEF+OpenSans-SemiBoldItalic" → Open Sans 600 kursywa; podpowiedź
   z `/FontWeight` i `/ItalicAngle`). Źródła: API css2 (stary User-Agent → .ttf), a gdy nie
   działa — repozytorium google/fonts na GitHubie (`METADATA.pb` z listą plików; fonty
   zmienne → statyczna grubość przez `fontTools.varLib.instancer`). Pobrane w `data/fonts/`.
3. **Osadzenie** (`embed`) — litery dopasowane po Unicode, NIE po numerach glifów:
   - Type0 / Identity-H: ToUnicode → znak → glif w pobranym foncie → nowa `/CIDToGIDMap`,
   - fonty proste (Type1/TrueType + kodowanie): Subtype → TrueType, `/FontFile2`, flaga
     nie-symboliczna (kod → nazwa glifu → Unicode → cmap). Szerokości zostają z PDF-a.
   Sprawdzamy WSZYSTKIE litery faktycznie użyte w tekście; brak choćby jednej → odmowa.
4. Czego nie pobrano — Ghostscript szuka w **fontach Windowsa** (`-sFONTPATH`).
5. Zamiennik z zasobów Ghostscripta → **odmowa** z instrukcją dla klienta
   (Illustrator/InDesign: Zapisz jako / Eksportuj → Adobe PDF, „Wysoka jakość druku").

Raport mówi, co pobrano i osadzono, co wzięto z systemu, co pominięto jako niewidoczne.

## Sprawdzone

- `Test_font_NIEOSADZONY.pdf` (Type0): osadzenie Lora Italic → 0,001 % pikseli różnicy względem
  pliku z oryginalnie osadzonym fontem; krzywe i spłaszczenie przechodzą, kształt Lora.
- Font prosty Type1 WinAnsi „Lora-Bold" (é, à, %, —): identyczny z wzorcem.
- Niewidoczny tekst OCR w nieistniejącym foncie: pominięty, zamiana przechodzi.
- Nieistniejący „KlientowyFontXyz-Bold": odmowa z instrukcją.

Uwaga: nowa zależność `fonttools` (requirements.txt) — instaluje się przy starcie `run.bat`.
W sandboxie Claude'a nie ma dostępu do fonts.googleapis.com (tylko GitHub raw), więc ścieżka
przez API css2 jest przetestowana dopiero u Tomasza.
