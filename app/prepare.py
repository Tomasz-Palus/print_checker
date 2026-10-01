"""Przygotowanie wgranego PDF-a: plik ma drukować się TAK SAMO w każdej drukarni.

Dwie rzeczy w PDF-ie zależą od programu, który go otwiera:

  • Warstwy (Optional Content, OCG) — warstwa może być ukryta na ekranie, a drukować się
    (albo odwrotnie: Illustrator „nie drukuj”, pomocnicze linie, szablon zostawiony na
    wyłączonej warstwie). Starsze RIP-y warstwy ignorują i drukują WSZYSTKO.
  • Adnotacje — stemple, komentarze, pola formularza z Acrobata. Drukują się tylko z flagą
    „Print”, a RIP-y różnie to traktują; podgląd (MuPDF) rysuje je wszystkie.

Tu ustalamy stan DO DRUKU (tak, jak drukuje Acrobat) i wpisujemy go na stałe w treść strony:
treść ukrytych warstw i niedrukowane adnotacje znikają, wygląd drukowanych adnotacji staje
się zwykłą treścią. Od tej chwili podgląd = wydruk, a analiza nie liczy rzeczy, które się
nie drukują (przegląd kodu 27.09, „Ukryte warstwy (OCG)” i A7; Tomasz 29.09 — „edge cases”).

Plus: strona ponad 200 cali (≈ 5 m) — przy pobieraniu wraca UserUnit, żeby Acrobat i RIP-y
przyjęły jej wymiar (render.normalize_geometry wpisuje UserUnit w treść przy wgraniu).
"""
from __future__ import annotations

import math
import os

import pikepdf

PDF_MAX_PT = 14400.0            # 200 cali — największa strona, jaką przyjmuje Acrobat

ANNOT_NAMES = {"/Stamp": "stempel", "/FreeText": "pole tekstowe", "/Text": "komentarz", "/Widget": "pole formularza",
               "/Square": "prostokąt", "/Circle": "elipsa", "/Line": "linia", "/Ink": "odręczny rysunek",
               "/Highlight": "zakreślenie", "/Underline": "podkreślenie", "/StrikeOut": "przekreślenie",
               "/Polygon": "wielokąt", "/PolyLine": "łamana", "/FileAttachment": "załącznik",
               "/Caret": "znak wstawienia", "/Squiggly": "falista linia", "/Watermark": "znak wodny"}
SKIP_ANNOTS = {"/Link", "/Popup"}       # nic nie rysują


def _key(o):
    try:
        g = tuple(o.objgen)
        return g if g != (0, 0) else id(o)
    except Exception:
        return id(o)


# ----------------------------------------------------------------------------
# warstwy
# ----------------------------------------------------------------------------
class _Layers:
    """Stan warstw do druku: {klucz OCG: (nazwa, widoczna na ekranie, drukuje się)}."""

    def __init__(self, pdf):
        self.ocgs = {}
        ocp = pdf.Root.get("/OCProperties")
        if ocp is None:
            return
        d = ocp.get("/D") or pikepdf.Dictionary()
        base = str(d.get("/BaseState", "/ON")) != "/OFF"
        on = {_key(x) for x in (d.get("/ON") or [])}
        off = {_key(x) for x in (d.get("/OFF") or [])}
        # Acrobat przy druku stosuje /PrintState, gdy konfiguracja ma zdarzenie /Print w /AS
        # (tak zapisuje Illustrator warstwy „nie drukuj”); bez /AS też ją uwzględniamy — lepiej
        # zgodzić się z intencją autora niż z ekranem.
        for g in (ocp.get("/OCGs") or []):
            k = _key(g)
            view = (k in on) or (base and k not in off)
            prn = view
            try:
                ps = g.get("/Usage", {}).get("/Print", {}).get("/PrintState")
                if ps is not None:
                    prn = str(ps) == "/ON"
            except Exception:
                pass
            self.ocgs[k] = (str(g.get("/Name", "bez nazwy")), view, prn)

    def printed(self, oc) -> bool:
        """Czy treść z tym /OC (warstwa albo OCMD) się drukuje. Nieznane = drukuje się."""
        try:
            if str(oc.get("/Type", "")) == "/OCMD":
                gs = oc.get("/OCGs")
                if gs is None:
                    return True
                gs = [gs] if isinstance(gs, pikepdf.Dictionary) else list(gs)
                st = [self.ocgs.get(_key(g), ("", True, True))[2] for g in gs]
                p = str(oc.get("/P", "/AnyOn"))
                return {"/AllOn": all(st), "/AnyOff": not all(st), "/AllOff": not any(st)}.get(p, any(st))
            return self.ocgs.get(_key(oc), ("", True, True))[2]
        except Exception:
            return True


