#!/usr/bin/env bash
set -euo pipefail

echo "[10] Removing existing NVIDIA drivers..."
sudo apt remove --purge -y '^nvidia-.*' || true
sudo apt autoremove --purge -y || true
sudo update-initramfs -u
echo "System cleaned. Ready for fresh driver installation."
