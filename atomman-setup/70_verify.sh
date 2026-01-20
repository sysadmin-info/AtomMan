#!/usr/bin/env bash
set -euo pipefail

echo "[70] Verification:"
echo "• NVIDIA modules:"
lsmod | grep nvidia || true
echo
echo "• NVIDIA SMI output:"
nvidia-smi || true
echo
echo "• AtomMan service status:"
systemctl --no-pager --full status atomman || true
echo
echo "• Recent log output:"
journalctl -u atomman -n 50 --no-pager || true

echo
echo "If Weather shows OFFLINE, check your API key and try:"
echo "  curl -s 'https://api.openweathermap.org/data/2.5/weather?lat=51.7687&lon=19.4570&appid=YOUR_KEY'"
