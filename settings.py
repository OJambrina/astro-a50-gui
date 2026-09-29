"""Persistent user preferences (language, theme), stored next to the user templates."""
import json
import os
from pathlib import Path

SETTINGS_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    / "astro-a50-gui" / "settings.json"
)


def load() -> dict:
    try:
        data = json.loads(SETTINGS_PATH.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get(key: str, default=None):
    """Stored value, or `default` if it's missing or of another type than `default`."""
    value = load().get(key, default)
    if default is not None and not isinstance(value, type(default)):
        return default
    return value


def put(key: str, value) -> None:
    """Store a value. Raises OSError if the file can't be written."""
    data = load()
    data[key] = value
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n")
