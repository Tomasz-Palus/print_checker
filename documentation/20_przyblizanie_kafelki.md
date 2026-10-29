# 20 — Przybliżanie wszędzie: kafelki na żądanie (plan i krok 1, 27.10.2026)

Tomasz: „przybliżać można tylko przy sprawdzaniu jakości, a chciałbym też np. przy symulacji wydruku;
problem był taki, że strasznie długo się podgląd wczytywał. W Photoshopie wczytuje się szybko i edycja
pliku nie powoduje, że wczytuje się od nowa”.

## Dlaczego dziś jest wolno

Przybliżanie wymaga piramidy (`views.py`, `render.build`): **cała strona** w 120 ppi wydruku,
nadpróbkowana 2× — dla banera 5×3 m ok. 1,3 mld pikseli — osobno dla każdej wersji pliku (każda poprawka
= nowa wersja) i każdego trybu (ekran / druk / overprint). Dlatego od 28.09 przybliżanie jest tylko
w „Jakości wydruku”.

## Plan

1. **Test zgodności MuPDF ↔ Ghostscript** (ten dokument, niżej).
2. **Kafelki na żądanie**: liczone tylko te, które widać przy danym przybliżeniu (najpierw rozmyty podgląd
   całości, potem ostre kafelki, sąsiednie w tle), pamiętane na dysku. Przybliżanie we wszystkich
   rozdziałach. Silnik według reguły z kroku 1.
3. **Kafelki między wersjami**: krzywe i spłaszczenie nie zmieniają wyglądu (kafelki zostają), usunięcie
   szablonu zmienia tylko kafelki pod ramkami, spady — ten sam obraz przycięty.
4. **Liczenie w tle**, gdy nic się nie dzieje; overprint przez Ghostscripta.

## Krok 1 — wynik

Narzędzie: `narzedzia/porownaj_silniki.py <folder>` (raport `raport.md`/`.csv` + obrazy porównań).
Plik przygotowany jak przy wgraniu, tekst na krzywych (jak podgląd), Ghostscript dokładnie z argumentami
programu (`render._gs_args`, nadpróbkowanie 2×). MuPDF: piksele CMYK (`csCMYK`) → ekran tym samym
profilem co symulacja druku (`render.proof_rgb`) — „mu_cmyk”; dla porównania MuPDF RGB wprost — „mu_rgb”.
Próg „zgodne”: 99. percentyl różnicy koloru (bloki 4×4) ≤ 6/255 i ≤ 1 % pikseli różnych o > 32.

Korpus w kontenerze Claude'a (prawdziwe projekty Tomasza — do powtórzenia u niego): plik przykładowy
programu (3 strony: RGB, Lab, ICC, spot, DeviceN, overprint, przezroczystość, rastry, tekst), Multiply /
krycie / Screen z i bez przestrzeni mieszania, spot + overprint, gradient + Lab + linie 0,1–1 pt,
zdjęcie RGB z maską miękką + zdjęcie CMYK JPEG + tekst 7 pt.

| | wynik |
|---|---|
| **czas kafla 1024 px** | Ghostscript śr. 0,41 s (maks. 0,71), MuPDF śr. 0,04 s (maks. 0,10) — ok. 10× szybciej |
| **„druk”, strona czysto CMYK** (CMYK, szarość, spot z alternatywą CMYK) | MuPDF = Ghostscript (p99 0–4, także Multiply / krycie / Screen bez przestrzeni mieszania i spot z overprintem — overprint w tym trybie wyłączony) |
| **„ekran”, strona czysto CMYK z zadeklarowaną przestrzenią mieszania** | MuPDF = Ghostscript (8/8) |
| „ekran”, przezroczystość bez przestrzeni mieszania | różne (p99 22–60) — Ghostscript na ekranie miesza w RGB (doc 17, 0.6.9: Kolory to poprawiają) |
| treść RGB / Lab (przed „Zamień na CMYK”) | różne (p99 10–75) — MuPDF przelicza RGB → CMYK własnym profilem, nie FOGRA39 |
| MuPDF RGB wprost („mu_rgb”) | różne prawie wszędzie (p99 ~10–15 nawet na czystym CMYK) — CMYK → ekran własnym profilem |

