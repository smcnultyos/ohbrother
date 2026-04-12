from __future__ import annotations

import argparse
import sys
import textwrap


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ohbrother",
        description="Print labels on a Brother QL-800",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            examples:
              ohbrother print "Hello World"
              ohbrother print --label 62red --red "URGENT"
              ohbrother print --label 62red --red --text-color red "ALERT"
              ohbrother print --label 29x90 "Jane Smith\\n123 Main St"
              ohbrother print --image artwork.png
              ohbrother print --dry-run "test"
              ohbrother cut
              ohbrother detect
              ohbrother list-labels
              ohbrother status
        """),
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_print = sub.add_parser("print", help="print a label")

    content = p_print.add_mutually_exclusive_group(required=True)
    content.add_argument("text", nargs="?", help="text to print")
    content.add_argument("--image", metavar="PATH", help="image file to print")

    p_print.add_argument("--printer", metavar="USB_ID",
                         help="usb://0x04f9:0x209b[/SERIAL] (default: auto-detect)")
    p_print.add_argument("--model", default="QL-800")
    p_print.add_argument("--label", default="62",
                         help="label type, e.g. 62, 29, 62red, 62x100 (default: 62)")
    p_print.add_argument("--rotate", default="auto", choices=["auto", "0", "90", "270"])
    p_print.add_argument("--dpi-600", action="store_true", default=False)
    p_print.add_argument("--no-hq", action="store_false", dest="hq", default=True)
    p_print.add_argument("--no-cut", action="store_false", dest="cut", default=True)
    p_print.add_argument("--dither", action="store_true", default=False)
    p_print.add_argument("--threshold", type=float, default=70.0, metavar="0-100")
    p_print.add_argument("--red", action="store_true", default=False,
                         help="enable red channel (required for DK-22251 tape)")
    p_print.add_argument("--font-size", type=int, default=90, metavar="PTS")
    p_print.add_argument("--font", metavar="PATH")
    p_print.add_argument("--padding", type=int, default=10, metavar="PX")
    p_print.add_argument("--text-color", default="black", metavar="black|red",
                         help="text color for text rendering (default: black)")
    p_print.add_argument("--dry-run", action="store_true",
                         help="rasterize but don't send to printer")

    p_cut = sub.add_parser("cut", help="feed and cut without printing")
    p_cut.add_argument("--printer", metavar="USB_ID")
    p_cut.add_argument("--model", default="QL-800")
    p_cut.add_argument("--label", default="62")
    p_cut.add_argument("--red", action="store_true", default=False)

    sub.add_parser("detect", help="list connected Brother QL printers")
    sub.add_parser("list-labels", help="list supported label identifiers")

    p_status = sub.add_parser("status", help="query printer status")
    p_status.add_argument("--printer", metavar="USB_ID")

    return parser


def _resolve_printer(identifier: str | None) -> str:
    if identifier:
        return identifier
    from .detect import discover
    devices = [d for d in discover() if d["usable"]]
    if not devices:
        print("No usable Brother QL printer found. Is it plugged in?", file=sys.stderr)
        sys.exit(1)
    if len(devices) > 1:
        print("Multiple printers found; using first. Pass --printer to select.", file=sys.stderr)
    return devices[0]["identifier"]


def _parse_text_color(value: str) -> tuple[int, int, int]:
    if value.lower() == "red":
        return (255, 0, 0)
    if value.lower() == "black":
        return (0, 0, 0)
    # Accept hex or r,g,b
    if value.startswith("#"):
        v = value.lstrip("#")
        r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
        return (r, g, b)
    parts = value.split(",")
    if len(parts) == 3:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    raise argparse.ArgumentTypeError(f"Unknown color: {value!r}. Use 'black', 'red', '#rrggbb', or 'r,g,b'.")


def _cmd_detect() -> None:
    from .detect import discover
    devices = discover()
    if not devices:
        print("No Brother QL printers found.")
        return
    for d in devices:
        print(f"{d['identifier']:<40}  {d['model']}")
        if d["notes"]:
            suffix = "" if d["usable"] else "  [not usable]"
            print(f"    {d['notes']}{suffix}")


def _cmd_list_labels() -> None:
    from brother_ql.labels import ALL_LABELS
    print(f"{'ID':<14} {'Name':<32} {'Size (mm)':<12} Pixels")
    print("-" * 72)
    for lbl in ALL_LABELS:
        w, h = lbl.tape_size
        size = f"{w}x{h}" if h else f"{w}"
        px = f"{lbl.dots_printable[0]}x{lbl.dots_printable[1]}" if h else f"{lbl.dots_printable[0]}"
        print(f"{lbl.identifier:<14} {lbl.name:<32} {size:<12} {px}")


def _cmd_status(args: argparse.Namespace) -> None:
    from .backend import BrotherQLBackendQL800
    identifier = _resolve_printer(args.printer)
    be = BrotherQLBackendQL800(identifier)
    try:
        st = be.request_status()
    finally:
        be.dispose()

    if not st.get("valid"):
        print(f"Invalid status packet: {st.get('raw_hex')}")
        return

    media = f"{st['media_width_mm']}mm"
    if st.get("media_length_mm"):
        media += f" x {st['media_length_mm']}mm"
    media += f" {st['media_type']}"
    print(f"Model:      {st['model_code']}")
    print(f"Media:      {media}")
    print(f"Status:     {st['status_type']}")
    print(f"Phase:      {st['phase']}")
    print(f"Two-color:  {st['two_color_tape']}")
    if st["errors"]:
        print(f"Errors:     {', '.join(st['errors'])}")


def _cmd_cut(args: argparse.Namespace) -> None:
    from .printer import Printer, PrintOptions
    identifier = _resolve_printer(args.printer)
    opts = PrintOptions(label=args.label, model=args.model, red=args.red)
    with Printer(identifier, opts) as p:
        p.cut()
    print("Cut.")


def _cmd_print(args: argparse.Namespace) -> None:
    from .printer import Printer, PrintOptions
    from .render import render_for_label, render_image

    identifier = _resolve_printer(args.printer)
    opts = PrintOptions(
        label=args.label,
        model=args.model,
        rotate=args.rotate,
        dpi_600=args.dpi_600,
        hq=args.hq,
        cut=args.cut,
        dither=args.dither,
        threshold=args.threshold,
        red=args.red,
    )

    if args.image:
        images = [render_image(args.image)]
    else:
        try:
            text_color = _parse_text_color(args.text_color)
        except argparse.ArgumentTypeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        images = [render_for_label(
            args.text,
            args.label,
            font_size=args.font_size,
            padding=args.padding,
            font_path=args.font,
            text_color=text_color,
        )]

    if args.dry_run:
        from . import _suppress  # noqa: F401
        from brother_ql.raster import BrotherQLRaster
        from brother_ql.conversion import convert as bql_convert

        qlr = BrotherQLRaster(opts.model)
        qlr.exception_on_warning = True
        bql_convert(
            qlr, images, opts.label,
            rotate=opts.rotate, dpi_600=opts.dpi_600, hq=opts.hq,
            cut=opts.cut, compress=opts.compress, dither=opts.dither,
            threshold=opts.threshold, red=opts.red,
        )
        print(f"[dry-run] {len(qlr.data)} bytes — {opts.label} via {identifier}")
        return

    with Printer(identifier, opts) as p:
        st = p.status()
        print(f"Ready — {st.get('media_width_mm')}mm {st.get('media_type')} tape")
        post = p.print_images(images)
        if post.get("errors"):
            print(f"Errors: {', '.join(post['errors'])}", file=sys.stderr)
            sys.exit(1)
        print(f"Done — {post.get('status_type')}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "print":
        _cmd_print(args)
    elif args.command == "cut":
        _cmd_cut(args)
    elif args.command == "detect":
        _cmd_detect()
    elif args.command == "list-labels":
        _cmd_list_labels()
    elif args.command == "status":
        _cmd_status(args)
    else:
        parser.print_help()
        sys.exit(1)
