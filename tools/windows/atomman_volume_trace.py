#!/usr/bin/env python3
"""Trace AtomMan touchscreen RX, outgoing VOLUME frames and Windows master volume.

Designed to run the *existing*, working screen_windows.py in-process without
editing it or opening COM3 a second time. No extra serial writes and no
changes to audio levels. Non-volume TX packets are never recorded (weather API
keys / system metrics are intentionally excluded).

PowerShell:
  py .\atomman_volume_trace.py --port COM3 --start-delay 5
  py .\atomman_volume_trace.py --analyze-log .\atomman_touch_rx.log
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
import re
import runpy
import sys
import threading
import time

TRAILER = bytes.fromhex('cc 33 c3 3c')
VOL_RE = re.compile(rb'\{VOLUME\s*:\s*(-?\d+)\}', re.I)
LOG_LOCK = threading.Lock()


def stamp():
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


class EnqSplitter:
    """Reassemble serial reads into firmware-delimited frames."""
    def __init__(self, on_other):
        self.buf = bytearray()
        self.on_other = on_other
        self.enqs = 0
        self.other = 0
        self.noise = 0

    def feed(self, chunk: bytes, timestamp: str):
        self.buf.extend(chunk)
        while True:
            end = self.buf.find(TRAILER)
            if end < 0:
                # Emergency bound in case malformed data fills the stream.
                if len(self.buf) > 8192:
                    self.noise += len(self.buf) - 2048
                    del self.buf[:-2048]
                return
            packet = bytes(self.buf[:end + 4])
            del self.buf[:end + 4]
            if len(packet) == 7 and packet[:2] == b'\xaa\x05':
                self.enqs += 1
            else:
                self.other += 1
                self.on_other(timestamp, packet)


def analyze_old(path: Path):
    """Analyze existing RX-only logger line format, independent of timestamps."""
    other_packets = []
    decoder = EnqSplitter(lambda ts, pkt: other_packets.append((ts, pkt)))
    count = 0
    with path.open('r', encoding='utf-8-sig') as fp:
        for line in fp:
            if ' RX ' not in line:
                continue
            ts, hextext = line.rstrip('\r\n').split(' RX ', 1)
            try:
                data = bytes.fromhex(hextext)
            except ValueError:
                continue
            decoder.feed(data, ts)
            count += 1
    print(f'RX reads={count}; normal ENQ={decoder.enqs}; other packets={decoder.other}; remaining bytes={len(decoder.buf)}')
    print('Normal ENQ is AA 05 <sequence> CC 33 C3 3C; it is NOT a touchscreen event.')
    for ts, packet in other_packets[:100]:
        print(f'{ts} RX OTHER ({len(packet)} bytes): {packet.hex(" ")}')
    if len(other_packets) > 100:
        print(f'... {len(other_packets) - 100} further OTHER packets omitted')
    if not other_packets:
        print('No non-ENQ packets found in this capture; cannot infer touchscreen events from ENQ alone.')


def run_trace(adapter: Path, args: list[str], log_path: Path):
    import serial
    real_read = serial.Serial.read
    real_write = serial.Serial.write
    events = Counter()
    last_tx = {'vol': None, 'time': 0.0}
    stop = threading.Event()

    with log_path.open('w', encoding='utf-8', buffering=1) as fp:
        fp.write('# Time-local | direction | note\n')

        def note(msg: str):
            line = f'{stamp()} {msg}'
            with LOG_LOCK:
                fp.write(line + '\n')
                print('[TRACE]', msg, flush=True)

        def on_other(ts, packet):
            events['rx_other'] += 1
            # Cap payload emitted for safety; unexpected serial frames may have data.
            note('RX OTHER ' + packet[:128].hex(' ') + (' ...' if len(packet) > 128 else ''))

        splitter = EnqSplitter(on_other)

        def rx_hook(self, *a, **kw):
            data = real_read(self, *a, **kw)
            if data:
                splitter.feed(bytes(data), stamp())
            return data

        def tx_hook(self, data, *a, **kw):
            data_bytes = bytes(data)
            m = VOL_RE.search(data_bytes)
            if m:
                vol = int(m.group(1))
                events['tx_volume_frames'] += 1
                now = time.monotonic()
                if vol != last_tx['vol'] or now - last_tx['time'] > 8:
                    note(f'TX VOLUME={vol}%')
                    last_tx['vol'] = vol
                    last_tx['time'] = now
            return real_write(self, data, *a, **kw)

        def audio_poll():
            try:
                import comtypes
                comtypes.CoInitialize()
                from pycaw.pycaw import AudioUtilities
                prev = None
                last_print = 0
                while not stop.wait(0.7):
                    try:
                        dev = AudioUtilities.GetSpeakers()
                        v = getattr(dev, 'volume_percent', None)
                        if v is None:
                            v = dev.EndpointVolume.GetMasterVolumeLevelScalar() * 100
                        val = max(0, min(100, round(float(v))))
                        now = time.monotonic()
                        if val != prev or now - last_print > 12:
                            note(f'WINDOWS VOLUME={val}%')
                            prev, last_print = val, now
                    except Exception as exc:
                        if not events['audio_warning']:
                            events['audio_warning'] += 1
                            note(f'WINDOWS AUDIO READ FAILED: {type(exc).__name__}: {exc}')
            except Exception as exc:
                note(f'AUDIO POLLER UNAVAILABLE: {type(exc).__name__}: {exc}')
            finally:
                try:
                    import comtypes
                    comtypes.CoUninitialize()
                except Exception:
                    pass

        poller = threading.Thread(target=audio_poll, daemon=True, name='atomman-audio-readonly')
        serial.Serial.read = rx_hook
        serial.Serial.write = tx_hook
        old_argv = sys.argv
        sys.argv = [str(adapter)] + args
        note('Started; change Windows volume, then drag AtomMan touchscreen slider')
        poller.start()
        try:
            runpy.run_path(str(adapter), run_name='__main__')
        except KeyboardInterrupt:
            note('KeyboardInterrupt')
        finally:
            stop.set()
            poller.join(timeout=2)
            serial.Serial.read = real_read
            serial.Serial.write = real_write
            sys.argv = old_argv
            note(f'SUMMARY: RX ENQ={splitter.enqs}, RX OTHER={splitter.other}, outgoing VOLUME frames={events["tx_volume_frames"]}')
            note(f'Saved log: {log_path}')


def main():
    parser = argparse.ArgumentParser(description='AtomMan non-invasive volume diagnostic')
    parser.add_argument('--analyze-log', type=Path, help='Analyze previously captured atomman_touch_rx.log (does not open COM)')
    parser.add_argument('--adapter', default='screen_windows.py', help='Existing working Windows adapter')
    parser.add_argument('--log-file', default='logs/atomman_volume_trace.log', help='Text log destination')
    opts, passthrough = parser.parse_known_args()
    base = Path(__file__).resolve().parents[2]
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    if opts.analyze_log:
        f = opts.analyze_log if opts.analyze_log.is_absolute() else base / opts.analyze_log
        return analyze_old(f)
    adapter = (base / opts.adapter).resolve()
    if not adapter.is_file():
        parser.error(f'Adapter not found: {adapter}')
    log_path = (base / opts.log_file).resolve()
    if log_path == adapter or log_path == Path(__file__).resolve():
        parser.error('Log destination conflicts with a Python script')
    print('Passive tracing of Windows audio + serial RX. Serial write payloads are not modified.')
    print('Non-volume TX payloads (incl. weather/API keys) are NOT logged.')
    log_path.parent.mkdir(parents=True, exist_ok=True)
    run_trace(adapter, passthrough, log_path)


if __name__ == '__main__':
    main()
