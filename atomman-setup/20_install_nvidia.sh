#!/usr/bin/env bash
set -euo pipefail

# Choose one of:
#   nvidia-driver-580
#   nvidia-driver-580-open
DRIVER_PACKAGE="${DRIVER_PACKAGE:-nvidia-driver-580}"

echo "[20] Installing driver: ${DRIVER_PACKAGE}"
echo "    (Check 'ubuntu-drivers devices' for the recommended package.)"

sudo apt update -y
sudo apt install -y "${DRIVER_PACKAGE}" nvidia-utils-580

# Enable Kernel Mode Setting (helps Wayland stability)
echo "options nvidia-drm modeset=1" | sudo tee /etc/modprobe.d/nvidia-kms.conf >/dev/null

sudo update-initramfs -u

echo
echo "Driver installed."
echo "Now REBOOT."
echo "After reboot, if 'nvidia-smi' works, continue with 50_app_setup.sh."
echo "If you get 'Key was rejected by service', run 30_secureboot_enroll_key.sh after reboot."
sudo reboot
