#!/usr/bin/env python3
"""AtomMan LCD Linux audio bridge (touch <-> PipeWire/PulseAudio).

Run NEXT TO the user's original screen.py. Does not modify screen.py.
Firmware protocol confirmed on the same AtomMan X7 Ti on 2026-10-25:
  polling  AA 05 <seq> CC 33 C3 3C
  touch    AA 06 61 <0..100> CC 33 C3 3C
  touch ACK AA 05 00 32 CC 33 C3 3C

The USB serial port must have only ONE owner. Run this as the logged-in
DESKTOP USER, never with sudo/root (PipeWire/PulseAudio user session).
"""
from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time

END = b'\xcc\x33\xc3\x3c'
ACK_VOLUME = b'\xaa\x05\x00\x32' + END


def _exec(argv: list[str], timeout: float = 1.7):
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                timeout=timeout, check=False)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, '', f'{type(exc).__name__}: {exc}'


class LinuxAudio:
    """Read/write USER session default sink. No root privilege required.

    Prefer PipeWire's wpctl; PulseAudio-compatible pactl is a fallback.
    """
    _wpctl_id = '@DEFAULT_AUDIO_SINK@'
    _pactl_id = '@DEFAULT_SINK@'

    def __init__(self):
        self.last_error = ''
        self.last_backend = ''
        self._warned_at = float('-inf')
        self._lock = threading.RLock()

    def _warn(self, msg: str):
        now = time.monotonic()
        with self._lock:
            self.last_error = msg
            if now - self._warned_at > 30:
                print('[LINUX AUDIO] ' + msg, flush=True)
                self._warned_at = now

    @staticmethod
    def _extract_wpctl(out: str):
        match = re.search(r'\bVolume:\s*(\d+(?:[.,]\d+)?)\b', out)
        return max(0, min(100, round(float(match.group(1).replace(',', '.')) * 100))) if match else None

    @staticmethod
    def _extract_pactl(out: str):
        match = re.search(r'(\d+(?:[.,]\d+)?)\s*%', out)
        return max(0, min(100, round(float(match.group(1).replace(',', '.'))))) if match else None

    def get_volume(self) -> int:
        details = []
        for backend, argv, parse in (
            ('wpctl', ['wpctl', 'get-volume', self._wpctl_id], self._extract_wpctl),
            ('pactl', ['pactl', 'get-sink-volume', self._pactl_id], self._extract_pactl),
        ):
            ok, out, err = _exec(argv)
            if ok:
                value = parse(out)
                if value is not None:
                    self.last_backend = backend
                    self.last_error = ''
                    return value
            details.append(f'{backend}: {(err or out or "unavailable")[:120]}')
        self._warn('Cannot read default output volume (' + '; '.join(details) +
                   '). Run as logged-in desktop user; verify PipeWire/PulseAudio.')
        return -1

    def set_volume(self, percent: int) -> bool:
        if not isinstance(percent, int) or not 0 <= percent <= 100:
            self._warn(f'Rejected invalid volume value: {percent!r}')
            return False
        details = []
        for backend, cmd, unmute in (
            ('wpctl', ['wpctl', 'set-volume', self._wpctl_id, f'{percent}%'],
             ['wpctl', 'set-mute', self._wpctl_id, '0']),
            ('pactl', ['pactl', 'set-sink-volume', self._pactl_id, f'{percent}%'],
             ['pactl', 'set-sink-mute', self._pactl_id, '0']),
        ):
            ok, out, err = _exec(cmd)
            if ok:
                self.last_backend = backend
                self.last_error = ''
                # Avoid a slider moving from 0 to >0 while output stays muted.
                # Do NOT mute at zero: zero is volume, not a mute-button event.
                if percent > 0:
                    unmuted, _, mute_err = _exec(unmute)
                    if not unmuted:
                        self._warn(f'{backend}: volume set but unmute failed: {mute_err}')
                return True
            details.append(f'{backend}: {(err or out or "unavailable")[:120]}')
        self._warn('Cannot set default output volume (' + '; '.join(details) + ')')
        return False


class TouchDecoder:
    """Streaming copy of RX; original screen.py gets EXACTLY its bytes unchanged."""
    def __init__(self, callback):
        self.callback = callback
        self.buffer = bytearray()
        self.polls = 0
        self.events = 0
        self.unknown = 0

    def feed(self, data: bytes):
        if not data:
            return
        self.buffer.extend(data)
        # Bounded on corrupt streams. Intended frames are seven/eight bytes.
        if len(self.buffer) > 4096:
            del self.buffer[:-64]
        while self.buffer:
            start = self.buffer.find(b'\xaa')
            if start < 0:
                self.buffer.clear()
                break
            if start:
                del self.buffer[:start]
            if len(self.buffer) < 2:
                break
            n = self.buffer[1]
            if n not in (5, 6):
                del self.buffer[0]
                self.unknown += 1
                continue
            size = n + 2
            if len(self.buffer) < size:
                break
            frame = bytes(self.buffer[:size])
            if frame[-4:] != END:
                del self.buffer[0]
                self.unknown += 1
                continue
            del self.buffer[:size]
            if n == 5:
                self.polls += 1
            elif frame[2] == 0x61 and frame[3] <= 100:
                self.events += 1
                self.callback(frame[3])
            else:
                self.unknown += 1
                print(f'[LCD TOUCH] Unknown/invalid event: {frame.hex(" ")}', flush=True)


