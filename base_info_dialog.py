"""Builds the "Informations base" dialog content.

Pure formatting: takes the typed values from eh_fifty's public API plus
the raw HID response payloads and returns the HTML lines to display in
a QMessageBox. Kept separate from the Qt widget so it's easy to test or
render in another UI.
"""
from i18n import t
from vendor.eh_fifty import DeviceInfo, FirmwareVersion


def format_base_info(
    dev_info: DeviceInfo,
    base_fw: FirmwareVersion,
    headset_fw: FirmwareVersion,
    raw: list[tuple[str, bytes]],
) -> list[str]:
    """Format the firmware info lines for the QMessageBox.

    `raw` holds (label, response payload) pairs dumped verbatim at the
    bottom of the dialog for diagnostics.
    """
    return [
        f"<b>{t('info_hwid')}:</b> {dev_info}",
        f"<b>{t('info_fw_base')}:</b> {base_fw}",
        f"<b>{t('info_fw_headset')}:</b> {headset_fw}",
        "",
        f"<b>{t('info_raw_title')}</b>",
        *(f"<small><code>{label + ':':<10}{data.hex()}</code></small>"
          for label, data in raw),
    ]
