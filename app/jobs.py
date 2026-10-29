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

import detailmap
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
        self._plock = threading.Lock()   # wycinanie stron wielostronicowego obrazu
        self._alocks: dict = {}          # (id wersji, strona) -> blokada analizy (jedna naraz)
        self.progress: dict | None = None  # postęp trwającej poprawki (spłaszczenie) — pasek w interfejsie

    def analysis_of(self, v: Version, page: int) -> dict:
        """Analiza strony wersji — liczona RAZ. Równoległe /analysis i /frames tej samej strony
        liczyły ją dwa razy, cztery zapytania — cztery razy (przegląd 09.10, C)."""
        import analyze
        cache = self.analysis.setdefault(v.id, {})
        if page in cache:
            return cache[page]
        with self._plock:
            lk = self._alocks.setdefault((v.id, page), threading.Lock())
        with lk:
            if page not in cache:
                res = analyze.analyze(self.page_path(v, page), page)
                self.images.setdefault(v.id, {})[page] = res.pop("_images", None)
                cache[page] = res
        return cache[page]

    def page_path(self, v: Version, page: int) -> str:
        """Plik z daną stroną wersji. Wielostronicowy obraz (TIFF) — strona wycięta do osobnego
        pliku jednostronicowego: analiza, poprawki, podgląd i pobranie dotyczą WYBRANEJ strony,
        a nie zawsze pierwszej (przegląd 09.10, A8). Wersje po poprawkach mają już jedną stronę."""
        if (self.info.get("kind") != "raster" or self.info.get("page_count", 1) < 2
                or v is not self.versions[0] or not 0 <= page < self.info["page_count"]):
            return v.path
        ext = os.path.splitext(v.path)[1].lower()
        out = os.path.join(self.dir, f"{v.id}_strona{page + 1}{ext if ext in ('.tif', '.tiff') else '.png'}")
        with self._plock:
            if not os.path.exists(out):
                from PIL import Image
                with Image.open(v.path) as im:
                    im.seek(page)
                    fr = im.copy()
                    kw = {}
                    icc = im.info.get("icc_profile") or fr.info.get("icc_profile")
                    if icc:
                        kw["icc_profile"] = icc
                    # DPI tylko zapisane naprawdę (bez XResolution Pillow podaje umowne 1 × 1)
                    if im.info.get("dpi") and 282 in getattr(im, "tag_v2", {}):
                        kw["dpi"] = im.info["dpi"]
                tmp = f"{out}.{uuid.uuid4().hex[:6]}.part"
                if out.endswith((".tif", ".tiff")):
                    fr.save(tmp, "TIFF", compression="tiff_lzw", **kw)
                else:
                    fr.save(tmp, "PNG", **kw)
                os.replace(tmp, out)
        return out

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
            # rodzaj z rozszerzenia PLIKU (po rozpoznaniu treści przy wgraniu), nazwa — klienta
            info = render.inspect(path, os.path.splitext(self.info["name"])[0] + os.path.splitext(path)[1])
            info["name"] = self.info["name"]
            for k in ("converted", "geometry", "prepared", "base"):
                if k in self.info:
                    info[k] = self.info[k]
            info["base"], info["rot"] = base, total
            views.drop(self, {old.id})
            self.analysis.pop(old.id, None)
            self.images.pop(old.id, None)
            for k in [k for k in self.ink if k[0] == old.id]:
                self.ink.pop(k, None)
            for p in ([old.path] if old.path != base else []) + glob.glob(os.path.join(self.dir, f"{old.id}_strona*")):
                try:
                    os.remove(p)
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
            page = int(params.get("page", 0) or 0)
            # wielostronicowy obraz: poprawka działa na wybranej stronie (przegląd 09.10, A8)
            try:
                result = steps.run(step, self.page_path(self.head, page), dst, params, self)
            finally:
                self.progress = None
            dst = result.pop("path", dst)          # obraz zostaje obrazem (JPG/TIFF), reszta to PDF
            mm = result.pop("pages_mm", None)      # obraz po dopasowaniu wymiaru: nowy wymiar z DPI
            if not os.path.exists(dst):
                raise ValueError(result.get("text") or "Poprawka nic nie zmieniła.")
            v = Version(vid, dst, step, params, result)
            if render.is_raster(dst):              # wymiar obrazu w mm wynika z DPI — jak w oryginale
                v.pages_mm = [list(x) for x in self.head.pages_mm]
                if mm and 0 <= page < len(v.pages_mm):   # lista per strona; zmienia się wybrana
                    v.pages_mm[page] = list(mm[0])
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
                # wyniki jakości tej wersji i jej pobrane pliki (przegląd kodu, doc 18 D) — zajmowały pamięć
                # i dysk do końca pracy z plikiem
                detailmap.forget(f"{self.id}#{v.id}")
                for p in [v.path, *glob.glob(os.path.splitext(v.path)[0] + "_p*_krzywe.pdf"),
                          *glob.glob(os.path.join(self.dir, f"pobierz_{v.id}_p*"))]:
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
        tr = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}[total]
        r = im.transpose(tr)
        n = getattr(im, "n_frames", 1)
        if n > 1 and (im.format or "") == "TIFF":
            # wielostronicowy TIFF: obrót wszystkich stron, nie tylko pierwszej (przegląd 09.10, A8)
            rest = []
            for i in range(1, n):
                im.seek(i)
                rest.append(im.transpose(tr))
            d = info.get("dpi")
            kw = {"dpi": (d[1], d[0]) if d and total in (90, 270) else d} if d else {}
            if info.get("icc_profile"):
                kw["icc_profile"] = info["icc_profile"]
            r.save(out, "TIFF", compression="tiff_lzw", save_all=True, append_images=rest, **kw)
            return out
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
def _ext_of(name: str) -> str:
    """Rozszerzenie z nazwy — także dla nazwy „.pdf” (splitext uznaje ją za plik bez rozszerzenia)."""
    base = os.path.basename((name or "").replace("\\", "/"))
    return ("." + base.rsplit(".", 1)[1].lower()) if "." in base else ""


