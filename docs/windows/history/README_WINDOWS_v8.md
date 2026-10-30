# AtomMan X7 Ti — Windows adapter v8 (Direct CPU + DTR touchscreen experiment)

The package contains `screen_windows.py`, `atomman_lhm_direct.py`, `atomman_touch_volume.py`, `atomman_nvme_temp_test.py` and self-tests. **Do not replace `screen.py` (original Linux script)** and **do not overwrite `screen_windows.local.json`**. No SCCS binary, SCCS.sys, WinRing0, LibreHardwareMonitorLib.dll or PawnIO driver is included in the ZIP.

## What is confirmed

- The previous v6.1/v7 Windows adapter displayed the CPU/GPU/SSD temperatures when LibreHardwareMonitor's HTTP server was active; Windows → LCD volume sync worked.
- `atomman_lhm_direct.py` adds direct .NET library access, not GUI/HTTP. The CPU temperature reader accepts **only CPU temperature sensors**, preferring `CPU Package`, not the same-named power sensor.
- `atomman_touch_volume.py` recognizes the volume event decoded from the original SCCS executable: `AA 05 61 VV CC 33 C3 3C` where `VV` is 0..100. `--touch-volume` performs the Windows Audio update and ACK only after receiving a valid event. However previous captures were ENQ-only; **LCD→Windows functionality has not been proven on physical hardware**.
- SCCS.exe DCB settings include `DTR_CONTROL_ENABLE` (DTR on) and `RTS_CONTROL_ENABLE` (RTS on). Your current Linux script's default `DSRDTR=True` instead causes pyserial on Windows to select `DTR_CONTROL_HANDSHAKE`. `--touch-sccs-dtr` changes *only this serial-port setting* for an opt-in test. No undocumented firmware/EC commands are sent.

## 1. Prerequisites for direct CPU reads

Keep your official LibreHardwareMonitor 0.9.6 extracted folder, including `LibreHardwareMonitorLib.dll` and its companion managed DLL files. Use only official source: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases

In PowerShell:

```powershell
py -m pip install --upgrade "pythonnet>=3.2.1"
```

Open `$env:USERPROFILE\AtomMan\screen_windows.local.json`. Add **one new key** while keeping the existing `owm_api_key`, `location` and other settings. Example with backslashes escaped for JSON:

```json
{
  "location": "Lodz,PL",
  "owm_api_key": "KEEP_YOUR_EXISTING_PRIVATE_KEY",
  "lhm_dll": "C:\\Tools\\LibreHardwareMonitor\\LibreHardwareMonitorLib.dll",
  "disk_number": 0
}
```

Use the actual DLL path on your PC, not the illustrative `C:\Tools` path. You can locate it with:

```powershell
Get-ChildItem "$HOME\Downloads" -Filter LibreHardwareMonitorLib.dll -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
```

If you put `LibreHardwareMonitorLib.dll` and its companion DLLs under your AtomMan repository's `vendor\LHM\`, `"lhm_dll": "vendor/LHM/LibreHardwareMonitorLib.dll"` also works; avoid committing third-party binaries without following their licenses. No secret API key is packaged.

**Close** the LibreHardwareMonitor GUI/tray application (Exit). In PowerShell:

```powershell
py .\screen_windows.py --cpu-direct-test
py .\screen_windows.py --check-api --port COM3
```

Expected: `[Direct CPU] Temperature: ... C` and `p_cpu: {CPU:...;Tempr:...}`. If the direct test fails, report its `[Direct CPU] ERROR` line. It may require running PowerShell elevated and may depend on a separately installed, supported PawnIO driver. **It does not require the LHM GUI or HTTP server.** The older HTTP source remains a fallback *only when `lhm_dll` is not configured.* With the direct DLL configured there are no HTTP sensor requests, including fan reads.

## 2. Touch screen: safe DTR comparison

Make sure SCCS is stopped, and only one application holds COM3. Backup your known-good `screen_windows.py` before replacement. Verify the CPU test first. Then use **monitor-only** mode:

```powershell
py .\screen_windows.py --touch-self-test
py .\screen_windows.py --port COM3 --start-delay 5 --touch-monitor --touch-sccs-dtr
```

You should see a startup line indicating `DSRDTR=False`, `RTSCTS=False`. Drag the LCD volume slider to 20%, 50%, 80%. If the display sends the event, the console prints `[LCD TOUCH] Event 0x61 requests ...%`. The monitor **does not alter Windows audio**. If there is no such event, the experiment did not resolve the missing incoming touch events; do not enable `--touch-volume` and revert to your previous adapter if needed.

If and **only if** the event appears:

```powershell
py .\screen_windows.py --port COM3 --start-delay 5 --touch-volume --touch-sccs-dtr
```

This changes Windows volume and acknowledges a valid incoming event. The DTR setting is reset upon stopping this process, not flashed to firmware. `--touch-sccs-dtr` does not change BIOS, CPU power modes or fan speed.

If the DTR setting disrupts activation, press Ctrl+C and restore the backup:

```powershell
Copy-Item .\screen_windows_v7_backup.py .\screen_windows.py
```

(The backup filename is illustrative; use the actual name you chose.)

## Other limitations

- Internal AtomMan fan RPM still unavailable (`-1`); LibreHardwareMonitor did not report this sensor. GPU fan sensors do **not** represent the AtomMan internal fan.
- No power profile EC control is implemented.
- The Python source has existing unrelated `datetime.utcfromtimestamp()` deprecation warnings; v8 does not modify it.
- Only static/parser tests were possible here. Direct LHM loading and touch event delivery require a physical Windows/AtomMan test.
- **Security:** direct DLL access can still use PawnIO for hardware register access. It avoids the continuously running LibreHardwareMonitor *application*, not necessarily a kernel driver. The package itself does not install any driver.
