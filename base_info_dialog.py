"""Builds the "Informations base" dialog content.

Pure formatting: takes the typed values from eh_fifty's public API plus
the raw HID response payloads and returns the HTML lines to display in
a QMessageBox. Kept separate from the Qt widget so it's easy to test or
render in another UI.
"""
import html

from i18n import t
from vendor.eh_fifty import DeviceInfo, FirmwareVersion


def _value(v) -> str:
    """A read that failed arrives as its exception: show n/a and why."""
    if isinstance(v, Exception):
        return f"{t('na')} ({html.escape(repr(v))})"
    return html.escape(str(v))


def format_base_info(
    dev_info: DeviceInfo | Exception,
    base_fw: FirmwareVersion | Exception,
    headset_fw: FirmwareVersion | Exception,
    raw: list[tuple[str, bytes | Exception]],
) -> list[str]:
    """Format the firmware info lines for the QMessageBox.

    `raw` holds (label, response payload) pairs dumped verbatim at the
    bottom of the dialog for diagnostics. Any value may be the exception its
    read raised (headset off or undocked), shown as n/a with its reason.
    """
    return [
        f"<b>{t('info_hwid')}:</b> {_value(dev_info)}",
        f"<b>{t('info_fw_base')}:</b> {_value(base_fw)}",
        f"<b>{t('info_fw_headset')}:</b> {_value(headset_fw)}",
        "",
        f"<b>{t('info_raw_title')}</b>",
        *(f"<small><code>{label + ':':<10}"
          f"{_value(data) if isinstance(data, Exception) else data.hex()}</code></small>"
          for label, data in raw),
    ]
