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
                "pages_mm": self.pages_mm, "map": r.get("map")}


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
        return {"job_id": self.id, "file": self.info, "suggestions": self.suggestions,
                "versions": [v.to_json() for v in self.versions]}

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
            if not os.path.exists(dst):
                raise ValueError(result.get("text") or "Poprawka nic nie zmieniła.")
            v = Version(vid, dst, step, params, result)
            if render.is_raster(dst):              # wymiar obrazu w mm wynika z DPI — jak w oryginale
                v.pages_mm = self.head.pages_mm
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
                for p in [v.path, *glob.glob(os.path.splitext(v.path)[0] + "_p*_krzywe.pdf")]:
                    try:
                        os.remove(p)
                    except OSError:
                        pass      # Windows: plik jeszcze otwarty — zniknie przy sprzątaniu


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
        path, converted = render.canonicalize(path)
        info = render.inspect(path, name)
        if converted:
            info["converted"] = converted
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
