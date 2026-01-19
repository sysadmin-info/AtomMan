#!/usr/bin/env bash
set -euo pipefail

echo "[40] Signing NVIDIA modules (or triggering DKMS auto-sign)..."
K="/root/mok/MOK.key"
C="/root/mok/MOK.crt"
H="/usr/src/linux-headers-$(uname -r)/scripts/sign-file"

if [[ ! -f "$K" || ! -f "$C" ]]; then
  echo "Missing /root/mok/MOK.key or .crt – run 30_secureboot_enroll_key.sh first."
  exit 1
fi

MODDIR="/lib/modules/$(uname -r)/updates/dkms"
FOUND=0
for m in nvidia nvidia-modeset nvidia-uvm nvidia-drm; do
  if [[ -f "$MODDIR/$m.ko.zst" ]]; then
    FOUND=1
    echo "  • Signing $m"
    sudo zstd -d -f "$MODDIR/$m.ko.zst" -o "$MODDIR/$m.ko"
    sudo "$H" sha256 "$K" "$C" "$MODDIR/$m.ko"
    sudo zstd -T0 -f --rm "$MODDIR/$m.ko"
  fi
done

sudo depmod -a

if [[ $FOUND -eq 0 ]]; then
  echo "No .ko.zst modules found – fallback: reinstall via DKMS (auto-sign enabled)"
  PKG=$(dpkg -l | awk '/nvidia-driver-[0-9]+/ {print $2}' | head -n1)
  PKG=${PKG:-nvidia-driver-580}
  echo "Reinstalling: $PKG"
  sudo apt install --reinstall -y "$PKG"
fi

# Attempt to load signed modules
set +e
sudo modprobe nvidia nvidia_modeset nvidia_uvm nvidia_drm modeset=1
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  echo "modprobe failed — REBOOT and run 'nvidia-smi' after boot."
else
  echo "Modules loaded successfully. Check 'nvidia-smi'."
fi
echo "Rebooting the system now"
sudo reboot
