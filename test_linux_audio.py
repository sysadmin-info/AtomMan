#!/usr/bin/env python3
"""Offline regression tests for AtomMan Linux audio bridge, no device required."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import screen_linux_audio as m


def check_parser():
    hits = []
    decoder = m.TouchDecoder(hits.append)
    raw = Path('/mnt/data/atomman_touch_dtr.log')
    if raw.exists():
        for line in raw.read_text().splitlines():
            if ' RX ' in line and not line.startswith('#'):
                decoder.feed(bytes.fromhex(line.split(' RX ', 1)[1]))
        assert hits == [0, 32, 0], hits
        print(f'PASS: actual capture {decoder.polls} ENQ, {decoder.events} touch events: {hits}')
    else:
        m.self_test()


def check_audio():
    calls = []
    def fake_exec(argv, timeout=1.7):
        calls.append(argv)
        if argv[:2] == ['wpctl', 'get-volume']:
            return True, 'Volume: 0.57', ''
        if argv[:2] == ['pactl', 'get-sink-volume']:
            return True, 'front-left: 32768 / 50% / -10 dB', ''
        return True, '', ''
    with patch.object(m, '_exec', fake_exec):
        audio = m.LinuxAudio()
        assert audio.get_volume() == 57
        assert audio.set_volume(32) is True
        assert ['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', '32%'] in calls
        assert ['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '0'] in calls
        assert audio.set_volume(0) is True
        # No mute-on-zero side effects.
        assert calls.count(['wpctl', 'set-mute', '@DEFAULT_AUDIO_SINK@', '0']) == 1
        assert audio.set_volume(101) is False
    with patch.object(m, '_exec', lambda argv, timeout=1.7: (
        (False,'','not available') if argv[0] == 'wpctl' else
        (True,'front-left: 32768 / 45% / -10 dB',''))):
        assert m.LinuxAudio().get_volume() == 45
    print('PASS: wpctl read/write, mute handling, pactl read fallback, invalid volume rejected')


def check_integration():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d, 'screen.py')
        src.write_text("""PORT='/dev/ttyUSB_FAKE'\nDSRDTR=True\nRTSCTS=True\n_last_vol_bat = {'volume': -1}\ndef _read_volume():\n    return -1\ndef p_vol():\n    return '{VOLUME:%s}' % _read_volume()\nROT = [(0x10,p_vol)]\nif __name__ == '__main__':\n    print('THIS SHOULD NOT RUN WHEN --check-volume-tile')\n""")
        fake = Path(d, 'wpctl')
        fake.write_text('#!/bin/sh\nif [ "$1" = "get-volume" ]; then echo "Volume: 0.65"; exit 0; fi\nexit 0\n')
        fake.chmod(0o755)
        env = dict(os.environ, PATH=str(d) + os.pathsep + os.environ['PATH'])
        cp = subprocess.run([sys.executable, m.__file__, '--source', str(src), '--check-volume-tile'],
                            text=True, capture_output=True, env=env, timeout=5)
        assert cp.returncode == 0, (cp.stdout,cp.stderr)
        assert '[LINUX AUDIO] VOL payload: {VOLUME:65}' in cp.stdout, cp.stdout
        assert 'THIS SHOULD NOT RUN' not in cp.stdout, cp.stdout
        print('PASS: mock original script patched before __main__, volume tile outputs 65%')


def check_python314_argparse_help_compatibility():
    # Reproduces the exact argparse problem on the user's Ubuntu Python 3.14.
    # --check-volume-tile short-circuits before main(), so exercise actual main.
    with tempfile.TemporaryDirectory() as d:
        original = Path(d, 'screen.py')
        original_text = """import argparse
PORT='/dev/ttyTEST'
DSRDTR=True
RTSCTS=True
VOL=0x10

