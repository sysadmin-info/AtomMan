#!/usr/bin/env python3
"""Passive input-only serial capture for the AtomMan Windows adapter.

Runs an existing screen_windows.py in-process, wrapping only pyserial's read
calls. No extra serial port, no injected packets, no SCCS/WinRing0 driver.

Use for a short test while changing the AtomMan touchscreen volume slider.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import runpy
import sys
import threading
import time

CAPTURE_MAX_BYTES = 4 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description='Passive AtomMan COM receive logger')
    parser.add_argument('--log-file', default='logs/atomman_touch_rx.log',
                        help='Relative path is resolved from project root')
    parser.add_argument('--adapter', default='screen_windows.py',
                        help='Existing Windows adapter filename')
    args, pass_args = parser.parse_known_args()

    base = Path(__file__).resolve().parents[2]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    script = (base / args.adapter).resolve()
    log_path = (base / args.log_file).resolve()
    if not script.is_file():
        parser.error(f'Missing adapter: {script}')
    if script == Path(__file__).resolve():
        parser.error('The adapter cannot be this capture script')
    if log_path == script:
        parser.error('Log file must not overwrite the adapter')

    import serial
    # The actual Windows Serial implementation is aliased by serial.Serial.
    real_read = serial.Serial.read
    lock = threading.Lock()
    capture_size = 0
    total_reads = 0
    total_bytes = 0
    stopped_at_limit = False
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open('w', encoding='ascii', buffering=1)
    log_file.write('# time_utc_ms  RX  bytes_hex\n')

    def spy_read(self, *a, **kw):
        nonlocal capture_size, total_reads, total_bytes, stopped_at_limit
        # Read the bytes using the original implementation, unchanged.
        data = real_read(self, *a, **kw)
        if not data:
            return data
        with lock:
            total_reads += 1
            total_bytes += len(data)
            if capture_size < CAPTURE_MAX_BYTES:
                timestamp = datetime.now().astimezone().isoformat(timespec='milliseconds')
                line = f'{timestamp} RX {bytes(data).hex(" ")}\n'
                log_file.write(line)
                capture_size += len(line.encode('ascii'))
            elif not stopped_at_limit:
                log_file.write('# capture limit reached; remaining RX not logged\n')
                stopped_at_limit = True
        return data

    serial.Serial.read = spy_read
    original_argv = sys.argv
    sys.argv = [str(script)] + pass_args
    print(f'[CAPTURE] Running: {script.name} {" ".join(pass_args)}')
    print(f'[CAPTURE] RX-only log: {log_path}')
    print('[CAPTURE] Do not start SCCS or another process using COM3.')
    print('[CAPTURE] Touch volume icon, move slider (low / mid / high), Ctrl+C.')
    try:
        runpy.run_path(str(script), run_name='__main__')
    except KeyboardInterrupt:
        print('\n[CAPTURE] Interrupted with Ctrl+C')
    finally:
        sys.argv = original_argv
        serial.Serial.read = real_read
        log_file.close()
        print(f'[CAPTURE] RX reads={total_reads}, bytes={total_bytes}, file={log_path}')
        print('[CAPTURE] The log contains received serial data only; no API key or TX payload is recorded by this logger.')


if __name__ == '__main__':
    main()
