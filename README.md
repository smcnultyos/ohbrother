# ohbrother

Brother QL-800 label printing on Linux without proprietary software.

Requires Python 3.11+. Dependencies: [pyusb](https://github.com/pyusb/pyusb) for USB I/O, [Pillow](https://python-pillow.org) for image handling. Rasterization is implemented in-house.

## Background

The QL-800 presents as USB class 8 (Mass Storage / BOT) in all modes, including printer mode. The standard `brother_ql` pyusb backend only scans for class-7 devices and never finds it. This library talks directly to the bulk endpoints and handles two QL-800-specific quirks:

- **Mid-stream status response.** The raster stream embeds `ESC i S`; the printer sends a 32-byte response mid-write. Not draining it before the next status read returns stale data.
- **Zero-length packets.** The IN endpoint sends ZLPs when idle instead of timing out.

## Installation

```bash
pip install ohbrother
sudo ohbrother-install-udev
```

Reconnect the printer after installing the udev rules.

## Editor Lite mode

If the printer enumerates as PID `0x209e`, it is in Editor Lite (virtual disk) mode. Hold the Editor Lite button until the green LED turns off, then reconnect. It re-enumerates as `0x209b`. `ohbrother` raises `EditorLiteModeError` on `0x209e`.

## Usage

```bash
ohbrother detect
ohbrother status
ohbrother list-labels                              # shows pixel dimensions too

# Endless tape
ohbrother print "Hello World"
ohbrother print --label 29 "narrow 29mm label"

# Die-cut labels — image is sized to exact label dimensions
ohbrother print --label 29x90 "Jane Smith\n123 Main St\nSpringfield IL"
ohbrother print --label 62x100 --image shipping.png

# Two-color tape (DK-22251)
ohbrother print --label 62red --red "black text"
ohbrother print --label 62red --red --text-color red "red text"

# Utilities
ohbrother cut                                      # feed and cut without printing
ohbrother print --dry-run "test"
```

## Python API

```python
from ohbrother import Printer, PrintOptions, render_for_label, label_dims

# Endless tape, black text
opts = PrintOptions(label="62")
with Printer("usb://0x04f9:0x209b", opts) as p:
    img = render_for_label("Hello World", "62")
    p.print_images([img])

# Die-cut label (29x90mm standard address label)
# render_for_label sizes the canvas to exactly (306, 991)px as required
opts = PrintOptions(label="29x90")
with Printer("usb://0x04f9:0x209b", opts) as p:
    img = render_for_label("Jane Smith\n123 Main St", "29x90", font_size=50)
    p.print_images([img])

# Two-color tape — red text
opts = PrintOptions(label="62red", red=True)
with Printer("usb://0x04f9:0x209b", opts) as p:
    img = render_for_label("URGENT", "62red", text_color=(255, 0, 0), font_size=140)
    p.print_images([img])

# Feed and cut without printing
with Printer("usb://0x04f9:0x209b", opts) as p:
    p.cut()

# Recover from a stuck state
with Printer("usb://0x04f9:0x209b") as p:
    p.reset()
```

Auto-detect the first available printer:

```python
from ohbrother.detect import discover

identifier = next(d["identifier"] for d in discover() if d["usable"])
```

### Die-cut labels

Die-cut labels require the image to be exactly `(width_px, height_px)` — any mismatch raises a `ValueError`. `render_for_label()` handles this automatically. If you construct images manually, use `label_dims(label_id)` to get the required pixel dimensions.

### Two-color tape (DK-22251)

Always use `label="62red"` and `red=True`, even for black-only prints. Single-color mode against two-color tape produces a generic error with no error bits; `validate_preflight()` catches this before the write and raises `TapeMismatchError`.

Red vs black separation uses HSV: hue < 40 or > 210, saturation > 100, value > 80. `(255, 0, 0)` renders as red ink; `(0, 0, 0)` renders as black. Both can appear in the same image.

## License

MIT
