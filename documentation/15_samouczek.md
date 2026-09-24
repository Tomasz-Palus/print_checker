# 15 — Samouczek (wersja 0.2, 24.09.2026)

Prośba Tomasza: samouczek jak w nowoczesnych aplikacjach. Pojawiają się po kolei dymki z tekstem,
co zrobić. Jest dla osób nietechnicznych, które mają mało wspólnego z grafiką i drukiem. Zaczyna się
od kalibracji monitora, dokładności oceny jakości i indeksu wymiarów.

Decyzje Tomasza:
- Część z rozdziałami idzie na **wbudowanym pliku przykładowym**.
- Dymek **czeka na akcję** użytkownika i sam przechodzi dalej.
- Samouczek startuje **sam przy pierwszym uruchomieniu**. Potem tylko z przycisku „🎓 Samouczek”
  obok „Ustawienia”.

## Jak działa

- **Przyciemnienie:** cały ekran jest przyciemniony. Widać tylko wskazane miejsca („dziury”
  z pulsującą niebieską obwódką) i tylko je da się kliknąć. Może ich być kilka naraz, np. rozdział
  i podgląd.
  - Klik w przyciemnienie nic nie robi, tylko dymek „podskakuje”.
  - Kółko myszy nad przyciemnieniem przewija to, co pod nim (panel rozdziałów, okno ustawień).
- **Dymek:**
  - U góry część i numer kroku („Przykładowy projekt · 5 z 25”) oraz pasek postępu.
  - Tytuł i 2–3 zdania prostym językiem.
  - Na dole „Wstecz” i „×” (zakończ).
  - Dymek ustawia się obok wskazanego miejsca: najpierw po prawej, potem po lewej, pod, nad. Ma
    strzałkę do tego miejsca i nie zasłania go.
- **Krok z akcją** („Kliknij Potwierdź”): pokazuje „● Twój ruch — dalej przejdę sam”. Gdy
  użytkownik zrobi, co trzeba, dymek przechodzi dalej sam.
  - Gdy program liczy, zamiast tego pokazuje „Program pracuje — chwileczkę…”.
- **Krok z opisem:** ma przycisk „Dalej”.
- **Akcja zrobiona wcześniej** (powrót „Wstecz”, monitor już skalibrowany, indeks zbudowany):
  zamiast czekania jest „Dalej”.
- **Pomijanie:**
  - Kroki rozdziałów, które są już domknięte, samouczek idąc do przodu pomija.
  - Kroki opcjonalne (kalibracja, indeks, podgląd szablonu, suwak) mają link „Pomiń”.
- **Pytanie „na pewno?”** (np. „Wgrać inny plik?”): samouczek się chowa, aż ktoś odpowie.
- **Zakończenie:** „×”, „Nie teraz” albo ostatni krok zapisują `localStorage adcheck.tourDone`. Od
  tej chwili samouczek nie startuje sam.

## Kroki

**Część 1 — Ustawienia (7):**
1. powitanie („Zaczynamy” / „Nie teraz”)
2. kliknij Ustawienia
3. kalibracja (przekątna → Zastosuj)
4. sprawdzenie linijką (100 mm)
5. dokładność oceny jakości
6. indeks wymiarów (Zbuduj / wznów)
7. zamknij ustawienia

**Część 2 — Przykładowy projekt (25):**
1. wczytaj plik przykładowy
2. rozdziały
3. podgląd
4. strona
5. produkt
6. rola
7. podgląd szablonu (włącz, a potem wyłącz)
8. usuń szablon
9. suwak przed / po
10. spady
11. wymiar: „wypełnij format”
12. wymiar: „Dopasuj wymiar”
13. kolory: Zamień na CMYK
14. profil FOGRA39
15. Pokaż, jak wydrukuje
16. podgląd = wydruk (suwak ekran ↔ druk)
17. overprint
18. fonty
19. spłaszczenie
20. jakość: Pokaż na podglądzie
21. słabe miejsca (‹ ›, zamknij ×)
22. akceptacja: Pokaż wydruk przed i po
23. przed i po → Akceptuję plik
24. pobieranie
25. koniec (przycisk Samouczek)

**Plik przykładowy:** `static/samples/przyklad_adChecker.pdf`. To kopia
`PRINT_CHECKER_TEST_100x200_SZABLON_PASERY.pdf`. Ma:
- 3 strony;
- propozycję produktu z szablonu w pliku (Pop-up Lightbox 100x200, rola Front);
- szablon z wytycznych;
- spady 20 mm;
- wymiar 1000 × 2000 zamiast 1015 × 2014;
- RGB, Lab, PANTONE i złoto;
- overprint, fonty i przezroczystość;
- 3 obrazy o za małej rozdzielczości.

Nazwa pliku jest neutralna (bez „100x200”), żeby propozycja produktu szła z treści pliku.

## Kod

- `static/js/tour.js`:
  - lista kroków (`STEPS`) i silnik (`startTour`, `go`, `tick` co 120 ms, `layout`,
    `placeBubble`);
  - `initTour({upload})` dostaje funkcję wgrywania z `main.js`;
  - `autoStartTour()` startuje samouczek przy pierwszym uruchomieniu.
- **Przyciemnienie:** SVG z maską; dziury łączą się, gdy zachodzą na siebie. Kliknięcia blokuje
  osobna, przezroczysta ścieżka z komórek siatki, które nie leżą w żadnej dziurze.
  - Pierwsza wersja z `evenodd` zamykała część wspólną dwóch dziur (pasek miejsc leży na podglądzie).
- `settings.js`: `calCount()` (ile razy zapisano kalibrację) i `idxState()` (ostatni stan indeksu),
  potrzebne w krokach samouczka.
- `index.html`:
  - przycisk `#btnTour`;
  - sekcje ustawień w `#setCal`, `#calCheckWrap`, `#setAcc`, `#setIdx`;
  - „100 %” w kalibracji przemianowane na „Rzeczywista wielkość” (tak nazywa się przycisk);
  - wersja v0.2.
- `server.py`: `VERSION = "0.2"`; User-Agent `adChecker/0.2`.

## Test (Playwright, 1600 × 950 i 1366 × 768)

- Cały samouczek przechodzi od powitania do końca. Każdy krok przechodzi dalej sam po akcji, bez
  zawieszeń.
- „Nie teraz” zapisuje flagę; po odświeżeniu samouczek nie startuje, a przycisk go włącza.
- Klik w tło nic nie zmienia.
- „Pomiń” i „Wstecz” działają. Po powrocie do niezrobionej kalibracji krok znów czeka na akcję.
- Plik wgrany wcześniej: „Wczytaj plik przykładowy” pyta „Wgrać inny plik?”. Samouczek chowa się na
  czas pytania i idzie dalej po odpowiedzi.
