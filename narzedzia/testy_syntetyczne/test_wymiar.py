import sys, os, json, glob
sys.path.insert(0, "/home/user/print_checker/narzedzia"); sys.path.insert(0, "/home/user/print_checker/app")
import test_projektu as T, porownaj_silniki as P, pymupdf, pikepdf
from PIL import Image
D = "wymiar"; WORK = "/home/user/print_checker/app/work"
res = []
def check(name, ok, info=""):
    res.append((name, ok)); print(("OK    " if ok else "BŁĄD  ") + name + (f"  [{info}]" if info else ""), flush=True)
def up(f):
    j = T.upload(f"{D}/{f}"); return j
def step(jid, name, **p):
    return T.post_json(f"/api/jobs/{jid}/steps", {"name": name, "params": {"page": p.pop("page", 0), **p}})
def vfile(jid, r):
    v = r["versions"][-1]["id"]; return (glob.glob(f"{WORK}/{jid}/{v}.*") or [None])[0]
def look(f, page=0):
    r = pymupdf.open(f)[page].rect; return P.gs_render(f, page, 800 / max(r.width, r.height), True, None, r)
near = lambda a, b, t=0.6: abs(a - b) <= t

# A: spad z TrimBox
j = up("A_spad_trimbox_1020x2020.pdf"); p = j["file"]["pages"][0]
check("A wgranie: spad 10 mm i format netto 1000×2000", p.get("trim_mm") == [1000.0, 2000.0] and p.get("bleed_mm") == [10.0] * 4, f"{p.get('trim_mm')} {p.get('bleed_mm')}")
r = step(j["job_id"], "trim", w_mm=1000, h_mm=2000); f = vfile(j["job_id"], r)
check("A przycięcie → 1000×2000", r["versions"][-1]["pages_mm"][0] == [1000.0, 2000.0], r["versions"][-1]["text"])
# B: spad bez TrimBox — przycięcie do wymiaru z wytycznych
j = up("B_spad_bez_trimbox_1020x2020.pdf"); r = step(j["job_id"], "trim", w_mm=1000, h_mm=2000)
check("B przycięcie bez TrimBox (z wymiaru) → 1000×2000", "_status" not in r and r["versions"][-1]["pages_mm"][0] == [1000.0, 2000.0], r.get("error") or r["versions"][-1]["text"])
# C: połowa wymiaru — skala 200 %, wektor zostaje wektorem
j = up("C_polowa_wymiaru_500x1000.pdf"); jid = j["job_id"]
r = step(jid, "resize", w_mm=1000, h_mm=2000, scale=2); f = vfile(jid, r)
import analyze
a = analyze.analyze(f, 0)
check("C dopasowanie 200 % → 1000×2000", r["versions"][-1]["pages_mm"][0] == [1000.0, 2000.0], r["versions"][-1]["text"])
check("C wektor nadal wektorem (bez obrazów)", not (a.get("color") or {}).get("families", {}).get("CMYK", {}).get("image"), str(a.get("color", {}).get("families")))
m = P.measure(look(f"{D}/C_polowa_wymiaru_500x1000.pdf"), look(f)); check("C wygląd = oryginał powiększony", m["p99_kol"] <= 6, str(m))
# D: złe proporcje — wypełnij format (cover), tło z krawędzi, odbicie
j = up("D_zle_proporcje_1000x1500.pdf"); jid = j["job_id"]
r = step(jid, "resize", w_mm=1000, h_mm=2000, scale=2000 / 1500)
check("D wypełnij format (133 %) → 1000×2000", r["versions"][-1]["pages_mm"][0] == [1000.0, 2000.0], r["versions"][-1]["text"])
T.req(f"/api/jobs/{jid}/steps/resize", "DELETE")
r = step(jid, "resize", w_mm=1000, h_mm=2000, scale=1, fill_edges=True, fill_mode="stretch"); f = vfile(jid, r)
im = look(f); px_top = im.getpixel((im.width // 4, 3)); px_mid_edge = im.getpixel((im.width // 4, int(im.height * 0.2)))
check("D tło z krawędzi: pas = kolor krawędzi projektu", max(abs(x - y) for x, y in zip(px_top, px_mid_edge)) <= 6, f"pas {px_top} krawędź {px_mid_edge}; {r['versions'][-1]['text']}")
T.req(f"/api/jobs/{jid}/steps/resize", "DELETE")
r = step(jid, "resize", w_mm=1000, h_mm=2000, scale=1, fill_edges=True, fill_mode="mirror")
check("D odbicie lustrzane działa", "_status" not in r, r.get("error") or r["versions"][-1]["text"])
# E: poziomy → obrót
j = up("E_poziomy_2000x1000.pdf"); jid = j["job_id"]
r = T.post_json(f"/api/jobs/{jid}/rotate", {"deg": 90, "page": 0})
check("E obrót 90° → 1000×2000", r.get("versions", [{}])[0].get("pages_mm", [[0]])[0] == [1000.0, 2000.0], str(r.get("versions", [{}])[0].get("pages_mm") or r.get("error")))
# F: /Rotate 90 zapisany w stronie
j = up("F_rotate90_w_pliku.pdf"); p = j["file"]["pages"][0]
check("F /Rotate 90: wymiar jak widać (1000×2000)", near(p["width_mm"], 1000) and near(p["height_mm"], 2000), f"{p['width_mm']}×{p['height_mm']} {j['file'].get('geometry')}")
# G: UserUnit 10 → 6000×3000, a pobrany plik znów z UserUnit
j = up("G_userunit_6000x3000.pdf"); jid = j["job_id"]; p = j["file"]["pages"][0]
check("G UserUnit 10: wymiar 6000×3000", near(p["width_mm"], 6000, 2) and near(p["height_mm"], 3000, 2), f"{p['width_mm']}×{p['height_mm']}")
data = T.req(f"/api/jobs/{jid}/download?page=0", raw=True); open("G_pobrany.pdf", "wb").write(data)
with pikepdf.open("G_pobrany.pdf") as q:
    uu = float(q.pages[0].obj.get("/UserUnit", 1)); mb = [float(x) for x in q.pages[0].MediaBox]
check("G pobrany plik: UserUnit wraca (strona ≤ 200 cali)", uu > 1 and (mb[2] - mb[0]) <= 14400, f"UserUnit {uu}, MediaBox {mb}")
# H: 1:10 — plik 50×100 dla formatu pliku 100×200 (wydruk 1000×2000)
j = up("H_1do10_polowa_50x100.pdf"); r = step(j["job_id"], "resize", w_mm=100, h_mm=200, scale=2, k=10)
check("H 1:10: dopasowanie do 100×200 mm pliku", r["versions"][-1]["pages_mm"][0] == [100.0, 200.0], r["versions"][-1]["text"])
# R1: JPG 150 dpi — wymiar 200×400 (błąd A1 z 09.10: DPI > 72)
j = up("R1_jpg_150dpi_200x400.jpg"); jid = j["job_id"]; p = j["file"]["pages"][0]
check("R1 JPG 150 dpi: 200×400 mm", near(p["width_mm"], 200, 0.5) and near(p["height_mm"], 400, 0.5), f"{p['width_mm']}×{p['height_mm']} dpi {p.get('dpi')}")
r = step(jid, "resize", w_mm=1000, h_mm=2000, scale=5); f = vfile(jid, r); im = Image.open(f)
check("R1 dopasowanie 500 %: piksele bez zmian, DPI 30", im.size == (1181, 2362) and round(im.info.get("dpi", (0,))[0]) == 30, f"{im.size} dpi {im.info.get('dpi')} | {r['versions'][-1]['text']}")
r = step(jid, "cmyk"); f = vfile(jid, r); im = Image.open(f)
check("R1 → CMYK: tryb CMYK, DPI zostaje", im.mode == "CMYK" and round(im.info.get("dpi", (0,))[0]) == 30, f"{im.mode} {im.info.get('dpi')} {os.path.basename(f)}")
# R2: TIFF 2 strony — strona 2
j = up("R2_tiff_2_strony.tif"); jid = j["job_id"]
check("R2 TIFF: 2 strony", j["file"]["page_count"] == 2, str(j["file"]["page_count"]))
r = step(jid, "cmyk", page=1); f = vfile(jid, r); im = Image.open(f)
check("R2 CMYK na stronie 2: wynik ma wymiar strony 2 (300×150 px)", im.size == (300, 150), f"{im.size} {getattr(im, 'n_frames', 1)} klatek")
data = T.req(f"/api/jobs/{jid}/download?page=1", raw=True); open("R2_pobrany.tif", "wb").write(data); im = Image.open("R2_pobrany.tif")
check("R2 pobranie: tylko strona 2, CMYK", getattr(im, "n_frames", 1) == 1 and im.mode == "CMYK" and im.size == (300, 150), f"{im.size} {im.mode} {getattr(im, 'n_frames', 1)}")
# R3: PNG z przezroczystością → CMYK na białym
j = up("R3_png_alfa_100dpi.png"); r = step(j["job_id"], "cmyk"); f = vfile(j["job_id"], r); im = Image.open(f)
c = im.getpixel((5, im.height // 2))
check("R3 PNG alfa → CMYK, przezroczyste = białe (0,0,0,0)", im.mode == "CMYK" and c == (0, 0, 0, 0), f"{im.mode} {c} {os.path.basename(f)}")
# R4: JPG już w CMYK
j = up("R4_jpg_cmyk_100dpi.jpg"); r = step(j["job_id"], "cmyk")
check("R4 JPG CMYK: zamiana odmawia (już CMYK)", r.get("_status") == 400, r.get("error", "") or "przepuścił")
# R5: TIFF 16 bit szary → CMYK nie biały (B16)
j = up("R5_tiff_16bit_szary.tif"); r = step(j["job_id"], "cmyk"); f = vfile(j["job_id"], r)
im = Image.open(f); k = [im.getpixel((150, y))[3] for y in (50, 300, 550)]
check("R5 16-bit szary → CMYK: gradient zachowany", im.mode == "CMYK" and k[0] > k[1] > k[2], f"K w 3 miejscach {k}")
# AI
j = T.upload(f"{D}/AI_zgodny_z_pdf.ai"); check("AI z PDF-em w środku: przyjęty", "_status" not in j, j.get("error", ""))
j = T.upload(f"{D}/AI_bez_pdf.ai"); check("AI bez PDF-u: czytelna odmowa", j.get("_status") in (400, 415, 422) and "PDF" in (j.get("error") or ""), f"{j.get('_status')} {j.get('error')}")
# R6: JPG bez DPI → pobranie: wymiar dokładny (JFIF ma tylko liczby całkowite — DPI też w EXIF i Photoshopie)
import io, numpy as np, pdfutil
Image.fromarray(np.random.default_rng(6).integers(0, 255, (1200, 600, 3), dtype=np.uint8)).save(f"{D}/R6_bez_dpi.jpg", quality=90)
j = up("R6_bez_dpi.jpg"); jid = j["job_id"]
data = T.req(f"/api/jobs/{jid}/download?page=0&w_mm=1015&h_mm=2014", raw=True); im = Image.open(io.BytesIO(data))
d = pdfutil.raster_dpi(im); h = 1200 / d[1] * 25.4
check("R6 JPG bez DPI: pobrany ma wymiar dokładny (2014 mm, nie 2000)", abs(h - 2014) < 0.5, f"{h:.2f} mm, JFIF {im.info.get('dpi')}, dokładne {d[1]:.4f}")
open(f"{D}/R6_pobrany.jpg", "wb").write(data)
j = up("R6_pobrany.jpg"); p = j["file"]["pages"][0]
check("R6 ponowne wgranie pobranego: ten sam wymiar", near(p["height_mm"], 2014.0), f"{p['width_mm']} × {p['height_mm']}")
r = step(j["job_id"], "cmyk"); f = vfile(j["job_id"], r); d2 = pdfutil.raster_dpi(Image.open(f))
check("R6 → CMYK: wymiar zostaje dokładny", abs(1200 / d2[1] * 25.4 - 2014) < 0.5, f"{1200 / d2[1] * 25.4:.2f} mm")
print(f"\n{sum(o for _, o in res)}/{len(res)} OK")
