"""Background worker for HID status polls.

Runs on a QThread so the main UI thread never blocks on USB I/O during the
periodic refresh. The shared lock serialises access to the device between this
thread and the main thread's explicit writes.
"""
import threading

import usb.core
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from device_handle import DeviceHandle
from vendor.eh_fifty import DeviceNotConnected


class StatusWorker(QObject):
    """Polls the headset/battery status on demand from another thread."""

    statusReady = pyqtSignal(object, object)  # (HeadsetStatus|None, BatteryStatus|None)
    reconnected = pyqtSignal()  # the handle was reopened after a USB failure

    def __init__(self, device: DeviceHandle, lock: threading.RLock):
        super().__init__()
        self._device = device
        self._lock = lock

    @pyqtSlot()
    def refresh(self) -> None:
        status: object | None = None
        battery: object | None = None
        with self._lock:
            status, battery, usb_error = self._poll()
            reopened = usb_error and self._device.reopen()
            if reopened:
                status, battery, _ = self._poll()
        self.statusReady.emit(status, battery)
        if reopened:
            self.reconnected.emit()

    def _poll(self):
        status = battery = None
        usb_error = False
        try:
            status = self._device.get_headset_status()
        except Exception as e:
            usb_error = _is_usb_failure(e)
        try:
            battery = self._device.get_battery_status()
        except Exception as e:
            usb_error = usb_error or _is_usb_failure(e)
        return status, battery, usb_error


def _is_usb_failure(error: Exception) -> bool:
    """The handle itself is dead (unplug, suspend, reset after a timeout) or
    the base is still absent, as opposed to an ERROR answer from a live base."""
    return isinstance(error, (usb.core.USBError, DeviceNotConnected))
