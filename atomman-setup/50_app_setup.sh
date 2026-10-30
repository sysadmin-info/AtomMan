#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
USER_NAME="${SUDO_USER:-$USER}"

if [[ "$USER_NAME" == "root" ]]; then
    echo "Run as a normal user (the script uses sudo only where needed)." >&2
    exit 1
fi

HOME_DIR="$(getent passwd "$USER_NAME" | cut -d: -f6)"
if [[ -z "$HOME_DIR" || ! -d "$HOME_DIR" ]]; then
    echo "Cannot determine home directory for $USER_NAME" >&2
    exit 1
fi
USER_ID="$(id -u "$USER_NAME")"
APP_DIR="$HOME_DIR/atomman"

for f in screen.py screen_linux_audio.py test_linux_audio.py; do
    if [[ ! -f "$REPO_DIR/$f" ]]; then
        echo "Missing required repository file: $REPO_DIR/$f" >&2
        exit 1
    fi
done

if [[ ! -f /etc/atomman.env ]]; then
    echo "Missing /etc/atomman.env. Configure it before installing the service." >&2
    echo "See atomman-setup/60_env_write_example.sh or existing setup instructions." >&2
    exit 1
fi

printf '[50] Installing AtomMan for %s in %s\n' "$USER_NAME" "$APP_DIR"
sudo apt install -y python3-venv python3-pip git
sudo -u "$USER_NAME" mkdir -p "$APP_DIR/src"
if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
    sudo -u "$USER_NAME" python3 -m venv "$APP_DIR/venv"
fi
sudo -u "$USER_NAME" "$APP_DIR/venv/bin/python" -m pip install --upgrade pip
sudo -u "$USER_NAME" "$APP_DIR/venv/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.txt"

for f in screen.py screen_linux_audio.py test_linux_audio.py; do
    sudo -u "$USER_NAME" install -m 0644 "$REPO_DIR/$f" "$APP_DIR/src/$f"
done

# Version-controlled template uses __USER__ and __HOME__ placeholders.
sudo install -D -m 0644 "$SCRIPT_DIR/systemd/atomman.service" /etc/systemd/system/atomman.service
sudo sed -i "s|__USER__|$USER_NAME|g; s|__HOME__|$HOME_DIR|g; s|__UID__|$USER_ID|g" /etc/systemd/system/atomman.service

sudo install -D -m 0440 "$SCRIPT_DIR/sudoers/atomman-dmidecode" /etc/sudoers.d/atomman-dmidecode
sudo sed -i "s|__USER__|$USER_NAME|g" /etc/sudoers.d/atomman-dmidecode

cat <<'LOGROTATE' | sudo tee /etc/logrotate.d/atomman >/dev/null
/var/log/atomman.log {
  weekly
  rotate 4
  compress
  missingok
  notifempty
  create 0640 __USER__ adm
}
LOGROTATE
sudo sed -i "s|__USER__|$USER_NAME|g" /etc/logrotate.d/atomman

sudo systemd-analyze verify /etc/systemd/system/atomman.service
sudo systemctl daemon-reload
sudo systemctl enable atomman.service
sudo systemctl restart atomman.service

echo "[50] Done. AtomMan service installed (fan falls back to NVIDIA if EC module is absent)."
echo "EC fan driver must be installed separately after verifying hardware and EC test."
