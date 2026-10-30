"""Read AtomMan CPU fan RPM from AIDA64's Windows registry export."""

import winreg
import psutil

REG_PATH = r"Software\FinalWire\AIDA64\SensorValues"

def fan_rpm(*_args):
    try:
        running = any(
            (p.info.get("name") or "").lower() == "aida64.exe"
            for p in psutil.process_iter(["name"])
        )
        if not running:
            return -1

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as key:
            value, _ = winreg.QueryValueEx(key, "Value.FCPU")

        rpm = int(value)
        return rpm if 0 <= rpm < 4000 else -1

    except (OSError, ValueError, TypeError, psutil.Error):
        return -1
