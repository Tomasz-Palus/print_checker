"""Bardzo duże pliki (miliony operatorów) — sprawdzenie, czy analiza przechodzi cały plik.

    python gen_duze.py [folder]

W każdym pliku na KOŃCU treści (po milionach operatorów) jest błąd do wykrycia: kolor RGB, overprint
i nieosadzony font. Analiza, która nie dojdzie do końca, go nie zobaczy.
"""
import os
import sys

import numpy as np
import pikepdf

OUT = sys.argv[1] if len(sys.argv) > 1 else "pliki_duze"
os.makedirs(OUT, exist_ok=True)
W, H = 1000 / 25.4 * 72, 1000 / 25.4 * 72          # strona 1 × 1 m

TAIL = b"q 1 0 0 rg 10 10 50 50 re f Q\nq /GSop gs 0 0 0 1 k 100 10 50 50 re f Q\nBT /FX 24 Tf 200 20 Td (Koniec) Tj ET\n"


def symbol(n_ops: int, seed: int = 0) -> bytes:
    """Kształt z krzywych (ok. n_ops operatorów), sam CMYK."""
    rng = np.random.default_rng(seed)
    out = [b"0.2 0.6 0 0.1 k"]
    pts = rng.uniform(0, 20, size=(n_ops, 6))
    out.append(b"0 0 m")
    for i in range(n_ops - 3):
        out.append(("%.1f %.1f %.1f %.1f %.1f %.1f c" % tuple(pts[i])).encode())
    out.append(b"f")
    return b"\n".join(out)


def page(pdf, content: bytes, xobjects: dict | None = None):
    res = pikepdf.Dictionary({
        "/Font": pikepdf.Dictionary({"/FX": pdf.make_indirect(pikepdf.Dictionary({
            "/Type": pikepdf.Name.Font, "/Subtype": pikepdf.Name.TrueType, "/BaseFont": pikepdf.Name("/BrakujacyFont-Bold"),
            "/FirstChar": 32, "/LastChar": 126, "/Widths": [500] * 95,
            "/FontDescriptor": pdf.make_indirect(pikepdf.Dictionary({
                "/Type": pikepdf.Name.FontDescriptor, "/FontName": pikepdf.Name("/BrakujacyFont-Bold"), "/Flags": 32,
                "/FontBBox": [0, -200, 1000, 900], "/ItalicAngle": 0, "/Ascent": 900, "/Descent": -200,
                "/CapHeight": 700, "/StemV": 80}))}))}),
        "/ExtGState": pikepdf.Dictionary({"/GSop": pikepdf.Dictionary({"/Type": pikepdf.Name.ExtGState, "/op": True, "/OP": True, "/OPM": 1})}),
    })
    if xobjects:
        res["/XObject"] = pikepdf.Dictionary(xobjects)
    pdf.pages.append(pikepdf.Page(pikepdf.Dictionary({
        "/Type": pikepdf.Name.Page, "/MediaBox": [0, 0, W, H], "/Resources": res,
        "/Contents": pdf.make_stream(content)})))


def form(pdf, content: bytes, bbox=(0, 0, 20, 20), xobjects: dict | None = None):
    d = {"/Type": pikepdf.Name.XObject, "/Subtype": pikepdf.Name.Form, "/BBox": list(bbox)}
    if xobjects:
        d["/Resources"] = pikepdf.Dictionary({"/XObject": pikepdf.Dictionary(xobjects)})
    return pdf.make_stream(content, **{k[1:]: v for k, v in d.items()})


def grid(n: int, name: str, step: float = 2.5) -> bytes:
    side = int(np.ceil(np.sqrt(n)))
    out = []
    for i in range(n):
        out.append(f"q 0.1 0 0 0.1 {(i % side) * step:.2f} {(i // side) * step:.2f} cm /{name} Do Q".encode())
    return b"\n".join(out)


def image(pdf):
    a = (np.random.default_rng(1).uniform(0, 255, (32, 32, 4))).astype(np.uint8)
    return pdf.make_stream(a.tobytes(), Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image, Width=32, Height=32,
                           ColorSpace=pikepdf.Name.DeviceCMYK, BitsPerComponent=8)


# D1: jeden symbol (400 operatorów) powtórzony 30 000 razy — 12 mln operatorów (np. wzór z Illustratora)
pdf = pikepdf.new()
s = form(pdf, symbol(400))
page(pdf, grid(30000, "S") + b"\n" + TAIL, {"/S": s})
pdf.save(f"{OUT}/D1_symbol_30000x.pdf")

# D2: zagnieżdżone formy 100 × 100 × symbol 1000 operatorów — 10 mln
pdf = pikepdf.new()
c = form(pdf, symbol(1000, 2))
b = form(pdf, grid(100, "C", 20), (0, 0, 200, 200), {"/C": c})
a = form(pdf, grid(100, "B", 200), (0, 0, 2000, 2000), {"/B": b})
page(pdf, b"q 1 0 0 1 10 10 cm /A Do Q\n" + TAIL, {"/A": a})
pdf.save(f"{OUT}/D2_zagniezdzone_100x100.pdf")

# D3: płaska treść, 8 mln operatorów bez form (mapa, wektor z CAD): 800 000 małych kształtów po
# 10 operatorów (m, 8 × c, f), każdy w innym miejscu i kolorze. (Jeden kształt z 8 mln krzywych —
# pierwsza wersja — to przypadek nierealny: Ghostscript wypełnia go ponad 15 min.)
rng = np.random.default_rng(3)
n = 800_000
xy = rng.uniform(0, W - 30, size=(n, 2))
d = rng.uniform(0, 20, size=(n, 8, 6))
col = rng.uniform(0, 1, size=(n, 4))
lines = []
for i in range(n):
    x, y = xy[i]
    seg = " ".join("%.1f %.1f %.1f %.1f %.1f %.1f c" % tuple(v) for v in (d[i] + [x, y, x, y, x, y]))
    lines.append(("%.2f %.2f %.2f %.2f k %.1f %.1f m %s f" % (*col[i], x, y, seg)).encode())
pdf = pikepdf.new()
page(pdf, b"\n".join(lines) + b"\n" + TAIL)
pdf.save(f"{OUT}/D3_plaski_8mln.pdf")

# D4: symbol z obrazem (300 operatorów + obraz) powtórzony 20 000 razy — miejsca obrazu się liczą
pdf = pikepdf.new()
im = image(pdf)
s = form(pdf, symbol(300, 4) + b"\nq 20 0 0 20 0 0 cm /I Do Q", xobjects={"/I": im})
page(pdf, grid(20000, "S") + b"\n" + TAIL, {"/S": s})
pdf.save(f"{OUT}/D4_symbol_z_obrazem_20000x.pdf")

for f in sorted(os.listdir(OUT)):
    print(f, round(os.path.getsize(os.path.join(OUT, f)) / 1e6, 1), "MB")
