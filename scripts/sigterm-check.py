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
4. slow poll: SIGTERM while the status thread is inside a 3.5 s poll
   (slowed down by a launcher). Must exit cleanly: closeEvent's 2 s
   thread wait expires, but device.close() then blocks on the device
   lock the poll holds, so the thread is done before Qt tears it down.
   Fails if device.close() ever moves out of that lock.
"""
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CMD = [sys.executable, str(ROOT / "gui.py")]
# Runs the GUI with worker-thread status polls slowed to 3.5 s, and fires
# one as soon as the window shows (no need for it to get the focus).
SLOW_POLL = f"""
import sys, threading, time
sys.path.insert(0, {str(ROOT)!r})
import gui
from PyQt6.QtCore import QTimer
get_status = gui.Device.get_headset_status
def slow(self):
    if threading.current_thread() is not threading.main_thread():
        print("POLL", flush=True)
        time.sleep(3.5)
    return get_status(self)
gui.Device.get_headset_status = slow
show = gui.A50Window.show
def show_and_poll(self):
    show(self)
    QTimer.singleShot(0, self._trigger_async_status)
gui.A50Window.show = show_and_poll
sys.exit(gui.main())
"""
ok = True


def launch(cmd=CMD, stdout=subprocess.DEVNULL):
    return subprocess.Popen(cmd, stdout=stdout, stderr=subprocess.PIPE, text=True)


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

a = launch([sys.executable, "-c", SLOW_POLL], stdout=subprocess.PIPE)
if a.stdout.readline().strip() == "POLL":
    time.sleep(0.3)
    a.send_signal(signal.SIGTERM)
    check("slow poll", a, 10)
else:
    a.kill()
    a.wait()
    ok = False
    print("slow poll: the launcher never started a poll -> FAIL")

sys.exit(0 if ok else 1)
