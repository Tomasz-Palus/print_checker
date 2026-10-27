"""Test projektu „jak użytkownik”: każdy plik z folderu przez cały program (API działającego serwera).

    py narzedzia\\test_projektu.py <folder albo pliki…> [--serwer http://127.0.0.1:5000] [--wyniki folder]

Dla każdego pliku: wgranie → analiza → szablon (bez wytycznych) → spady → kolory (CMYK) → czerń →
overprint → krzywe → spłaszczenie (każdy krok tylko wtedy, gdy rozdział by go zalecił) → jakość →
pobranie. Pobrany plik sprawdzany niezależnie (analiza od nowa: sam CMYK, bez overprintu, fonty, wymiar),
a jego wygląd porównany z oryginałem w symulacji druku (Ghostscript, jak drukarnia) — obraz porównania
w folderze wyników. Na końcu `raport.md`: kroki, czasy, uwagi (UWAGA = do sprawdzenia, BŁĄD = błąd).
Serwer musi działać (app/run.bat albo `python app/server.py`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "app"))

B = "http://127.0.0.1:5000"


def req(url: str, method: str = "GET", data: bytes | None = None, ctype: str | None = None, raw: bool = False):
    r = urllib.request.Request(B + url, method=method, data=data)
    if ctype:
        r.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(r, timeout=1800) as f:
            body = f.read()
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return {"_status": e.code, **json.loads(body)}
        except Exception:
            return {"_status": e.code, "error": body[:300].decode("utf-8", "replace")}
    return body if raw else json.loads(body)


def post_json(url: str, obj: dict):
    return req(url, "POST", json.dumps(obj).encode(), "application/json")


def upload(path: str) -> dict:
    bnd = uuid.uuid4().hex
    name = os.path.basename(path)
    body = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n").encode() + open(path, "rb").read() + f"\r\n--{bnd}--\r\n".encode()
    return req("/api/upload", "POST", body, f"multipart/form-data; boundary={bnd}")


REAL_TR = ("krycie", "tryb mieszania", "maska", "obraz z maską")


def plan_steps(a: dict, pg: dict) -> list:
    """Które poprawki zaleciłby program (jak rozdziały w interfejsie: state.js / print.js)."""
    out = []
    if pg.get("trim_mm"):
        out.append(("trim", {"w_mm": pg["trim_mm"][0], "h_mm": pg["trim_mm"][1]}))
    c = a.get("color") or {}
    fam = list((c.get("families") or {}).keys())
    rgbish = any("RGB" in f for f in fam) or "Lab" in fam or bool({"Unknown", "Indexed"} & set(fam))
    real = any(k.startswith(REAL_TR) for k in (a.get("transparency") or {}))
    # przezroczystość liczona w RGB + kolory RGB: kolory przelicza spłaszczenie (Kolory → „Zostaw”, jak w interfejsie)
    if not (a.get("group_rgb") and real and rgbish) and (rgbish or c.get("spots") or (a.get("group_rgb") and not real)
                                                         or a.get("blend_space_missing")):
        out.append(("cmyk", {}))
    if (a.get("heavy_black") or 0) > 0:
        out.append(("black", {}))
    if (a.get("overprint_uses") or 0) > 0:
        out.append(("overprint", {}))
    if a.get("fonts"):
        out.append(("outline", {}))
    tr = [k for k in (a.get("transparency") or {}) if k.startswith(REAL_TR)]
    if tr and not a.get("flat_image"):
        out.append(("flatten", {"k": 1}))
    return out


def summary(a: dict) -> dict:
    c = a.get("color") or {}
    return {"przestrzenie": c.get("families"), "spoty": [s.get("name") for s in c.get("spots") or []],
            "overprint": a.get("overprint_uses"), "fonty": [(f["name"], f["embedded"]) for f in a.get("fonts") or []],
            "przezroczystość": a.get("transparency"), "grupa_rgb": a.get("group_rgb"),
            "bez_przestrzeni_mieszania": a.get("blend_space_missing"), "ciężka_czerń": a.get("heavy_black"),
            "obrazy": (a.get("images") or {}).get("count") if isinstance(a.get("images"), dict) else None,
            "niepełna": a.get("partial"), "błąd": a.get("error")}


def compare(orig: str, final: str, out_jpg: str, trimmed: bool = False) -> dict:
    """Wygląd w symulacji druku (Ghostscript, profil pliku / FOGRA39) — oryginał vs plik do druku.
    `trimmed` — spady przycięte: oryginał porównywany w obrębie TrimBox (format netto)."""
    import pymupdf
    if trimmed:
        import pikepdf
        with pikepdf.open(orig) as p:
            o = p.pages[0].obj
            tb = o.get("/TrimBox") or o.get("/ArtBox")
            if tb is not None:
                o["/MediaBox"] = o["/CropBox"] = tb
                orig = final + ".ref_netto.pdf"
                p.save(orig)
    import porownaj_silniki as P
    from PIL import Image
    ims = []
    for f in (orig, final):
        r = pymupdf.open(f)[0].rect
        ims.append(P.gs_render(f, 0, 1400 / max(r.width, r.height), True, None, r))
    a, b = ims
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    m = P.measure(a, b)
    P.triptych(a, b, out_jpg)
    return m


def run_file(path: str, outdir: str) -> dict:
    name = os.path.basename(path)
    rep = {"plik": name, "kroki": [], "uwagi": []}
    t = time.time()
    j = upload(path)
    rep["wgranie_s"] = round(time.time() - t, 1)
    if "_status" in j:
        rep["uwagi"].append(f"wgranie odrzucone ({j['_status']}): {j.get('error')}")
        return rep
    jid, f = j["job_id"], j["file"]
    pg = f["pages"][0]
    rep["plik_info"] = {"rodzaj": f.get("kind"), "stron": f.get("page_count"),
                        "mm": [pg.get("width_mm"), pg.get("height_mm")], "spad": pg.get("bleed_mm"),
                        "przygotowanie": f.get("prepared")}
    t = time.time()
    a = req(f"/api/jobs/{jid}/analysis?page=0")
    rep["analiza_s"] = round(time.time() - t, 1)
    rep["analiza"] = summary(a)
    fr = req(f"/api/jobs/{jid}/frames?page=0")
    rep["szablon"] = {k: fr.get(k) for k in ("found", "foreign", "pixels", "error")}
    steps = plan_steps(a, pg)
    for st, params in steps:
        t = time.time()
        r = post_json(f"/api/jobs/{jid}/steps", {"name": st, "params": {"page": 0, **params}})
        dt = round(time.time() - t, 1)
        if "_status" in r:
            rep["kroki"].append({"krok": st, "s": dt, "BŁĄD": r.get("error")})
            continue
        v = r["versions"][-1]
        rep["kroki"].append({"krok": st, "s": dt, "wynik": v.get("text"), "zastępcze_fonty": v.get("fonts_subst") or None})
    jobj = req(f"/api/jobs/{jid}")
    head = jobj["versions"][-1]
    mm = head["pages_mm"][0]
    # jakość (k = 1: wymiar pliku = wydruk)
    t = time.time()
    q = {}
    while time.time() - t < 900:
        q = req(f"/api/jobs/{jid}/quality?page=0&k=1&w_mm={mm[0]}&h_mm={mm[1]}")
        if q.get("_status") or q.get("state") in ("done", "error", "err") or q.get("verdict"):
            break
        time.sleep(2)
    rep["jakość_s"] = round(time.time() - t, 1)
    rep["jakość"] = {k: q.get(k) for k in ("state", "verdict", "summary", "error") if k in q} or q
    # pobranie i niezależne sprawdzenie
    data = req(f"/api/jobs/{jid}/download?page=0&v={head['id']}&w_mm={mm[0]}&h_mm={mm[1]}", raw=True)
    if isinstance(data, dict):
        rep["uwagi"].append(f"BŁĄD pobrania: {data}")
        return rep
    ext = ".pdf" if data[:4] == b"%PDF" else os.path.splitext(name)[1]
    final = os.path.join(outdir, os.path.splitext(name)[0] + "_DO_DRUKU" + ext)
    with open(final, "wb") as fh:
        fh.write(data)
    if ext == ".pdf":
        import analyze
        import pikepdf
        fa = analyze.analyze(final, 0)
        with pikepdf.open(final) as p:
            box = [float(x) for x in p.pages[0].MediaBox]
            npages = len(p.pages)
        fmm = [round((box[2] - box[0]) * 25.4 / 72, 1), round((box[3] - box[1]) * 25.4 / 72, 1)]
        rep["do_druku"] = {"stron": npages, "mm": fmm, **summary(fa)}
        fam = set((fa.get("color") or {}).get("families") or {})
        if fam - {"CMYK", "Gray", "Spot"}:
            rep["uwagi"].append(f"BŁĄD: w pliku do druku zostały przestrzenie {sorted(fam - {'CMYK', 'Gray', 'Spot'})}")
        if (fa.get("overprint_uses") or 0) > 0:
            rep["uwagi"].append(f"BŁĄD: w pliku do druku został overprint ({fa['overprint_uses']})")
        if any(not e for _, e in summary(fa)["fonty"]):
            rep["uwagi"].append("UWAGA: w pliku do druku są nieosadzone fonty")
        if npages != 1:
            rep["uwagi"].append(f"BŁĄD: plik do druku ma {npages} stron")
        # punkt odniesienia: plik PO przygotowaniu przy wgraniu (ukryte warstwy, adnotacje, hasło) — tak go
        # pokazuje program; serwer na tym samym komputerze, więc katalog zadania jest dostępny
        jdir = os.path.join(os.path.dirname(HERE), "app", "work", jid)
        cands = [os.path.join(jdir, x) for x in os.listdir(jdir) if x.startswith("original") and x.endswith(".pdf")
                 and "_krzywe" not in x and "_p0" not in x] if os.path.isdir(jdir) else []
        ref = max(cands, key=os.path.getmtime) if cands else path
        try:
            rep["wygląd_oryginał_vs_druk"] = compare(ref, final,
                                                     os.path.join(outdir, os.path.splitext(name)[0] + "_porownanie.jpg"),
                                                     trimmed=any(k["krok"] == "trim" and "wynik" in k for k in rep["kroki"]))
        except Exception as e:
            rep["uwagi"].append(f"porównanie wyglądu nieudane: {type(e).__name__}: {e}")
    return rep


def main():
    global B
    ap = argparse.ArgumentParser()
    ap.add_argument("pliki", nargs="+")
    ap.add_argument("--serwer", default=B)
    ap.add_argument("--wyniki", default="wyniki_testu")
    a = ap.parse_args()
    B = a.serwer.rstrip("/")
    files = []
    for p in a.pliki:
        files += sorted(os.path.join(p, f) for f in os.listdir(p)) if os.path.isdir(p) else [p]
    files = [f for f in files if f.lower().endswith((".pdf", ".ai", ".jpg", ".jpeg", ".png", ".tif", ".tiff"))]
    os.makedirs(a.wyniki, exist_ok=True)
    reps = []
    for i, f in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {os.path.basename(f)}", flush=True)
        try:
            r = run_file(f, a.wyniki)
        except Exception as e:
            r = {"plik": os.path.basename(f), "uwagi": [f"BŁĄD testu: {type(e).__name__}: {e}"]}
        reps.append(r)
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str), flush=True)
    with open(os.path.join(a.wyniki, "raport.json"), "w", encoding="utf-8") as fh:
        json.dump(reps, fh, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
