# AtomMan Windows adapter v5 — native NVMe temperature

This package builds on the **v4 audio fix**, which in turn uses the original Linux `screen.py` as-is. It adds real read-only Windows NVMe temperature via `IOCTL_STORAGE_QUERY_PROPERTY`, using the already-tested `atomman_nvme_temp_test.py` implementation.

## Files

- `screen_windows.py`: Windows adapter v5 (includes v4 thread-local pycaw fix)
- `atomman_nvme_temp_test.py`: Windows NVMe temperature reader (independent, no extra driver)

Keep your original `screen.py`, `screen_windows.local.json` and other files. **No private API keys are included.**

## Installation (PowerShell)

1. Stop any running AtomMan scripts with `Ctrl+C` (only one process can own COM3).
2. Back up the current adapter:

   ```powershell
   cd $HOME\AtomMan
   Copy-Item .\screen_windows.py "$HOME\screen_windows_backup.py"
   ```

3. Unzip both `.py` files into `$HOME\AtomMan` (overwrite only `screen_windows.py`). Do not replace your `screen.py` or `screen_windows.local.json`.
4. Optional: add `"disk_number": 0` to your existing private JSON config. Windows reported that drive `C:` is `PhysicalDrive0` (KINGSTON OM8PGP41024Q-A0). If the key is omitted, the adapter defaults to physical disk 0.

   Example JSON (substitute your own values; do not commit the actual key):

   ```json
   {
     "location": "Lodz,PL",
     "owm_api_key": "MY_PRIVATE_API_KEY",
     "disk_number": 0
   }
   ```

## Checks

1. Native NVMe check, without opening COM3:

   ```powershell
   py .\screen_windows.py --nvme-test
   ```

   Expected from your previously observed readings: `PhysicalDrive0 ... 35 C` (temperature can change).

2. Check display payload without opening COM3:

   ```powershell
   py .\screen_windows.py --check-api --port COM3
   ```

   `p_dsk` should now contain `Tempr:<actual value>` instead of `Tempr:0`. Other payloads should remain unchanged.

3. Start the actual display:

   ```powershell
   py .\screen_windows.py --port COM3 --start-delay 5
   ```

## Details / limitations

- **Disk selection**: the tile reports `PhysicalDrive0` sensor index 0; the code uses this value as the possible composite temperature. It is cached for 10 seconds to avoid excessive IOCTL calls. It remains `0` if unavailable, not a fabricated reading. The adapter does not yet auto-resolve C: to a physical disk: update `disk_number` if numbering changes.
- **Security**: read-only native Windows storage ioctl; no kernel sensor monitoring driver installed by this package.
- **CPU temperature** and **fan RPM**: still unavailable. The new code does not pretend that NVMe temperatures are CPU values or that NVIDIA GPU fan percentage is AtomMan fan RPM.
- **Touchscreen volume slider -> Windows**: not implemented; prior RX-only captures showed only the regular ENQ sequence. v4's Windows audio thread fix is included but must still be validated on the device.
- **Troubleshooting**: if `--nvme-test` reports an error, run from an elevated PowerShell once to distinguish permissions from unsupported queries. The separate NVMe diagnostic can still run with `py .\atomman_nvme_temp_test.py --disk 0 1`.
- The time-zone deprecation warnings originate in the original Linux `screen.py` and do not affect this patch.
