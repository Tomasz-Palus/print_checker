"""Projekty do testów wymiaru, spadów, obrotu i obrazów."""
import io, os
import numpy as np, pikepdf
from PIL import Image, ImageDraw
P = 72 / 25.4
OUT = "wymiar"; os.makedirs(OUT, exist_ok=True)

def art(W, H):
    """Rozpoznawalny projekt: tło, ramka 20 mm od krawędzi, krzyż i kółko w środku (do porównań)."""
    return (f"0.9 0.7 0.1 0.4 k 0 0 {W*P:.2f} {H*P:.2f} re f "
            f"0 0.6 0.9 0 k {20*P:.2f} {20*P:.2f} {(W-40)*P:.2f} {(H-40)*P:.2f} re {30*P:.2f} {30*P:.2f} {(W-60)*P:.2f} {(H-60)*P:.2f} re f* "
            f"0 0 0 0 k {W/2*P-5:.2f} 0 10 {H*P:.2f} re f 0 {H/2*P-5:.2f} {W*P:.2f} 10 re f ")

def save(name, W, H, content, **page):
    pdf = pikepdf.new()
    d = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, W * P, H * P], Resources=pikepdf.Dictionary(),
                           Contents=pdf.make_stream(content.encode()))
    for k, v in page.items():
        d[f"/{k}"] = v
    pdf.pages.append(pikepdf.Page(d)); pdf.save(os.path.join(OUT, name))

save("A_spad_trimbox_1020x2020.pdf", 1020, 2020, art(1020, 2020), TrimBox=[10 * P, 10 * P, 1010 * P, 2010 * P])
save("B_spad_bez_trimbox_1020x2020.pdf", 1020, 2020, art(1020, 2020))
save("C_polowa_wymiaru_500x1000.pdf", 500, 1000, art(500, 1000))
save("D_zle_proporcje_1000x1500.pdf", 1000, 1500, art(1000, 1500))
save("E_poziomy_2000x1000.pdf", 2000, 1000, art(2000, 1000))
save("F_rotate90_w_pliku.pdf", 2000, 1000, art(2000, 1000), Rotate=90)
# ponad 5 m: UserUnit 10 (strona 600 × 300 mm × 10 = 6000 × 3000 mm)
save("G_userunit_6000x3000.pdf", 600, 300, art(600, 300), UserUnit=10)
save("H_1do10_polowa_50x100.pdf", 50, 100, art(50, 100))
# obrazy
def raster(W_mm, H_mm, dpi, mode="RGB"):
    px = (round(W_mm / 25.4 * dpi), round(H_mm / 25.4 * dpi))
    im = Image.new("RGB", px, (20, 60, 110)); d = ImageDraw.Draw(im)
    d.rectangle([px[0] // 10, px[1] // 10, px[0] * 9 // 10, px[1] * 9 // 10], outline=(240, 130, 20), width=max(2, px[0] // 50))
    d.ellipse([px[0] // 3, px[1] // 3, px[0] * 2 // 3, px[1] * 2 // 3], fill=(0, 200, 90))
    return im
raster(200, 400, 150).save(f"{OUT}/R1_jpg_150dpi_200x400.jpg", quality=92, dpi=(150, 150))
im = raster(200, 400, 100).convert("RGBA"); a = np.array(im); a[:, : a.shape[1] // 4, 3] = 0
Image.fromarray(a).save(f"{OUT}/R3_png_alfa_100dpi.png", dpi=(100, 100))
raster(200, 400, 100).convert("CMYK").save(f"{OUT}/R4_jpg_cmyk_100dpi.jpg", quality=92, dpi=(100, 100))
g16 = (np.linspace(0, 65535, 300 * 600, dtype=np.uint32).reshape(600, 300)).astype(np.uint16)
Image.fromarray(g16).save(f"{OUT}/R5_tiff_16bit_szary.tif", dpi=(75, 75))
p1, p2 = raster(200, 400, 60), raster(400, 200, 60).transpose(Image.Transpose.ROTATE_90).resize((300, 150))
p1.save(f"{OUT}/R2_tiff_2_strony.tif", save_all=True, append_images=[p2], dpi=(60, 60), compression="tiff_lzw")
# .ai: PDF w środku i śmieci
save("AI_zgodny.pdf", 500, 500, art(500, 500)); os.replace(f"{OUT}/AI_zgodny.pdf", f"{OUT}/AI_zgodny_z_pdf.ai")
open(f"{OUT}/AI_bez_pdf.ai", "wb").write(b"%!PS-Adobe-3.0\n%%Creator: Adobe Illustrator(R) 8.0\n%%BoundingBox: 0 0 100 100\n")
print(sorted(os.listdir(OUT)))
