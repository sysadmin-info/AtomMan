#!/usr/bin/env bash
set -euo pipefail

USER_NAME="${SUDO_USER:-$USER}"
HOME_DIR=$(eval echo "~$USER_NAME")
APP_DIR="$HOME_DIR/atomman"

echo "[50] Installing AtomMan app in $APP_DIR..."
sudo -u "$USER_NAME" mkdir -p "$APP_DIR"/{src,venv}

sudo apt install -y python3-venv python3-pip git
sudo -u "$USER_NAME" python3 -m venv "$APP_DIR/venv"
sudo -u "$USER_NAME" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$USER_NAME" "$APP_DIR/venv/bin/pip" install -r "$(pwd)/requirements.txt"

# Copy screen.py
if [[ -f ./screen.py ]]; then
  sudo -u "$USER_NAME" install -m 0644 ./screen.py "$APP_DIR/src/screen.py"
else
  echo "Warning: ./screen.py not found – copy your file to $APP_DIR/src manually."
fi

# systemd unit
sudo install -D -m 0644 systemd/atomman.service /etc/systemd/system/atomman.service
sudo sed -i "s|__USER__|$USER_NAME|g" /etc/systemd/system/atomman.service
sudo sed -i "s|__HOME__|$HOME_DIR|g" /etc/systemd/system/atomman.service

# sudoers rule
sudo install -D -m 0440 sudoers/atomman-dmidecode /etc/sudoers.d/atomman-dmidecode
sudo sed -i "s|__USER__|$USER_NAME|g" /etc/sudoers.d/atomman-dmidecode

# logrotate
cat <<'EOF' | sudo tee /etc/logrotate.d/atomman >/dev/null
/var/log/atomman.log {
  weekly
  rotate 4
  compress
  missingok
  notifempty
  create 0640 __USER__ adm
}
EOF
sudo sed -i "s|__USER__|$USER_NAME|g" /etc/logrotate.d/atomman

sudo systemctl daemon-reload
sudo systemctl enable atomman.service
sudo systemctl start atomman.service

echo "Done — AtomMan service started."
echo "Edit /etc/atomman.env with your OpenWeatherMap API key and restart service."