Próby podania MuPDF profilu FOGRA39 jako docelowego / domyślnego CMYK (`pymupdf.mupdf`:
`fz_new_icc_colorspace`, `fz_set_default_cmyk`, `fz_set_default_output_intent`) pogorszyły zgodność
(interpreter PDF nadpisuje domyślne przestrzenie strony; DeviceCMYK przestaje przechodzić 1:1). Włączenie
`TOOLS.set_icc(True)` zmniejsza rozjazd RGB o połowę, ale nie do progu.

### Reguła silnika dla kroku 2

- **MuPDF (`csCMYK` → `proof_rgb`)**: strona bez RGB / Lab / Indexed / nieznanych przestrzeni
  - tryb „druk” — zawsze,
  - tryb „ekran” — gdy strona nie ma przezroczystości bez przestrzeni mieszania (`blend_space_missing`)
    ani grupy RGB (`group_rgb`).
- **Ghostscript (kafel wycinkiem, 0,3–0,7 s)**: pozostałe strony, symulacja overprintu, strony, na
  których MuPDF zgłasza błąd (`render._mupdf_can`, `_mupdf_failed`).

Po „Zamień na CMYK” (wymagane do druku) praktycznie każda strona trafia do szybkiej ścieżki.

### Do sprawdzenia u Tomasza

`py narzedzia\porownaj_silniki.py "…\przykladowe projekty"` — czy reguła trzyma się na prawdziwych
projektach (duże zdjęcia, maski, pliki z Illustratora/Corela) i ile trwa kafel Ghostscripta na ciężkich
plikach (Ghostscript czyta przy każdym kafelku całą stronę).

### Wynik na prawdziwych projektach Tomasza (27.10, 3 pliki)

| plik | co ma | wynik |
|---|---|---|
| Volvo adTent (wektor, sam DeviceCMYK) | linie szablonu, tekst | kolory identyczne; różnice tylko na krawędziach cienkich linii (wygładzanie) — p99 ~10 to włosowe linie, wizualnie to samo |
| Skolae adWall 300 | gradienty (`sh`), maski miękkie, Multiply | ukośny pas tła minimalnie inny (p99 4–10) |
| konferencja adWall 400 (21 MB zdjęć CMYK z SMask) | maski miękkie z gradientem, Multiply, krycie | **różny kształt**: MuPDF rysuje ostre ukośne „kliny” na pionowych pasach kurtyny, Ghostscript pasy z lekkim skosem, Poppler (trzeci silnik, do porównania) prawie gładko |

- Czas kafla na adWall 400: Ghostscript 7–17 s, MuPDF 1,7–4 s (skrypt otwiera plik od nowa przy każdym kaflu).
- **Wniosek:** reguła z korpusu testowego nie wystarcza. Maski miękkie (gradientowe maski luminancji) każdy
  silnik liczy inaczej — MuPDF dla stron z maskami odpada. Który wynik jest prawdziwy (Acrobat / RIP
  drukarni), musi sprawdzić Tomasz w Acrobacie: ma to znaczenie także dla druku, bo spłaszczenie liczy
  Ghostscript.

### Kto ma rację — Acrobat (Tomasz 27.10)

Zrzut z Acrobata (adWall 400, twarz przy kurtynie): granice pasów proste i pionowe, bez ukośnego klina —
**jak Ghostscript**. MuPDF źle liczy te maski. Wniosek: podgląd i spłaszczenie (Ghostscript) zgadzają się
z Acrobatem; MuPDF tylko dla stron bez miękkich masek.

## Krok 2 — zrobione (0.6.10)

