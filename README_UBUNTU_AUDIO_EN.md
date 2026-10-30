# AtomMan X7 Ti — Ubuntu, bidirectional volume control v1.2

This adapter is **tailored to the `screen.py` shared on 2026-10-26**. It does not replace or modify the original `screen.py`: the CPU/GPU/RAM/SSD/NET/DATE/OWM/ENQ features remain unchanged.

> **Scope:** This document describes the Linux audio/touch adapter. For the current Ubuntu installation, systemd service and optional EC fan RPM driver, see [`atomman-setup/README-QUICK.md`](atomman-setup/README-QUICK.md) and [`drivers/atomman-ec-fan/README.md`](drivers/atomman-ec-fan/README.md).

## What was incompatible

1. `read_enq()` in `screen.py` only accepts `AA 05 ...`, while the touch panel transmits `AA 06 61 XX CC 33 C3 3C`.
2. `DSRDTR` defaults to `true`. On the working Windows 11 setup, receiving touch events required DTR to remain enabled without DSR handshaking.
3. `p_vol()` and `update_latest_from_payload(VOL)` call `pactl get-sink-volume` and return `-1` when an active PulseAudio/PipeWire session is unavailable. The adapter prefers `wpctl`, falling back to `pactl`, and uses the logged-in user's audio session.

The adapter intercepts `serial.Serial.read()` **on the same serial connection**; it does not open a second port. On a valid touch event (0–100%), it sets the volume using `wpctl`/`pactl` and sends the acknowledgement `AA 05 00 32 CC 33 C3 3C`. Monitor mode only logs events and does not change the volume.

## Requirements

Ubuntu/Linux, Python 3.10+, `pyserial` (check with `python3 -c 'import serial'`), and either `wpctl` or `pactl`. **The audio adapter itself does not require a new kernel driver.**

Run the adapter **as the logged-in desktop user, not with `sudo`**. PipeWire generally requires `XDG_RUNTIME_DIR` to refer to that user's session. A system-level systemd service can work when it runs with `User=<desktop-user>` and has the appropriate audio-session environment; the tested AtomMan configuration uses this approach.

Put `screen_linux_audio.py` alongside the current `screen.py`. Run `screen_linux_audio.py` on Ubuntu instead of invoking `screen.py` directly.

## Step 1: Audio tests (without the LCD)

```bash
cd /path/to/AtomMan
python3 screen_linux_audio.py --self-test
python3 screen_linux_audio.py --audio-test
python3 screen_linux_audio.py --check-volume-tile
```

Expect output similar to `[LINUX AUDIO] VOL payload: {VOLUME:50}` (the number is only an example). If you get `-1`, check:

```bash
id -un
printf '%s\n' "$XDG_RUNTIME_DIR"
wpctl get-volume @DEFAULT_AUDIO_SINK@
pactl get-sink-volume @DEFAULT_SINK@
```

A missing audio session (commonly caused by running the system service as root) is a separate issue from touch events. If this happens, first test manually as the logged-in desktop user.

## Step 2: Touch test (does not change volume)

Stop the old `screen.py` service/process so that the serial port is free. If `pyserial` cannot access the port, the user may need to belong to the `dialout` group; log out and back in after changing group membership.

```bash
python3 screen_linux_audio.py --touch-monitor --start-delay 5
```

Touch the volume control on the LCD. Expect a message such as `[LCD TOUCH] Event 0x61 requests 60%`.

## Step 3: Actual LCD ↔ Ubuntu volume control

Stop monitor mode with `Ctrl+C`, then run:

```bash
python3 screen_linux_audio.py --touch-volume --start-delay 5
```

Check that a change made on the LCD reaches Ubuntu:

```bash
wpctl get-volume @DEFAULT_AUDIO_SINK@
```

Then check the reverse direction:

```bash
wpctl set-volume @DEFAULT_AUDIO_SINK@ 25%
wpctl set-volume @DEFAULT_AUDIO_SINK@ 75%
```

The LCD slider should update on the next VOL tile refresh, which may not be immediate. For touch input, expect `Linux audio update: OK` and `ACK` messages.

## systemd considerations

If the original `screen.py` runs as a **system service under root**, it may not be able to access the desktop user's audio session. A `systemd --user` service started after PipeWire/WirePlumber is one option. Alternatively, a system service can run as the desktop user with the appropriate `XDG_RUNTIME_DIR` and D-Bus environment; this is how the tested installation is configured.

**Never run the old and new screen processes on the same serial port simultaneously.**

For the tested systemd configuration, see [`atomman-setup/systemd/atomman.service`](atomman-setup/systemd/atomman.service).

## Troubleshooting

- **Serial port failure:** inspect `ls -l /dev/serial/by-id/`, `groups`, and whether an older service is still running.
- **Volume unavailable:** check `--audio-test`; do not run the interactive audio adapter using `sudo`.
- **Touch input missing:** start with `--touch-monitor`. The `AA 06 61` frame format was verified on the physical device under Windows.
- **Scope of changes:** the adapter only affects volume handling, DTR/RTS behavior, and optionally the dashboard's Volume tile. The original `screen.py` remains unchanged.

## Testing history

**Original v1.2 validation:** parser tests against the 2026-10-25 capture (127 ENQ messages and three touch events: 0/32/0%), simulated `wpctl`/`pactl` tests, Volume tile tests, dashboard tests, and ACK tests passed. At that time, a physical Ubuntu test was still outstanding.

**Updated status (2026-10-30):** bidirectional touch-volume handling is working on the physical AtomMan X7 Ti under Ubuntu 26.04. The `atomman.service` system service starts successfully, including after a reboot, with `screen_linux_audio.py --touch-volume`. The independent `atomman_ec_fan` DKMS module also supplies actual internal fan RPM through `hwmon`; that module is documented separately and does **not** modify `screen.py`.

## v1.2 fix: Python 3.14 and `argparse`

The supplied `screen.py` contains `help="... RPM = % * this / 100"`. `argparse` treats a single `%` as a formatting placeholder, raising `ValueError: badly formed help string` before the LCD starts. Version 1.2 replaces `RPM = % * this / 100` with `RPM = %% * this / 100` **in interpreter memory only**. The original file is not changed. `pactl` is optional when `wpctl` works.

Run these commands from the directory containing `screen.py`:

```bash
python3 screen_linux_audio.py --self-test
python3 screen_linux_audio.py --touch-monitor --start-delay 5
# After confirming a 0x61 frame:
python3 screen_linux_audio.py --touch-volume --start-delay 5
```

Before manual testing, stop the production service:

```bash
sudo systemctl stop atomman.service
```

After testing, restore it if needed:

```bash
sudo systemctl start atomman.service
```

Do not run two processes against the same port.

**Installation paths:** the production systemd service invokes `/home/adrian/atomman/src/screen_linux_audio.py`, while development and Git operations use `~/AtomMan/`. These are distinct directories on the tested machine. The repository's service template uses placeholders so that a new installation does not depend on this particular username.