def p_vol():
    return '{VOLUME:-1}'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--fan-max-rpm', type=int, default=5000,
                    help='Used only when NVIDIA reports percent; RPM = % * this / 100')
    ap.add_argument('--start-delay', type=float, default=0)
    args=ap.parse_args()
    print('[MOCK] Original main started with fan-max-rpm=', args.fan_max_rpm)

if __name__ == '__main__':
    main()
"""
        original.write_text(original_text)
        fake_serial = Path(d, 'serial.py')
        fake_serial.write_text('class Serial:\n    def read(self, count=1): return b""\n')
        fake_wpctl = Path(d, 'wpctl')
        fake_wpctl.write_text('#!/bin/sh\necho "Volume: 0.61"\n')
        fake_wpctl.chmod(0o755)
        env = dict(os.environ,
                   PATH=str(d) + os.pathsep + os.environ['PATH'],
                   PYTHONPATH=str(d) + os.pathsep + os.environ.get('PYTHONPATH', ''))
        cp = subprocess.run([sys.executable, m.__file__, '--source', str(original),
                             '--touch-monitor', '--start-delay', '5'],
                            text=True, capture_output=True, env=env, timeout=5)
        assert cp.returncode == 0, (cp.stdout, cp.stderr)
        assert 'escaped argparse % in memory' in cp.stdout, cp.stdout
        assert '[MOCK] Original main started with fan-max-rpm= 5000' in cp.stdout, cp.stdout
        assert original.read_text() == original_text, 'Original screen.py modified!'
        print('PASS: Python 3.14 argparse literal percent patched in memory; original unchanged')

if __name__ == '__main__':
    check_parser()
    check_audio()
    check_integration()
    check_python314_argparse_help_compatibility()
    print('All offline tests passed')

# Source-specific integration checks for the Linux screen.py version
# posted by the user. These do not open a physical serial port.
def check_source_specific():
    import types
    from unittest.mock import MagicMock
    fake = types.ModuleType('serial')

    class FakeSerial:
        def __init__(self):
            self.port = '/dev/ttyTEST'
            self.to_read = bytearray()
            self.writes = []
        def read(self, count=1):
            result = bytes(self.to_read[:count])
            del self.to_read[:count]
            return result
        def write(self, data):
            self.writes.append(data)
            return len(data)
    fake.Serial = FakeSerial

    aud = m.LinuxAudio()
    aud.get_volume = MagicMock(return_value=43)
    aud.set_volume = MagicMock(return_value=True)
    with patch.dict(sys.modules, {'serial': fake}):
        ns = {
            'PORT':'/dev/ttyTEST', 'DSRDTR':True, 'RTSCTS':False,
            'VOL': 0x10,
            'p_vol':lambda: '{VOLUME:-1}',
            'update_latest_from_payload': lambda id_byte, latest, a, b: latest.update({'default_called': True}),
            'UNLOCK_ROT':[(0x53, lambda: 'irrelevant')],
        }
        m.patch_original(ns, aud, 'control')
        assert ns['DSRDTR'] is False and ns['RTSCTS'] is False
        assert ns['p_vol']() == '{VOLUME:43}'
        dashboard = {}
        ns['update_latest_from_payload'](0x10, dashboard, 'auto', 5000)
        assert dashboard == {'volume': 43}, dashboard
        ns['update_latest_from_payload'](0x53, dashboard, 'auto', 5000)
        assert dashboard.get('default_called') is True
        ser = FakeSerial()
        ser.to_read.extend(b'\xaa\x05\x32\xcc\x33\xc3\x3c')
        ser.to_read.extend(b'\xaa\x06\x61\x3c\xcc\x33\xc3\x3c')  # 60%
        while ser.to_read:
            ser.read(1)
        assert aud.set_volume.call_args_list == [((60,), {})], aud.set_volume.call_args_list
        assert ser.writes == [m.ACK_VOLUME], ser.writes
    print('PASS: actual screen.py functions: dashboard VOL, DTR, touch 60%, ACK')

check_source_specific()
