"""Brother QL-800 raster stream encoder.

Converts PIL images to the ESC/P raster byte stream the printer expects.
Handles both single-color and two-color (black+red) jobs.

Stream structure per image:
    ESC i S          status request (printer responds mid-write; drained by backend)
    ESC i z          media and quality
    ESC i M          autocut on
    ESC i A          cut every 1
    ESC i K          expanded mode (cut_at_end, dpi_600, two_color flags)
    ESC i d          feed margin
    [raster rows]    0x67/0x77 row headers + data
    0x1A / 0x0C      print+cut (last page) or form-feed (intermediate)

Preamble (once, before first image):
    ESC i a 0x01     switch to raster mode
    0x00 × 200       invalidate command buffer
    ESC @            initialize
    ESC i a 0x01     switch to raster mode (second call per brother_ql convention)
"""

from __future__ import annotations

import struct
from io import BytesIO
from typing import Sequence

import PIL.ImageChops
import PIL.ImageOps
from PIL import Image

from .labels import DEVICE_PIXEL_WIDTH, LABELS, Label


def rasterize(
    images: Sequence[Image.Image],
    label_id: str,
    *,
    rotate: str | int = "auto",
    dpi_600: bool = False,
    hq: bool = True,
    cut: bool = True,
    dither: bool = False,
    threshold: float = 70.0,
    red: bool = False,
) -> bytes:
    """Return the complete raster byte stream for the given images and label.

    Raises ValueError for unknown label_id or if a die-cut image has wrong
    dimensions.
    """
    if label_id not in LABELS:
        raise ValueError(f"Unknown label: {label_id!r}. Run 'ohbrother list-labels'.")

    label = LABELS[label_id]
    if label.dots_printable[0] > DEVICE_PIXEL_WIDTH:
        raise ValueError(
            f"Label '{label_id}' requires {label.dots_printable[0]}px print width "
            f"but QL-800 device width is {DEVICE_PIXEL_WIDTH}px. "
            f"This label requires a QL-1050 or QL-1060N."
        )
    thresh_int = min(255, max(0, int((100.0 - threshold) / 100.0 * 255)))

    buf = BytesIO()

    # Preamble
    buf.write(b"\x1B\x69\x61\x01")  # ESC i a: switch to raster mode
    buf.write(b"\x00" * 200)          # invalidate
    buf.write(b"\x1B\x40")            # ESC @: initialize
    buf.write(b"\x1B\x69\x61\x01")  # ESC i a: switch to raster mode

    for page_idx, img in enumerate(images):
        im = _prepare(img, label, rotate, dpi_600, red)
        n_rows = im.size[1]

        if red:
            black_1bit, red_1bit = _split_two_color(im, thresh_int)
        else:
            black_1bit = _to_1bit(im, thresh_int, dither)
            red_1bit = None

        # ESC i S: status request — printer sends 32-byte response mid-write
        buf.write(b"\x1B\x69\x53")

        # ESC i z: media and quality (10-byte payload)
        buf.write(_media_quality(label, n_rows, hq, page_idx))

        # ESC i M: autocut on (bit 6)
        buf.write(b"\x1B\x69\x4D\x40")

        # ESC i A: cut every 1
        buf.write(b"\x1B\x69\x41\x01")

        # ESC i K: expanded mode
        exp = 0x00
        if red:    exp |= 0x01
        if cut:    exp |= 0x08
        if dpi_600: exp |= 0x40
        buf.write(b"\x1B\x69\x4B" + bytes([exp]))

        # ESC i d: feed margin
        buf.write(b"\x1B\x69\x64" + struct.pack("<H", label.feed_margin))

        # Raster rows
        buf.write(_encode_rows(black_1bit, red_1bit))

        # Print command
        buf.write(b"\x1A" if page_idx == len(images) - 1 else b"\x0C")

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Image preparation
# ---------------------------------------------------------------------------

