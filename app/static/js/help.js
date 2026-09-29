// Wyjaśnienia pod „?" w każdym rozdziale. Rozdział pokazuje tylko stan i przycisk
// (uwaga Tomasza: ma być jak najmniej na ekranie) — całe „po co i jak" siedzi tutaj.
export const HELP = {
  file: `Wgraj plik, który ma iść do druku: PDF (najlepiej), AI, EPS, SVG albo obraz (JPG, PNG, TIFF).
    CorelDRAW, InDesign i PSD trzeba najpierw wyeksportować do PDF.<br><br>
    Oryginał nigdy nie jest zmieniany — każda poprawka tworzy nową wersję obok, a na końcu
    pobierasz gotowy plik.<br><br>
    Przy wczytaniu program ustawia plik tak, jak się <b>wydrukuje</b>: warstwy ukryte albo oznaczone
    „nie drukuj” i niedrukowane komentarze Acrobata usuwa, a drukowane stemple i pola wpisuje w stronę
    (różne drukarnie traktują je różnie). Zdejmuje też hasło do uprawnień i przelicza stronę zapisaną
    w powiększonej jednostce (UserUnit, strony ponad 5 m). Dzieje się to samo, bez pytania.
    PDF-a z hasłem do otwarcia albo zniszczonego otworzyć się nie da — trzeba poprosić klienta o nowy.`,
  product: `Program zgaduje produkt z nazwy pliku, z szablonu zostawionego w projekcie albo z wymiaru
    strony — ale zawsze trzeba go <b>potwierdzić</b>. Od produktu zależą wytyczne: wymiar,
    skala (1:1 albo 1:10) i obszar bezpieczny.<br><br>
    Wytyczne pobierają się za każdym razem na nowo ze strony Adsystem, więc są zawsze aktualne.
    Gdy nie ma sieci, program użyje kopii lokalnej i powie o tym na żółto.`,
  role: `Wytyczne produktu mają zwykle kilka <b>ról</b> — np. Front, Back, Dach — i każda ma swój
    wymiar. Wskazujesz, którą z nich jest ten plik; od tego zależy docelowy format.<br><br>
    <b>Skala</b> jest odczytana z wytycznych i tylko pokazana: w skali 1:10 plik 500 mm drukuje się
    jako 5000 mm, więc każdy piksel jest 10× większy.`,
  page: `Do druku idzie zawsze <b>jedna strona</b> — nigdy nie pobieramy PDF-a z kilkoma stronami.
    Poprawki i ocena jakości dotyczą wybranej strony; jej zmiana zdejmuje nałożone poprawki.`,
  frames: `Częsty błąd: projektant robi projekt na stronie wytycznych i zapomina wyłączyć warstwę
    z szablonem — na wydruk idzie wtedy cyjanowa ramka formatu, czerwona ramka obszaru
    bezpiecznego i napisy ze środka.<br><br>
    Program porównuje <b>cały szablon z wytycznych</b> tego produktu — ramki, ich kolory i położenie —
    z tym, co jest w pliku. Kilka milimetrów różnicy (starsza wersja szablonu, pokrewny produkt)
    nie przeszkadza. „Usuń szablon" kasuje dokładnie te linie i napisy; suwak pokazuje różnicę.<br><br>
    Program sprawdza też, czy szablon <b>w ogóle widać</b>: jeśli leży pod grafiką i nic z niego
    nie wychodzi na wierzch, nie drukuje się — wtedy nic nie trzeba robić.<br><br>
    Linii wtopionych w obraz (piksele) usunąć się nie da — wtedy trzeba poprosić klienta
    o plik bez szablonu.`,
  trim: `Spad to zapas treści poza formatem, żeby przy krojeniu nie został biały brzeg. W wielkim
    formacie Adsystem spadów się nie stosuje: plik ma mieć dokładnie format z wytycznych.<br><br>
    Gdzie ciąć, program wie z <b>ramek PDF-a</b> (TrimBox), które zapisuje każdy porządny eksport.
    Gdy ich nie ma, sprawdza, czy strona jest równomiernie większa od formatu z wytycznych.<br><br>
    Przycięcie niczego nie przerysowuje — zmienia tylko ramki strony, treść zostaje bit w bit ta sama.`,
  size: `Porównujemy wymiar pliku z wytycznymi. „Dopasuj wymiar" buduje nową stronę w formacie
    z wytycznych: projekt wchodzi jako całość (wektor zostaje wektorem), nadmiar jest przycinany.<br><br>
    <b>Wielkość</b> w procentach: 100 % = projekt w swoim rozmiarze. Skróty ustawiają „wypełnij format"
    (bez pustych pasów, coś zostanie odcięte) albo „cały projekt" (nic nie odcięte, mogą zostać pasy).
    <b>Przeskalowanie pliku</b> (zwinięte) przydaje się, gdy plik przyszedł w złej skali, np. 1:1 zamiast
    1:10 — wtedy ÷10 albo ×10. „Bez zmian” znaczy, że plik zostaje w skali wytycznych (przy wytycznych
    1:10 drukuje się 10× większy).<br><br>
    Puste pasy można wypełnić <b>tłem z krawędzi</b> (ostatni rząd pikseli projektu powielony na
    margines) albo <b>odbiciem lustrzanym</b>. Na podglądzie zielona ramka to format, a to, co poza
    nią (przyciemnione), zostanie odcięte.<br><br>
    <b>Przesuń</b> działa aż do przeciwnej krawędzi formatu. Suwak lekko „przyciąga" do środka
    i do położeń, w których krawędź projektu równa się z krawędzią formatu. Dwuklik na suwaku = środek.
    Dokładną wartość wpiszesz w pole obok: mm na wydruku od środka, plus = w prawo / w dół,
    minus = w lewo / w górę.`,
  print: `Od tego rozdziału <b>podgląd pokazuje wydruk</b>, nie ekran: kolory tak, jak przeliczy je
    drukarnia (profilem zapisanym w pliku, np. ISO Coated v2, a gdy plik go nie ma — Coated FOGRA39;
    intencja relatywna kolorymetryczna), i overprint, tak jak zrobi to maszyna. Zdjęcie, które już
    jest w CMYK, wygląda więc po obu stronach suwaka tak samo.<br><br>
    Ekran i wydruk zawsze się różnią. Monitor świeci, a farba tylko odbija światło, więc bardzo
    nasycone kolory (czysta zieleń, jaskrawy niebieski) w druku bledną. Przezroczystość drukarnia
    miesza w przestrzeni zapisanej w pliku, a czerń z samej farby K drukuje się grafitem.<br><br>
    Każdy dalszy suwak przed/po (Kolory, Overprint, Fonty, Spłaszczenie) porównuje <b>wydruk
    z wydrukiem</b> — widać tylko to, co zmieniła sama poprawka, a nie różnicę ekran–druk.`,
  color: `Maszyny drukują czterema farbami — <b>CMYK</b>. Kolory RGB (ekranowe), Lab i dodatkowe
    (PANTONE, złoto, Registration) ktoś musi przeliczyć; lepiej zrobić to tutaj i zobaczyć wynik.<br><br>
    Przeliczamy tak jak Photoshop przy „Konwertuj do profilu": RGB jako sRGB, profil
    <b>Coated FOGRA39</b>, intencja relatywna kolorymetryczna z kompensacją punktu czerni.
    CMYK, który już jest w pliku, zostaje nietknięty.<br><br>
    Wybierasz w rzędach: <b>Zamień na CMYK</b> albo <b>Zostaw jak jest</b>, a przy zamianie profil.
    Po zamianie suwak porównuje wydruk przed nią z wydrukiem po niej. „Zostaw jak jest” — podgląd
    pokazuje, jak kolory przeliczy drukarnia.<br><br>
    <b>Profil</b> tylko deklaruje, pod jaką maszynę jest plik. Gdy plik ma już swój profil CMYK
    (np. ISO Coated v2), można go zostawić („Z pliku").<br><br>
    Uwaga na <b>półprzezroczystość na jaskrawych kolorach RGB</b>: bez zamiany drukarnia najpierw
    miesza kolory, a potem je przelicza; po zamianie jest odwrotnie. Wynik w tych miejscach potrafi
    się wyraźnie różnić — porównaj suwakiem.<br><br>
    <b>Za dużo farby:</b> program liczy, ile farby maszyna położy w jednym miejscu (suma C+M+Y+K).
    Powyżej 360 % farba może nie schnąć i się rozmazywać — zwykle to czerń 100/100/100/100 albo kolor
    „Registration”. Gdy to <b>jednolita</b> czerń (pole, napis, linia), przycisk <b>Popraw czerń</b> zamienia ją
    na zalecaną czerń Adsystem <b>C78 M85 Y90 K100</b> (353 %). Czerni w obrazie ani w przejściu tonalnym
    program nie poprawi — wtedy trzeba poprosić klienta.`,
  op: `<b>Overprint</b> (nadruk) każe farbie kłaść się NA tło zamiast je zakrywać. Czerwony napis
    na czarnym tle wychodzi wtedy prawie czarny, choć na ekranie był czerwony. Większość
    programów na ekranie tego nie pokazuje — nasz podgląd pokazuje (to już wydruk).<br><br>
    Wytyczne Adsystem overprintu nie dopuszczają. „Wyłącz overprint" sprawia, że wydrukuje się
    to, co widać w projekcie; suwak porówna wydruk przed i po. „Zostaw jak jest" zostawia
    overprint.<br><br>
    <b>Biel z overprintem</b> w druku może zniknąć zupełnie (biała farba nie istnieje — biel to brak farby,
    a overprint każe nie zakrywać tła). Program zaznacza takie miejsca na podglądzie (ramki widać w tym rozdziale).`,
  fonts: `Tekst zapisany fontem drukarnia musi „złożyć" swoim programem — gdy fontu brakuje albo
    jest inna wersja, litery się zmieniają. <b>Krzywe</b> to gotowe kształty liter: wyglądają
    identycznie, tylko nie da się ich już edytować jako tekstu.<br><br>
    Kształty bierzemy z fontu <b>osadzonego w pliku</b>. Gdy fontu w pliku nie ma, program szuka go
    w Google Fonts, potem w fontach Windowsa. Gdy nie znajdzie, zamieni mimo to — litery dostaną
    kształt <b>kroju zastępczego</b>; program to powie, a na podglądzie zaznaczy je pomarańczową
    ramką. Wtedy najlepiej poprosić klienta o PDF z osadzonymi fontami.<br><br>
    Wybierasz <b>Zamień na krzywe</b> albo <b>Zostaw jak jest</b>.`,
  flat: `<b>Spłaszczenie</b> zamienia całą stronę w jeden obraz CMYK — jak „Spłaszcz” w Photoshopie.<br><br>
    <b>Używaj go tylko wtedy, gdy to konieczne.</b> Przezroczystość (cienie, półprzezroczyste
    elementy, tryby mieszania) drukarnia i tak spłaszcza przy druku i zwykle robi to lepiej:
    tekst i linie zostają wektorowe, a plik jest mniejszy. Spłaszcz tutaj, gdy drukarnia o to
    prosi albo gdy podgląd pokazuje ślady — szew albo jasną obwódkę tam, gdzie
    przezroczystość spotyka się z kolorem dodatkowym lub overprintem.<br><br>
    Rozdzielczość: zawsze <b>120 ppi na wydruku</b>, jak w ustaleniach z drukarnią. Cena: tekst i linie
    przestają być wektorowe, plik robi się większy. Tekst fontem, którego nie ma w pliku, spłaszczy się
    krojem zastępczym — program ostrzeże i zaznaczy go na podglądzie.<br><br>
Gdy strona <b>już jest jednym obrazem</b> (np. eksport z Photoshopa), program niczego nie spłaszcza —
    przeliczanie gotowych pikseli dałoby tylko drobne ząbki na krawędziach.<br><br>
    Wybierasz <b>Zostaw jak jest</b> albo <b>Spłaszcz projekt</b>. Gdy projekt nie ma
    przezroczystości, wystarczy <b>Zostaw jak jest</b>.`,
  qual: `Program otwiera każdy obraz w projekcie i czyta jego piksele. Sprawdza dwie rzeczy:<br><br>
    1) czy obraz ma <b>dość pikseli</b> na swój rozmiar na wydruku — wytyczne wymagają
    <b>120 ppi</b> (w pliku 1:10 to 1200 ppi w pliku). Za mało = rozmycie i schodki, trzeba
    wymienić obraz na większy;<br>
    2) czy piksele <b>niosą szczegół</b> — obraz powiększony z małego pliku ma dużo pikseli,
    ale nic w nich nie ma. To trzeba obejrzeć: bywa też zwykłym rozmyciem ze zdjęcia.<br><br>
    „Pokaż na podglądzie" przechodzi po takich miejscach (strzałki ← →) w <b>rzeczywistej
    wielkości wydruku</b>. Wektor (napisy, kształty) nie ma rozdzielczości i nie jest oceniany.
    Lupki, rzeczywistą wielkość i nawigator masz w panelu nad podglądem — tylko w tym rozdziale.<br><br>
    Program sprawdza też <b>cienkie linie</b> (cieńsze niż 0,25 mm na wydruku albo „hairline” o grubości 0 —
    mogą się nie wydrukować) i <b>tekst poza obszarem bezpiecznym</b> (czerwona ramka z wytycznych — przy
    krawędzi napis może zostać ucięty albo schowany w ramie). Zaznacza je na podglądzie; poprawić można
    w rozdziale Wymiar wydruku (przesunięcie, wielkość) albo u klienta.<br><br>
    <b>Uwaga:</b> ocena jest automatyczna i orientacyjna. Program może ocenić niektóre obrazy
    inaczej niż grafik i nie wychwyci każdego problemu — w razie wątpliwości poproś grafika
    o sprawdzenie.`,
  dl: `Pobierasz ostatnią wersję pliku — ze wszystkimi poprawkami. Zawsze <b>jedną stronę</b>:
    PDF-a z kilkoma stronami nie wysyłamy do druku nigdy. Nazwa pliku to produkt i rola, bez
    wymiarów. Oryginał zostaje nietknięty.`,
  acc: `Ostatnie spojrzenie przed pobraniem. <b>Pokaż wydruk przed i po</b> porównuje, jak plik
    wydrukowałby się bez poprawek z rozdziałów Kolory, Overprint, Fonty i Spłaszczenie, z tym,
    jak wydrukuje się teraz — oba tak, jak zrobi to drukarnia (kolory z drukarki, overprint).
    Suwak startuje od „po” — tak, jak plik pójdzie do druku. Gdy wszystko gra — <b>Akceptuję plik</b>. Każda późniejsza zmiana
    pliku zdejmuje akceptację.`,
};
