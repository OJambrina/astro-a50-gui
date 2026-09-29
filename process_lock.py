"""Single-instance helper: detect and terminate prior copies of the GUI."""
import ctypes
import os
import signal
import time
from contextlib import suppress
from pathlib import Path

PROCESS_NAME = "astro-a50-gui"
PID_FILE = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / f"{PROCESS_NAME}.pid"


def _set_process_name(name: str = PROCESS_NAME) -> None:
    # PR_SET_NAME=15; kernel truncates to TASK_COMM_LEN-1 = 15 chars.
    with suppress(OSError):
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(15, name.encode()[:15], 0, 0, 0)


def _is_our_instance(pid_dir: Path, script_path: Path) -> bool:
    # Primary check: kernel comm set via prctl matches our process name.
    try:
        comm = (pid_dir / "comm").read_bytes().strip()
    except OSError:
        return False
    if comm == PROCESS_NAME.encode():
        return True
    # Fallback: same script path running under a Python interpreter (handles
    # legacy instances launched before prctl was added).
    try:
        exe = os.readlink(pid_dir / "exe")
    except OSError:
        return False
    if "python" not in Path(exe).name.lower():
        return False
    try:
        cmdline = (pid_dir / "cmdline").read_bytes().split(b"\x00")
    except OSError:
        return False
    # The script is the interpreter's first non-option argument; a later
    # argument that happens to be named gui.py belongs to another program.
    script = next((a for a in cmdline[1:] if a and not a.startswith(b"-")), None)
    if script is None:
        return False
    try:
        decoded = script.decode()
    except UnicodeDecodeError:
        return False
    if Path(decoded).name != script_path.name:
        return False
    try:
        # A relative path is relative to that process's cwd, not ours.
        candidate = Path(os.readlink(pid_dir / "cwd")) / decoded
        return candidate.resolve(strict=True) == script_path
    except (OSError, RuntimeError):
        return False


def _start_time(pid_dir: Path) -> int | None:
    """Start time in clock ticks since boot (field 22 of /proc/<pid>/stat)."""
    try:
        stat = (pid_dir / "stat").read_bytes()
        return int(stat[stat.rindex(b")") + 2:].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def _find_other_instances(script_path: Path, proc: Path = Path("/proc")) -> list[int]:
    """Our user's older instances. Only older ones: two copies started at the
    same moment would otherwise each kill the other and leave no window."""
    me = os.getpid()
    uid = os.getuid()
    my_start = _start_time(proc / str(me))
    found: list[int] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == me:
            continue
        try:
            if entry.stat().st_uid != uid:
                continue  # another user's instance: not ours to stop
        except OSError:
            continue
        if not _is_our_instance(entry, script_path):
            continue
        start = _start_time(entry)
        if my_start is not None and start is not None and (start, pid) > (my_start, me):
            continue  # newer than us: it will stop us, not the reverse
        found.append(pid)
    return found


def _wait_for_exit(pid: int, timeout_s: float = 4.0) -> bool:
    for _ in range(int(timeout_s * 10)):
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return True
        time.sleep(0.1)
    return False


def _kill_previous(script_path: Path) -> None:
    pids = _find_other_instances(script_path)
    if not pids:
        return
    for pid in pids:
        with suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGTERM)
    for pid in pids:
        if not _wait_for_exit(pid):
            with suppress(ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGKILL)
    time.sleep(0.3)


def _remove_pid_file():
    with suppress(OSError):
        if PID_FILE.exists() and PID_FILE.read_text().strip() == str(os.getpid()):
            PID_FILE.unlink()
