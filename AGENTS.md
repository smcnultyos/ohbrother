# AGENTS.md

Guidance for AI agents working on this codebase.

## What this is

`ohbrother` is a Python library for rootless Brother QL-800 label printing on Linux. No proprietary software required. The QL-800 presents as USB class 8 (Mass Storage/BOT) in all modes; this library bypasses the standard class-7 filter and talks directly to the bulk endpoints.

## Repository layout

```
src/ohbrother/
  backend.py       USB I/O — BrotherQLBackendQL800, drain_context(), _read_status_packet()
  labels.py        Label dataclass, LABELS dict (23 entries), DEVICE_PIXEL_WIDTH=720
  raster.py        rasterize() → bytes, color separation, row encoding
  render.py        render_for_label(), render_text(), label_dims()
  status.py        parse_status(), validate_preflight()
  printer.py       Printer context manager, PrintOptions dataclass
  detect.py        discover() — scans USB for Brother QL printers
  cli.py           CLI entry point (print, cut, detect, list-labels, status)
  udev_install.py  Installs udev rules (requires sudo)
  udev/            99-brother-ql.rules
tests/
  test_smoke.py    43 hardware-free tests — always run these
  test_print.py    3 live-printer tests — auto-skip without hardware
```

## Before making changes

1. Run `pytest tests/test_smoke.py` — all 43 must pass before and after your change.
2. Read the relevant source file before editing. The protocol is precise; don't guess.
3. `raster.py` and `backend.py` implement the Brother ESC/P raster protocol directly. Changes here require understanding the protocol spec, not just Python.

## Protocol constraints (do not violate)

- **Preamble**: `ESC i a 01` + 200×`0x00` (invalidate) + `ESC @` + `ESC i a 01`. Exactly 200 null bytes — not 100, not 256.
- **DEVICE_PIXEL_WIDTH = 720** (90 bytes × 8 bits). Every row must be padded to this width.
- **ESC i S** embeds a status request in the raster stream. The printer sends a 32-byte response mid-write. `drain_context()` must wrap the `write()` call or the response sits on the IN endpoint and corrupts the next status read.
- **cut()** deliberately omits `ESC i S` — no drain thread needed. Do not add it back.
- **ZLPs**: `_read_status_packet()` loops until a 32-byte packet arrives. `USBTimeoutError` must `continue` (retry), not `break` (bail).
- **Two-color tape**: `label="62red"` + `red=True` required even for black-only prints. `validate_preflight()` raises `TapeMismatchError` otherwise.
- **Die-cut labels**: Image must be exactly `(dots_printable[0], dots_printable[1])` pixels. `rasterize()` raises `ValueError` on mismatch — do not silently resize.
- **102mm labels** exceed `DEVICE_PIXEL_WIDTH`; `rasterize()` raises `ValueError` for these on QL-800.

## Adding a label

Add an entry to `LABELS` in `labels.py`. Required fields: `identifier`, `name`, `form_factor` (`"endless"` or `"die_cut"`), `tape_size` (mm tuple), `dots_printable` (px tuple), `right_margin_dots`, `feed_margin`, `two_color`. Cross-reference the Brother QL raster protocol spec for margin values.

## Tests

```bash
pytest tests/test_smoke.py        # no hardware needed
pytest tests/test_print.py -v -s  # requires QL-800 with 62red tape
```

Smoke tests cover: label specs, raster stream structure, color separation, render sizing, status packet parsing, and preflight validation. If you add a new feature, add a smoke test for it.

## Dependencies

- `pyusb>=1.2` — USB I/O
- `Pillow>=10.0` — image handling and HSV color separation

No other runtime dependencies. `brother_ql` was removed (GPL); rasterization is implemented in-house in `raster.py`.
