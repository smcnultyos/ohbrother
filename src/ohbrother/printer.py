from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import _suppress  # noqa: F401 — must precede brother_ql imports
from .backend import BrotherQLBackendQL800
from .exceptions import PrinterError
from .status import validate_preflight
from .render import label_dims

from brother_ql.raster import BrotherQLRaster
from brother_ql.conversion import convert

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage


@dataclass
class PrintOptions:
    """Print job configuration.

    DK-22251 (black+red 62mm) requires label="62red" and red=True,
    even for black-only prints.

    compress has no effect on the QL-800 — it is absent from brother_ql's
    compressionsupport list, so the command byte is never emitted and
    _compression stays False regardless. The field is retained for
    compatibility with other QL models that do support PackBits compression.
    """
    label: str = "62"
    model: str = "QL-800"
    rotate: str = "auto"
    dpi_600: bool = False
    hq: bool = True
    cut: bool = True
    compress: bool = False
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
        be = self._require_open()
        be.write(b'\x00' * 200 + b'\x1B\x40')

    def cut(self) -> None:
        """Feed and cut without printing.

        Builds a minimal raster sequence that omits ESC i S so no mid-stream
        status response is generated and no drain thread is needed.
        """
        be = self._require_open()
        opts = self._opts

        from brother_ql.devicedependent import label_type_specs, ENDLESS_LABEL
        from brother_ql.exceptions import BrotherQLUnsupportedCmd

        spec = label_type_specs[opts.label]
        tape_w, tape_h = spec['tape_size']
        is_endless = spec['kind'] == ENDLESS_LABEL

        qlr = BrotherQLRaster(opts.model)
        try:
            qlr.add_switch_mode()
        except BrotherQLUnsupportedCmd:
            pass
        qlr.add_invalidate()
        qlr.add_initialize()
        try:
            qlr.add_switch_mode()
        except BrotherQLUnsupportedCmd:
            pass

        qlr.mtype = 0x0A if is_endless else 0x0B
        qlr.mwidth = tape_w
        qlr.mlength = 0 if is_endless else tape_h
        qlr.pquality = 1
        qlr.add_media_and_quality(0)

        try:
            qlr.add_autocut(True)
            qlr.add_cut_every(1)
        except BrotherQLUnsupportedCmd:
            pass
        try:
            qlr.cut_at_end = True
            qlr.two_color_printing = opts.red
            qlr.add_expanded_mode()
        except BrotherQLUnsupportedCmd:
            pass

        qlr.add_margins(0)
        qlr.add_print(last_page=True)

        be.write(qlr.data)
        time.sleep(0.2)

    def print_images(self, images: list[PILImage]) -> dict:
        """Preflight, rasterize, write, and return post-print status."""
        be = self._require_open()
        opts = self._opts

        validate_preflight(be.request_status(), red=opts.red, label=opts.label)

        qlr = BrotherQLRaster(opts.model)
        qlr.exception_on_warning = True
        convert(
            qlr,
            images,
            opts.label,
            rotate=opts.rotate,
            dpi_600=opts.dpi_600,
            hq=opts.hq,
            cut=opts.cut,
            compress=opts.compress,
            dither=opts.dither,
            threshold=opts.threshold,
            red=opts.red,
        )

        with be.drain_context():
            be.write(qlr.data)

        time.sleep(0.3)
        return be.request_status()
