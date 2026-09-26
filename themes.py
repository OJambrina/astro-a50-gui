"""Optional colour themes: palettes (.json) in the themes/ folder.

A theme only recolours the desktop's own style: every widget keeps its usual
shape and size, only the colours change. "auto" follows the desktop's own
colours, whatever they are. Each `themes/<name>.json` maps QPalette colour roles to
colours, with an optional "disabled" block for greyed-out widgets:

    {"Window": "#202326", "WindowText": "#fcfcfc", "disabled": {"Text": "#6d6f71"}}

A new file shows up in Tools → Theme; dashes in the file name become spaces.
"""
import json
from pathlib import Path

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from i18n import TRANSLATIONS, t

THEMES_DIR = Path(__file__).resolve().parent / "themes"
AUTO = "auto"
_native_palette = None  # desktop palette, captured on first use


def available() -> list[str]:
    if not THEMES_DIR.is_dir():
        return []
    return sorted(p.stem for p in THEMES_DIR.glob("*.json"))


def label(name: str) -> str:
    key = "theme_" + name.replace("-", "_")
    if key in TRANSLATIONS["en"]:
        return t(key)
    return name.replace("-", " ").replace("_", " ").title()


def load_palette(name: str, base: QPalette) -> QPalette:
    """Build the palette of themes/<name>.json on top of `base` (raises on a bad file)."""
    data = json.loads((THEMES_DIR / f"{name}.json").read_text())
    palette = QPalette(base)
    for group, colours in (
        (QPalette.ColorGroup.All, {k: v for k, v in data.items() if k != "disabled"}),
        (QPalette.ColorGroup.Disabled, data.get("disabled", {})),
    ):
        for role, value in colours.items():
            palette.setColor(group, QPalette.ColorRole[role], QColor(value))
    return palette


def apply(app: QApplication, name: str) -> str:
    """Apply a theme; return the name actually applied ("auto" if it can't be loaded)."""
    global _native_palette
    if _native_palette is None:
        _native_palette = app.palette()
    if name != AUTO:
        try:
            app.setPalette(load_palette(name, _native_palette))
            return name
        except (OSError, ValueError, KeyError):
            pass
    app.setPalette(_native_palette)
    return AUTO
