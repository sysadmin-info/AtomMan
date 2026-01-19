#!/usr/bin/env bash
set -euo pipefail

echo "[00] Checking environment..."
GPU_LINE=$(lspci -nn | grep -i 'vga\|3d' || true)
SB=$(mokutil --sb-state 2>/dev/null | awk '{print tolower($0)}' || echo "unknown")
KVER=$(uname -r)

echo "  • Kernel       : $KVER"
echo "  • GPU          : ${GPU_LINE:-not detected}"
echo "  • Secure Boot  : $SB"

echo "  • Installing base packages..."
sudo apt update -y
sudo apt install -y dkms build-essential linux-headers-$(uname -r) mokutil openssl zstd

echo "  • Available NVIDIA drivers:"
sudo ubuntu-drivers devices || true

echo
echo "If Secure Boot is enabled and you later see 'Key was rejected by service',"
echo "you’ll follow the MOK enrollment path."
echo "OK."
