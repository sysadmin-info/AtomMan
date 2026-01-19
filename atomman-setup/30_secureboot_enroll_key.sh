#!/usr/bin/env bash
set -euo pipefail

echo "[30] Generating and enrolling MOK key for Secure Boot..."

sudo mkdir -p /root/mok
cd /root/mok

# Generate PEM key and certificate for module signing
if [[ ! -f MOK.key || ! -f MOK.crt ]]; then
  sudo openssl req -new -x509 -newkey rsa:2048 \
    -keyout MOK.key -out MOK.crt -nodes -days 36500 \
    -subj "/CN=AtomMan-NVIDIA/"
fi

# Convert to DER — required by some firmware during import
sudo openssl x509 -in MOK.crt -outform DER -out MOK.der

echo "Registering MOK (using DER to avoid PEM import issues):"
sudo mokutil --import /root/mok/MOK.der

echo
echo "==> REBOOT now."
echo "    In the blue MOK Manager menu choose:"
echo "    Enroll MOK → Continue → Yes → enter password → Reboot."
echo "After reboot, run 40_sign_or_reinstall_dkms.sh."
sudo reboot

