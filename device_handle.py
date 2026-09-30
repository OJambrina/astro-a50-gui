"""Reopenable handle on the base station.

The window, the EQ widget and the status worker share one handle. After a
USB failure (unplug, suspend, reset after a read timeout), `reopen()` swaps in
a fresh eh_fifty `Device`, and every holder uses it on its next call. The
vendored library stays untouched: the handle forwards every attribute to the
current `Device`.
"""
from collections.abc import Callable
from contextlib import suppress

from vendor.eh_fifty import Device, DeviceNotConnected


class DeviceHandle:
    """Forwards to the current `Device`; raises DeviceNotConnected while absent."""

    def __init__(self, factory: Callable[[], Device] = Device):
        self._factory = factory
        self._device: Device | None = factory()

    def __getattr__(self, name: str):
        # Only reached for names not set in __init__: everything eh_fifty offers.
        if self._device is not None:
            return getattr(self._device, name)
        if callable(getattr(Device, name, None)):
            # Callers take the method first and call it inside their own try
            # (``safe(device.get_balance)``): fail on the call, not the lookup,
            # or the error escapes their handler and a Qt slot aborts the app.
            def absent(*_args, **_kwargs):
                raise DeviceNotConnected
            return absent
        raise DeviceNotConnected

    def reopen(self) -> bool:
        """Drop the dead Device and open the base again. Caller holds the
        device lock. Returns False while the base is absent; the next call
        tries again."""
        if self._device is not None:
            with suppress(Exception):
                self._device.close()
        self._device = None
        with suppress(Exception):
            self._device = self._factory()
        return self._device is not None

    def close(self) -> None:
        if self._device is not None:
            self._device.close()