def _sniff(path: str) -> str | None:
    """Rodzaj pliku po pierwszych bajtach (None = nie wiadomo — decyduje rozszerzenie)."""
    try:
        with open(path, "rb") as f:
            head = f.read(1024)
    except OSError:
        return None
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        return ".tif"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head.startswith(b"%PDF") or (b"%PDF-" in head and not head.startswith(b"%!PS")):
        return ".pdf"
    return None


def create(file_storage) -> Job:
    """Zapisuje wgrany plik i czyta jego metadane. Rzuca render.UnsupportedFormat."""
    name = file_storage.filename
    ext = _ext_of(name)
    if ext not in render.ALLOWED_EXT:
        raise render.UnsupportedFormat(f"Nieobsługiwany rodzaj pliku: {ext or '(brak rozszerzenia)'}")
    jid = uuid.uuid4().hex[:12]
    jdir = os.path.join(WORK_DIR, jid)
    os.makedirs(jdir, exist_ok=True)
    path = os.path.join(jdir, "original" + ext)            # ścieżka ASCII (Ghostscript)
    try:
        file_storage.save(path)
        import prepare
        opened = []
        # rodzaj pliku po TREŚCI: PDF nazwany .jpg szedł jako obraz bez wymiaru i pobierał się
        # jako „.jpg” z PDF-em w środku (przegląd 09.10, C)
        real = _sniff(path)
        if real and real != ext and not (real == ".pdf" and ext == ".ai") and not (
                real in (".jpg", ".jpeg") and ext in (".jpg", ".jpeg")) and not (real == ".tif" and ext == ".tiff"):
            kinds = {".pdf": "PDF", ".jpg": "JPG", ".png": "PNG", ".tif": "TIFF", ".gif": "GIF", ".bmp": "BMP", ".webp": "WEBP"}
            opened.append(f"plik ma rozszerzenie {ext}, a w środku jest {kinds.get(real, real)} — otwarty jako "
                          f"{kinds.get(real, real)}")
            fixed = os.path.join(jdir, "original" + real)
            os.replace(path, fixed)
            path, ext = fixed, real
        kind_name = os.path.splitext(name)[0] + ext            # rodzaj z treści, nazwa — jak u klienta
        if ext == ".ai" and not prepare.looks_pdf(path):
            raise render.UnsupportedFormat("Plik .ai bez zawartości PDF — zapisz go w Illustratorze z opcją "
                                           "„Create PDF Compatible File” albo wyeksportuj do PDF.")
        if ext == ".pdf" or ext == ".ai":
            path, opened2 = prepare.check_open(path)   # hasło, uszkodzenie (Tomasz 29.09)
            opened += opened2
        path, converted = render.canonicalize(path)
        geom, baked = [], []
        if not render.is_raster(kind_name):
            path, geom = render.normalize_geometry(path)
            # warstwy i adnotacje w stanie DO DRUKU (prepare.py) — podgląd = wydruk
            path, baked = prepare.bake_print_state(path)
        info = render.inspect(path, kind_name)
        info["name"] = name
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
    except Exception as e:
        shutil.rmtree(jdir, ignore_errors=True)
        import prepare
        if isinstance(e, (render.UnsupportedFormat, prepare.Unreadable)):
            raise
        # zamiast „UnidentifiedImageError: … /work/…/original.jpg” — komunikat dla człowieka
        # (szczegóły w dzienniku) (przegląd 09.10, C)
        print(f"[wgranie] {name}: {type(e).__name__}: {e}")
        if type(e).__name__ in ("UnidentifiedImageError", "FileDataError", "EmptyFileError", "DecompressionBombError") \
                or isinstance(e, (OSError, SyntaxError, ValueError)):
            raise prepare.Unreadable(f"Nie da się odczytać pliku {ext.upper().lstrip('.')} — jest pusty, uszkodzony "
                                     "albo zapisany w nieznanym formacie. Poproś klienta o ponowny eksport.") from e
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
