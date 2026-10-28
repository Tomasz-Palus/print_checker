# Testy syntetyczne (28.10.2026)

Własne pliki z typowymi błędami — gdy nie ma prawdziwych projektów z danym problemem.
Uruchamiać z tego folderu, przy działającym serwerze (`python app/server.py`).

1. `python gen_szablony.py` — wytyczne (1000 × 2000 mm i 1:10) + 11 projektów: czysty, pełny szablon,
   przesunięty o 3 mm, w formie, pod grafiką, innego produktu, cyjanowy pas projektu, w pikselach,
   sama czerwona ramka, stopka klienta przy napisie z szablonu, 1:10.
   Przed testem: skopiuj `szablony/_wytyczne_1000x2000.pdf` do `app/data/guidelines/aaaa…a.pdf`
   (32 × „a”) i `szablony/_wytyczne_1do10_100x200.pdf` do `bbbb…b.pdf` (32 × „b”).
   `python test_szablony.py` — skan szablonu i usunięcie, porównanie z czystym projektem.
2. `python gen_wymiar.py` + `python test_wymiar.py` — spady (z TrimBox i bez), dopasowanie wymiaru
   (200 %, złe proporcje, tło z krawędzi, odbicie), obrót, /Rotate w stronie, UserUnit (> 5 m), 1:10,
   JPG 150 dpi, TIFF 2 strony, PNG z alfą, JPG CMYK, TIFF 16 bit, .ai z PDF-em i bez. Wypisuje OK / BŁĄD.

Wynik 28.10 (wersja 0.6.11 + poprawka „cyjanowy pas”): szablony 11/11 jak oczekiwano, wymiar i obrazy 25/25.