def _strip_oc(pdf, container, resources, L: _Layers, done: set, stats: dict, depth=0):
    """Wycina z treści to, co leży na niedrukowanej warstwie; znaczniki warstw zamienia na
    zwykłe (bez /OC), więc po usunięciu /OCProperties nic nie zależy od programu."""
    ck = _key(container.obj if isinstance(container, pikepdf.Page) else container)
    if depth > 12 or ck in done:
        return
    done.add(ck)
    try:
        ops = list(pikepdf.parse_content_stream(container))
    except Exception:
        return
    props = resources.get("/Properties") if resources is not None else None
    xobj = resources.get("/XObject") if resources is not None else None
    out, skip, changed = [], 0, False      # skip = głębokość znaczników wewnątrz ukrytej warstwy
    for ins in ops:
        # obraz wpisany w treść (BI … ID … EI) przepisujemy bez zmian — rozebrany na (operandy, operator)
        # nie dał się złożyć z powrotem („don't know how to encode value PdfInlineImage”) i „Popraw czerń”
        # padała po cichu (Tomasz 01.10, plik z gs 10.07)
        if isinstance(ins, pikepdf.ContentStreamInlineImage):
            out.append(ins)
            continue
        operands, op = ins.operands, ins.operator
        o = str(op)
        if skip:
            changed = True
            if o in ("BMC", "BDC"):
                skip += 1
            elif o == "EMC":
                skip -= 1
            continue
        if o == "BDC" and len(operands) == 2 and str(operands[0]) == "/OC":
            oc = operands[1]
            if isinstance(oc, pikepdf.Name):
                oc = props.get(oc) if props is not None else None
            if oc is not None and not L.printed(oc):
                skip, changed = 1, True
                stats["removed"] += 1
                continue
            out.append(pikepdf.ContentStreamInstruction([pikepdf.Name("/OC")], pikepdf.Operator("BMC")))
            changed = True
            continue
        if o == "Do" and xobj is not None and operands and operands[0] in xobj:
            xo = xobj[operands[0]]
            oc = xo.get("/OC")
            if oc is not None and not L.printed(oc):
                changed = True
                stats["removed"] += 1
                continue
            if oc is not None:
                del xo["/OC"]
            if str(xo.get("/Subtype", "")) == "/Form":
                _strip_oc(pdf, xo, xo.get("/Resources") or resources, L, done, stats, depth + 1)
        out.append(pikepdf.ContentStreamInstruction(operands, op))
    if changed:
        data = pikepdf.unparse_content_stream(out)
        if isinstance(container, pikepdf.Page):
            container.obj.Contents = pdf.make_stream(data)
        else:
            container.write(data)


# ----------------------------------------------------------------------------
# adnotacje
# ----------------------------------------------------------------------------
def _annot_ctm(form, rect):
    import analyze
    return analyze._annot_ctm(form, rect)


def _bake_annots(pdf, page, L: _Layers | None, stats: dict):
    """Drukowane adnotacje → treść strony (ich wygląd /AP /N); reszta znika."""
    o = page.obj
    annots = o.get("/Annots")
    if not annots:
        return
    keep, cmds = [], []
    xo_dict = None
    for i, an in enumerate(list(annots)):
        try:
            sub = str(an.get("/Subtype", ""))
            if sub in SKIP_ANNOTS:
                continue
            name = ANNOT_NAMES.get(sub, sub.lstrip("/").lower() or "adnotacja")
            flags = int(an.get("/F", 0))
            oc = an.get("/OC")
            prints = bool(flags & 4) and not flags & 2 and (oc is None or L is None or L.printed(oc))
            n = an.get("/AP", {}).get("/N") if an.get("/AP") is not None else None
            if n is not None and not isinstance(n, pikepdf.Stream):
                st = an.get("/AS")
                n = n.get(st) if st is not None else None
            if not prints or not isinstance(n, pikepdf.Stream) or an.get("/Rect") is None:
                stats["annots_off"].append(name)
                continue
            if "/OC" in n:
                del n["/OC"]
            if xo_dict is None:
                res = o.get("/Resources")
                if res is None:
                    o.Resources = pikepdf.Dictionary()
                    res = o.Resources
                if "/XObject" not in res:
                    res.XObject = pikepdf.Dictionary()
                xo_dict = res.XObject
            nm = f"/adAnnot{i}"
            while nm in xo_dict:
                nm += "x"
            xo_dict[nm] = n if n.is_indirect else pdf.make_indirect(n)
            m = _annot_ctm(n, an.get("/Rect"))
            cmds.append("q " + " ".join(f"{v:.6f}".rstrip("0").rstrip(".") or "0" for v in m) + f" cm {nm} Do Q")
            stats["annots_on"].append(name)
        except Exception:
            stats["annots_off"].append("adnotacja")
    if cmds:
        page.contents_add(pdf.make_stream(b"q\n"), prepend=True)
        page.contents_add(pdf.make_stream(("\nQ\n" + "\n".join(cmds) + "\n").encode()), prepend=False)
    # linki zostają (nic nie rysują), reszta znika — okienka komentarzy (/Popup) razem z nimi
    o.Annots = pikepdf.Array([a for a in annots if str(a.get("/Subtype", "")) == "/Link"])
    if not len(o.Annots):
        del o["/Annots"]


