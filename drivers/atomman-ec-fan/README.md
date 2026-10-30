# AtomMan X7 Ti — experimental EC fan RPM hwmon / DKMS 0.2.0

**Status:** On one AtomMan X Series / MTBAC (Ubuntu 26.04, kernel 7.0.0-42-generic), version 0.2.0 is installed using DKMS and MOK signing. RPM was confirmed at about 1880–1910 at idle, climbing to 2260–2411 under a four-worker CPU load test (interrupted at a 90°C safety threshold, last sampled 91°C). After a reboot, systemd auto-loaded the driver and sensors showed ~1891 RPM. EC interface is ACPI `\\_SB.PC00.LPCB.H_EC.EC2R`, command 0xD5, offsets 0x18/0x19. Do not assume this is a certified hardware driver. EC read commands still write command/address values to hardware.

## Phase A — verify response to CPU load (before enabling persistent reads)

Install the load generator: `sudo apt install stress-ng`

1. Load the **existing, already signed, already tested** PoC for a one-off test:
   `sudo insmod ~/atomman-ec-poc/atomman_ec_fan.ko enable_ec_reads=1`
2. Run `bash ./fan_load_test.sh`. It records 5 baseline values, launches 4 CPU stress workers at 60% for 60 seconds, continuously monitors the coretemp package temperature and reads fan1_input, and records cooldown. It attempts to stop stress if package temp reaches 90°C (the confirmed test sampled 91°C before stopping). Stop manually with Ctrl+C if anything abnormal happens.
3. When done: `sudo rmmod atomman_ec_fan` (if loaded).

## Phase B — DKMS install (does not load or access EC)

Preconditions: Secure Boot MOK enrolled and `dkms`, `build-essential`, kernel headers installed.

```bash
sudo apt install dkms build-essential linux-headers-$(uname -r)
cd /path/to/atomman-ec-fan-dkms-v0.2.0
sudo install -d -m 755 /usr/src/atomman-ec-fan-0.2.0
sudo install -m 644 atomman_ec_fan.c Makefile dkms.conf /usr/src/atomman-ec-fan-0.2.0/
sudo dkms add -m atomman-ec-fan -v 0.2.0
sudo dkms build -m atomman-ec-fan -v 0.2.0 -k "$(uname -r)"
sudo dkms install -m atomman-ec-fan -v 0.2.0 -k "$(uname -r)"
dkms status
modinfo -n atomman_ec_fan
modinfo -F signer atomman_ec_fan
```

On Ubuntu, DKMS should automatically use enrolled MOK when configured appropriately. Confirm `modinfo -F signer` is nonempty and trusted **before loading**. If missing or signed by an untrusted key, stop here. Never disable Secure Boot to load the module.

## Phase C — explicit opt-in and LCD integration (AFTER successful stress test and DKMS signature check)

Create/edit `/etc/modprobe.d/atomman-ec-fan.conf` with:
```
options atomman_ec_fan enable_ec_reads=1
```

The version-controlled unit template is `atomman-setup/systemd/atomman.service`. For a manual installation, edit `/etc/systemd/system/atomman.service` with `sudo vim`:
- Add before `ExecStart` (next to existing pre-start):
  `ExecStartPre=-+/usr/sbin/modprobe atomman_ec_fan`
  The `+` runs modprobe with root privileges despite User= in the service; `-` makes failure nonfatal, allowing NVIDIA fallback.
- Switch command arguments from `--fan-prefer nvidia --fan-max-rpm 2200` to `--fan-prefer hwmon --fan-max-rpm 2200`.
- Keep the rest unchanged, including serial and audio settings.

Reload and restart:
```
sudo systemd-analyze verify /etc/systemd/system/atomman.service
sudo systemctl daemon-reload
sudo systemctl restart atomman.service
systemctl status atomman.service --no-pager -l
sensors | grep -A 3 -i atomman
```

## Verify reboot

```
uname -r
sudo dkms status
lsmod | grep atomman_ec_fan
modinfo -F signer atomman_ec_fan
systemctl is-active atomman.service
```

If kernel release changes, DKMS should rebuild automatically (`AUTOINSTALL=yes`); verify signing and `dkms status` after upgrade.

## Rollback

1. Edit `/etc/systemd/system/atomman.service`: remove `ExecStartPre=-+/usr/sbin/modprobe atomman_ec_fan` and restore `--fan-prefer nvidia`.
2. `sudo systemctl daemon-reload && sudo systemctl restart atomman.service`
3. `sudo rm -f /etc/modprobe.d/atomman-ec-fan.conf` (only if this is the file you created).
4. `sudo modprobe -r atomman_ec_fan` (if loaded).
5. Optional: `sudo dkms remove -m atomman-ec-fan -v 0.2.0 --all`; then remove `/usr/src/atomman-ec-fan-0.2.0` if no longer needed.

## Cautions and git

- Exact DMI gating: `Micro Computer (HK) Tech Limited` / `AtomMan X Series` / `MTBAC`.
- NO fan control or PWM writes; reads require EC command/address writes.
- Other ACPI/firmware users may share EC ports, and firmware AML mutex is not a universal guarantee of safety.
- Do not publish full `acpidump` directories, especially `msdm.dat` with a possible OEM Windows key.
- `.gitignore`: `*.ko`, `*.o`, `*.mod`, `*.mod.c`, `*.mod.o`, `Module.symvers`, `modules.order`, `.tmp_versions/`, `*.log`.

## Reproducible repository setup

Run `bash atomman-setup/50_app_setup.sh` after configuring `/etc/atomman.env`. For a new installation, use `bash atomman-setup/55_install_ec_fan.sh --build-only`, then perform a supervised EC test, and only then run `bash atomman-setup/55_install_ec_fan.sh --enable` (explicit `TAK` required). The repository systemd unit is a template; do not commit private `/etc/atomman.env`.
