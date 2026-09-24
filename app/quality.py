"""Rozdział „Jakość wydruku" — czy obrazy w projekcie wydrukują się ostro.

Liczy detailmap.py (bez zmian w metodzie, patrz dokumentacja 07): każdy obraz PDF-a czytany
w NATYWNYCH pikselach i rzutowany na wszystkie swoje miejsca na stronie; raster — cały plik.
Tu tylko: którą wersję pliku sprawdzać, z jaką skalą, i złożenie wyniku w werdykt dla osoby
nietechnicznej (ta sama logika, którą stara wersja miała w przeglądarce — teraz w jednym miejscu).

Która wersja: OSTATNIA PRZED SPŁASZCZENIEM. Po spłaszczeniu cała strona to jeden obraz
w rozdzielczości spłaszczenia — jego „ppi" nic nie mówi o zdjęciach, które w nim siedzą.
Wszystkie wcześniejsze poprawki nie zmieniają pikseli obrazów (kolory przeliczane bez strat),
a dopasowanie wymiaru jest już w położeniu obrazów na stronie — więc skala = tylko skala
wytycznych (1:1 / 1:10), a obszary leżą dokładnie na stronie, którą widać w podglądzie.
"""
from __future__ import annotations

import analyze
import detailmap

REQUIRED_PPI = detailmap.REQUIRED_PPI      # 120 — sztywny próg z wytycznych
MIN_AREA_MM = detailmap.MIN_REGION_MM      # 10 mm — mniejszych fragmentów nie zgłaszamy


def version_for(job):
    """Wersja do oceny: ostatnia przed spłaszczeniem."""
    vs = [v for v in job.versions if v.step != "flatten"]
    return vs[-1]


def request(job, page: int, k: float, block: int, print_mm: tuple | None) -> dict:
    """Stan oceny (i start w tle przy pierwszym pytaniu)."""
    v = version_for(job)
    kind = "raster" if job.info.get("kind") == "raster" else "pdf"
    images = page_mm = None
    if kind == "pdf":
        cache = job.analysis.setdefault(v.id, {})
        if page not in cache:
            res = analyze.analyze(v.path, page)
            job.images.setdefault(v.id, {})[page] = res.pop("_images", None)
            cache[page] = res
        a = cache[page]
        if not (a.get("resolution") or {}).get("has_images"):
            return {"status": "done", "version": v.id, "verdict": "vector", "areas": [], "groups": []}
        images = job.images.get(v.id, {}).get(page)
        sizes = a.get("resolution", {}).get("page_sizes_mm") or []
        page_mm = tuple(sizes[page]) if page < len(sizes) else None
    mid = f"{job.id}#{v.id}"
    st = detailmap.status(mid, page, k, block) or detailmap.start(
        mid, v.path, kind, page, k, block, images=images, page_mm=page_mm)
    out = {"status": st["status"], "version": v.id, "band": st.get("band", 0), "bands": st.get("bands", 0),
           "error": st.get("error")}
    if st["status"] == "done" and st.get("result"):
        out.update(verdict_of(st["result"], kind, print_mm))
    return out


def forget(job) -> None:
    detailmap.forget(job.id)
    for v in job.versions:
        detailmap.forget(f"{job.id}#{v.id}")


def verdict_of(r: dict, kind: str, print_mm: tuple | None) -> dict:
    """Wynik mapy → lista miejsc (od najgorszego), grupy do listy i werdykt:
    ok — wszystko ≥ 120 ppi; look — pikseli dość, ale gdzieś brak detalu (do obejrzenia);
    bad — za mało pikseli (pewna wada, trzeba wymienić obraz)."""
    base = None
    if kind == "raster" and print_mm and r.get("page_px"):
        base = r["page_px"][0] / (print_mm[0] / 25.4)          # natywne ppi obrazu NA WYDRUKU
    areas = []
    for a in r.get("areas") or []:
        a = dict(a)
        if a.get("ppi") is None and base:
            a["ppi"] = round(base / (a.get("factor") or 1), 1)
            a["nominal_ppi"] = round(base, 1)
        if not a.get("mm") and print_mm:
            a["mm"] = [round(a["fw"] * print_mm[0], 1), round(a["fh"] * print_mm[1], 1)]
        areas.append(a)
    # raster w całości za mały — fakt geometryczny, zgłaszany jak obraz w PDF-ie
    if base is not None and base < REQUIRED_PPI:
        areas.insert(0, {"fx": 0, "fy": 0, "fw": 1, "fh": 1, "scope": "element", "reason": "lowres",
                         "ppi": round(base, 1), "nominal_ppi": round(base, 1), "factor": 1,
                         "px": r.get("page_px"), "mm": [round(v, 1) for v in print_mm]})
    areas = [a for a in areas if a.get("ppi") is None or a["ppi"] < REQUIRED_PPI]
    areas = [a for a in areas if not a.get("mm") or (a["mm"][0] * a["mm"][1] >= MIN_AREA_MM ** 2
                                                     and min(a["mm"]) >= MIN_AREA_MM / 2)]
    for a in areas:
        a["whole"] = a["fw"] * a["fh"] >= 0.5
    areas.sort(key=lambda a: (a.get("confidence") == "synthetic", a.get("ppi") or 1e9,
                              0 if a.get("scope") == "element" else 1, a.get("xref") or 0))
    # Grupy tylko do listy: ten sam obraz (xref) albo te same zmierzone fakty (rozmiar ±5 %,
    # ppi) — 22 użycia tej samej grafiki to jedna wada w 22 miejscach, nie 22 wady.
    def near(x, y):
        return x > 0 and y > 0 and abs(x - y) / max(x, y) <= 0.05

    def same(a, b):
        return (a.get("scope") == b.get("scope") and (a.get("reason") == "lowres") == (b.get("reason") == "lowres")
                and a.get("ppi") is not None and b.get("ppi") is not None and round(a["ppi"]) == round(b["ppi"])
                and a.get("mm") and b.get("mm") and near(a["mm"][0], b["mm"][0]) and near(a["mm"][1], b["mm"][1]))
    groups, by_xref = [], {}
    for i, a in enumerate(areas):
        if a.get("scope") == "element" and a.get("xref") is not None:
            if a["xref"] in by_xref:
                groups[by_xref[a["xref"]]]["count"] += 1
                continue
            by_xref[a["xref"]] = len(groups)
            groups.append({"i": i, "count": 1, "kind": "image"})
            continue
        g = next((g for g in groups if g["kind"] == "facts" and same(areas[g["i"]], a)), None)
        if g:
            g["count"] += 1
        else:
            groups.append({"i": i, "count": 1, "kind": "facts"})
    few = [g for g in groups if areas[g["i"]].get("reason") == "lowres"]
    verdict = "bad" if few else ("look" if groups else "ok")
    return {"verdict": verdict, "areas": areas[:300], "groups": groups[:60], "few": len(few),
            "look": len(groups) - len(few), "seconds": r.get("seconds"),
            "objects": r.get("objects"), "placements": r.get("placements"),
            "hidden_skipped": r.get("hidden_skipped", 0), "small_skipped": r.get("small_skipped", 0)}
