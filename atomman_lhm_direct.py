"""AtomMan: read CPU temperature directly from LibreHardwareMonitorLib.dll.

No LibreHardwareMonitor GUI process or web server is required. The DLL is
provided separately by the user from the official LibreHardwareMonitor build.
Accessing CPU sensor registers may still need the installed PawnIO kernel driver.
This module does not install/load WinRing0 or SCCS.sys. It does not configure fans.
"""
from __future__ import annotations

import atexit
import os
from pathlib import Path
import sys
import threading
import time


class DirectCpuReader:
    def __init__(self, dll_path: str | Path | None, poll_seconds: float = 2.5):
        raw = Path(dll_path).expanduser() if dll_path else None
        self.path = ((Path(__file__).resolve().parent / raw) if raw and not raw.is_absolute() else raw)
        self.poll_seconds = max(1.0, float(poll_seconds))
        self._lock = threading.RLock()
        self._computer = None
        self._cpu = 0
        self._source = None
        self._last_error = 'not queried'
        self._last_poll = float('-inf')
        self._closed = False

    @staticmethod
    def _find_cpu_sensor(computer):
        """Return int Celsius and source from CPU's actual temperature sensors.

        Requires SensorType.Temperature and CPU HardwareType, never CPU Package
        power (watts), never GPU, and never Distance to TjMax.
        """
        options = []
        for hw in computer.Hardware:
            if str(hw.HardwareType).casefold() != 'cpu':
                continue
            hw.Update()
            for sensor in hw.Sensors:
                if str(sensor.SensorType).casefold() != 'temperature':
                    continue
                name = str(sensor.Name)
                lower = name.casefold()
                if 'distance to' in lower or 'tjmax' in lower:
                    continue
                value = sensor.Value
                if value is None:
                    continue
                try:
                    temp = float(value)
                except (TypeError, ValueError):
                    continue
                if not 1 <= temp <= 120:
                    continue
                if lower == 'cpu package':
                    priority = 0
                elif lower == 'core max':
                    priority = 1
                elif lower == 'core average':
                    priority = 2
                else:
                    continue
                options.append((priority, round(temp), str(sensor.Identifier)))
        options.sort(key=lambda x: x[0])
        return (options[0][1], options[0][2]) if options else (0, None)

    def _initialize(self):
        if self._computer is not None:
            return
        if self._closed:
            raise RuntimeError('CPU reader already closed')
        if not self.path:
            raise FileNotFoundError('No lhm_dll configured in screen_windows.local.json')
        dll = self.path.resolve()
        if not dll.is_file():
            raise FileNotFoundError(f'LibreHardwareMonitorLib.dll not found: {dll}')
        if dll.name.lower() != 'librehardwaremonitorlib.dll':
            raise ValueError('lhm_dll must point to LibreHardwareMonitorLib.dll')
        if os.name != 'nt':
            raise OSError('Direct LibreHardwareMonitor DLL backend only runs on Windows')
        try:
            import clr  # pythonnet, not the unrelated PyPI package named "clr"
        except ImportError as exc:
            raise RuntimeError('pythonnet missing; run: py -m pip install pythonnet') from exc
        # pythonnet searches sys.path for managed dependencies such as HidSharp.
        dll_dir = str(dll.parent)
        if dll_dir not in sys.path:
            sys.path.insert(0, dll_dir)
        clr.AddReference(str(dll))
        from LibreHardwareMonitor import Hardware
        computer = Hardware.Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = False
        computer.IsStorageEnabled = False
        computer.IsNetworkEnabled = False
        computer.IsMemoryEnabled = False
        computer.IsMotherboardEnabled = False
        computer.IsControllerEnabled = False
        computer.Open()
        self._computer = computer
        atexit.register(self.close)

    def _refresh(self):
        now = time.monotonic()
        with self._lock:
            if now - self._last_poll < self.poll_seconds:
                return
            self._last_poll = now
            try:
                self._initialize()
                temp, source = self._find_cpu_sensor(self._computer)
                self._cpu, self._source = temp, source
                self._last_error = None if temp else 'No usable CPU temperature from DLL'
            except Exception as exc:
                self._cpu = 0
                self._source = None
                self._last_error = f'{type(exc).__name__}: {exc}'

    def cpu_temp(self):
        self._refresh()
        return self._cpu

    def status(self):
        self._refresh()
        return {'cpu': self._cpu, 'source': self._source, 'error': self._last_error,
                'dll': str(self.path) if self.path else None}

    def close(self):
        with self._lock:
            if self._computer is not None:
                self._computer.Close()
                self._computer = None
            self._closed = True
