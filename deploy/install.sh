#!/usr/bin/env bash
# Installation Raumbelegungs-Display auf Raspberry Pi OS (Bookworm, 64-bit)
# Aufruf: sudo SERVICE_USER=pi bash install.sh
set -euo pipefail

TARGET=/opt/room-display
SRC="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_USER="${SERVICE_USER:-pi}"

echo ">>> Pakete installieren"
apt-get update
apt-get install -y --no-install-recommends \
    python3-venv python3-pip fonts-dejavu-core python3-spidev python3-rpi.gpio git

echo ">>> SPI aktivieren (raspi-config)"
if [ "$(raspi-config nonint get_spi)" != "0" ]; then
    raspi-config nonint do_spi 0
    echo "    SPI wurde aktiviert - Neustart erforderlich!"
fi

echo ">>> Dateien nach $TARGET"
mkdir -p "$TARGET" "$TARGET/data"
cp -r "$SRC/roomdisplay" "$SRC/fonts" "$SRC/config.yaml" "$SRC/requirements.txt" "$TARGET/"

echo ">>> Waveshare-Treiber (epd7in5_V3) laden"
if [ ! -d "$TARGET/waveshare_epd" ]; then
    if [ ! -d "$TARGET/e-Paper" ]; then
        git clone --depth 1 https://github.com/waveshareteam/e-Paper.git "$TARGET/e-Paper"
    fi
    cp -r "$TARGET/e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd" "$TARGET/"
fi

echo ">>> Virtualenv + Abhaengigkeiten"
# --system-site-packages: SPI-GPIO-Bindungen (spidev/RPi.GPIO) aus dem
# apt-Paket sind im venv sichtbar; sonst: ModuleNotFoundError 'spidev'
rm -rf "$TARGET/venv"
python3 -m venv --system-site-packages "$TARGET/venv"
"$TARGET/venv/bin/pip" install --upgrade pip
"$TARGET/venv/bin/pip" install -r "$TARGET/requirements.txt"

echo ">>> Berechtigungen (${SERVICE_USER})"
usermod -a -G spi,gpio "$SERVICE_USER" || true
chown -R "$SERVICE_USER":"$SERVICE_USER" "$TARGET"

echo ">>> systemd-Units installieren (User: ${SERVICE_USER})"
cp "$SRC/deploy/roomdisplay.service" /etc/systemd/system/
cp "$SRC/deploy/roomdisplay-web.service" /etc/systemd/system/
sed -i "s/^User=.*/User=${SERVICE_USER}/" /etc/systemd/system/roomdisplay*.service
systemctl daemon-reload
systemctl enable roomdisplay.service roomdisplay-web.service

cat <<'EOF'

Fertig. Naechste Schritte:
  1. Falls SPI neu aktiviert wurde:   sudo reboot
  2. Web-Upload-Passwort setzen (empfohlen im Uni-Netz):
       sudo systemctl edit roomdisplay-web
         [Service]
         Environment=ROOMDISPLAY_WEB_PASSWORD=geheim
     (Username steht in config.yaml unter web: username, Default "admin")
  3. Dienste starten:
       sudo systemctl start roomdisplay roomdisplay-web
  4. Upload-Seite: http://<ip-des-pi>:8080/
  5. Logs: journalctl -u roomdisplay -f
EOF
