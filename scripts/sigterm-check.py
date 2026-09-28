"""SIGTERM regression check for the GUI (needs the base station plugged in).

Run with the interpreter that has PyQt6 and pyusb:
    .venv/bin/python scripts/sigterm-check.py

1. idle: SIGTERM 3 s after launch, before refresh_timer's next tick. Must
   exit cleanly (code 0, no SIGABRT) within 1.5 s.
2. relaunch: start a second instance; _kill_previous SIGTERMs the first,
   which must exit cleanly, not abort or need SIGKILL.
"""
import signal
import subprocess
import sys
import time
from pathlib import Path

CMD = [sys.executable, str(Path(__file__).resolve().parent.parent / "gui.py")]
ok = True


def wait(p, limit):
    t0 = time.monotonic()
    try:
        rc = p.wait(limit)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        return None, limit
    return rc, time.monotonic() - t0


a = subprocess.Popen(CMD, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
time.sleep(3)
a.send_signal(signal.SIGTERM)
rc, dt = wait(a, 1.5)
good = rc == 0
ok &= good
print(f"idle: rc={rc} after {dt:.2f}s -> {'OK' if good else 'FAIL'}")

a = subprocess.Popen(CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)
b = subprocess.Popen(CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
rc, dt = wait(a, 6)
good = rc == 0
ok &= good
print(f"relaunch: first instance rc={rc} after {dt:.2f}s -> {'OK' if good else 'FAIL'}")
time.sleep(1)
b.send_signal(signal.SIGTERM)
wait(b, 6)

sys.exit(0 if ok else 1)
