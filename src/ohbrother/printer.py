from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .backend import BrotherQLBackendQL800
from .exceptions import PrinterError
from .labels import LABELS
from .raster import rasterize
from .render import label_dims
from .status import validate_preflight

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


@dataclass
class PrintOptions:
    """Print job configuration.

    DK-22251 (black+red 62mm) requires label="62red" and red=True,
    even for black-only prints.

    compress is not listed here — the QL-800 does not support PackBits
    compression (it is absent from the protocol's compression-capable model
    list), so the field would have no effect.
    """
    label: str = "62"
    model: str = "QL-800"
    rotate: str = "auto"
    dpi_600: bool = False
    hq: bool = True
    cut: bool = True
    dither: bool = False
    threshold: float = 70.0
    red: bool = False


class Printer:
    """Context manager for the QL-800.

        opts = PrintOptions(label="62red", red=True)
        with Printer("usb://0x04f9:0x209b", opts) as p:
            p.print_images([img])
    """

    def __init__(self, identifier: str, options: PrintOptions | None = None) -> None:
        self._identifier = identifier
        self._opts = options or PrintOptions()
        self._backend: BrotherQLBackendQL800 | None = None

    def __enter__(self) -> "Printer":
        self._backend = BrotherQLBackendQL800(self._identifier)
        return self

    def __exit__(self, *_) -> None:
        if self._backend is not None:
            self._backend.dispose()
            self._backend = None

    def _require_open(self) -> BrotherQLBackendQL800:
        if self._backend is None:
            raise PrinterError("Printer not open")
        return self._backend

    def status(self) -> dict:
        return self._require_open().request_status()

    def reset(self) -> None:
        """Send invalidate + initialize (ESC @) to recover from a stuck state."""
        self._require_open().write(b"\x00" * 200 + b"\x1B\x40")

    def cut(self) -> None:
        """Feed and cut without printing.

        Builds a minimal raster sequence that omits ESC i S so no mid-stream
        status response is generated and no drain thread is needed.
        """
        be = self._require_open()
        opts = self._opts
        label = LABELS[opts.label]

        import struct
        from io import BytesIO

        buf = BytesIO()
        buf.write(b"\x1B\x69\x61\x01")  # ESC i a
        buf.write(b"\x00" * 200)          # invalidate
        buf.write(b"\x1B\x40")            # ESC @
        buf.write(b"\x1B\x69\x61\x01")  # ESC i a

        mtype = 0x0A if label.form_factor == "endless" else 0x0B
        valid_flags = 0x80 | 0x02 | 0x04 | 0x08
        payload = struct.pack(
            "<BBBBLBB",
            valid_flags,
            mtype,
            label.tape_size[0],
            label.tape_size[1],
            0,    # 0 raster lines
            0,    # page 0
            0x00,
        )
        buf.write(b"\x1B\x69\x7A" + payload)   # ESC i z
        buf.write(b"\x1B\x69\x4D\x40")          # ESC i M: autocut on
        buf.write(b"\x1B\x69\x41\x01")          # ESC i A: cut every 1
        exp = 0x08 | (0x01 if opts.red else 0x00)
        buf.write(b"\x1B\x69\x4B" + bytes([exp]))  # ESC i K
        buf.write(b"\x1B\x69\x64" + struct.pack("<H", 0))  # ESC i d: 0 margin
        buf.write(b"\x1A")                       # print + cut

        be.write(buf.getvalue())
        time.sleep(0.2)

    def print_images(self, images: list[PILImage]) -> dict:
        """Preflight, rasterize, write, and return post-print status."""
        be = self._require_open()
        opts = self._opts

        validate_preflight(be.request_status(), red=opts.red, label=opts.label)

        data = rasterize(
            images,
            opts.label,
            rotate=opts.rotate,
            dpi_600=opts.dpi_600,
            hq=opts.hq,
            cut=opts.cut,
            dither=opts.dither,
            threshold=opts.threshold,
            red=opts.red,
        )

        with be.drain_context():
            be.write(data)

        time.sleep(0.3)
        return be.request_status()
