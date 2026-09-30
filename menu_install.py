"""KDE menu entry install / remove (writes a .desktop file)."""
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
        return t("msg_menu_removed")
    return t("msg_menu_absent")


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