**Przybliżanie w każdym rozdziale** (`main.js`: `setZoomAllowed(!!S.job)`, lupki i „Rzeczywista wielkość”
zawsze). Pełna jakość warstwy zamawiana dopiero przy pierwszym przybliżeniu (`Layer.full`); w „Jakości
wydruku” od razu, jak dawniej (`viewer.setPrefetch`).

Silnik wybiera serwer (`server.mupdf_tiles_ok`):

| strona | widok | czas (kontener, 2 rdzenie) |
|---|---|---|
| bez miękkich masek i bez RGB/Lab/Indexed, bez symulacji overprintu („ekran” — także bez mieszania w RGB) | **kafle MuPDF na żądanie** (`views` z `lazy`, `render.build_lazy` / `lazy_tile`): podgląd całości od razu, kafel liczony przy pierwszym zapytaniu, otwarty plik trzymany w pamięci (`render._doc_cached`) | widok gotowy ~0,3–1 s, kafel ~0,04 s (Volvo); pierwszy ostry obraz po przybliżeniu ~0,7 s |
| pozostałe (maski, RGB przed „Zamień na CMYK”, overprint) | piramida Ghostscripta jak dawniej + **wycinek widoku** (`views.region`, `render.gs_block`): przy przybliżeniu najpierw liczy się tylko widoczny prostokąt kafli (bez nadpróbkowania, pasmami), piramida czeka, aż wycinek się skończy | adWall 400 (21 MB, maski): wycinek 7 s (mocne przybliżenie) – 14–20 s (średnie; czas rośnie z polem strony, nie z liczbą pikseli); cała piramida ~6,5 min w tle |

Inne:
- „Krzywe” nie zmieniają wyglądu — widok bierze poprzednią wersję (`api_view`), nic się nie liczy od nowa.
- Kafel, który doszedł po zmianie przybliżenia, kładł się w starej skali (błąd był wcześniej, rzadko
  widoczny) — po wczytaniu kafla `draw()`.
- `text_as_curves` z blokadą na plik (piramida i wycinek prosiły o kopię naraz).
- `-dMaxBitmap` duży (cały wycinek w pamięci — ścieżka bezpieczna przy overprincie) liczył wycinek 2,5×
  dłużej — w `gs_block` bez overprintu mały (pasmami).

Zostało (krok 3–4): kafle między wersjami dla spłaszczenia / usunięcia szablonu / spadów, liczenie
piramidy zaraz po wgraniu.

## Krok 3 — widok poprzedniej wersji (29.10, 0.7.0)

| poprawka | widok | dlaczego |
|---|---|---|
| Krzywe | poprzedniej wersji (od 0.6.10) | podgląd i tak rysuje tekst z krzywych |
| **Wyłącz overprint**, podgląd bez symulacji overprintu | **poprzedniej wersji** (nowe) | Ghostscript (`-dOverprint=/disable`) i MuPDF overprint pomijają — piksele identyczne (sprawdzone: CMYK i RGB, Ghostscript i MuPDF) |
| Wyłącz overprint, z symulacją | liczony od nowa | widać właśnie tę zmianę |
| Spłaszczenie | liczony od nowa | użytkownik ogląda z bliska WYNIK spłaszczenia (ząbki na krawędziach, Tomasz 29.09) — stary obraz by je ukrył; spłaszczona strona to jeden obraz CMYK, kafle MuPDF na żądanie |
| Usunięcie szablonu | liczony od nowa | zmienia się tylko pod liniami, ale Ghostscript liczy wycinek ze stroną w całości (czas rośnie z polem strony) — ponowne liczenie kafli wzdłuż ramki dookoła strony kosztuje prawie tyle co cała piramida |
| Spady | liczony od nowa | przycięcie przesuwa siatkę kafli o ułamek piksela — kafle trzeba by przeskalować (rozmycie) |

Liczenie w tle zaraz po wgraniu (krok 4) — **nie** (Tomasz 28.10: użytkownicy mają przeważnie słabe
komputery); kafle tylko na żądanie.
