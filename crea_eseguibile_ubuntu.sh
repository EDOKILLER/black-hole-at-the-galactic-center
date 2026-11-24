#!/bin/bash
# Il buco nero al centro della Galassia 1.8 - eseguibile con PyInstaller (Ubuntu)
# 1) autotest dello script  2) compilazione  3) autotest dell'eseguibile  4) installazione
# Usa il venv ~/Claude/Astropy/venv_compila (PyInstaller, numpy, scipy, matplotlib, Pillow).
# (c) 2026 Edoardo Battistel
set -e
QUI="$(cd "$(dirname "$0")" && pwd)"
PY="$HOME/Claude/Astropy/venv_compila/bin/python"
cd "$QUI"
[ -x "$PY" ] || { echo "Manca $PY"; exit 1; }

echo "== 1/4 Autotest dello script =="
"$PY" buco_nero.py --autotest

echo "== 2/4 Compilazione =="
rm -rf build dist BucoNero.spec
"$PY" -m PyInstaller --noconfirm --clean --onefile --name BucoNero \
  --add-data "dati:dati" --add-data "buco_nero.png:." \
  --hidden-import PIL._tkinter_finder --hidden-import PIL.ImageTk \
  --hidden-import motore_bn --hidden-import grafici_bn --hidden-import contesto_bn \
  --exclude-module astropy --exclude-module healpy --exclude-module lal --exclude-module h5py \
  --exclude-module sklearn \
  buco_nero.py

echo "== 3/4 Autotest dell'eseguibile =="
./dist/BucoNero --autotest

echo "== 4/4 Installazione =="
DEST="$HOME/.local/share/buco_nero"
mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/icons" "$HOME/.local/share/applications"
cp dist/BucoNero "$DEST/BucoNero"
cp buco_nero.png "$HOME/.local/share/icons/buco_nero.png"
rm -f "$HOME/.local/bin/BucoNero"
ln -s "$DEST/BucoNero" "$HOME/.local/bin/BucoNero"
DESK="[Desktop Entry]
Type=Application
Name=Il buco nero al centro della Galassia
Comment=Massa e distanza di Sagittarius A* dalle orbite delle stelle S
Exec=$HOME/.local/bin/BucoNero
Icon=$HOME/.local/share/icons/buco_nero.png
Terminal=false
Categories=Education;Science;Astronomy;
StartupWMClass=Buconero
StartupNotify=true"
echo "$DESK" > "$HOME/.local/share/applications/buconero.desktop"
SCRIVANIA="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Scrivania")"
if [ -d "$SCRIVANIA" ]; then
  echo "$DESK" > "$SCRIVANIA/buconero.desktop"
  chmod +x "$SCRIVANIA/buconero.desktop"
  gio set "$SCRIVANIA/buconero.desktop" metadata::trusted true 2>/dev/null || true
fi
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
ls -lh "$DEST/BucoNero"
echo "Fatto: eseguibile installato. Avvio dal menu o con: BucoNero"
