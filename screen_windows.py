#!/usr/bin/env python3
"""Windows adapter v9 (real AA 06 61 touch volume and direct CPU DLL) for AtomMan screen.py, preserving the original Linux source.

Place next to screen.py and run with `py screen_windows.py --list-ports` followed by
`py screen_windows.py --port COMx --dashboard`.

Reads weather config from screen_windows.local.json (private), or environment.
Uses pyserial + psutil; optionally nvidia-ml-py and pycaw. Reads NVMe
temperature through the native Windows storage API, no WinRing0 driver.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time


def list_ports():
    from serial.tools import list_ports as lp
    ports = list(lp.comports())
    for p in ports:
        print(f"{p.device:7s} {p.description} | {p.hwid}")
    if not ports:
        print('No serial ports detected. Check Device Manager > Ports (COM & LPT).')
    return ports


def pick_port(explicit: str | None) -> str:
    if explicit:
        return explicit
    port_env = os.getenv('ATOMMAN_PORT')
    if port_env:
        return port_env
    from serial.tools.list_ports import comports
    matches = [p for p in comports()
               if 'synwit' in (' '.join(str(x or '') for x in
                   (p.description, p.manufacturer, p.product, p.hwid))).lower()]
    if len(matches) == 1:
        return matches[0].device
    if len(matches) > 1:
        raise RuntimeError('Multiple Synwit serial ports; specify --port COMx.')
    raise RuntimeError('Synwit COM port not detected. Run --list-ports then specify --port COMx.')


class WindowsNetMeter:
    def __init__(self, psutil):
        self.psutil = psutil
        self.iface = self._detect_iface()
        self.before = None
        self.ts = None

    def _detect_iface(self):
        preferred = os.getenv('ATOMMAN_NET_IFACE')
        if preferred:
            return preferred
        local_ip = None
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(('1.1.1.1', 80))  # route lookup; sends no packets
                local_ip = s.getsockname()[0]
        except OSError:
            pass
        by_if = self.psutil.net_if_addrs()
        if local_ip:
            for name, addr_list in by_if.items():
                if any(a.family == socket.AF_INET and a.address == local_ip for a in addr_list):
                    return name
        stats = self.psutil.net_if_stats()
        counters = self.psutil.net_io_counters(pernic=True)
        for name in counters:
            if stats.get(name) and stats[name].isup and not any(
                x in name.lower() for x in ('vethernet', 'virtual', 'loopback', 'tailscale', 'bluetooth')
            ):
                return name
        return next(iter(counters), None)

    def rates_ks(self):
        counters = self.psutil.net_io_counters(pernic=True)
        if self.iface not in counters:
            self.iface = self._detect_iface()
            self.before = None
        if self.iface not in counters:
            return None, None
        current = counters[self.iface]
        now = time.monotonic()
        if self.before is None:
            self.before = current
            self.ts = now
            return 0.0, 0.0
        delta = max(now - self.ts, 0.001)
        rx = max(0, current.bytes_recv - self.before.bytes_recv) / delta / 1024
        tx = max(0, current.bytes_sent - self.before.bytes_sent) / delta / 1024
        self.before, self.ts = current, now
        return rx, tx


class WindowsGPU:
    def __init__(self):
        self.pynvml = None
        self.handle = None
        try:
            import pynvml
            pynvml.nvmlInit()
            self.pynvml = pynvml
            self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            pass

    def info(self):
        if self.handle is not None:
            try:
                p = self.pynvml
                name = p.nvmlDeviceGetName(self.handle)
                if isinstance(name, bytes):
                    name = name.decode('utf-8', 'replace')
                return (str(name), int(p.nvmlDeviceGetTemperature(self.handle, p.NVML_TEMPERATURE_GPU)),
                        int(p.nvmlDeviceGetUtilizationRates(self.handle).gpu))
            except Exception:
                pass
        try:
            cp = subprocess.run(['nvidia-smi', '--query-gpu=name,temperature.gpu,utilization.gpu',
                                 '--format=csv,noheader,nounits'], text=True,
                                capture_output=True, timeout=2, check=True)
            n, t, u = [i.strip() for i in cp.stdout.splitlines()[0].split(',')[:3]]
            return (n, int(float(t)), int(float(u)))
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return ('GPU', 0, 0)

    def fan_estimate(self, max_rpm):
        # NVIDIA reports a *percentage*, not actual fan RPM. Explicit opt-in.
        if os.getenv('ATOMMAN_GPU_FAN_ESTIMATE', '0') != '1':
            return -1
        if self.handle is None:
            return -1
        try:
            percentage = self.pynvml.nvmlDeviceGetFanSpeed(self.handle)
            return round(float(percentage) * max_rpm / 100)
        except Exception:
            return -1


def windows_cpu_name():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as k:
            return winreg.QueryValueEx(k, 'ProcessorNameString')[0].strip()
    except Exception:
        import platform
        return platform.processor() or 'CPU'


def audio_info(verbose=False):
    """Read default Windows master volume safely from any Python thread.

    Unlike main-thread --audio-test, p_vol() can run from the display worker.
    COM must be initialized in that thread before using pycaw/comtypes. Every
    successful CoInitialize() is matched with CoUninitialize() on that thread.
    """
    comtypes_module = None
    initialized = False
    try:
        import comtypes
        comtypes_module = comtypes
        # An STA apartment is appropriate for pycaw. Windows COM initialization
        # is thread-local, not inherited from the Python main thread.
        comtypes.CoInitialize()
        initialized = True
        from pycaw.pycaw import AudioUtilities
        speaker = AudioUtilities.GetSpeakers()
        if speaker is None:
            raise RuntimeError('Windows has no default audio output device')
        label = getattr(speaker, 'FriendlyName', '(unknown output device)')
        try:
            pct = getattr(speaker, 'volume_percent')
            if pct is not None:
                value = int(round(float(pct)))
                if 0 <= value <= 100:
                    if verbose:
                        print(f'[Audio] Default output: {label}; volume: {value}% (volume_percent)')
                    return value
        except (AttributeError, TypeError, ValueError, OSError):
            pass
        endpoint = speaker.EndpointVolume
        value = int(round(float(endpoint.GetMasterVolumeLevelScalar()) * 100))
        if verbose:
            print(f'[Audio] Default output: {label}; volume: {value}% (EndpointVolume)')
        return min(max(value, 0), 100)
    except Exception as exc:
        if verbose:
            print(f'[Audio] Unavailable: {type(exc).__name__}: {exc}')
            print('[Audio] Check the output device and per-thread COM initialization.')
        return -1
    finally:
        if initialized and comtypes_module is not None:
            comtypes_module.CoUninitialize()


def audio_worker_test():
    """Simulate p_vol() running on a background display thread."""
    import threading
    results = []
    def worker():
        results.append(audio_info(verbose=True))
    th = threading.Thread(target=worker, name='atomman-audio-worker-test')
    th.start()
    th.join(timeout=5)
    if th.is_alive():
        raise RuntimeError('Audio worker did not finish in five seconds')
    value = results[0] if results else -1
    print(f'[Audio] Worker-thread result: {value}%')
    if value < 0:
        raise RuntimeError('Unable to read Windows volume from background thread')


def windows_volume():
    return audio_info(verbose=False)


def load_local_config():
    """Private local JSON config, stored beside the adapter, not in Git."""
    f = Path(__file__).with_name('screen_windows.local.json')
    if not f.is_file():
        return {}
    try:
        with f.open('r', encoding='utf-8-sig') as fp:
            cfg = json.load(fp)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'Cannot read {f.name}: {exc}') from exc
    if not isinstance(cfg, dict):
        raise RuntimeError(f'{f.name}: expected a JSON object')
    return cfg


class LocalHardwareSensors:
    """Optional read-only LibreHardwareMonitor bridge on loopback only.

    This adapter itself installs/loads no drivers. LHM may require its own
    kernel access driver: install/enable that separately only if acceptable.
    Never treat GPU fan as the AtomMan CPU/system fan.
    """

    URL = 'http://127.0.0.1:8085/data.json'

    def __init__(self, poll_seconds: float = 5.0, fan_sensor: str | None = None):
        import threading
        self.poll_seconds = max(2.0, float(poll_seconds))
        self.fan_sensor = str(fan_sensor or '').strip().casefold()
        self._lock = threading.RLock()
        self._last_at = float('-inf')
        self._cpu = 0
        self._fan = -1
        self._last_error = 'not queried'
        self._candidates = []

    @staticmethod
    def _numeric(x):
        # LHM JSON has localized strings like '48.5 °C', '2240 RPM', or numeric Value.
        if isinstance(x, (float, int)) and not isinstance(x, bool):
            return float(x)
        if isinstance(x, str):
            m = re.search(r'[-+]?\d+(?:[.,]\d+)?', x)
            if m:
                return float(m.group(0).replace(',', '.'))
        return None

    @classmethod
    def parse(cls, data):
        """Return CPU temp, supported fan candidates, all readable temp/fan nodes.

        No sensor is assumed to be an AtomMan CPU fan purely by sensor order.
        """
        entries = []
        def walk(node, path=()):
            if isinstance(node, list):
                for child in node:
                    walk(child, path)
                return
            if not isinstance(node, dict):
                return
            name = str(node.get('Text') or node.get('Name') or '').strip()
            current = path + ((name,) if name else ())
            value = cls._numeric(node.get('Value'))
            if value is not None and name:
                entries.append({'path': '/'.join(current), 'name': name,
                                'value': value, 'raw_value': node.get('Value'),
                                'ancestors': path})
            walk(node.get('Children', ()), current)
        walk(data)
        cpu_choices = []
        fans = []
        diagnostic = []
        for entry in entries:
            ancestors = '/'.join(entry['ancestors']).casefold()
            leaf = entry['name'].casefold()
            path = entry['path']
            val = entry['value']
            # Only take CPU-specific measurements; skip GPUs and drive groups.
            cpu_branch = any(k in ancestors for k in (
                '/cpu/', 'intel core', 'core ultra', 'intelcpu', 'intel cpu', 'amd ryzen',
                'cpu [', 'cpu/', 'cpu #'))
            if ('gpu' in ancestors or '/hdd' in ancestors or
                    'storage' in ancestors or '/nvme' in ancestors):
                cpu_branch = False
            # The same leaf label (e.g. CPU Package) is used for both
            # Watts and Celsius in LibreHardwareMonitor.  v6 mistakenly
            # selected the CPU Package under /Powers/ (e.g. 22 W => 22 C).
            # Require an explicit temperature category or Celsius unit.
            categories = tuple(str(x).strip().casefold() for x in entry['ancestors'])
            raw_value = str(entry['raw_value']).casefold()
            is_temperature = (
                any('temperat' in x or x in ('temps', 'thermal') for x in categories)
                or '°c' in raw_value or '℃' in raw_value
            )
            is_power = any('power' in x or 'watt' in x for x in categories)
            if cpu_branch and is_temperature and not is_power and 1 <= val <= 120 and (
                    'cpu package' in leaf or 'cpu core max' in leaf or
                    'core max' in leaf or 'cpu cores' in leaf or 'core average' in leaf):
                if 'cpu package' in leaf:
                    priority = 0
                elif 'core max' in leaf:
                    priority = 1
                else:
                    priority = 2
                cpu_choices.append((priority, val, path))
            # Known-value fan nodes, filtered to exclude GPU fan speed/percent.
            if ('fan' in ancestors or 'fan' in leaf) and (
                    'rpm' in str(entry.get('path', '')).casefold() or
                    '/fans/' in ancestors or '/fan/' in ancestors or
                    'fan' in leaf):
                if 0 <= val <= 15000:
                    if not any(k in ancestors for k in ('gpu', 'graphics', 'nvidia', 'radeon', 'geforce', 'intel arc')):
                        fans.append(entry)
            if ('temperature' in ancestors or 'fan' in ancestors) and (
                    'cpu' in path.casefold() or 'fan' in path.casefold()):
                diagnostic.append(entry)
        cpu_choices.sort(key=lambda x: x[0])
        cpu = round(cpu_choices[0][1]) if cpu_choices else 0
        cpu_source = cpu_choices[0][2] if cpu_choices else None
        return cpu, cpu_source, fans, diagnostic

    def _refresh(self):
        import urllib.request
        now = time.monotonic()
        with self._lock:
            if now - self._last_at < self.poll_seconds:
                return
            self._last_at = now
            self._cpu, self._fan = 0, -1
            self._candidates = []
            try:
                req = urllib.request.Request(self.URL, headers={'User-Agent': 'AtomMan-local-sensor-reader/1'})
                # Disable any global proxy settings; loopback only.
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(req, timeout=0.8) as response:
                    if response.status != 200:
                        raise RuntimeError(f'HTTP {response.status}')
                    body = response.read(1024 * 1024 + 1)
                    if len(body) > 1024 * 1024:
                        raise RuntimeError('sensor data too large')
                obj = json.loads(body)
                cpu, source, fans, diagnostic = self.parse(obj)
                self._cpu = cpu
                self._candidates = fans
                if self.fan_sensor:
                    matches = [f for f in fans if self.fan_sensor == f['path'].casefold()]
                    if len(matches) == 1:
                        self._fan = round(matches[0]['value'])
                    elif len(matches) > 1:
                        self._last_error = 'ambiguous fan sensor match'
                self._last_error = None if cpu else 'no CPU Package/Core Max temperature'
                self._cpu_source = source
            except Exception as e:
                self._cpu_source = None
                self._last_error = f'{type(e).__name__}: {e}'

    def cpu_temp(self):
        self._refresh()
        return self._cpu

    def fan_rpm(self, *_unused):
        # Leave at -1 until explicitly configured using --lhm-test sensor path.
        self._refresh()
        return self._fan

    def status(self):
        self._refresh()
        return {'cpu': self._cpu, 'source': self._cpu_source,
                'fan': self._fan, 'error': self._last_error,
                'fans': [{'path': f['path'], 'rpm': f['value']} for f in self._candidates]}


def direct_cpu_test(config):
    from atomman_lhm_direct import DirectCpuReader
    reader = DirectCpuReader(config.get('lhm_dll'))
    try:
        status = reader.status()
        print('[Direct CPU] DLL:', status['dll'] or '(unset)')
        print('[Direct CPU] Temperature:', f"{status['cpu']} C" if status['cpu'] else 'unavailable')
        print('[Direct CPU] Sensor:', status['source'] or '(none)')
        if status['error']:
            print('[Direct CPU] ERROR:', status['error'])
            return False
        return bool(status['cpu'])
    finally:
        reader.close()


def lhm_test(config):
    sensors = LocalHardwareSensors(fan_sensor=config.get('fan_sensor'))
    st = sensors.status()
    print('[LHM] URL:', sensors.URL)
    print('[LHM] CPU:', f"{st['cpu']} C" if st['cpu'] else 'unavailable',
          '| source:', st['source'] or '(none)')
    print('[LHM] AtomMan fan:', f"{st['fan']} RPM" if st['fan'] >= 0 else 'unavailable')
    print('[LHM] Fan candidates (not necessarily AtomMan fan):')
    for f in st['fans']:
        print('  ', f['path'], '=', f['rpm'], 'RPM')
    if st['error']:
        print('[LHM] Note:', st['error'])
        if 'urlopen' in st['error'] or 'URLError' in st['error']:
            print('[LHM] Optional: start LibreHardwareMonitor, then enable local Remote Web Server on port 8085.')
    print('[LHM] No new drivers installed by AtomMan.')


class WindowsNvmeTemp:
    """Cached, read-only Windows NVMe temperature for a specific PhysicalDrive.

    The bundled atomman_nvme_temp_test.py contains the IOCTL implementation
    already tested separately on this AtomMan. Sensor index 0 represents the
    drive's composite temperature where supplied by the NVMe controller.
    """

    def __init__(self, disk_number: int, poll_seconds: float = 10.0):
        self.disk_number = disk_number
        self.poll_seconds = max(1.0, float(poll_seconds))
        self._last_query_at = float('-inf')
        self._last_result = 0  # Existing firmware payload uses 0 for unavailable.
        self._last_error = None

    def read(self) -> int:
        now = time.monotonic()
        if now - self._last_query_at < self.poll_seconds:
            return self._last_result
        self._last_query_at = now
        self._last_result = 0
        try:
            from atomman_nvme_temp_test import query_disk
            response = query_disk(self.disk_number)
            if isinstance(response, str):
                self._last_error = response
                return 0
            method, sensors = response
            values = {int(idx): int(temp) for idx, temp in sensors}
            # Only index 0 is defined as possibly representing composite temp.
            # Do not silently substitute a different hotspot sensor.
            temp = values.get(0)
            if temp is None:
                self._last_error = f'no composite sensor 0 ({method}; {sensors})'
                return 0
            if not (-20 <= temp <= 125):
                self._last_error = f'implausible sensor 0 temperature: {temp} C'
                return 0
            self._last_result = temp
            self._last_error = None
        except Exception as exc:
            self._last_error = f'{type(exc).__name__}: {exc}'
        return self._last_result

    @property
    def last_error(self):
        return self._last_error


def nvme_test(config: dict):
    try:
        disk_number = int(config.get('disk_number', 0))
    except (TypeError, ValueError):
        raise RuntimeError('disk_number must be an integer in screen_windows.local.json')
    if not 0 <= disk_number <= 255:
        raise RuntimeError('disk_number must be between 0 and 255')
    sensor = WindowsNvmeTemp(disk_number)
    temp = sensor.read()
    print(f'[NVMe] PhysicalDrive{disk_number} composite sensor 0: '
          + (f'{temp} C' if temp else 'unavailable'))
    if sensor.last_error:
        print('[NVMe] Details:', sensor.last_error)
    return temp


def apply_patch(mod):
    """Patch source functions in their original global namespace before main runs."""
    import psutil

    # These symbols are required by the original display protocol and metrics.
    # disk_temp_c/_read_volume/_read_battery are absent from older forks: optional.
    required = ('PORT', 'cpu_model', 'cpu_usage_pct', 'cpu_freq_khz', 'cpu_temp_c',
                'gpu_info', 'mem_info', 'disk_numbers', 'ram_label', 'disk_label',
                'fan_rpm', '_nm')
    missing = [name for name in required if name not in mod]
    if missing:
        raise RuntimeError('Your screen.py has a different API. Missing: ' + ', '.join(missing))

    gpu = WindowsGPU()
    config = load_local_config()
    sensors = LocalHardwareSensors(fan_sensor=config.get('fan_sensor'))
    direct = None
    if config.get('lhm_dll'):
        from atomman_lhm_direct import DirectCpuReader
        direct = DirectCpuReader(config['lhm_dll'])
    cpu_reader = direct if direct is not None else sensors
    psutil.cpu_percent(interval=None)  # prime sampling
    name = windows_cpu_name()
    net = WindowsNetMeter(psutil)

    mod['cpu_model'] = lambda: name
    mod['cpu_usage_pct'] = lambda: round(psutil.cpu_percent(interval=None))
    def cpu_freq_khz():
        f = psutil.cpu_freq()
        return round(f.current * 1000) if f else 0

    mod['cpu_freq_khz'] = cpu_freq_khz
    mod['cpu_temp_c'] = cpu_reader.cpu_temp  # direct DLL, or original HTTP fallback
    mod['gpu_info'] = gpu.info

    def memory():
        mem = psutil.virtual_memory()
        gb = lambda x: round(x / (1024**3), 1)
        return (gb(mem.total - mem.available), gb(mem.available), gb(mem.total), round(mem.percent))

    def disk():
        drive = os.environ.get('SystemDrive', 'C:') + '\\' if sys.platform == 'win32' else '/'
        d = psutil.disk_usage(drive)
        gb = lambda x: round(x / (1024**3))
        return (gb(d.used), gb(d.total), round(d.percent))

    mod['mem_info'] = memory
    mod['disk_numbers'] = disk
    mod['ram_label'] = lambda: 'Memory'
    mod['disk_label'] = lambda: 'Windows Drive'
    # On this AtomMan Windows identifies the system drive C: as PhysicalDrive0
    # (KINGSTON OM8PGP41024Q-A0). Its native NVMe sensor 0 reports a real temp.
    # Change disk_number in private JSON if drive numbering changes.
    try:
        disk_number = int(config.get('disk_number', 0))
    except (TypeError, ValueError):
        raise RuntimeError('disk_number must be an integer in screen_windows.local.json')
    if not 0 <= disk_number <= 255:
        raise RuntimeError('disk_number must be between 0 and 255')
    nvme = WindowsNvmeTemp(disk_number)
    mod['disk_temp_c'] = nvme.read
    mod['fan_rpm'] = (lambda *_args: -1) if direct is not None else sensors.fan_rpm  # no HTTP if direct DLL
    mod['_nm'] = net
    mod['_read_volume'] = windows_volume
    def windows_battery():
        try:
            battery = psutil.sensors_battery()
            return round(battery.percent) if battery else 177
        except (OSError, RuntimeError, AttributeError):
            return 177

    mod['_read_battery'] = windows_battery

    # Older Linux screen.py forks implement disk/volume/battery tiles directly,
    # without disk_temp_c, _read_volume, or _read_battery functions. Patch their
    # payload generators, and update any rotations that captured old callables.
    replacements = {}

    if 'p_dsk' in mod and callable(mod['p_dsk']):
        old_disk_tile = mod['p_dsk']
        def windows_disk_tile():
            payload = old_disk_tile()
            # Older Linux forks hardcode a placeholder temperature in p_dsk().
            # Replace only that field with the real NVMe reading (cached 10 s).
            return re.sub(r'\bTempr:\s*-?\d+',
                          lambda _: f'Tempr:{nvme.read()}', payload, count=1)
        replacements[old_disk_tile] = windows_disk_tile
        mod['p_dsk'] = windows_disk_tile

    if 'p_vol' in mod and callable(mod['p_vol']):
        old_vol_tile = mod['p_vol']
        def windows_volume_tile():
            volume = windows_volume()
            if isinstance(mod.get('_last_vol_bat'), dict):
                mod['_last_vol_bat']['volume'] = volume
            return f'{{VOLUME:{volume}}}'
        replacements[old_vol_tile] = windows_volume_tile
        mod['p_vol'] = windows_volume_tile

    if 'p_bat' in mod and callable(mod['p_bat']):
        old_bat_tile = mod['p_bat']
        def windows_battery_tile():
            battery = windows_battery()
            if isinstance(mod.get('_last_vol_bat'), dict):
                mod['_last_vol_bat']['battery'] = battery
            return f'{{Battery:{battery}}}'
        replacements[old_bat_tile] = windows_battery_tile
        mod['p_bat'] = windows_battery_tile

    def update_function_refs(obj):
        # Some versions build the rotation list before this patch runs.
        try:
            if callable(obj):
                return replacements.get(obj, obj)
        except TypeError:
            return obj
        if isinstance(obj, tuple):
            return tuple(update_function_refs(x) for x in obj)
        if isinstance(obj, list):
            return [update_function_refs(x) for x in obj]
        if isinstance(obj, dict):
            return {k: update_function_refs(v) for k, v in obj.items()}
        return obj

    for key, value in list(mod.items()):
        if key.isupper() and isinstance(value, (tuple, list, dict)):
            mod[key] = update_function_refs(value)

    # A private local file is more convenient than setting PowerShell variables.
    # Env vars take precedence when intentionally specified for this run.
    key = os.getenv('ATOMMAN_OWM_API') or config.get('owm_api_key')
    city = os.getenv('ATOMMAN_LOCATION') or config.get('location')
    if key:
        mod['OW_API_KEY'] = str(key).strip()
    if city:
        mod['OW_LOCATION'] = str(city).strip()
    if '_internet_ok' in mod:
        mod['_internet_ok'] = lambda *a, **kw: True  # HTTPS weather fetch does real connectivity test

    touch_mode = os.environ.get('_ATOMMAN_TOUCH_MODE', '')
    if os.environ.get('_ATOMMAN_SCCS_DTR') == '1':
        # SCCS.exe sets Win32 DCB fDtrControl=DTR_CONTROL_ENABLE and
        # fRtsControl=RTS_CONTROL_ENABLE. pyserial's dsrdtr=True instead
        # means DTR_CONTROL_HANDSHAKE, which is not equivalent.
        # Changes ONLY COM3 flow-control setup, no firmware commands.
        mod['DSRDTR'] = False
        mod['RTSCTS'] = False
        print('[LCD TOUCH] SCCS serial: DTR=enabled, RTS=enabled, flow handshake=OFF')
    if touch_mode in ('monitor', 'control'):
        from atomman_touch_volume import install_serial_listener
        install_serial_listener(mod['PORT'],
                                set_volume=(touch_mode == 'control'), debug=True)

    print('[Windows adapter] Serial port:', mod['PORT'])
    print('[Windows adapter] NIC:', net.iface)
    print('[Windows adapter] CPU:', name)
    print('[Windows adapter] GPU:', gpu.info()[0])
    temp = nvme.read()
    if direct is not None:
        st = direct.status()
        print('[Windows adapter] CPU temp (direct DLL):', st['cpu'], 'C (0 = unavailable)')
        if st['error']:
            print('[Windows adapter] CPU DLL note:', st['error'])
    else:
        print('[Windows adapter] CPU temp (LHM HTTP fallback):', sensors.cpu_temp(), 'C (0 = unavailable)')
    print('[Windows adapter] Fan RPM:', -1 if direct is not None else sensors.fan_rpm(), '(-1 = unavailable)')
    print(f'[Windows adapter] SSD PhysicalDrive{disk_number} temperature: '
          + (f'{temp} C (NVMe sensor 0)' if temp else f'unavailable ({nvme.last_error})'))
    print('[Windows adapter] No WinRing0 / SCCS driver used.')
    print('[Windows adapter] Default audio volume:', windows_volume(), '% (-1 = unavailable)')
    print('[Windows adapter] Weather location:', mod.get('OW_LOCATION', '(unset)'))
    print('[Windows adapter] OWM API key:', 'configured' if mod.get('OW_API_KEY') else 'missing')


def check_api(mod):
    print('[Windows adapter] Dry-run: serial port NOT opened.')
    for name, args in (
        ('p_cpu', ()), ('p_gpu', ()), ('p_mem', ()), ('p_dsk', ()),
        ('p_net', ('auto', 2000)), ('p_vol', ()), ('p_bat', ()),
    ):
        func = mod.get(name)
        if not callable(func):
            print(f'{name}: NOT AVAILABLE')
            continue
        try:
            print(f'{name}: {func(*args)}')
        except Exception as exc:
            print(f'{name}: ERROR: {type(exc).__name__}: {exc}')
    print('[Windows adapter] End of dry-run.')


def main():
    parser = argparse.ArgumentParser(description='AtomMan screen.py Windows adapter')
    parser.add_argument('--list-ports', action='store_true')
    parser.add_argument('--port', metavar='COMx', help='Explicit Windows serial port')
    parser.add_argument('--self-test', action='store_true', help='Check Windows metrics without opening the display')
    parser.add_argument('--audio-test', action='store_true', help='Diagnose default Windows audio output volume, no display access')
    parser.add_argument('--audio-test-background', action='store_true', help='Test pycaw COM access from a worker thread, no display access')
    parser.add_argument('--nvme-test', action='store_true', help='Test native NVMe disk temperature, without opening COM')
    parser.add_argument('--lhm-test', action='store_true', help='Read localhost LibreHardwareMonitor CPU and fan sensors, no COM')
    parser.add_argument('--cpu-direct-test', action='store_true', help='Read CPU directly via LibreHardwareMonitorLib.dll, no app/http/COM')
    parser.add_argument('--check-api', action='store_true', help='Check adapted screen.py payloads without opening COM port')
    parser.add_argument('--touch-monitor', action='store_true', help='Log inbound touchscreen events (read-only, no audio changes)')
    parser.add_argument('--touch-volume', action='store_true', help='Set Windows volume on verified SCCS touchscreen event 0x61')
    parser.add_argument('--touch-self-test', action='store_true', help='Test the touch event decoder without COM or audio')
    parser.add_argument('--touch-sccs-dtr', action='store_true', help='Enable SCCS-style DTR=ON, RTS=ON; verified to receive physical 0x61 events')
    args, passthrough = parser.parse_known_args()

    if args.touch_self_test:
        from atomman_touch_volume import self_test
        self_test()
        return
    if args.touch_monitor and args.touch_volume:
        parser.error('Choose one of --touch-monitor or --touch-volume')
    if args.touch_sccs_dtr and not (args.touch_monitor or args.touch_volume):
        parser.error('--touch-sccs-dtr requires --touch-monitor or --touch-volume')
    if args.touch_sccs_dtr:
        os.environ['_ATOMMAN_SCCS_DTR'] = '1'
    if args.touch_monitor or args.touch_volume:
        os.environ['_ATOMMAN_TOUCH_MODE'] = 'control' if args.touch_volume else 'monitor'

    if args.list_ports:
        list_ports()
        return
    if args.audio_test:
        audio_info(verbose=True)
        return
    if args.audio_test_background:
        audio_worker_test()
        return
    if args.lhm_test:
        lhm_test(load_local_config())
        return
    if args.cpu_direct_test:
        ok = direct_cpu_test(load_local_config())
        if not ok:
            raise SystemExit(1)
        return
    if args.nvme_test:
        if sys.platform != 'win32':
            parser.error('--nvme-test requires native Windows Python')
        nvme_test(load_local_config())
        return
    if sys.platform != 'win32' and not (args.self_test or args.check_api):
        parser.error('This adapter is intended to run under native Windows Python, not WSL/Linux.')
    if args.self_test:
        import psutil
        print('CPU:', windows_cpu_name(), psutil.cpu_percent(interval=0.1), '%')
        print('RAM:', psutil.virtual_memory())
        print('Disk:', psutil.disk_usage(os.environ.get('SystemDrive', '/') + ('\\' if sys.platform == 'win32' else '')))
        print('GPU:', WindowsGPU().info())
        print('Network:', WindowsNetMeter(psutil).iface)
        return

    port = args.port or ('COM3' if args.check_api else pick_port(args.port))
    os.environ['ATOMMAN_PORT'] = port
    source_file = Path(__file__).with_name('screen.py')
    if not source_file.is_file():
        parser.error(f'Place the original Linux screen.py next to this file: {source_file}')
    source = source_file.read_text(encoding='utf-8-sig')
    tree = ast.parse(source, filename=str(source_file))

    def is_main_guard(node):
        if not isinstance(node, ast.If):
            return False
        t = node.test
        return (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                and t.left.id == '__name__' and len(t.ops) == 1
                and isinstance(t.ops[0], ast.Eq) and len(t.comparators) == 1
                and isinstance(t.comparators[0], ast.Constant)
                and t.comparators[0].value == '__main__')

    guards = [n for n in tree.body if is_main_guard(n)]
    if len(guards) != 1:
        parser.error('Expected one `if __name__ == "__main__"` guard in screen.py; found ' + str(len(guards)))
    lines = source.splitlines(keepends=True)
    idx = guards[0].lineno - 1
    injected = '\n_atomman_windows_patch(globals())\n'
    if args.check_api:
        injected += '_atomman_windows_check(globals())\nraise SystemExit(0)\n'
    lines.insert(idx, injected)
    namespace = {'__name__': '__main__', '__file__': str(source_file),
                 '_atomman_windows_patch': apply_patch,
                 '_atomman_windows_check': check_api}
    sys.argv = [str(source_file)] + passthrough
    exec(compile(''.join(lines), str(source_file), 'exec'), namespace)


if __name__ == '__main__':
    main()