def _fmt_list(names: list) -> str:
    from collections import Counter
    c = Counter(names)
    return ", ".join(f"{n} ×{k}" if k > 1 else n for n, k in c.most_common())


def bake_print_state(path: str) -> tuple[str, list]:
    """Warstwy i adnotacje w stanie do druku, wpisane na stałe. Zwraca (ścieżka, notatki dla
    użytkownika); bez warstw i adnotacji — ta sama ścieżka i pusta lista."""
    try:
        pdf = pikepdf.open(path)
    except Exception:
        return path, []
    notes = []
    try:
        has_oc = "/OCProperties" in pdf.Root
        has_an = any(p.obj.get("/Annots") for p in pdf.pages)
        has_form = "/AcroForm" in pdf.Root
        if not (has_oc or has_an or has_form):
            return path, []
        L = _Layers(pdf) if has_oc else None
        stats = {"removed": 0, "annots_on": [], "annots_off": []}
        if L is not None:
            done = set()
            for page in pdf.pages:
                _strip_oc(pdf, page, page.obj.get("/Resources"), L, done, stats)
        for page in pdf.pages:
            _bake_annots(pdf, page, L, stats)
        if L is not None:
            del pdf.Root["/OCProperties"]
            hidden = [n for n, v, p in L.ocgs.values() if not p]
            np_view = [n for n, v, p in L.ocgs.values() if v and not p]     # widać na ekranie, nie drukuje się
            shown = [n for n, v, p in L.ocgs.values() if p and not v]       # ukryta na ekranie, ale drukuje się
            if hidden:
                txt = "warstwy, które się nie drukują: " + ", ".join(f"„{n}”" for n in hidden[:6]) + " — usunięte z pliku"
                if np_view:
                    txt += " (" + ", ".join(f"„{n}”" for n in np_view[:4]) + " widać na ekranie, ale ma ustawione „nie drukuj”)"
                notes.append(txt)
            if shown:
                notes.append("warstwy ukryte na ekranie, ale drukowane: " + ", ".join(f"„{n}”" for n in shown[:6])
                             + " — zostają i są widoczne na podglądzie")
            if not hidden and not shown:
                notes.append(f"warstwy ({len(L.ocgs)}) — wszystkie się drukują, połączone w jedną")
        if has_form:
            del pdf.Root["/AcroForm"]
        if stats["annots_on"]:
            notes.append("adnotacje, które się drukują: " + _fmt_list(stats["annots_on"]) + " — wpisane w stronę")
        if stats["annots_off"]:
            notes.append("adnotacje, które się nie drukują: " + _fmt_list(stats["annots_off"]) + " — usunięte")
        out = os.path.splitext(path)[0] + "_druk.pdf"
        pdf.save(out)
    finally:
        pdf.close()
    return out, notes


# ----------------------------------------------------------------------------
# pobieranie: strona ponad 200 cali dostaje z powrotem UserUnit
# ----------------------------------------------------------------------------
def user_unit_for(w_pt: float, h_pt: float) -> int:
    """1 dla zwykłej strony, inaczej najmniejsza całkowita jednostka, przy której strona
    mieści się w 14 400 pt (Illustrator używa zwykle 10)."""
    big = max(w_pt, h_pt)
    return 1 if big <= PDF_MAX_PT + 0.01 else int(math.ceil(big / PDF_MAX_PT))


