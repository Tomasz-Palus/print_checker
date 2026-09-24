#!/bin/bash
# Ghostscript na Maca, zbudowany ze źródeł: jeden plik `gs` z zasobami wkompilowanymi w środek
# i własnymi bibliotekami (freetype, jpeg, png, lcms2, openjpeg…) — bez Homebrew u użytkownika.
# Wynik: build/gs/bin/gs + build/gs/iccprofiles.  Użycie: packaging/build_gs_mac.sh 10.07.1
set -euo pipefail
VER="${1:-10.07.1}"
TAG="gs$(echo "$VER" | tr -d .)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/build/gs-src"
mkdir -p "$WORK" && cd "$WORK"
curl -sSL -o gs.tar.xz "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/$TAG/ghostscript-$VER.tar.xz"
tar xf gs.tar.xz && cd "ghostscript-$VER"
export MACOSX_DEPLOYMENT_TARGET=11.0
# Homebrew na maszynie GitHuba ma własne libtiff/libpng… — nie wolno ich podlinkować
export PKG_CONFIG_PATH="" PKG_CONFIG_LIBDIR=/nonexistent
./configure --disable-cups --disable-dbus --disable-gtk --disable-fontconfig --disable-contrib \
  --without-x --without-libidn --without-libpaper --without-tesseract --without-ijs \
  --without-pdftoraster --without-so --without-urf --without-cal >/dev/null
make -j"$(sysctl -n hw.ncpu)" >/dev/null
echo "== zależności gs =="
otool -L bin/gs
if otool -L bin/gs | tail -n +2 | grep -vE "^\s+(/usr/lib/|/System/)"; then
  echo "BŁĄD: gs zależy od bibliotek spoza systemu (u użytkownika ich nie będzie)"; exit 1
fi
rm -rf "$ROOT/build/gs" && mkdir -p "$ROOT/build/gs/bin"
cp bin/gs "$ROOT/build/gs/bin/gs"
cp -R iccprofiles "$ROOT/build/gs/iccprofiles"
"$ROOT/build/gs/bin/gs" --version
