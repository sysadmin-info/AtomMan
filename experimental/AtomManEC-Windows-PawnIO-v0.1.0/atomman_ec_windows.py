"""Standalone, opt-in Windows AtomMan EC fan-RPM reader via signed PawnIO module.

The package does not provide a signed .bin. No hardware access is performed
on import or by --probe. Do not run an EC read while AIDA64 or another EC
monitor is active. Does not modify SCCS, COM3, Windows security settings.
"""

from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import platform
import sys
import time
import winreg

BIOS_KEY = r"HARDWARE\DESCRIPTION\System\BIOS"
EXPECTED_VENDOR = "Micro Computer (HK) Tech Limited"
EXPECTED_PRODUCT = "AtomMan X Series"
EXPECTED_BOARD = "MTBAC"
DEFAULT_MODULE = Path(__file__).resolve().parent / "AtomManEC.bin"
DEFAULT_DLL = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "PawnIO" / "PawnIOLib.dll"


class AtomManECError(RuntimeError):
    pass


def read_dmi() -> dict[str, str]:
    """Read Windows BIOS/SMBIOS registry data; no EC or PawnIO access."""
    keys = {
        "vendor": "SystemManufacturer",
        "product": "SystemProductName",
        "board": "BaseBoardProduct",
    }
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, BIOS_KEY) as key:
        return {k: str(winreg.QueryValueEx(key, name)[0]).strip()
                for k, name in keys.items()}


def verify_hardware() -> dict[str, str]:
    if sys.platform != "win32":
        raise AtomManECError("Windows required")
    info = read_dmi()
    if info != {"vendor": EXPECTED_VENDOR, "product": EXPECTED_PRODUCT,
                "board": EXPECTED_BOARD}:
        raise AtomManECError(f"DMI mismatch; refusing EC I/O: {info}")
    return info


def aida64_running() -> bool:
    """Best-effort safety guard; cross-process EC coordination is still required."""
    try:
        import psutil
    except ImportError as exc:
        raise AtomManECError("Install psutil for the AIDA64 safety check") from exc
    try:
        return any((p.info.get("name") or "").lower() == "aida64.exe"
                   for p in psutil.process_iter(["name"]))
    except psutil.Error as exc:
        raise AtomManECError(f"Cannot determine AIDA64 process state: {exc}") from exc


def check_hresult(code: int, action: str) -> None:
    if (code & 0xFFFFFFFF) != 0:
        raise AtomManECError(f"PawnIO {action}: HRESULT 0x{code & 0xFFFFFFFF:08X}")


class PawnIO:
    """Small ctypes wrapper following the installed PawnIOLib.h C ABI."""

    def __init__(self, dll_path: Path = DEFAULT_DLL):
        if not dll_path.is_file():
            raise AtomManECError(f"PawnIOLib.dll missing: {dll_path}")
        self.lib = ctypes.WinDLL(str(dll_path))
        self.lib.pawnio_open.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self.lib.pawnio_open.restype = ctypes.c_long
        self.lib.pawnio_load.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.pawnio_load.restype = ctypes.c_long
        self.lib.pawnio_execute.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                            ctypes.POINTER(ctypes.c_uint64), ctypes.c_size_t,
                                            ctypes.POINTER(ctypes.c_uint64), ctypes.c_size_t,
                                            ctypes.POINTER(ctypes.c_size_t)]
        self.lib.pawnio_execute.restype = ctypes.c_long
        self.lib.pawnio_close.argtypes = [ctypes.c_void_p]
        self.lib.pawnio_close.restype = ctypes.c_long
        self.handle = ctypes.c_void_p()

    def __enter__(self):
        check_hresult(self.lib.pawnio_open(ctypes.byref(self.handle)), "open")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle.value:
            self.lib.pawnio_close(self.handle)
            self.handle = ctypes.c_void_p()

    def load(self, module: Path) -> None:
        blob = module.read_bytes()
        if not blob:
            raise AtomManECError(f"Empty PawnIO module: {module}")
        buffer = ctypes.create_string_buffer(blob)
        check_hresult(self.lib.pawnio_load(self.handle, buffer, len(blob)), "load signed module")

    def rpm(self) -> int:
        output = (ctypes.c_uint64 * 1)()
        count = ctypes.c_size_t()
        check_hresult(self.lib.pawnio_execute(self.handle, b"ioctl_read_fan_rpm",
                                              None, 0, output, 1, ctypes.byref(count)),
                      "read fan RPM")
        if count.value != 1 or output[0] >= 4000:
            raise AtomManECError(f"Invalid response: count={count.value}, rpm={output[0]}")
        return int(output[0])


def read_once(module: Path = DEFAULT_MODULE, dll: Path = DEFAULT_DLL) -> int:
    verify_hardware()
    if aida64_running():
        raise AtomManECError("Close AIDA64 before using the direct EC reader")
    if not module.is_file():
        raise AtomManECError(f"SIGNED module not found: {module}; unsigned .amx won't work")
    with PawnIO(dll) as driver:
        driver.load(module)
        return driver.rpm()


def main() -> int:
    parser = argparse.ArgumentParser(description="AtomMan X7 Ti PawnIO EC RPM proof of concept")
    parser.add_argument("--probe", action="store_true", help="Only check DMI / files, no EC I/O")
    parser.add_argument("--read-once", action="store_true", help="One explicit EC transaction (signed module required)")
    parser.add_argument("--module", type=Path, default=DEFAULT_MODULE)
    parser.add_argument("--dll", type=Path, default=DEFAULT_DLL)
    args = parser.parse_args()

    if not args.probe and not args.read_once:
        parser.error("choose --probe or --read-once (no automatic hardware access)")

    try:
        info = verify_hardware()
        print("DMI verified:", info)
        print("PawnIO DLL:", args.dll, "exists:", args.dll.is_file())
        print("Signed module:", args.module, "exists:", args.module.is_file())
        if args.probe:
            print("Probe complete. EC hardware NOT accessed.")
            return 0
        start = time.monotonic()
        rpm = read_once(args.module, args.dll)
        print(f"AtomMan CPU Fan: {rpm} RPM ({time.monotonic() - start:.3f}s)")
        return 0
    except (OSError, ValueError, AtomManECError) as exc:
        print(f"AtomMan EC: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