def _prepare(
    img: Image.Image,
    label: Label,
    rotate: str | int,
    dpi_600: bool,
    red: bool,
) -> Image.Image:
    """Normalize mode, rotate, resize/validate, and pad to DEVICE_PIXEL_WIDTH."""
    im = _normalize_mode(img, red)

    is_endless = label.form_factor == "endless"
    dots_px = label.dots_printable

    if dpi_600:
        dots_expected = (dots_px[0] * 2, dots_px[1] * 2)
    else:
        dots_expected = dots_px

    if is_endless:
        if rotate not in ("auto", 0):
            im = im.rotate(int(rotate), expand=True)
        if dpi_600:
            im = im.resize((im.size[0] // 2, im.size[1]), Image.LANCZOS)
        if im.size[0] != dots_px[0]:
            h = int((dots_px[0] / im.size[0]) * im.size[1])
            im = im.resize((dots_px[0], h), Image.LANCZOS)
    else:
        # Die-cut / round die-cut
        if rotate == "auto":
            if im.size[0] == dots_expected[1] and im.size[1] == dots_expected[0]:
                im = im.rotate(90, expand=True)
        elif rotate != 0:
            im = im.rotate(int(rotate), expand=True)
        if im.size != dots_expected:
            raise ValueError(
                f"Image is {im.size[0]}×{im.size[1]}px but label '{label.identifier}' "
                f"requires exactly {dots_expected[0]}×{dots_expected[1]}px. "
                f"Use render_for_label() to size the canvas automatically."
            )
        if dpi_600:
            im = im.resize((im.size[0] // 2, im.size[1]), Image.LANCZOS)

    # Pad to device pixel width
    if im.size[0] < DEVICE_PIXEL_WIDTH:
        white = (255,) * len(im.mode)
        canvas = Image.new(im.mode, (DEVICE_PIXEL_WIDTH, im.size[1]), white)
        canvas.paste(im, (DEVICE_PIXEL_WIDTH - im.size[0] - label.right_margin_dots, 0))
        im = canvas

    return im


def _normalize_mode(img: Image.Image, red: bool) -> Image.Image:
    if img.mode.endswith("A"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, img.split()[-1])
        return bg
    if img.mode == "P":
        return img.convert("RGB" if red else "L")
    if img.mode == "L" and red:
        return img.convert("RGB")
    return img


# ---------------------------------------------------------------------------
# Color conversion
# ---------------------------------------------------------------------------

def _to_1bit(im: Image.Image, thresh_int: int, dither: bool) -> Image.Image:
    im = im.convert("L")
    im = PIL.ImageOps.invert(im)
    if dither:
        return im.convert("1", dither=Image.FLOYDSTEINBERG)
    return im.point(lambda x: 0 if x < thresh_int else 255, mode="1")


def _hsv_filter(
    im: Image.Image,
    hue_fn,
    sat_fn,
    val_fn,
    default: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Return a copy of im with non-matching pixels replaced by default color.

    Matching criteria are per-pixel lambdas on H, S, V channels (0–255 each).
    Equivalent to brother_ql.image_trafos.filtered_hsv.
    """
    hsv = im.convert("HSV")
    h_ch, s_ch, v_ch = hsv.split()

    mask_data = [
        255 if (hue_fn(h) and sat_fn(s) and val_fn(v)) else 0
        for h, s, v in zip(h_ch.getdata(), s_ch.getdata(), v_ch.getdata())
    ]
    mask = Image.new("L", im.size)
    mask.putdata(mask_data)

    result = Image.new("RGB", im.size, default)
    result.paste(im, mask=mask)
    return result


def _split_two_color(
    im: Image.Image, thresh_int: int
) -> tuple[Image.Image, Image.Image]:
    """Split an RGB image into (black_1bit, red_1bit) for two-color printing.

    Red pass: hue < 40 or > 210 (PIL HSV hue 0–255), sat > 100, val > 80.
    Black pass: val < 80 (dark pixels), minus any red pixels.
    """
    # Red
    red_filtered = _hsv_filter(
        im,
        hue_fn=lambda h: 255 if (h < 40 or h > 210) else 0,
        sat_fn=lambda s: 255 if s > 100 else 0,
        val_fn=lambda v: 255 if v > 80 else 0,
    )
    red_l = PIL.ImageOps.invert(red_filtered.convert("L"))
    red_1bit = red_l.point(lambda x: 0 if x < thresh_int else 255, mode="1")

    # Black (dark pixels, subtract red)
    black_filtered = _hsv_filter(
        im,
        hue_fn=lambda h: 255,
        sat_fn=lambda s: 255,
        val_fn=lambda v: 255 if v < 80 else 0,
    )
    black_l = PIL.ImageOps.invert(black_filtered.convert("L"))
    black_1bit = black_l.point(lambda x: 0 if x < thresh_int else 255, mode="1")
    black_1bit = PIL.ImageChops.subtract(black_1bit, red_1bit)

    return black_1bit, red_1bit


# ---------------------------------------------------------------------------
# Row encoding
# ---------------------------------------------------------------------------

def _encode_rows(
    black: Image.Image, red: Image.Image | None
) -> bytes:
    """Encode 1-bit image(s) as raster row commands.

    Single-color: 0x67 0x00 <len> <data>
    Two-color:    0x77 0x01 <len> <black_data>
                  0x77 0x02 <len> <red_data>   (interleaved, one pair per row)

    Rows are flipped left-right before packing, matching print head orientation.
    """
    frames = []
    for im in ([black] if red is None else [black, red]):
        flipped = im.transpose(Image.FLIP_LEFT_RIGHT).convert("1")
        frames.append(flipped.tobytes(encoder_name="raw"))

    row_len = black.size[0] // 8
    headers = (
        [b"\x67\x00"] if red is None
        else [b"\x77\x01", b"\x77\x02"]
    )

    buf = BytesIO()
    offset = 0
    total = len(frames[0])
    while offset + row_len <= total:
        for header, frame in zip(headers, frames):
            row = frame[offset : offset + row_len]
            buf.write(header + bytes([len(row)]) + row)
        offset += row_len

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Command helpers
# ---------------------------------------------------------------------------

def _media_quality(label: Label, n_rows: int, hq: bool, page_idx: int) -> bytes:
    """Build ESC i z (media and quality) payload.

    valid_flags: 0x80 base | 0x02 mtype | 0x04 mwidth | 0x08 mlength | 0x40 hq
    mtype: 0x0A endless, 0x0B die-cut
    mlength: 0 for endless
    rnumber: number of raster lines (4-byte LE uint32)
    page: 0 for first, 1 for subsequent
    """
    valid_flags = 0x80 | 0x02 | 0x04 | 0x08 | (0x40 if hq else 0x00)
    mtype = 0x0A if label.form_factor == "endless" else 0x0B
    mwidth = label.tape_size[0]
    mlength = label.tape_size[1]
    page = 0 if page_idx == 0 else 1

    payload = struct.pack(
        "<BBBBLBB",
        valid_flags,
        mtype,
        mwidth,
        mlength,
        n_rows,
        page,
        0x00,
    )
    return b"\x1B\x69\x7A" + payload
