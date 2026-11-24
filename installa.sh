#!/bin/bash
# Il buco nero al centro della Galassia 1.8 - installazione per l'utente (Ubuntu)
# Copia il programma in ~/.local/share/buco_nero, crea il comando ~/.local/bin/BucoNero,
# l'icona e il collegamento nel menu e sulla Scrivania.  (c) 2026 Edoardo Battistel
set -e
QUI="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/buco_nero"
echo "Controllo i pacchetti Python..."
python3 - <<'PY' || { echo "Mancano pacchetti: sudo apt install python3-tk python3-numpy python3-scipy python3-matplotlib"; exit 1; }
import tkinter, numpy, scipy, matplotlib
print("  tkinter", tkinter.TkVersion, "| numpy", numpy.__version__, "| scipy", scipy.__version__, "| matplotlib", matplotlib.__version__)
PY
mkdir -p "$DEST/dati" "$HOME/.local/bin" "$HOME/.local/share/icons" "$HOME/.local/share/applications"
cp "$QUI"/buco_nero.py "$QUI"/motore_bn.py "$QUI"/grafici_bn.py "$QUI"/contesto_bn.py "$QUI"/buco_nero.png "$DEST/"
cp "$QUI"/dati/*.tsv "$DEST/dati/"
cp "$QUI/buco_nero.png" "$HOME/.local/share/icons/buco_nero.png"
cat > "$HOME/.local/bin/BucoNero" <<SH
#!/bin/bash
exec python3 "$DEST/buco_nero.py" "\$@"
SH
chmod +x "$HOME/.local/bin/BucoNero"
# Tk dichiara la classe "BucoNero" come "Buconero": StartupWMClass deve essere uguale
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
echo "Installato. Avvio dal menu o con: BucoNero   (prova: BucoNero --autotest)"
