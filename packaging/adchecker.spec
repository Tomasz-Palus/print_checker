# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: jeden folder z programem (adChecker.exe na Windows, adChecker.app na Macu).
# Uruchamiać z katalogu głównego repozytorium:  pyinstaller packaging/adchecker.spec
# Ghostscript musi już leżeć w build/gs (przygotowuje go .github/workflows/build.yml):
#   build/gs/bin/        gswin64c.exe + gsdll64.dll (Windows) albo gs (Mac)
#   build/gs/iccprofiles profile Ghostscripta (potrzebne przy zamianie na CMYK)
#   build/gs/lib, Resource  (Windows — gdy są w instalacji Ghostscripta)
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
APP = os.path.join(ROOT, "app")
GS = os.path.join(ROOT, "build", "gs")
VERSION = re.search(r'VERSION\s*=\s*"([^"]+)"', open(os.path.join(APP, "version.py"), encoding="utf-8").read()).group(1)

datas = [
    (os.path.join(APP, "static"), "static"),
    (os.path.join(APP, "data", "icc"), os.path.join("data", "icc")),
    (os.path.join(APP, "data", "products_snapshot.json"), "data"),
    (os.path.join(APP, "data", "template_index.json"), "data"),
]
binaries = []
if not os.path.isdir(os.path.join(GS, "bin")):
    raise SystemExit("Brak build/gs/bin — najpierw przygotuj Ghostscripta (patrz build.yml).")
for d, _, files in os.walk(GS):
    rel = os.path.relpath(d, GS)
    dest = os.path.normpath(os.path.join("gs", rel))
    for f in files:
        src = os.path.join(d, f)
        # programy do `binaries` — PyInstaller je podpisze (Mac) i ułoży tam, gdzie wolno kod
        (binaries if rel == "bin" else datas).append((src, dest))

a = Analysis(
    [os.path.join(APP, "desktop.py")],
    pathex=[APP],
    binaries=binaries,
    datas=datas,
    hiddenimports=["waitress", "webview"],
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = os.path.join(SPECPATH, "adchecker.icns" if sys.platform == "darwin" else "adchecker.ico")
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="adChecker",
    console=False,               # bez czarnego okna konsoli
    icon=icon,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="adChecker", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="adChecker.app",
        icon=icon,
        bundle_identifier="pl.adsystem.adchecker",
        version=VERSION,
        info_plist={
            "CFBundleName": "adChecker",
            "CFBundleDisplayName": "adChecker",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