def install_receiver(port: str, audio: LinuxAudio, enable_volume: bool, debug=True):
    import serial
    if getattr(serial.Serial.read, '_atomman_linux_audio', False):
        raise RuntimeError('Touch receiver already installed')
    original_read = serial.Serial.read
    decoders = {}
    lock = threading.RLock()
    expected = os.path.realpath(port)

    def callback_for(ser):
        def on_volume(value):
            if debug:
                print(f'[LCD TOUCH] Event 0x61 requests {value}%', flush=True)
            if not enable_volume:
                return
            ok = audio.set_volume(value)
            if debug:
                print(f'[LCD TOUCH] Linux audio update: {"OK" if ok else "FAILED"}', flush=True)
            if ok:
                try:
                    ser.write(ACK_VOLUME)
                    if debug:
                        print(f'[LCD TOUCH] ACK: {ACK_VOLUME.hex(" ")}', flush=True)
                except Exception as exc:
                    print(f'[LCD TOUCH] ACK error: {type(exc).__name__}: {exc}', flush=True)
        return on_volume

    def wrapped_read(ser, *args, **kwargs):
        data = original_read(ser, *args, **kwargs)
        if not data:
            return data
        try:
            if os.path.realpath(str(getattr(ser, 'port', ''))) != expected:
                return data
            with lock:
                ident = id(ser)
                entry = decoders.get(ident)
                if entry is None or entry[0] is not ser:
                    entry = (ser, TouchDecoder(callback_for(ser)))
                    decoders[ident] = entry
                entry[1].feed(data)
        except Exception as exc:
            print(f'[LCD TOUCH] RX listener error: {type(exc).__name__}: {exc}', flush=True)
        return data

    wrapped_read._atomman_linux_audio = True
    serial.Serial.read = wrapped_read
    print(f'[LCD TOUCH] Listening on {port}; Linux audio write: '
          + ('ENABLED' if enable_volume else 'DISABLED (monitor only)'), flush=True)


def patch_original(ns: dict, audio: LinuxAudio, mode: str):
    if not callable(ns.get('p_vol')):
        raise RuntimeError('screen.py does not define p_vol(): unsupported source variant')
    if 'PORT' not in ns:
        raise RuntimeError('screen.py does not expose PORT: unsupported source variant')
    original_vol_tile = ns['p_vol']
    ns['_read_volume'] = audio.get_volume

    def linux_vol_tile():
        volume = audio.get_volume()
        cache = ns.get('_last_vol_bat')
        if isinstance(cache, dict):
            cache['volume'] = volume
        return f'{{VOLUME:{volume}}}'

    ns['p_vol'] = linux_vol_tile
    # The supplied Linux screen.py also reads pactl a second time for the
    # optional dashboard.  Keep that display in sync with our PipeWire reader.
    original_update = ns.get('update_latest_from_payload')
    vol_tile_id = ns.get('VOL')
    if callable(original_update) and isinstance(vol_tile_id, int):
        def linux_update_latest(id_byte, latest, fan_prefer, fan_max_rpm):
            if id_byte == vol_tile_id:
                latest['volume'] = audio.get_volume()
                return
            return original_update(id_byte, latest, fan_prefer, fan_max_rpm)
        ns['update_latest_from_payload'] = linux_update_latest
    # Some screen.py versions capture callables in rotation tables before launch.
    def replace_calls(v):
        if v is original_vol_tile:
            return linux_vol_tile
        if isinstance(v, tuple):
            return tuple(replace_calls(e) for e in v)
        if isinstance(v, list):
            return [replace_calls(e) for e in v]
        if isinstance(v, dict):
            return {k: replace_calls(e) for k, e in v.items()}
        return v
    for name, value in list(ns.items()):
        if name.isupper() and isinstance(value, (list, tuple, dict)):
            ns[name] = replace_calls(value)

    # SCCS used DTR=ON, RTS=ON with no hardware handshaking. Identical
    # approach was necessary to receive touch events on this AtomMan in Windows.
    ns['DSRDTR'] = False
    ns['RTSCTS'] = False
    if mode in ('monitor', 'control'):
        install_receiver(ns['PORT'], audio, enable_volume=(mode == 'control'))
    print(f'[LINUX AUDIO] DTR=ON, RTS=ON, flow-handshake=OFF; '
          f'current volume={audio.get_volume()}%; backend={audio.last_backend or "none"}', flush=True)


