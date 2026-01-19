# AtomMan (Linux) — Secure Boot + NVIDIA (DKMS signing) + AtomMan USB LCD daemon

This repository contains two parts:

- `screen.py` — the Python daemon that talks to the AtomMan USB serial LCD panel (runs as a systemd service).
- `atomman-setup/` — a numbered, reboot-friendly setup flow for Ubuntu with **Secure Boot enabled** (dual-boot safe) and NVIDIA drivers.

The goal is: after an `apt upgrade` (kernel / DKMS rebuild), you can re-run **one script** to re-sign NVIDIA modules and reboot.

---

## Repository layout

```
.
├── README.md
├── screen.py
└── atomman-setup/
    ├── 00_check.sh
    ├── 10_purge_nvidia.sh
    ├── 20_install_nvidia.sh
    ├── 30_secureboot_enroll_key.sh
    ├── 40_sign_or_reinstall_dkms.sh
    ├── 50_app_setup.sh
    ├── 60_env_write_example.sh
    ├── 70_verify.sh
    ├── requirements.txt
    ├── sudoers/atomman-dmidecode
    └── systemd/atomman.service
```

---

## Quick start (app only, without touching drivers)

If your NVIDIA driver is already working and Secure Boot signing is already done:

```bash
# Clone your fork
git clone https://github.com/sysadmin-info/AtomMan.git
cd AtomMan

# Create venv
python3 -m venv venv
. venv/bin/activate
pip install --upgrade pip
pip install -r atomman-setup/requirements.txt || pip install pyserial

# Run dashboard test in foreground
python ./screen.py --dashboard
```

---

## OpenWeather configuration (no secrets in code)

`screen.py` reads OpenWeather from environment variables.
Recommended: store them in `/etc/atomman.env` (used by systemd).

Example:

```bash
sudo tee /etc/atomman.env >/dev/null <<'EOF'
# Serial device (optional override)
ATOMMAN_PORT=/dev/serial/by-id/usb-Synwit_USB_Virtual_COM-if00
ATOMMAN_BAUD=115200

# Weather (OpenWeather)
ATOMMAN_OWM_API=YOUR_OPENWEATHER_KEY
ATOMMAN_OWM_LOCATION=51.7687,19.4570
ATOMMAN_OWM_UNITS=metric
ATOMMAN_OWM_LANG=pl
ATOMMAN_WEATHER_REFRESH=600

# Fan reading behavior (optional)
ATOMMAN_FAN_PREFER=nvidia
ATOMMAN_FAN_MAX_RPM=2200
EOF

sudo chmod 600 /etc/atomman.env
```

Notes:
- `ATOMMAN_OWM_LOCATION` can be `lat,lon` (best) or `City,CC`.
- `ATOMMAN_WEATHER_REFRESH=600` means “refresh every 10 minutes”.
- Keep the key **only** in `/etc/atomman.env` (or a user `.env` if you run manually).

---

## systemd service

A service unit is shipped in:

- `atomman-setup/systemd/atomman.service`

Install it:

```bash
sudo install -m 0644 atomman-setup/systemd/atomman.service /etc/systemd/system/atomman.service
sudo systemctl daemon-reload
sudo systemctl enable --now atomman
sudo systemctl status atomman --no-pager -l
```

Logs:

```bash
sudo tail -n 200 /var/log/atomman.log
# or
sudo journalctl -u atomman -b --no-pager -n 200
```

---

## Secure Boot + NVIDIA (the numbered scripts)

These scripts are designed so you can run them step-by-step, with clean reboot boundaries.

### 00_check.sh
Sanity checks (kernel, Secure Boot, GPU visibility, prerequisites).

```bash
cd atomman-setup
./00_check.sh
```

### 10_purge_nvidia.sh
Remove old NVIDIA packages (clean baseline).

```bash
sudo ./10_purge_nvidia.sh
```

### 20_install_nvidia.sh
Install NVIDIA driver (Ubuntu repo) and prerequisites.

```bash
sudo ./20_install_nvidia.sh
sudo reboot
```

After reboot:

```bash
nvidia-smi
```

If Secure Boot blocks modules, you will typically see:

```bash
dmesg | grep -i rejected | tail -n 50
```

### 30_secureboot_enroll_key.sh  (MOK key enrollment, includes DER conversion)
Creates a Machine Owner Key (MOK) and imports it into firmware (MOK Manager).

```bash
sudo ./30_secureboot_enroll_key.sh
sudo reboot
```

During reboot you must enroll the key in the blue MOK Manager screen:
Enroll MOK → Continue → Yes → enter password → reboot.

### 40_sign_or_reinstall_dkms.sh  (re-sign NVIDIA DKMS modules)
This is the “recovery” script you typically re-run after `apt upgrade` (new kernel / DKMS rebuild).

```bash
sudo ./40_sign_or_reinstall_dkms.sh
sudo reboot
```

After reboot:

```bash
nvidia-smi
```

### 50_app_setup.sh
Creates the venv, installs deps, installs systemd unit, prepares permissions.

```bash
sudo ./50_app_setup.sh
```

### 60_env_write_example.sh
Writes an example environment file (you should edit and put your real key).

```bash
sudo ./60_env_write_example.sh
```

### 70_verify.sh
Quick verification checklist.

```bash
./70_verify.sh
```

---

## Typical “after updates” recovery

If NVIDIA breaks after an `apt upgrade` and you see the module rejection message:

```bash
cd atomman-setup
sudo ./40_sign_or_reinstall_dkms.sh
```

The script will reboot the operating system automatically.

That is usually enough.

---

## Keeping your fork in sync with upstream (optional)

Upstream (original base): `RamSet/AtomMan` (if you still want to track it).

One approach:

```bash
git remote add upstream https://github.com/RamSet/AtomMan.git
git fetch upstream
git merge upstream/main   # or upstream/master depending on upstream
```

If upstream’s `screen.py` diverges from yours, keep yours and resolve conflicts in favor of your changes.

---

## License

Follow the license of the upstream project you forked from.
