"""Offline tests; no drivers, no COM port, no Windows volume changes."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import re
from pathlib import Path
from atomman_touch_volume import EventDecoder, END, self_test, install_serial_listener

self_test()
import os
log = Path(os.environ['ATOMMAN_TOUCH_LOG']) if os.environ.get('ATOMMAN_TOUCH_LOG') else ROOT / 'logs' / 'atomman_touch_dtr.log'
if log.is_file():
    rx_chunks = []
    for line in log.read_text(encoding='utf-8').splitlines():
        m = re.search(r' RX ([0-9a-fA-F ]+)\s*$', line)
        if m:
            rx_chunks.append(bytes.fromhex(m.group(1)))
    results=[]
    dec=EventDecoder(results.append,debug=False)
    for chunk in rx_chunks:
        dec.feed(chunk)
    assert results == [0,32,0], results
    assert dec.volume_events == 3 and dec.unknown == 0 and dec.enqs == 127, (dec.volume_events,dec.unknown,dec.enqs)
    assert not dec.buffer
    print(f'[v9] Real COM3 log replay OK: {len(rx_chunks)} RX chunks, {dec.enqs} polling frames, {dec.volume_events} volume events: {results}')

# Validate that even when real serial read is split byte-by-byte, output passes
# unchanged to screen.py; monitor never invokes volume updates or ACK.
import sys
from types import ModuleType
mockserial = ModuleType('serial')
class MockSerial:
    def __init__(self, port):
        self.port = port
        self.queue = [bytes((b,)) for b in (b'\xaa\x05\x32'+END+b'\xaa\x06\x61\x20'+END)]
        self.sent=[]
    def read(self,*args,**kwargs):
        return self.queue.pop(0) if self.queue else b''
    def write(self,payload):
        self.sent.append(bytes(payload))
        return len(payload)
mockserial.Serial=MockSerial
old=sys.modules.get('serial')
sys.modules['serial']=mockserial
try:
    install_serial_listener('COM3',set_volume=False,debug=False)
    ser=MockSerial('COM3')
    assert b''.join(ser.read() for _ in range(15)) == (b'\xaa\x05\x32'+END+b'\xaa\x06\x61\x20'+END)
    assert ser.sent == [],ser.sent
    print('[v9] Monitor passthrough: RX unchanged, no writes')
finally:
    if old is None:del sys.modules['serial']
    else:sys.modules['serial']=old

# Active-mode integration test: precise volume change and ACK emitted only
# for a valid AA 06 61 percent frame, never for ENQ or malformed packets.
from atomman_touch_volume import ACK_VOLUME
import atomman_touch_volume as touch
updated=[]
old_set_volume=touch.windows_set_volume
touch.windows_set_volume=lambda p: updated.append(p) or True
try:
    class MockControlSerial:
        port='COM3'
        def __init__(self):
            self.queue=[b'\xaa\x05\x32'+END, b'\xaa\x06\x61\x20'+END, b'\xaa\x06\x61\xff'+END]
            self.sent=[]
        def read(self,*args,**kwargs):
            return self.queue.pop(0) if self.queue else b''
        def write(self,payload):
            self.sent.append(bytes(payload))
            return len(payload)
    mockserial.Serial=MockControlSerial
    sys.modules['serial']=mockserial
    install_serial_listener('COM3',set_volume=True,debug=False)
    ser=MockControlSerial()
    while ser.queue:ser.read()
    assert updated == [32],updated
    assert ser.sent == [ACK_VOLUME],ser.sent
    print(f'[v9] Control integration: set={updated}, ACK={ser.sent[0].hex(" ")}')
finally:
    touch.windows_set_volume=old_set_volume
    if old is None:del sys.modules['serial']
    else:sys.modules['serial']=old
