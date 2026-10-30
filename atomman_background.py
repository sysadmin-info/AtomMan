"""Start the existing AtomMan Windows v9 adapter without a console.

This is a small logging launcher for pythonw.exe and Task Scheduler.  It does
NOT change screen_windows.py, screen.py, or the COM3 touch protocol.
"""
from __future__ import annotations

import os
import runpy
import sys
import time
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOGS = BASE / 'logs'
LOG_FILE = LOGS / 'atomman.log'
ARGS = ('--port', 'COM3', '--start-delay', '5', '--touch-volume', '--touch-sccs-dtr')


def rotate_logs(limit_bytes=3 * 1024 * 1024):
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > limit_bytes:
            oldest = LOGS / 'atomman.log.2'
            middle = LOGS / 'atomman.log.1'
            if oldest.exists():
                oldest.unlink()
            if middle.exists():
                middle.replace(oldest)
            LOG_FILE.replace(middle)
    except OSError:
        # Logging problems should never damage or modify the device.
        pass


def main() -> int:
    os.chdir(BASE)
    LOGS.mkdir(exist_ok=True)
    rotate_logs()
    with open(LOG_FILE, 'a', encoding='utf-8', buffering=1) as stream:
        sys.stdout = stream
        sys.stderr = stream
        print('\n' + '=' * 70, flush=True)
        print(f'AtomMan background start: {time.strftime("%Y-%m-%d %H:%M:%S")}', flush=True)
        print(f'Python: {sys.executable}; directory: {BASE}', flush=True)
        # Allow Windows login session, audio endpoint and COM3 to settle.
        time.sleep(10)
        sys.path.insert(0, str(BASE))
        sys.argv = [str(BASE / 'screen_windows.py'), *ARGS]
        try:
            runpy.run_path(str(BASE / 'screen_windows.py'), run_name='__main__')
            print('AtomMan process exited normally.', flush=True)
            return 0
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
            print(f'AtomMan process exited: {exc.code!r}', flush=True)
            return code
        except BaseException:
            print('AtomMan process crashed:', flush=True)
            traceback.print_exc(file=stream)
            return 1


if __name__ == '__main__':
    sys.exit(main())
