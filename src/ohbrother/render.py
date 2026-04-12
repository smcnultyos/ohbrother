from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_DEFAULT_FONTS = [
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
    "/usr/share/fonts/open-sans/OpenSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]


def label_dims(label_id: str) -> tuple[int, int]:
    """Return (width_px, height_px) from brother_ql label specs.

    height_px is 0 for endless tape. Die-cut labels require images sized
    to exactly (width_px, height_px).
    """
    from brother_ql.labels import ALL_LABELS
    label = next((l for l in ALL_LABELS if l.identifier == label_id), None)
    if label is None:
        raise ValueError(f"Unknown label identifier: {label_id!r}. Run 'ohbrother list-labels'.")
    return label.dots_printable


def _load_font(font_size: int, font_path: str | None) -> ImageFont.FreeTypeFont:
    candidates = ([font_path] if font_path else []) + _DEFAULT_FONTS
    for path in candidates:
        if not path:
            continue
        try:
            return ImageFont.truetype(path, font_size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default(size=font_size)


def render_text(
    text: str,
    *,
    label_width_px: int,
    label_height_px: int | None = None,
    font_size: int = 90,
    padding: int = 10,
    font_path: str | None = None,
    text_color: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """Word-wrap text into an RGB image.

    If label_height_px is provided the canvas is exactly that height and the
    text block is vertically centered — required for die-cut labels, which
    reject any image whose height doesn't match the label spec exactly.

    text_color controls the ink color. Use (255, 0, 0) for red on two-color
    tape; brother_ql separates the passes by HSV hue (red = hue < 40 or > 210).
    """
    font = _load_font(font_size, font_path)

    tmp = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(tmp)

    usable_width = label_width_px - 2 * padding
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        line: list[str] = []
        for word in words:
            candidate = " ".join(line + [word])
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] > usable_width and line:
                lines.append(" ".join(line))
                line = [word]
            else:
                line.append(word)
        lines.append(" ".join(line))

    line_height = draw.textbbox((0, 0), "Ag", font=font)[3] + 4
    content_height = line_height * len(lines)

    if label_height_px is not None:
        canvas_h = label_height_px
        y = (canvas_h - content_height) // 2
    else:
        canvas_h = content_height + 2 * padding
        y = padding

    img = Image.new("RGB", (label_width_px, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    for line in lines:
        draw.text((padding, y), line, font=font, fill=text_color)
        y += line_height

    return img


def render_for_label(
    text: str,
    label_id: str,
    *,
    font_size: int = 90,
    padding: int = 10,
    font_path: str | None = None,
    text_color: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """Render text sized for a specific label type.

    Equivalent to calling label_dims(label_id) then render_text() with the
    right label_width_px / label_height_px. Use this instead of render_text()
    when working with die-cut labels.
    """
    w, h = label_dims(label_id)
    return render_text(
        text,
        label_width_px=w,
        label_height_px=h if h > 0 else None,
        font_size=font_size,
        padding=padding,
        font_path=font_path,
        text_color=text_color,
    )


def render_image(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")
