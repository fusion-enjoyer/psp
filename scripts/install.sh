#!/bin/sh
# pspkit PC side installer (Linux, per user; no root needed except the udev rule).
#
#   scripts/install.sh              install / update
#   scripts/install.sh --uninstall  remove (keeps ~/.config/pspkit/deck.yaml)
#
# Installs:
#   ~/.local/bin/pspkit, ~/.local/bin/pspkit-deck     commands
#   ~/.config/systemd/user/pspkit-bridge.service      bridge, started at login
#   ~/.local/share/applications/pspkit-deck.desktop   "pspkit Deck" in the app menu
set -eu

REPO=$(cd "$(dirname "$0")/.." && pwd)
BIN="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

if [ "${1:-}" = "--uninstall" ]; then
    systemctl --user disable --now pspkit-bridge.service 2>/dev/null || true
    rm -f "$BIN/pspkit" "$BIN/pspkit-deck" "$UNIT_DIR/pspkit-bridge.service" "$APPS/pspkit-deck.desktop"
    systemctl --user daemon-reload 2>/dev/null || true
    echo "pspkit kaldırıldı. Ayarların duruyor: ~/.config/pspkit/deck.yaml"
    exit 0
fi

missing=""
python3 -c "import yaml" 2>/dev/null || missing="$missing python3-yaml"
python3 -c "import PySide6" 2>/dev/null || missing="$missing python3-pyside6.qtwidgets"
python3 -c "import dbus" 2>/dev/null || missing="$missing python3-dbus"
if [ -n "$missing" ]; then
    echo "Eksik paketler:$missing"
    echo "  sudo apt install$missing"
    exit 1
fi

mkdir -p "$BIN" "$UNIT_DIR" "$APPS"

cat > "$BIN/pspkit" <<EOF
#!/bin/sh
PYTHONPATH="$REPO/bridge\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m pspkit "\$@"
EOF
cat > "$BIN/pspkit-deck" <<EOF
#!/bin/sh
exec python3 "$REPO/desktop/pspkit_deck_gui.py" "\$@"
EOF
chmod +x "$BIN/pspkit" "$BIN/pspkit-deck"

cat > "$UNIT_DIR/pspkit-bridge.service" <<EOF
[Unit]
Description=pspkit bridge (PSP apps over USB and TCP)
After=graphical-session.target

[Service]
ExecStart=$BIN/pspkit run
Environment=PATH=$HOME/pspdev/bin:/usr/local/bin:/usr/bin:/bin
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

cat > "$APPS/pspkit-deck.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=pspkit Deck
Comment=PSP'yi Stream Deck'e çevir: tuşları ayarla
Exec=$BIN/pspkit-deck
Icon=input-gaming
Terminal=false
Categories=Utility;Settings;
EOF

"$BIN/pspkit" init >/dev/null
systemctl --user daemon-reload
systemctl --user enable --now pspkit-bridge.service
systemctl --user restart pspkit-bridge.service

echo "pspkit kuruldu."
echo "  Köprü servisi: systemctl --user status pspkit-bridge"
echo "  Ayar uygulaması: uygulama menüsünde 'pspkit Deck' ya da: pspkit-deck"
echo "  Kontrol: pspkit doctor"
if ! ls /etc/udev/rules.d/*pspkit-psp* /etc/udev/rules.d/*psplink* >/dev/null 2>&1; then
    echo
    echo "PSP'nin USB ile bağlanabilmesi için bir kerelik (sudo ister):"
    echo "  sudo cp $REPO/scripts/udev/60-pspkit-psp.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules"
fi
case ":$PATH:" in *":$BIN:"*) ;; *) echo; echo "Not: $BIN PATH'inde değil; komutları tam yoluyla çalıştır ya da PATH'e ekle." ;; esac
