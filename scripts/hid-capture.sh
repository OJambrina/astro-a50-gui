#!/bin/bash
# Capture HID traffic to/from the Astro A50 (Gen 4) via usbmon text interface.
#
# Usage:
#   sudo ./hid-capture.sh [output-file]
#
# Stop with Ctrl-C. Output is text-format usbmon (kernel doc:
# https://www.kernel.org/doc/html/latest/usb/usbmon.html).
#
# We filter only lines for the A50 endpoints (5 OUT / 5 IN) on the device's
# bus, to keep the file small. The bus/dev numbers are auto-detected via
# lsusb at start; if the device re-enumerates mid-capture (e.g. bootloader
# PID swap), restart the capture.

set -euo pipefail

OUT="${1:-/tmp/a50-hid-$(date +%Y%m%d-%H%M%S).txt}"

if [[ $EUID -ne 0 ]]; then
  echo "Need root (sudo) to read /sys/kernel/debug/usb/usbmon/" >&2
  exit 1
fi

read -r BUS DEV < <(lsusb | awk '/9886:002[ac]/ {gsub(":","",$2); gsub(":","",$4); print $2+0, $4+0; exit}')
if [[ -z "${BUS:-}" || -z "${DEV:-}" ]]; then
  echo "A50 not found on USB bus (looked for 9886:002c or 9886:002a)" >&2
  exit 1
fi

# The "u" interface: the legacy "t" one drops the bus from the address
# ("Io:002:05"), so FILTER below would never match it.
USBMON="/sys/kernel/debug/usb/usbmon/${BUS}u"
if [[ ! -r "$USBMON" ]]; then
  echo "Cannot read $USBMON (usbmon enabled? debugfs mounted?)" >&2
  exit 1
fi

DEV_PAD=$(printf "%03d" "$DEV")
# usbmon text format is "Type:BUS:DEV:EP" (DEV zero-padded to 3 digits, EP not
# padded), e.g. "Io:1:017:5" / "Ii:1:017:5". EP 5 is the HID custom interface
# (eh_fifty endpoints 0x05 OUT / 0x85 IN). Skipping audio EPs 1/2/3 which would
# drown the capture. The trailing space avoids matching EP 50+ and the like.
FILTER=":${BUS}:${DEV_PAD}:5 "

echo "Capturing A50 traffic from bus $BUS dev $DEV ($USBMON)"
echo "Filtering on '$FILTER'"
echo "Writing to $OUT"
echo "Press Ctrl-C to stop."
echo ""

# stdbuf -oL to avoid buffering swallowing the tail; grep --line-buffered too.
exec stdbuf -oL cat "$USBMON" | grep --line-buffered -F "$FILTER" | tee "$OUT"
