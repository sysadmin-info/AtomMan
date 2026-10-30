#!/usr/bin/env bash
# Hardware-dependent EC module: build and enable are deliberately separate steps.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SRC="$REPO_DIR/drivers/atomman-ec-fan"
NAME="atomman-ec-fan"
VERSION="0.2.0"
TARGET="/usr/src/${NAME}-${VERSION}"
KERNEL="$(uname -r)"
MODE="${1:-}"

if [[ "$MODE" != '--build-only' && "$MODE" != '--enable' ]]; then
    printf 'Usage: bash %s --build-only | --enable\n' "$0" >&2
    exit 2
fi
for f in atomman_ec_fan.c Makefile dkms.conf; do
    [[ -f "$SRC/$f" ]] || { echo "Missing $SRC/$f" >&2; exit 1; }
done

get_dmi() { tr -d '\n' < "/sys/class/dmi/id/$1"; }
if [[ "$(get_dmi sys_vendor)" != 'Micro Computer (HK) Tech Limited' || \
      "$(get_dmi product_name)" != 'AtomMan X Series' || \
      "$(get_dmi board_name)" != 'MTBAC' ]]; then
    echo "Unexpected hardware DMI. Aborting experimental AtomMan module installation." >&2
    exit 1
fi

sudo apt install -y dkms build-essential "linux-headers-$KERNEL"
sudo install -d -m 0755 "$TARGET"
sudo install -m 0644 "$SRC/atomman_ec_fan.c" "$SRC/Makefile" "$SRC/dkms.conf" "$TARGET/"
if [[ ! -L "/var/lib/dkms/${NAME}/${VERSION}/source" ]]; then
    sudo dkms add -m "$NAME" -v "$VERSION"
fi
if ! sudo dkms status -m "$NAME" -v "$VERSION" -k "$KERNEL" | grep -q 'installed'; then
    sudo dkms build -m "$NAME" -v "$VERSION" -k "$KERNEL"
    sudo dkms install -m "$NAME" -v "$VERSION" -k "$KERNEL"
fi
SIGNER="$(modinfo -F signer atomman_ec_fan 2>/dev/null || true)"
if [[ -z "$SIGNER" ]]; then
    echo "No module signer found. Check DKMS/MOK before testing or enabling EC reads." >&2
    exit 1
fi
printf 'Module signer: %s\n' "$SIGNER"
if command -v mokutil >/dev/null 2>&1 && mokutil --sb-state 2>/dev/null | grep -qi 'enabled'; then
    if [[ ! -f /var/lib/shim-signed/mok/MOK.der ]]; then
        echo "Missing expected enrolled MOK certificate; verify signing before testing EC." >&2
        exit 1
    fi
    if ! sudo mokutil --test-key /var/lib/shim-signed/mok/MOK.der; then
        echo "MOK certificate is not enrolled. EC reads NOT enabled." >&2
        exit 1
    fi
fi

if [[ "$MODE" == '--build-only' ]]; then
    echo "Build-only complete. No EC reads or modprobe configuration enabled."
    echo "See atomman-setup/README-QUICK.md for explicit, supervised load test."
    exit 0
fi

cat <<'CAUTION'
EXPERIMENTAL MODEL-SPECIFIC EC READER.
Even RPM reads involve writing the read command/address to the embedded controller.
Only enable persistently on this particular tested hardware after successful load test.
CAUTION
read -r -p "Have you run the supervised EC RPM/load test on THIS machine? Type TAK: " ANSWER
[[ "$ANSWER" == "TAK" ]] || { echo "Aborted."; exit 1; }

sudo install -D -m 0644 "$SCRIPT_DIR/systemd/atomman-ec-fan.conf" /etc/modprobe.d/atomman-ec-fan.conf
sudo modprobe atomman_ec_fan
if [[ "$(sudo cat /sys/module/atomman_ec_fan/parameters/enable_ec_reads)" != 'Y' ]]; then
    echo "Module previously loaded with reads disabled; no automatic reload performed." >&2
    echo "Stop atomman.service, unload atomman_ec_fan, then start atomman.service again." >&2
    exit 1
fi
sudo systemctl restart atomman.service

echo "EC RPM module ready. Verify with: sensors | grep -A 3 atomman_ec_fan"
echo "Then verify again after reboot."
