"""Probe opcode 0x83 with different argument bytes to find what info each returns.

SAFETY: never uses eh_fifty's high-level get_* methods (they call dev.reset() on
timeout and disconnect the base). On the first timeout we ABORT — repeated
unanswered requests can leave the HID firmware stuck for the rest of the session.

Run order: 0x01 (known good, smoke-test) then args to try. If 0x01 succeeds and a
following arg returns data → likely a real sub-type. If 0x01 succeeds and the next
arg times out → that arg is invalid and we stop.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vendor.eh_fifty import Device

ARGS_TO_TRY = [0x01, 0x02, 0x00, 0x03, 0x04]


def raw_request(dev, opcode, payload):
    req = bytes([0x02, opcode, len(payload)]) + payload
    dev._dev.write(0x05, req, 1500)
    return bytes(dev._dev.read(0x85, 64, 1500))


def maybe_decode_date(data):
    """Decode the 0x03/0x83 image header from the response payload.

    Layout: [0:4] flash pointer, [4:6] VID LE, [6:8] PID LE, [8:10] year LE,
    [10..15] month, day, hour, min, sec as plain binary bytes.
    """
    if len(data) < 15:
        return None
    year = int.from_bytes(data[8:10], "little")
    if not (2015 <= year <= 2035):
        return None
    mo, d, h, mi, sec = data[10:15]
    return f"{year:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{sec:02d}"


with Device() as d:
    print(f"{'arg':>4}  {'status':>6}  {'len':>3}  {'date?':<22}  raw")
    print("-" * 100)
    for arg in ARGS_TO_TRY:
        try:
            resp = raw_request(d, 0x83, bytes([arg]))
        except Exception:
            print(f"  {arg:02x}  TIMEOUT — aborting (firmware may be stuck if we continue)")
            sys.exit(1)
        status = resp[1]
        length = min(resp[2], len(resp) - 3) if len(resp) >= 3 else 0
        data = resp[3:3 + length]
        date_str = maybe_decode_date(data) or "—"
        print(f"  {arg:02x}  0x{status:02x}    {length:>3}  {date_str:<22}  {data.hex()}")
