#!/usr/bin/env bash
set -euo pipefail

echo "[60] Creating /etc/atomman.env (SAMPLE – edit with your real API key)..."
sudo tee /etc/atomman.env >/dev/null <<'EOF'
# OpenWeatherMap configuration
ATOMMAN_OWM_API=__YOUR_API_KEY__
ATOMMAN_OWM_LOCATION=51.7687,19.4570
ATOMMAN_OWM_UNITS=metric
ATOMMAN_OWM_LANG=pl
ATOMMAN_WEATHER_REFRESH=600
EOF

sudo chown root:root /etc/atomman.env
sudo chmod 0640 /etc/atomman.env

echo "Now edit /etc/atomman.env, insert your OpenWeatherMap API key, then run:"
echo "  sudo systemctl daemon-reload && sudo systemctl restart atomman"
