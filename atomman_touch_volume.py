"""AtomMan LCD volume event receiver; matched to physical COM3 capture from 2026-10-25.

Does not execute SCCS, load SCCS.sys, or alter the original Linux screen.py.
Only reads already-consumed input chunks on the same serial connection. It writes
an acknowledgement ONLY after validating an inbound 8-byte volume event.
"""
from __future__ import annotations
from collections import deque
import threading

END = b'\xcc\x33\xc3\x3c'
EVENT_VOLUME = 0x61
# Confirmed physical screen packet: AA 06 61 VV CC 33 C3 3C.
# Its length byte is 0x06 (NOT 0x05 as previously assumed).
EVENT_HEADER = b'\xaa\x06'
ENQ_HEADER = b'\xaa\x05'
ENQ_SEQ = set(b'0123456789:;<')
ACK_VOLUME = b'\xaa\x05\x00\x32' + END


def windows_set_volume(percent: int) -> bool:
    """Set master output volume through Windows Audio COM, on caller's thread."""
    if not isinstance(percent, int) or not 0 <= percent <= 100:
        return False
    import comtypes
    initialized = False
    try:
        comtypes.CoInitialize()
        initialized = True
        from pycaw.pycaw import AudioUtilities
        speaker = AudioUtilities.GetSpeakers()
        if speaker is None:
            return False
        speaker.EndpointVolume.SetMasterVolumeLevelScalar(percent / 100.0, None)
        return True
    except Exception as exc:
        print(f'[LCD TOUCH] Could not set Windows volume: {type(exc).__name__}: {exc}')
        return False
    finally:
        if initialized:
            comtypes.CoUninitialize()


class EventDecoder:
    """Decode fragmented serial reads; retain bounded private RX copy only."""
    def __init__(self, on_volume, *, debug: bool = True):
        self.on_volume = on_volume
        self.debug = debug
        self.buffer = bytearray()
        self.enqs = 0
        self.volume_events = 0
        self.unknown = 0

    def feed(self, chunk: bytes):
        """Decode complete packets without dropping 0x06-header touch events.

        The original 7-byte tile polling requests start AA 05, whereas the
        captured 8-byte volume requests start AA 06. Both can be fragmented
        across any number of reads and both are returned unchanged to screen.py.
        """
        events = []
        if not chunk:
            return events
        self.buffer.extend(chunk)
        while self.buffer:
            start = self.buffer.find(b'\xaa')
            if start < 0:
                self.buffer.clear()
                break
            if start:
                del self.buffer[:start]
            if len(self.buffer) < 2:
                break
            length = self.buffer[1]
            if length not in (0x05, 0x06):
                self.unknown += 1
                if self.debug:
                    print(f'[LCD TOUCH] Unexpected length byte 0x{length:02x} after AA')
                del self.buffer[0]
                continue
            packet_size = 7 if length == 0x05 else 8
            if len(self.buffer) < packet_size:
                break
            frame = bytes(self.buffer[:packet_size])
            if frame[-4:] != END:
                self.unknown += 1
                if self.debug:
                    print(f'[LCD TOUCH] Invalid RX frame: {frame.hex(" ")}')
                del self.buffer[0]
                continue
            del self.buffer[:packet_size]
            if length == 0x05:
                # A normal tile polling request is AA 05 <seq> CC 33 C3 3C.
                self.enqs += 1
                continue
            op, value = frame[2], frame[3]
            if op == EVENT_VOLUME and 0 <= value <= 100:
                self.volume_events += 1
                events.append(value)
            else:
                self.unknown += 1
                if self.debug:
                    print(f'[LCD TOUCH] Other/invalid event 0x{op:02x}: {frame.hex(" ")}')
        for level in events:
            self.on_volume(level)
        return events


def install_serial_listener(port: str, *, set_volume: bool = False, debug: bool = True):
    """Observe serial.Serial.read() without discarding/changing any bytes.

    Uses same COM port owned by screen.py; does not open COM independently.
    Apply once after screen.py imports and before its main loop.
    """
    import serial
    if getattr(serial.Serial.read, '_atomman_touch_hook', False):
        return
    original_read = serial.Serial.read
    lock = threading.RLock()
    state = {}

    def listener_for(instance):
        instance_port = str(getattr(instance, 'port', '') or '')
        if instance_port.lower() != str(port).lower():
            return None
        ident = id(instance)
        with lock:
            if ident not in state:
                def action(level, s=instance):
                    if debug:
                        print(f'[LCD TOUCH] Event 0x61 requests {level}%')
                    if set_volume:
                        ok = windows_set_volume(level)
                        if debug:
                            print(f'[LCD TOUCH] Windows Audio update: {"OK" if ok else "FAILED"}')
                        if ok:
                            # SCCS.exe sends this ACK in case 0x61; never send
                            # it based on an ENQ, only the validated event.
                            try:
                                s.write(ACK_VOLUME)
                                if debug:
                                    print(f'[LCD TOUCH] ACK: {ACK_VOLUME.hex(" ")}')
                            except Exception as exc:
                                print(f'[LCD TOUCH] ACK error: {exc}')
                state[ident] = EventDecoder(action, debug=debug)
            return state[ident]

    def wrapped_read(self, *args, **kwargs):
        data = original_read(self, *args, **kwargs)
        if data:
            dec = listener_for(self)
            if dec is not None:
                try:
                    dec.feed(data)
                except Exception as exc:
                    print(f'[LCD TOUCH] Decoder error: {exc}')
        return data

    wrapped_read._atomman_touch_hook = True
    serial.Serial.read = wrapped_read
    print(f'[LCD TOUCH] Listening on {port}; Windows volume write: {"ENABLED" if set_volume else "DISABLED (probe only)"}')


def self_test():
    messages = []
    d = EventDecoder(messages.append, debug=False)
    standard = ENQ_HEADER + b'\x32' + END
    event_30 = EVENT_HEADER + b'\x61\x1e' + END
    event_100 = EVENT_HEADER + b'\x61\x64' + END
    d.feed(standard[:2]); d.feed(standard[2:]); d.feed(event_30[:3]); d.feed(event_30[3:6]); d.feed(event_30[6:]); d.feed(event_100)
    assert messages == [30,100],messages
    assert d.enqs == 1 and d.volume_events == 2,(d.enqs,d.volume_events)
    # Invalid event (>100) must never change sound.
    d.feed(EVENT_HEADER + b'\x61\xff' + END)
    assert messages == [30,100]
    # The previous v8 decoder erroneously assumed header AA 05 for events.
    # An old malformed AA 05 61 VV frame must NOT change Windows volume.
    d.feed(ENQ_HEADER + b'\x61\x20' + END)
    assert messages == [30,100]
    # Actual captured frame sequences (AA 06 61 00, AA 06 61 20, ...).
    d2_messages = []
    d2 = EventDecoder(d2_messages.append, debug=False)
    d2.feed(ENQ_HEADER + b'\x32' + END)
    d2.feed(EVENT_HEADER + b'\x61\x00' + END)
    d2.feed(EVENT_HEADER + b'\x61\x20' + END)
    d2.feed(EVENT_HEADER + b'\x61\x00' + END)
    assert d2_messages == [0,32,0], d2_messages
    print('[LCD TOUCH] Decoder self-test passed (AA 05 ENQ, AA 06 volume events, fragments, 0/30/32/100%, invalid rejected).')


if __name__ == '__main__':
    self_test()