def with_user_unit(pdf, page, u: int) -> None:
    """Treść i pola strony zmniejszone u razy + /UserUnit u: wydruk wychodzi tej samej wielkości."""
    k = 1.0 / u
    o = page.obj
    page.contents_add(pdf.make_stream(f"q {k:.8f} 0 0 {k:.8f} 0 0 cm\n".encode()), prepend=True)
    page.contents_add(pdf.make_stream(b"\nQ\n"), prepend=False)
    for key in ("/MediaBox", "/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"):
        b = o.get(key)
        if b is not None:
            o[key] = pikepdf.Array([float(v) * k for v in b])
    res = o.get("/Resources")
    pats = res.get("/Pattern") if res is not None else None
    if pats is not None:        # wzory liczą się w przestrzeni strony, nie w bieżącej macierzy
        newp = pikepdf.Dictionary()
        for name, pat in pats.items():
            pm = [float(x) for x in pat.get("/Matrix", [1, 0, 0, 1, 0, 0])]
            if isinstance(pat, pikepdf.Stream):
                cp = pikepdf.Stream(pdf, pat.read_raw_bytes())
                for k2, v2 in pat.items():
                    if k2 != "/Length":
                        cp[k2] = v2
            else:
                cp = pikepdf.Dictionary({k2: v2 for k2, v2 in pat.items()})
            cp["/Matrix"] = pikepdf.Array([v * k for v in pm])
            newp[name] = pdf.make_indirect(cp)
        res = pikepdf.Dictionary({k2: v2 for k2, v2 in res.items()})
        res["/Pattern"] = newp
        o["/Resources"] = res
    for an in (o.get("/Annots") or []):
        r = an.get("/Rect")
        if r is not None:
            an["/Rect"] = pikepdf.Array([float(v) * k for v in r])
    o["/UserUnit"] = u


# ----------------------------------------------------------------------------
# hasło i uszkodzenia — przed wszystkim innym
# ----------------------------------------------------------------------------
class Unreadable(Exception):
    """Pliku nie da się otworzyć — komunikat jest dla użytkownika."""


def looks_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return b"%PDF" in f.read(1024)
    except OSError:
        return False


def check_open(path: str) -> tuple[str, list]:
    """Czy PDF da się w ogóle czytać. Hasło do otwarcia i zniszczony plik = jasny komunikat
    (dawniej: „Nie udało się otworzyć pliku: PasswordError…”). Hasło tylko do uprawnień
    (drukowanie / edycja) zdejmujemy — plik i tak otwiera się bez niego, a Ghostscript
    i niektóre RIP-y potrafią się na nim zatrzymać. Plik naprawiony przy otwarciu = notatka."""
    notes = []
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    if size < 64:
        raise Unreadable("Plik jest pusty albo niepełny (mniej niż 64 bajty) — wgraj go jeszcze raz "
                         "albo poproś klienta o ponowne przesłanie.")
    with open(path, "rb") as f:
        head = f.read(1024)
    if b"%PDF" not in head:
        raise Unreadable("To nie jest PDF, choć ma takie rozszerzenie (w środku nie ma nagłówka PDF). "
                         "Poproś klienta o prawidłowy eksport do PDF.")
    try:
        pdf = pikepdf.open(path)
    except pikepdf.PasswordError:
        raise Unreadable("Plik jest zabezpieczony hasłem — bez hasła nie da się go otworzyć ani wydrukować. "
                         "Poproś klienta o PDF bez hasła.")
    except Exception as e:
        raise Unreadable("Plik PDF jest uszkodzony i nie da się go odczytać "
                         f"({type(e).__name__}). Poproś klienta o ponowny eksport do PDF.")
    try:
        if len(pdf.pages) < 1:
            raise Unreadable("PDF nie ma żadnej strony — poproś klienta o ponowny eksport.")
        warn = []
        try:
            warn = list(pdf.get_warnings())
        except Exception:
            pass
        enc = pdf.is_encrypted
        if not enc and not warn:
            return path, []
        out = os.path.splitext(path)[0] + "_otwarty.pdf"
        pdf.save(out)                       # bez `encryption` = zapis bez zabezpieczeń
        if enc:
            notes.append("zabezpieczenie pliku (hasło do uprawnień: drukowanie / edycja) zdjęte — "
                         "bez niego drukarnia może odmówić druku")
        if warn:
            notes.append("plik był uszkodzony i został naprawiony przy otwarciu — obejrzyj dokładnie podgląd, "
                         "czy niczego nie brakuje")
        return out, notes
    finally:
        pdf.close()
