"""SIGTERM regression check for the GUI (needs the base station plugged in).

Run with the interpreter that has PyQt6 and pyusb:
    .venv/bin/python scripts/sigterm-check.py

Closes any GUI instance already running (unsaved changes are lost), like
any relaunch does.

1. early: SIGTERM 0.8 s after launch, during start-up. Must exit cleanly
   (code 0) instead of being swallowed before the window shows.
2. idle: SIGTERM 3 s after launch, before refresh_timer's next tick. Must
   exit cleanly (code 0, no SIGABRT) within 1.5 s.
3. relaunch: start a second instance; _kill_previous SIGTERMs the first,
   which must exit cleanly, not abort or need SIGKILL.
"""
import signal
import subprocess
import sys
import time
from pathlib import Path

CMD = [sys.executable, str(Path(__file__).resolve().parent.parent / "gui.py")]
ok = True


def launch():
    return subprocess.Popen(CMD, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def check(name, p, limit):
    global ok
    t0 = time.monotonic()
    try:
        rc = p.wait(limit)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        rc = None
    good = rc == 0
    ok &= good
    print(f"{name}: rc={rc} after {time.monotonic() - t0:.2f}s -> {'OK' if good else 'FAIL'}")
    err = p.stderr.read().strip()
    if not good and err:
        print("  stderr:", err.replace("\n", "\n          "))


a = launch()
time.sleep(0.8)
a.send_signal(signal.SIGTERM)
check("early", a, 8)

a = launch()
time.sleep(3)
a.send_signal(signal.SIGTERM)
check("idle", a, 1.5)

a = launch()
time.sleep(3)
b = launch()
check("relaunch", a, 6)
time.sleep(3)
b.send_signal(signal.SIGTERM)
check("second instance", b, 6)

sys.exit(0 if ok else 1)