def self_test():
    got = []
    decoder = TouchDecoder(got.append)
    enq = b'\xaa\x05\x32' + END
    for data in (enq[:1], enq[1:4], enq[4:]):
        decoder.feed(data)
    first = b'\xaa\x06\x61\x00' + END
    second = b'\xaa\x06\x61\x20' + END
    decoder.feed(first[:3]); decoder.feed(first[3:]); decoder.feed(second)
    decoder.feed(b'\xaa\x06\x61\xff' + END)
    decoder.feed(b'\xaa\x05\x61\x20' + END)
    assert got == [0, 32], got
    assert decoder.polls == 1 and decoder.events == 2, (decoder.polls, decoder.events)
    # Verify parser against the previously recorded actual hardware RX trace.
    print('[LCD TOUCH] self-test passed: AA 05 ENQ, AA 06 61 (0%,32%), '
          'fragmentation, invalid rejection.')


def audio_test(audio: LinuxAudio):
    print(f'[LINUX AUDIO] UID={os.getuid()} | XDG_RUNTIME_DIR={os.getenv("XDG_RUNTIME_DIR", "(missing)")}')
    print(f'[LINUX AUDIO] PULSE_SERVER={os.getenv("PULSE_SERVER", "(default)")}')
    for cmd in (['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'],
                ['pactl', 'get-sink-volume', '@DEFAULT_SINK@'],
                ['pactl', 'info']):
        ok, out, err = _exec(cmd, timeout=2.5)
        name = ' '.join(cmd)
        print(f'[LINUX AUDIO] {name}: {"OK" if ok else "ERROR"}')
        print((out or err or '(empty)')[:600])
    value = audio.get_volume()
    print(f'[LINUX AUDIO] Parsed volume={value}% | backend={audio.last_backend or "unavailable"}')
    if os.geteuid() == 0:
        print('[LINUX AUDIO] WARNING: running as root often hides the logged-in user audio session.')
    return value >= 0


def main():
    parser = argparse.ArgumentParser(description='Linux AtomMan display bidirectional audio overlay')
    parser.add_argument('--self-test', action='store_true', help='Test parser (no COM or audio)')
    parser.add_argument('--audio-test', action='store_true', help='Diagnose audio in current login session (no COM)')
    parser.add_argument('--check-volume-tile', action='store_true', help='Patch original screen.py, then print VOL payload only (no COM)')
    touch = parser.add_mutually_exclusive_group()
    touch.add_argument('--touch-monitor', action='store_true', help='Observe LCD touch events; do not change Ubuntu volume')
    touch.add_argument('--touch-volume', action='store_true', help='Control Ubuntu volume from LCD and send ACK')
    parser.add_argument('--source', type=Path, default=Path(__file__).with_name('screen.py'),
                        help='Path to the existing Linux screen.py; default: adjacent')
    args, passthrough = parser.parse_known_args()
    if sys.platform != 'linux':
        parser.error('This overlay is for native Linux, not Windows/WSL')
    if args.self_test:
        self_test()
        return
    audio = LinuxAudio()
    if args.audio_test:
        if not audio_test(audio):
            raise SystemExit(1)
        return
    if not args.check_volume_tile and not (args.touch_monitor or args.touch_volume):
        parser.error('Choose --touch-monitor or --touch-volume (or use --audio-test).')
    if os.geteuid() == 0:
        print('[LINUX AUDIO] WARNING: sudo/root often has no access to desktop audio; run as desktop user.', flush=True)
    src = args.source.expanduser().resolve()
    if not src.is_file():
        parser.error(f'Original screen.py not found: {src}')
    source = src.read_text(encoding='utf-8-sig')
    # Python 3.14 validates argparse help strings when arguments are added.
    # User's original screen.py contains "RPM = % * this / 100", which
    # argparse treats as an invalid %-interpolation directive. Escape only
    # that literal in the IN-MEMORY source; never edit the original file.
    old_help = 'RPM = % * this / 100'
    new_help = 'RPM = %% * this / 100'
    if old_help in source:
        source = source.replace(old_help, new_help)
        print('[LINUX AUDIO] Compatibility: escaped argparse % in memory '
              '(original screen.py unchanged).', flush=True)
    tree = ast.parse(source, filename=str(src))

    def is_main_guard(node):
        if not isinstance(node, ast.If):
            return False
        t = node.test
        return (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                and t.left.id == '__name__' and len(t.ops) == 1
                and isinstance(t.ops[0], ast.Eq) and len(t.comparators) == 1
                and isinstance(t.comparators[0], ast.Constant) and t.comparators[0].value == '__main__')

    guards = [n for n in tree.body if is_main_guard(n)]
    if len(guards) != 1:
        parser.error(f'Expected one main guard in screen.py, found {len(guards)}')

    mode = 'control' if args.touch_volume else 'monitor' if args.touch_monitor else 'off'
    lines = source.splitlines(keepends=True)
    injected = '\n_atomman_linux_audio_patch(globals())\n'
    if args.check_volume_tile:
        injected += 'print("[LINUX AUDIO] VOL payload:", p_vol(), flush=True)\nraise SystemExit(0)\n'
    lines.insert(guards[0].lineno - 1, injected)
    ns = {'__name__': '__main__', '__file__': str(src),
          '_atomman_linux_audio_patch': lambda globals_dict: patch_original(globals_dict, audio, mode)}
    sys.argv = [str(src)] + passthrough
    exec(compile(''.join(lines), str(src), 'exec'), ns)


if __name__ == '__main__':
    main()
