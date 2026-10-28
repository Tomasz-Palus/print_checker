"""Wytyczne i projekty z błędami szablonu (testy adCheckera)."""
import io, os
import numpy as np, pikepdf
from PIL import Image, ImageDraw
P = 72 / 25.4                       # pt na mm
OUT = "szablony"; os.makedirs(OUT, exist_ok=True)
CYAN, RED = "1 0 0 0", "0 0.947 0.912 0"

def ring(x, y, w, h, t, col, H):
    """Wypełniona ramka (zewn. − wewn., parzysto-nieparzyste) w mm, y od góry strony H mm."""
    X, Y = x * P, (H - y - h) * P
    return (f"{col} k {X:.2f} {Y:.2f} {w*P:.2f} {h*P:.2f} re {(x+t)*P:.2f} {(H-y-h+t)*P:.2f} "
            f"{(w-2*t)*P:.2f} {(h-2*t)*P:.2f} re f* ")

def text(pdf, s, x, y, size_mm, H, font="F1", col="0 0 0 1"):
    return f"BT /{font} {size_mm*P:.2f} Tf {col} k {x*P:.2f} {(H-y)*P:.2f} Td ({s}) Tj ET "

def fonts(pdf):
    return pikepdf.Dictionary(F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica),
                              F2=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name("/Type1"), BaseFont=pikepdf.Name("/Helvetica-Bold")))

def template(W, H, s=1.0, dx=0, dy=0):
    """Szablon produktu: cyjanowy kształt (krawędź), czerwony obszar ochronny (50 mm w głąb), napisy."""
    t = 2 * s
    c = ring(dx, dy, W, H, t, CYAN, H) + ring(dx + 50 * s, dy + 50 * s, W - 100 * s, H - 100 * s, t, RED, H)
    return c

def template_txt(pdf, W, H, s=1.0, dx=0, dy=0):
    return (text(pdf, "Front", dx + W / 2 - 60 * s, dy + H / 2, 40 * s, H, "F2", CYAN)
            + text(pdf, f"{round(W)} x {round(H)} [mm]", dx + W / 2 - 110 * s, dy + H / 2 + 60 * s, 30 * s, H, "F1", CYAN)
            + text(pdf, "Linia ciecia", dx + 60 * s, dy + H - 20 * s, 12 * s, H, "F1", RED))

def design(W, H, s=1.0):
    """Projekt klienta: granatowe tło, pomarańczowy pas, napis."""
    return (f"0.9 0.7 0.1 0.4 k 0 0 {W*P:.2f} {H*P:.2f} re f "
            f"0 0.6 0.9 0 k {100*s*P:.2f} {(H-700*s)*P:.2f} {(W-200*s)*P:.2f} {300*s*P:.2f} re f "
            + text(None, "WYPRZEDAZ 2026", 150 * s, 600 * s, 90 * s, H, "F2", "0 0 0 0"))

def save(name, W, H, content, xobj=None):
    pdf = pikepdf.new()
    res = pikepdf.Dictionary(Font=fonts(pdf))
    if xobj:
        res.XObject = pikepdf.Dictionary({"/" + k: v(pdf) for k, v in xobj.items()})
    pdf.pages.append(pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, W * P, H * P],
                                                     Resources=res, Contents=pdf.make_stream(content.encode()))))
    pdf.save(os.path.join(OUT, name))

W, H = 1000, 2000
# wytyczne: str. 1 wymagania (umowna), str. 2 szablon
pdf = pikepdf.new()
for c in ("BT /F1 30 Tf 50 700 Td (Wymagania techniczne) Tj ET", template(W, H) + template_txt(None, W, H)
          + text(None, "Wydruk adTest 100x200", 300, 120, 30, H)):
    pdf.pages.append(pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, W * P, H * P],
                                                     Resources=pikepdf.Dictionary(Font=fonts(pdf)), Contents=pdf.make_stream(c.encode()))))
