# AtomMan X7 Ti Windows v6 — optional CPU/fan sensor bridge

## Status

- **Confirmed on user's Windows 11 with v5:** COM3 screen activation; GPU, RAM, storage usage, Wi-Fi, OpenWeatherMap weather, Windows volume -> LCD; Kingston `PhysicalDrive0` NVMe temperature via native Windows IOCTL.
- **New, unverified on user's hardware:** optional CPU temperature from *LibreHardwareMonitor* (LHM) local sensor web server; optional explicitly chosen fan RPM sensor.
- **Not solved by v6:** touchscreen slider -> Windows audio control. Prior RX captures contained only ENQ handshake frames, no touch packets; may be different interface/firmware behavior.
- v6 **does not install a driver**, load a kernel module, write fan controls, or enable remote LHM access. LHM itself may need its own hardware access driver, which must be assessed separately.

## Install v6 adapter (after checking LHM)

1. Stop existing `screen_windows.py` with `Ctrl+C`.
2. Back it up:

   ```powershell
   cd $HOME\AtomMan
   Copy-Item .\screen_windows.py .\screen_windows_v5_backup.py
   ```

3. Extract `screen_windows.py` from this ZIP to the `AtomMan` folder. You may keep your existing `atomman_nvme_temp_test.py` (unchanged); it is also bundled for convenience. **Do not replace** `screen.py` or `screen_windows.local.json`.
4. In your existing private `screen_windows.local.json`, continue using the original weather settings and optionally add `disk_number` and (later) `fan_sensor`:

   ```json
   {
     "location": "Lodz,PL",
     "owm_api_key": "KEEP_MY_EXISTING_KEY_PRIVATE",
     "disk_number": 0
   }
   ```

## CPU temperature check

1. Download LHM **only from** [official GitHub releases](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases). The 0.9.6 release (Feb 2026) includes updates to PawnIO modules. Review the drivers it installs before allowing kernel access; this is not a zero-driver hardware sensor solution.
2. Launch LHM, look for a **CPU Package** or **Core Max** temperature, and inspect whether a system fan is listed (do not confuse it with NVIDIA GPU fan).
3. Optional API integration: enable LHM **Options -> Remote Web Server -> Run** only for local access, and keep access blocked from LAN. Port is usually `8085`. You can verify it in PowerShell:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8085/data.json | Select-Object Text
   ```

   **Security:** Restrict it to 127.0.0.1 in LHM where possible; do not create a Windows Firewall inbound allow rule. Avoid 0.0.0.0 or externally exposed server without strong authentication.
4. Without opening COM3:

   ```powershell
   py .\screen_windows.py --lhm-test
   py .\screen_windows.py --check-api --port COM3
   ```

   `--lhm-test` prints selected CPU temperature and all **non-GPU** fan candidates. If LHM is absent or doesn't expose the sensor, the existing v5 behavior remains: `Tempr:0`, `fan=-1`.
5. Run the screen:

   ```powershell
   py .\screen_windows.py --port COM3 --start-delay 5
   ```

## Fan detection

**Do not assume the first Fan sensor is the X7 Ti chassis fan.** If LHM exposes a plausible system/EC fan, check its name and watch that it reacts to machine load. Only after positive identification add the exact sensor path from the `--lhm-test` output to your private JSON, e.g.:

```json
"fan_sensor": "PC/My Controller/Fans/CPU Fan"
```

This string is **illustrative, not a real detected path**. The adapter requires an exact (case-insensitive) match. It will never substitute RTX GPU fan speed.

## Touchscreen -> Windows volume diagnosis (separate task)

To check USB siblings for the screen's `0416:50A1` interface, without altering any drivers:

```powershell
Get-PnpDevice -PresentOnly | Where-Object InstanceId -Match 'VID_0416&PID_50A1|VID_0416' |
    Select-Object Class, FriendlyName, InstanceId | Format-List
```

The existing RX-only COM3 capture had 586 normal ENQ frames, 0 other packets. That is **not evidence of an actionable volume command on COM3**. A HID interface or proprietary USB control transfer remains possible, but unconfirmed. Do not send random commands to the controller or start SCCS to capture touch traffic; its driver was flagged vulnerable.

## Tests retained

```powershell
py .\screen_windows.py --nvme-test
py .\screen_windows.py --audio-test-background
py .\screen_windows.py --check-api --port COM3
```

Original Linux `screen.py` is unchanged. The two `utcfromtimestamp()` DeprecationWarnings originate there and are unrelated to v6.
