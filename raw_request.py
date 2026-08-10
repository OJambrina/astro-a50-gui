"""Raw HID helper for the base info dialog's diagnostic dump.

Since eh_fifty 0.4.0, device info and firmware versions are available as
typed calls (get_device_info / get_base_firmware_version /
get_headset_firmware_version). This module remains to dump the raw
response payloads shown in the dialog — including opcode 0x83 (firmware
info), which has no public wrapper.
"""
from vendor.eh_fifty import Device


_OP_DEVICE_INFO = 0x03
_OP_FIRMWARE_INFO = 0x83
_OP_BASE_FW_MINOR = 0x55
_OP_HEADSET_FW_MAJOR = 0xDA
_OP_HEADSET_FW_MINOR = 0xD6


def _raw_request(device: Device, opcode: int, payload: bytes = b"") -> bytes:
    """Issue a raw HID request bypassing eh_fifty's _CommandType whitelist.

    Returns the response payload (bytes after the [0x02, status, len] header).
    """
    req = bytes([0x02, opcode])
    if payload:
        req += bytes([len(payload)]) + payload
    device._dev.write(0x05, req, 3000)
    resp = bytes(device._dev.read(0x85, 64, 3000))
    if not resp or resp[0] != 0x02 or len(resp) < 3:
        raise ValueError(f"unexpected response: {resp.hex()}")
    length = min(resp[2], len(resp) - 3)
    return resp[3:3 + length]
