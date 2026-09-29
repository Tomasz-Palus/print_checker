"""Zadanie = jeden wgrany plik i ŁAŃCUCH jego wersji.

    v0 (oryginał) → v1 (po 1. poprawce) → v2 (po 2.) → …

Zasady (Tomasz, od pierwszego dnia):
  • oryginał nigdy nie jest nadpisywany,
  • nic nie dzieje się samo — każdą poprawkę uruchamia użytkownik,
  • poprawki idą w ustalonej kolejności rozdziałów (steps.ORDER).
Każda wersja to OSOBNY, NIEZMIENNY plik. Poprawka dopisuje wersję na końcu łańcucha,
cofnięcie poprawki ucina łańcuch przed nią (razem z krokami zrobionymi później).
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import threading
import time
import uuid

import pdfutil
import render
import views

import paths

WORK_DIR = paths.WORK

_jobs: dict = {}
_lock = threading.Lock()


class Version:
    def __init__(self, vid: str, path: str, step: str | None = None, params: dict | None = None,
                 result: dict | None = None):
        self.id, self.path, self.step = vid, path, step
        self.params = params or {}
        self.result = result or {}
        self.pages_mm = pdfutil.page_sizes_mm(path)

    def to_json(self) -> dict:
        r = self.result
        return {"id": self.id, "step": self.step, "text": r.get("text", ""), "note": r.get("note", ""),
                "pages_mm": self.pages_mm, "map": r.get("map"), "fonts_subst": r.get("fonts_subst") or []}


class Job:
    def __init__(self, jid: str, jdir: str, path: str, info: dict):
        self.id, self.dir, self.info = jid, jdir, info
        self.created = time.time()
        self.suggestions: list = []
        self.versions = [Version("v0", path)]
        if info.get("kind") == "raster":      # wymiar rastra w mm wynika z DPI, nie z pikseli
            self.versions[0].pages_mm = [[p.get("width_mm"), p.get("height_mm")] for p in info["pages"]]
        self.analysis: dict = {}         # id wersji -> wynik analyze.analyze
        self.images: dict = {}           # id wersji -> pełne rekordy obrazów (mapa detalu)
        self.ink: dict = {}              # (id wersji, strona) -> suma farb (ink.py)
        self.lock = threading.RLock()    # jedna poprawka naraz

    @property
    def original(self) -> Version:
        return self.versions[0]

    @property
    def head(self) -> Version:
        return self.versions[-1]

    def version(self, vid: str | None) -> Version:
        for v in self.versions:
            if v.id == vid:
                return v
        return self.head if vid in (None, "", "head") else None

    def to_json(self) -> dict:
        return {"job_id": self.id, "file": {k: v for k, v in self.info.items() if k != "base"},
                "suggestions": self.suggestions,
                "versions": [v.to_json() for v in self.versions]}

    # --- obrót pliku (Tomasz 29.09) ---------------------------------------------------------
    def rotate(self, deg: int) -> None:
        """Obraca CAŁY plik o 90° / 180° (w prawo = dodatnio). To nowy punkt wyjścia: obrócony plik
        zastępuje wersję v0, a nałożone poprawki przepadają (robione były pod starą orientację —
        frontend pyta o to wcześniej). Zawsze od pliku z wgrania (`info["base"]`), z łącznym kątem:
        JPG przy kilku obrotach nie traci jakości po kilka razy, a powrót do 0° oddaje go bit w bit."""
        with self.lock:
            if deg % 90:
                raise ValueError("Obrót tylko o wielokrotność 90°.")
            total = (int(self.info.get("rot", 0)) + int(deg)) % 360
            if len(self.versions) > 1:
                self.undo(self.versions[1].step)
            old = self.versions[0]
            base = self.info.get("base") or old.path
            path = base if total == 0 else _rotated_file(base, total, self.dir)
            info = render.inspect(path, self.info["name"])
            for k in ("converted", "geometry", "prepared", "base"):
                if k in self.info:
                    info[k] = self.info[k]
            info["base"], info["rot"] = base, total
            views.drop(self, {old.id})
            self.analysis.pop(old.id, None)
            self.images.pop(old.id, None)
            for k in [k for k in self.ink if k[0] == old.id]:
                self.ink.pop(k, None)
            if old.path != base:
                try:
                    os.remove(old.path)
                except OSError:
                    pass
            self.info = info
            # nowy identyfikator: podgląd i analizy w przeglądarce są zapamiętane pod id wersji
            v0 = Version(f"v0r{total}{uuid.uuid4().hex[:4]}", path)
            if info.get("kind") == "raster":
                v0.pages_mm = [[p.get("width_mm"), p.get("height_mm")] for p in info["pages"]]
            self.versions = [v0]

    # --- łańcuch wersji -----------------------------------------------------------------
    def apply(self, step: str, params: dict) -> Version:
        """Nowa wersja = poprawka `step` nałożona na ostatnią wersję."""
        import steps
        with self.lock:
            if step not in steps.ORDER:
                raise ValueError(f"Nieznana poprawka: {step}")
            if any(v.step == step for v in self.versions):
                raise ValueError("Ta poprawka jest już nałożona — najpierw ją cofnij.")
            last = self.head.step
            if last and steps.ORDER.index(last) > steps.ORDER.index(step):
                raise ValueError("Poprawki idą po kolei — tę trzeba było zrobić wcześniej. Cofnij późniejsze.")
            vid = f"v{len(self.versions)}{uuid.uuid4().hex[:4]}"
            dst = os.path.join(self.dir, vid + ".pdf")
            result = steps.run(step, self.head.path, dst, params, self)
            dst = result.pop("path", dst)          # obraz zostaje obrazem (JPG/TIFF), reszta to PDF
            mm = result.pop("pages_mm", None)      # obraz po dopasowaniu wymiaru: nowy wymiar z DPI
            if not os.path.exists(dst):
                raise ValueError(result.get("text") or "Poprawka nic nie zmieniła.")
            v = Version(vid, dst, step, params, result)
            if render.is_raster(dst):              # wymiar obrazu w mm wynika z DPI — jak w oryginale
                v.pages_mm = mm or self.head.pages_mm
            self.versions.append(v)
            return v

    def undo(self, step: str) -> None:
        """Cofa poprawkę `step` i wszystko, co zrobiono po niej."""
        with self.lock:
            idx = next((i for i, v in enumerate(self.versions) if v.step == step), None)
            if idx is None:
                return
            gone, self.versions = self.versions[idx:], self.versions[:idx]
            ids = {v.id for v in gone}
            views.drop(self, ids)
            for v in gone:
                self.analysis.pop(v.id, None)
                self.images.pop(v.id, None)
                for k in [k for k in self.ink if k[0] == v.id]:
                    self.ink.pop(k, None)
                for p in [v.path, *glob.glob(os.path.splitext(v.path)[0] + "_p*_krzywe.pdf")]:
                    try:
                        os.remove(p)
                    except OSError:
                        pass      # Windows: plik jeszcze otwarty — zniknie przy sprzątaniu


def _rotated_file(base: str, total: int, jdir: str) -> str:
    """Kopia pliku z wgrania obrócona o `total` stopni w prawo (90 / 180 / 270)."""
    ext = os.path.splitext(base)[1].lower()
    out = os.path.join(jdir, f"rot{total}_{uuid.uuid4().hex[:4]}{ext}")
    if render.is_raster(base):
        from PIL import Image
        im = Image.open(base)
        im.seek(0)
        info = dict(im.info)
        r = im.transpose({90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
                          270: Image.Transpose.ROTATE_90}[total])
        kw = {}
        if info.get("icc_profile"):
            kw["icc_profile"] = info["icc_profile"]
        d = info.get("dpi")
        if d:
            kw["dpi"] = (d[1], d[0]) if total in (90, 270) else d
        fmt = im.format or ("JPEG" if ext in (".jpg", ".jpeg") else "PNG")
        if fmt == "JPEG":
            r.save(out, "JPEG", quality=95, subsampling=0, **kw)
        elif fmt == "TIFF":
            r.save(out, "TIFF", compression="tiff_lzw", **kw)
        else:
            if fmt not in ("PNG", "BMP", "GIF", "WEBP"):
                fmt = "PNG"
                out = os.path.splitext(out)[0] + ".png"
            r.save(out, fmt, **({"lossless": True, **kw} if fmt == "WEBP" else kw))
        return out
    import pikepdf
    with pikepdf.open(base) as pdf:
        for pg in pdf.pages:
            pg.obj["/Rotate"] = (int(pg.obj.get("/Rotate", 0)) + total) % 360
        pdf.save(out)
    path, _ = render.normalize_geometry(out)   # obrót wpisany w treść — jak przy wgraniu
    if path != out:
        try:
            os.remove(out)
        except OSError:
            pass
    return path


# ----------------------------------------------------------------------------
# rejestr zadań
# ----------------------------------------------------------------------------
def create(file_storage) -> Job:
    """Zapisuje wgrany plik i czyta jego metadane. Rzuca render.UnsupportedFormat."""
    name = file_storage.filename
    ext = os.path.splitext(name)[1].lower()
    if ext not in render.ALLOWED_EXT:
        raise render.UnsupportedFormat(f"Nieobsługiwany rodzaj pliku: {ext or '(brak rozszerzenia)'}")
    jid = uuid.uuid4().hex[:12]
    jdir = os.path.join(WORK_DIR, jid)
    os.makedirs(jdir, exist_ok=True)
    path = os.path.join(jdir, "original" + ext)            # ścieżka ASCII (Ghostscript)
    file_storage.save(path)
    try:
        import prepare
        opened = []
        if ext == ".pdf" or (ext == ".ai" and prepare.looks_pdf(path)):
            path, opened = prepare.check_open(path)   # hasło, uszkodzenie (Tomasz 29.09)
        path, converted = render.canonicalize(path)
        geom, baked = [], []
        if not render.is_raster(name):
            path, geom = render.normalize_geometry(path)
            # warstwy i adnotacje w stanie DO DRUKU (prepare.py) — podgląd = wydruk
            path, baked = prepare.bake_print_state(path)
        info = render.inspect(path, name)
        info["base"] = path                            # punkt wyjścia do obrotu (Job.rotate)
        if converted:
            info["converted"] = converted
        if geom:                                       # wygląd bez zmian — tylko zapis strony
            info["geometry"] = geom
        # to, co program zmienił w pliku przy wgraniu — pokazane w rozdziale Plik
        uu = sorted({m for g in geom for m in re.findall(r"UserUnit ([\d.]+)", g)})
        info["prepared"] = opened + ([f"strona zapisana w powiększonej jednostce (UserUnit {', '.join(uu)} — "
                                      "tak Illustrator i Acrobat zapisują strony ponad 5 m); wymiar przeliczony na "
                                      "prawdziwy (plik do druku ponad 5 m dostanie ją z powrotem przy pobraniu)"] if uu else []) + baked
        job = Job(jid, jdir, path, info)
    except Exception:
        shutil.rmtree(jdir, ignore_errors=True)
        raise
    with _lock:
        _jobs[jid] = job
    return job


def get(jid: str) -> Job | None:
    with _lock:
        return _jobs.get(jid)


def delete(jid: str) -> None:
    with _lock:
        job = _jobs.pop(jid, None)
    if job:
        views.drop(job)
        shutil.rmtree(job.dir, ignore_errors=True)


def clean_work_dir() -> None:
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    os.makedirs(WORK_DIR, exist_ok=True)
