"""USB backend for the Brother QL-800 in printer mode (PID 0x209b).

The QL-800 presents as USB class 8 (Mass Storage / BOT) even in printer mode,
which bypasses brother_ql's stock pyusb backend (class-7 only). Two quirks
distinguish it from older QL models:

- The raster stream embeds ESC i S; the printer responds with a 32-byte status
  packet mid-write. That packet must be drained before the next status read or
  you get stale data. drain_context() handles this with a background thread.

- The IN endpoint returns ZLPs when idle rather than timing out. _read_status_packet()
  loops until a 32-byte packet arrives.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Iterator

import usb.core
import usb.util

from .exceptions import EditorLiteModeError, PrinterError
from .status import parse_status

BROTHER_VENDOR = 0x04F9
QL800_PRINTER_PID = 0x209B
QL800_STORAGE_PID = 0x209E


class BrotherQLBackendQL800:
    """Direct USB backend for the QL-800 in printer mode.

    Prefer the Printer context manager over using this class directly.
    """

    def __init__(self, device_specifier: str | usb.core.Device) -> None:
        self.read_timeout = 10.0      # ms
        self.write_timeout = 15000.0  # ms
        self._was_kernel_driver_active = False

        if isinstance(device_specifier, str):
            self._dev = self._open_by_identifier(device_specifier)
        elif isinstance(device_specifier, usb.core.Device):
            self._dev = device_specifier
        else:
            raise TypeError("device_specifier must be a usb:// string or usb.core.Device")

        self._claim()

    def _open_by_identifier(self, identifier: str) -> usb.core.Device:
        spec = identifier.removeprefix("usb://")
        vendor_product, _, _ = spec.partition("/")
        vendor_str, _, product_str = vendor_product.partition(":")
        vendor = int(vendor_str, 16)
        product = int(product_str, 16)

        if product == QL800_STORAGE_PID:
            raise EditorLiteModeError()

        dev = usb.core.find(idVendor=vendor, idProduct=product)
        if dev is None:
            raise PrinterError(f"Device {identifier} not found. Is it plugged in?")
        return dev

    def _claim(self) -> None:
        try:
            if self._dev.is_kernel_driver_active(0):
                self._dev.detach_kernel_driver(0)
                self._was_kernel_driver_active = True
        except (NotImplementedError, usb.core.USBError):
            pass

        self._dev.set_configuration()
        cfg = self._dev.get_active_configuration()

        ep_in = ep_out = None
        for intf in cfg:
            ep_out = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                == usb.util.ENDPOINT_OUT,
            )
            ep_in = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
                == usb.util.ENDPOINT_IN,
            )
            if ep_in and ep_out:
                break

        if ep_in is None or ep_out is None:
            raise PrinterError("Could not find bulk IN/OUT endpoints on device")

        self._ep_out = ep_out
        self._ep_in = ep_in

    def dispose(self) -> None:
        try:
            usb.util.dispose_resources(self._dev)
            if self._was_kernel_driver_active:
                self._dev.attach_kernel_driver(0)
        except Exception:
            pass

    def write(self, data: bytes) -> None:
        self._ep_out.write(data, timeout=int(self.write_timeout))

    def _read_status_packet(self, timeout_s: float = 3.0) -> bytes:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                chunk = bytes(self._ep_in.read(64, timeout=500))
                if len(chunk) == 32:
                    return chunk
                # ZLP or short packet — keep waiting
            except usb.core.USBTimeoutError:
                # No data for 500ms; the printer may have paused ZLPs mid-write.
                # Continue retrying until the outer deadline rather than bailing early.
                continue
            except usb.core.USBError:
                break
        return b""

    @contextmanager
    def drain_context(self) -> Iterator[None]:
        """Drain the mid-stream ESC i S response in the background.

        brother_ql embeds ESC i S in the raster stream; the printer responds
        mid-write. Starting the drain thread before write() ensures the packet
        is consumed before the post-print request_status() call.
        """
        drained: list[bytes] = []

        def _drain() -> None:
            pkt = self._read_status_packet(timeout_s=6.0)
            if pkt:
                drained.append(pkt)

        t = threading.Thread(target=_drain, daemon=True)
        t.start()
        try:
            yield
        finally:
            t.join(timeout=7.0)

    def request_status(self) -> dict:
        self.write(bytes([0x1B, 0x69, 0x53]))
        raw = self._read_status_packet(timeout_s=3.0)
        return parse_status(raw)
