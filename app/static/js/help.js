// Wyjaśnienia pod „?" w każdym rozdziale. Rozdział pokazuje tylko stan i przycisk
// (uwaga Tomasza: ma być jak najmniej na ekranie) — całe „po co i jak" siedzi tutaj.
export const HELP = {
  file: `Wgraj plik, który ma iść do druku: PDF (najlepiej), AI, EPS, SVG albo obraz (JPG, PNG, TIFF).
    CorelDRAW, InDesign i PSD trzeba najpierw wyeksportować do PDF.<br><br>
    Oryginał nigdy nie jest zmieniany — każda poprawka tworzy nową wersję obok, a na końcu
    pobierasz gotowy plik.`,
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
    <b>Skala projektu</b> (zwinięta) przydaje się, gdy plik przyszedł w złej skali, np. 1:1 zamiast 1:10.<br><br>
    Puste pasy można wypełnić <b>tłem z krawędzi</b> (ostatni rząd pikseli projektu powielony na
    margines) albo <b>odbiciem lustrzanym</b>. Na podglądzie zielona ramka to format, a to, co poza
    nią (przyciemnione), zostanie odcięte.<br><br>
    <b>Przesuń</b> działa aż do przeciwnej krawędzi formatu. Suwak lekko „przyciąga" do środka
    i do położeń, w których krawędź projektu równa się z krawędzią formatu. Dwuklik na suwaku = środek.`,
  color: `Maszyny drukują czterema farbami — <b>CMYK</b>. Kolory RGB (ekranowe), Lab i dodatkowe
    (PANTONE, złoto, Registration) ktoś musi przeliczyć; lepiej zrobić to tutaj i zobaczyć wynik.<br><br>
    Przeliczamy tak jak Photoshop przy „Konwertuj do profilu": RGB jako sRGB, profil
    <b>Coated FOGRA39</b>, intencja relatywna kolorymetryczna z kompensacją punktu czerni.
    CMYK, który już jest w pliku, zostaje nietknięty.<br><br>
    Wybierasz w rzędach: najpierw <b>Zamień na CMYK</b> albo <b>Zostaw jak jest</b>, przy zamianie
    profil, a na końcu zawsze <b>Pokaż, jak wydrukuje</b> — suwak porówna ekran z tym, co wyjdzie
    z drukarki. Dalej idziesz, gdy w każdym rzędzie coś wybierzesz.
    Kolory bardzo nasycone (czysta zieleń, jaskrawy niebieski) w druku zawsze bledną — farby ich
    nie mają.<br><br>
    <b>Profil</b> tylko deklaruje, pod jaką maszynę jest plik. Gdy plik ma już swój profil CMYK
    (np. ISO Coated v2), można go zostawić („Z pliku").<br><br>
    Po tym rozdziale (zamiana albo „Zostaw jak jest") <b>podgląd pokazuje już wydruk</b>, nie
    ekran: drukarnia miesza przezroczystość w CMYK, a czerń z samej farby K drukuje się grafitem.`,
  op: `<b>Overprint</b> (nadruk) każe farbie kłaść się NA tło zamiast je zakrywać. Czerwony napis
    na czarnym tle wychodzi wtedy prawie czarny, choć na ekranie był czerwony. Większość
    programów na ekranie tego nie pokazuje — dlatego „Pokaż, jak wydrukuje".<br><br>
    Wytyczne Adsystem overprintu nie dopuszczają. „Wyłącz overprint" sprawia, że wydrukuje się
    to, co widać w projekcie. „Zostaw jak jest" przełącza podgląd na wydruk z overprintem.
    Dalej idziesz po „Pokaż, jak wydrukuje".`,
  fonts: `Tekst zapisany fontem drukarnia musi „złożyć" swoim programem — gdy fontu brakuje albo
    jest inna wersja, litery się zmieniają. <b>Krzywe</b> to gotowe kształty liter: wyglądają
    identycznie, tylko nie da się ich już edytować jako tekstu.<br><br>
    Kształty bierzemy z fontu <b>osadzonego w pliku</b>. Gdy fontu w pliku nie ma, program szuka go
    w Google Fonts, potem w fontach Windowsa. Kroju zastępczego nie używa nigdy — wtedy odmówi
    i powie, o co poprosić klienta.<br><br>
    Wybierasz w rzędach: <b>Zamień na krzywe</b> albo <b>Zostaw jak jest</b>, a potem
    <b>Pokaż, jak wydrukuje</b>.`,
  flat: `<b>Spłaszczenie</b> zamienia całą stronę w jeden obraz CMYK — jak „Spłaszcz" w Photoshopie.<br><br>
    Po co: przezroczystość (cienie, półprzezroczyste elementy, tryby mieszania) drukarnia i tak
    spłaszcza przed drukiem, a tam, gdzie spotyka się z kolorem dodatkowym albo overprintem,
    potrafi zostawić szew albo jasną obwódkę. Spłaszczone tutaj — widzisz dokładnie to, co
    pójdzie na maszynę.<br><br>
    Rozdzielczość zależy od wielkości wydruku: 300 ppi do 80 cm, 200 ppi do 1,5 m, 150 ppi do 3 m,
    wyżej 120 ppi. Cena: tekst i linie przestają być wektorowe, plik robi się większy.<br><br>
    Wybierasz w rzędach: <b>Spłaszcz projekt</b> albo <b>Zostaw jak jest</b>, a potem
    <b>Pokaż, jak wydrukuje</b>. Gdy projekt nie ma przezroczystości, wystarczy <b>Zostaw jak
    jest</b> — rozdział od razu się zamyka (spłaszczyć można i tak).`,
  qual: `Program otwiera każdy obraz w projekcie i czyta jego piksele. Sprawdza dwie rzeczy:<br><br>
    1) czy obraz ma <b>dość pikseli</b> na swój rozmiar na wydruku — wytyczne wymagają
    <b>120 ppi</b> (w pliku 1:10 to 1200 ppi w pliku). Za mało = rozmycie i schodki, trzeba
    wymienić obraz na większy;<br>
    2) czy piksele <b>niosą szczegół</b> — obraz powiększony z małego pliku ma dużo pikseli,
    ale nic w nich nie ma. To trzeba obejrzeć: bywa też zwykłym rozmyciem ze zdjęcia.<br><br>
    „Pokaż na podglądzie" przechodzi po takich miejscach (strzałki ← →) w <b>rzeczywistej
    wielkości wydruku</b>. Wektor (napisy, kształty) nie ma rozdzielczości i nie jest oceniany.
    Dokładność oceny ustawisz w Ustawieniach.`,
  dl: `Pobierasz ostatnią wersję pliku — ze wszystkimi poprawkami. Zawsze <b>jedną stronę</b>:
    PDF-a z kilkoma stronami nie wysyłamy do druku nigdy. Nazwa pliku to produkt i rola, bez
    wymiarów. Oryginał zostaje nietknięty.`,
  acc: `Ostatnie spojrzenie przed pobraniem. <b>Pokaż wydruk przed i po</b> porównuje, jak plik
    wydrukowałby się bez poprawek z rozdziałów Kolory, Overprint, Fonty i Spłaszczenie, z tym,
    jak wydrukuje się teraz — oba tak, jak zrobi to drukarnia (kolory z drukarki, overprint).
    Suwak startuje od „przed". Gdy wszystko gra — <b>Akceptuję plik</b>. Każda późniejsza zmiana
    pliku zdejmuje akceptację.`,
};
