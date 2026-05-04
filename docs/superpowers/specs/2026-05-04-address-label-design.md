# Address Label Support

**Date:** 2026-05-04  
**Status:** Approved

## Summary

Extend `ohbrother` to accept an unformatted address string, parse and normalize it using `usaddress`, and print it on a Brother DK address label reel (DK-1201 `29x90` or DK-1202 `62x100`). The `print` subcommand is unchanged but emits a stderr hint when its input looks like an address.

## Architecture

No new modules are introduced beyond `address.py`. The data flow is:

```
raw string → format_address() → render_for_label() → rasterize() → Printer
```

`address.py` sits between the user and `render.py`, with no awareness of the printer layer. `render.py` gains one convenience wrapper. The CLI gains one subcommand.

## New module: `src/ohbrother/address.py`

### `format_address(raw: str) -> str`

Uses `usaddress.tag()` to parse the input into labeled tokens, then assembles a 2–3 line string:

```
Jane Smith            ← Recipient token (omitted if absent)
123 Main St Apt 3B    ← AddressNumber + StreetName + StreetNamePostType + OccupancyType + OccupancyIdentifier
Springfield, IL 62701 ← PlaceName + StateName + ZipCode
```

Casing rules:
- All tokens are title-cased by default.
- `StateName` tokens of ≤ 2 characters are uppercased (e.g. `"il"` → `"IL"`).

Raises `ValueError` if `usaddress.tag()` returns a type other than `"Street Address"`, or if `usaddress.RepeatedLabelError` is raised (ambiguous input).

### `looks_like_address(raw: str) -> bool`

Returns `True` if `usaddress.tag()` succeeds, returns type `"Street Address"`, and the result contains an `AddressNumber` token. Returns `False` on `RepeatedLabelError` or any other failure. Never raises.

## Changes to `src/ohbrother/render.py`

New function:

```python
def render_address(
    raw: str,
    label_id: str = "29x90",
    *,
    font_size: int = 60,
    padding: int = 10,
    font_path: str | None = None,
) -> Image.Image
```

Calls `format_address(raw)` then `render_for_label()`. Default `font_size=60` (vs the existing default of 90) to fit 3 lines comfortably on the narrow 29x90 canvas.

## Changes to `src/ohbrother/cli.py`

### New `address` subcommand

```
ohbrother address TEXT
    [--label 29x90|62x100]   default: 29x90
    [--printer USB_ID]
    [--model QL-800]
    [--font-size PTS]        default: 60
    [--font PATH]
    [--dry-run]
```

Calls `render_address()` then follows the same print/dry-run path as `_cmd_print`.

### Hint in `print`

After parsing `args.text`, before rendering:

```python
if looks_like_address(args.text):
    print("Hint: looks like an address — try `ohbrother address` for formatted output.", file=sys.stderr)
```

No enforcement. The hint is purely informational.

## Changes to `src/ohbrother/__init__.py`

Export `format_address` and `render_address` so they are part of the public API:

```python
from .address import format_address
from .render import render_address
```

Add both to `__all__`.

## Changes to `pyproject.toml`

Add to `[project] dependencies`:

```
"usaddress>=0.5",
```

## Testing (`tests/test_address.py`)

- `format_address` with recipient + zip
- `format_address` without recipient
- `format_address` without zip code
- `format_address` all-caps input → correct title/upper casing
- `format_address` raises `ValueError` on unparseable input
- `looks_like_address` returns `True` for valid street address strings
- `looks_like_address` returns `False` for plain sentences
- `looks_like_address` returns `False` for ambiguous/repeated-label input
- `render_address("...", "29x90")` returns image with size `(306, 991)`
- `render_address("...", "62x100")` returns image with size `(696, 1109)`
- `_cmd_print` hint appears on stderr when input looks like an address (via `unittest.mock`)
