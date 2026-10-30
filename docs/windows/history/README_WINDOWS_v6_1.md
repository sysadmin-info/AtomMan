# AtomMan Windows v6.1 — CPU temperature sensor fix

This is a focused fix for the v6 LibreHardwareMonitor (LHM) sensor selector.

## Confirmed problem

`py screen_windows.py --lhm-test` in v6 could report a fake CPU temperature such as `22 C` with source `.../Powers/CPU Package`. This is CPU **power** in watts, not CPU temperature. LHM's sensor report shows an actual `CPU Package` **temperature** (`/intelcpu/0/temperature/18`) of 53 C at the moment of the report.

The v6.1 adapter requires an LHM `Temperatures` category or a Celsius unit and explicitly excludes `Powers` categories. If no valid temperature is available, the value stays 0 (unavailable), rather than using a power reading.

## Install

In PowerShell, stop the currently running display script with Ctrl+C, then:

```powershell
cd $HOME\AtomMan
Copy-Item .\screen_windows.py .\screen_windows_v6_backup.py
```

Copy `screen_windows.py` from this archive over `$env:USERPROFILE\AtomMan\screen_windows.py`. Leave the original Linux `screen.py` and private `screen_windows.local.json` unchanged. `atomman_nvme_temp_test.py` is unchanged from v6, so replacing it is optional.

LibreHardwareMonitor must already be running and its *local* web server available at http://127.0.0.1:8085/data.json. Avoid exposing this interface to the network.

First run the no-display tests:

```powershell
py .\screen_windows.py --lhm-test
py .\screen_windows.py --check-api --port COM3
```

The first result should show something like:

```
[LHM] CPU: 53 C | source: Sensor/<hostname>/Intel Core Ultra 9 185H/Temperatures/CPU Package
```

Live temperatures will vary. Critically, the selected source must be `Temperatures/CPU Package` (or `Temperatures/Core Max`) and **not** `Powers/CPU Package`.

Then test physical screen:

```powershell
py .\screen_windows.py --port COM3 --start-delay 5
```

Expected screen payload: `p_cpu: {CPU:...;Tempr:53;...}` with actual changing reading; numeric value may differ at run time.

## What remains unresolved

- The LHM report only contains NVIDIA GPU fan sensors; there is **no** identified fan sensor for the AtomMan chassis/CPU fan, so the adapter intentionally preserves `fan=-1`.
- Touchscreen LCD -> Windows volume is not implemented. The serial RX capture only contained ENQ frames and no touch commands. Windows -> LCD audio synchronization already works in v5/v6.
- The original Linux `screen.py` raises harmless `datetime.utcfromtimestamp()` deprecation warnings, which this change does not touch.
- The v6.1 adapter does not install, update or remove any driver. LibreHardwareMonitor may require its own system component for temperature readings. Ensure it is trustworthy before enabling its kernel driver.
