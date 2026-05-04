"""ohbrother — Brother QL-800 label printing without proprietary software.

    from ohbrother import Printer, PrintOptions, render_for_label

    opts = PrintOptions(label="62red", red=True)
    with Printer("usb://0x04f9:0x209b", opts) as p:
        img = render_for_label("Hello World", "62red")
        p.print_images([img])
"""

from .address import format_address, looks_like_address
from .exceptions import EditorLiteModeError, PrinterError, StatusError, TapeMismatchError
from .printer import PrintOptions, Printer
from .render import label_dims, render_address, render_for_label, render_text
from .raster import rasterize

__all__ = [
    "Printer",
    "PrintOptions",
    "PrinterError",
    "EditorLiteModeError",
    "StatusError",
    "TapeMismatchError",
    "format_address",
    "looks_like_address",
    "label_dims",
    "render_address",
    "render_for_label",
    "render_text",
    "rasterize",
]
