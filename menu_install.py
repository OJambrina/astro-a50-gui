"""KDE menu entry install / remove (writes a .desktop file)."""
import os
import re
import subprocess
import sys
import textwrap
from contextlib import suppress
from pathlib import Path

from i18n import t


def install_entry(
    apps_dir: Path,
    desktop_file: Path,
    legacy_desktop_file: Path,
    process_name: str,
    script_path: Path,
) -> str:
    """Write a .desktop file in `apps_dir`. Returns a status-bar message,
    raises on error."""
    apps_dir.mkdir(parents=True, exist_ok=True)
    content = textwrap.dedent(f"""\
        [Desktop Entry]
        Type=Application
        Name={t('desktop_name')}
        GenericName=Headset configuration
        Comment={t('desktop_comment')}
        Exec={_exec_arg(sys.executable)} {_exec_arg(str(script_path))}
        Icon=audio-headset
        Terminal=false
        Categories=AudioVideo;Audio;Settings;
        Keywords=astro;a50;headset;audio;
        StartupWMClass={process_name}
    """)
    desktop_file.write_text(content)
    if legacy_desktop_file.exists():
        legacy_desktop_file.unlink()
    _refresh_desktop_db(apps_dir)
    if _system_entry(apps_dir, desktop_file.name):
        return t("msg_menu_installed_system")
    return t("msg_menu_installed")


def remove_entry(
    apps_dir: Path,
    desktop_file: Path,
    legacy_desktop_file: Path,
) -> str:
    """Delete the .desktop files (legacy and current). Returns a status-bar
    message indicating whether anything was removed."""
    removed = False
    for path in (desktop_file, legacy_desktop_file):
        if path.exists():
            path.unlink()  # OSError reaches the caller: the entry is still there
            removed = True
    if removed:
        _refresh_desktop_db(apps_dir)
    # A package's entry of the same name stays in the menu (issue #19).
    if _system_entry(apps_dir, desktop_file.name):
        return t("msg_menu_removed_system" if removed else "msg_menu_absent_system")
    return t("msg_menu_removed" if removed else "msg_menu_absent")


def own_entry(path: Path) -> bool:
    """Whether `path` is an entry written by install_entry, which runs gui.py,
    rather than the menu editor's copy of the package's entry (same file name,
    Exec=astro-a50-gui)."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return False
    return any(line.startswith("Exec=") and "gui.py" in line for line in text.splitlines())


def _system_entry(apps_dir: Path, name: str) -> Path | None:
    """The system-wide .desktop file of this name (e.g. from the package), which
    the user entry shadows while it exists. `apps_dir`, the user's own, is
    skipped: some sessions list it in XDG_DATA_DIRS too."""
    dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    for d in dirs.split(":"):
        path = Path(d) / "applications" / name
        if d and path.parent.resolve() != apps_dir.resolve() and path.is_file():
            return path
    return None


def _exec_arg(arg: str) -> str:
    """Quote one Exec argument per the Desktop Entry spec.

    Reserved characters need double quotes, inside which ", `, $ and \\ are
    backslash-escaped; % is doubled (field codes). The string-value escape
    then doubles every backslash, since it is applied before quoting.
    """
    arg = arg.replace("%", "%%")
    if re.search(r"[\s\"'\\><~|&;$*?#()`]", arg):
        arg = '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'
    return arg.replace("\\", "\\\\")


def _refresh_desktop_db(apps_dir: Path) -> None:
    with suppress(Exception):
        subprocess.run(
            ["update-desktop-database", str(apps_dir)],
            check=False, capture_output=True, timeout=5,
        )