pdf.save(os.path.join(OUT, "_wytyczne_1000x2000.pdf"))
# wytyczne 1:10 (szablon rysowany w wymiarze pliku 100 × 200 mm)
pdf = pikepdf.new()
for c in ("BT /F1 3 Tf 5 70 Td (Wymagania) Tj ET", template(100, 200, 0.1) + template_txt(None, 100, 200, 0.1)):
    pdf.pages.append(pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 100 * P, 200 * P],
                                                     Resources=pikepdf.Dictionary(Font=fonts(pdf)), Contents=pdf.make_stream(c.encode()))))
pdf.save(os.path.join(OUT, "_wytyczne_1do10_100x200.pdf"))

save("01_czysty.pdf", W, H, design(W, H))
save("02_szablon_pelny.pdf", W, H, design(W, H) + template(W, H) + template_txt(None, W, H))
save("03_szablon_przesuniety_3mm.pdf", W, H, design(W, H) + template(W, H, dx=3, dy=-2) + template_txt(None, W, H, dx=3, dy=-2))
def form(pdf):
    f = pikepdf.Stream(pdf, (template(W, H) + template_txt(None, W, H)).encode())
    f.Type, f.Subtype, f.BBox = pikepdf.Name.XObject, pikepdf.Name.Form, [0, 0, W * P, H * P]
    f.Resources = pikepdf.Dictionary(Font=fonts(pdf))
    return f
save("04_szablon_w_formie.pdf", W, H, design(W, H) + "q /Fm1 Do Q ", {"Fm1": form})
save("05_szablon_pod_grafika.pdf", W, H, template(W, H) + template_txt(None, W, H) + design(W, H))
save("06_szablon_innego_produktu.pdf", W, H, design(W, H) + ring(0, 0, W, 1500, 2, CYAN, H) + ring(50, 50, 900, 1400, 2, RED, H))
save("07_cyjanowy_pas_projektu.pdf", W, H, design(W, H) + f"{CYAN} k 0 {(H-80)*P:.2f} {W*P:.2f} {80*P:.2f} re f ")
save("09_tylko_czerwona_ramka.pdf", W, H, design(W, H) + ring(50, 50, W - 100, H - 100, 2, RED, H))
save("10_stopka_klienta_przy_napisie.pdf", W, H, design(W, H) + template(W, H) + template_txt(None, W, H)
     + text(None, "www.klient.pl tel. 600 100 200", 400, H - 20, 12, H, "F1", "0 0 0 0"))
# 1:10 — plik 100 × 200 mm
save("11_skala_1do10_szablon.pdf", 100, 200, design(100, 200, 0.1) + template(100, 200, 0.1) + template_txt(None, 100, 200, 0.1))
# szablon wtopiony w obraz (raster 120 ppi na wydruku 1000 × 2000 → 4724 × 9449 px; tu 25 ppi, żeby było lekko)
px = (984, 1969)
im = Image.new("RGB", px, (20, 50, 90)); d = ImageDraw.Draw(im)
d.rectangle([100, 500, 884, 800], fill=(240, 120, 30))
f = px[0] / W
d.rectangle([0, 0, px[0] - 1, px[1] - 1], outline=(0, 174, 239), width=max(2, int(2 * f)))
d.rectangle([int(50 * f), int(50 * f), px[0] - int(50 * f), px[1] - int(50 * f)], outline=(237, 28, 36), width=max(2, int(2 * f)))
b = io.BytesIO(); im.save(b, "JPEG", quality=92)
def img(pdf):
    s = pikepdf.Stream(pdf, b.getvalue()); s.Type, s.Subtype = pikepdf.Name.XObject, pikepdf.Name.Image
    s.Width, s.Height, s.ColorSpace, s.BitsPerComponent, s.Filter = px[0], px[1], pikepdf.Name.DeviceRGB, 8, pikepdf.Name.DCTDecode
    return s
save("08_szablon_w_pikselach.pdf", W, H, f"q {W*P:.2f} 0 0 {H*P:.2f} 0 0 cm /Im1 Do Q ", {"Im1": img})
print(sorted(os.listdir(OUT)))
