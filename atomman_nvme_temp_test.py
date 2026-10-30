"""Read-only Windows NVMe storage temperature diagnostic.

Queries Windows IOCTL_STORAGE_QUERY_PROPERTY (StorageDeviceTemperatureProperty /
StorageAdapterTemperatureProperty) for selected PhysicalDrive numbers. Does not send
writes or alter SSD configuration. Requires native Windows Python, possibly admin.
"""

from __future__ import annotations
import argparse
import ctypes
import struct
import sys
from ctypes import wintypes

PROPERTY_DEVICE_TEMPERATURE = 52  # STORAGE_PROPERTY_ID enum
PROPERTY_ADAPTER_TEMPERATURE = 51
IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
GENERIC_READ = 0x80000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class TemperatureInfo(ctypes.Structure):
    _fields_ = [
        ('index', ctypes.c_uint16),
        ('temperature_c', ctypes.c_short),
        ('over_threshold_c', ctypes.c_short),
        ('under_threshold_c', ctypes.c_short),
        ('over_threshold_changeable', ctypes.c_ubyte),
        ('under_threshold_changeable', ctypes.c_ubyte),
        ('event_generated', ctypes.c_ubyte),
        ('reserved0', ctypes.c_ubyte),
        ('reserved1', ctypes.c_uint32),
    ]


class TemperatureDescriptorHeader(ctypes.Structure):
    _fields_ = [
        ('version', ctypes.c_uint32),
        ('size', ctypes.c_uint32),
        ('critical_temperature_c', ctypes.c_short),
        ('warning_temperature_c', ctypes.c_short),
        ('info_count', ctypes.c_uint16),
        ('reserved0', ctypes.c_ubyte * 2),
        ('reserved1', ctypes.c_uint32 * 2),
    ]


def query_disk(disk_number: int):
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
        wintypes.HANDLE]
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    k32.DeviceIoControl.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    path = rf'\\.\PhysicalDrive{disk_number}'

    # DesiredAccess=0 is sufficient for many storage property queries.
    # Try GENERIC_READ if the driver requires read access.
    handle = None
    errors = []
    for access in (0, GENERIC_READ):
        candidate = k32.CreateFileW(path, access,
            FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
        if candidate != INVALID_HANDLE_VALUE and candidate is not None:
            handle = candidate
            break
        errors.append(ctypes.get_last_error())
    if handle is None:
        return f'cannot open {path} (Win32 error codes: {errors}; try PowerShell as Administrator)'

    try:
        for prop_name, property_id in (
                ('StorageDeviceTemperatureProperty', PROPERTY_DEVICE_TEMPERATURE),
                ('StorageAdapterTemperatureProperty', PROPERTY_ADAPTER_TEMPERATURE)):
            # STORAGE_PROPERTY_QUERY: PropertyId, QueryType=PropertyStandardQuery,
            # AdditionalParameters[0]. An extra DWORD keeps input size aligned.
            request = ctypes.create_string_buffer(struct.pack('<III', property_id, 0, 0), 12)
            output = ctypes.create_string_buffer(4096)
            n = wintypes.DWORD(0)
            ok = k32.DeviceIoControl(handle, IOCTL_STORAGE_QUERY_PROPERTY,
                request, len(request), output, len(output), ctypes.byref(n), None)
            if not ok:
                errors.append(f'{prop_name}: Win32 error {ctypes.get_last_error()}')
                continue
            header_size = ctypes.sizeof(TemperatureDescriptorHeader)
            info_size = ctypes.sizeof(TemperatureInfo)
            if n.value < header_size:
                errors.append(f'{prop_name}: short response ({n.value} bytes)')
                continue
            hdr = TemperatureDescriptorHeader.from_buffer_copy(output.raw)
            if not hdr.info_count:
                errors.append(f'{prop_name}: no temperature sensors reported')
                continue
            max_count = (n.value - header_size) // info_size
            if hdr.info_count > max_count:
                errors.append(f'{prop_name}: inconsistent count ({hdr.info_count}, available {max_count})')
                continue
            sensors = []
            for i in range(hdr.info_count):
                start = header_size + i * info_size
                item = TemperatureInfo.from_buffer_copy(output.raw[start:start+info_size])
                sensors.append((item.index, item.temperature_c))
            return prop_name, sensors
        return 'no supported temperature property; ' + '; '.join(str(e) for e in errors)
    finally:
        k32.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description='AtomMan: read Windows native NVMe temperatures (read-only)')
    parser.add_argument('--disk', type=int, nargs='+', default=[0, 1], metavar='N',
                        help='PhysicalDrive numbers, e.g. --disk 0 1 (default: 0 1)')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Run this using native Windows Python, not Linux/WSL')
    assert ctypes.sizeof(TemperatureDescriptorHeader) == 24
    assert ctypes.sizeof(TemperatureInfo) == 16
    print('Windows native temperature property test (read-only, no additional driver)')
    for d in args.disk:
        if d < 0 or d > 255:
            print(f'PhysicalDrive{d}: invalid disk number')
            continue
        result = query_disk(d)
        if isinstance(result, str):
            print(f'PhysicalDrive{d}: {result}')
            continue
        method, sensors = result
        print(f'PhysicalDrive{d} [{method}]: ' + ', '.join(
            f'sensor {idx} = {temp} C' for idx, temp in sensors))


if __name__ == '__main__':
    main()
