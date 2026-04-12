"""Smoke tests for ohbrother — no printer required.

Covers: label specs, raster stream structure, image sizing, color separation,
status packet parsing, and preflight validation.
"""

import unittest

from PIL import Image

from ohbrother.exceptions import StatusError, TapeMismatchError
from ohbrother.labels import LABELS, DEVICE_PIXEL_WIDTH
from ohbrother.raster import rasterize, _split_two_color, _to_1bit
from ohbrother.render import label_dims, render_text, render_for_label
from ohbrother.status import parse_status, validate_preflight


# ---------------------------------------------------------------------------
# Label specs
# ---------------------------------------------------------------------------

class TestLabels(unittest.TestCase):

    def test_known_endless_dims(self):
        self.assertEqual(label_dims("62"), (696, 0))
        self.assertEqual(label_dims("62red"), (696, 0))
        self.assertEqual(label_dims("29"), (306, 0))

    def test_known_die_cut_dims(self):
        self.assertEqual(label_dims("29x90"), (306, 991))
        self.assertEqual(label_dims("62x100"), (696, 1109))

    def test_unknown_label_raises(self):
        with self.assertRaises(ValueError):
            label_dims("not_a_label")

    def test_two_color_flag(self):
        self.assertTrue(LABELS["62red"].two_color)
        self.assertFalse(LABELS["62"].two_color)

    def test_device_pixel_width(self):
        # QL-800: 90 bytes × 8 bits
        self.assertEqual(DEVICE_PIXEL_WIDTH, 720)

    def test_ql800_labels_fit_device_width(self):
        # Labels wider than DEVICE_PIXEL_WIDTH require QL-1050/1060N and
        # should raise ValueError when rasterized on the QL-800.
        for lbl in LABELS.values():
            pw = lbl.dots_printable[0]
            if pw > DEVICE_PIXEL_WIDTH:
                continue  # QL-1050/1060N label; tested separately below
            self.assertGreaterEqual(
                DEVICE_PIXEL_WIDTH, pw + lbl.right_margin_dots,
                f"{lbl.identifier}: printable + right_margin exceeds device width",
            )

    def test_wide_label_raises_on_ql800(self):
        with self.assertRaises(ValueError, msg="102mm label should fail on QL-800"):
            rasterize([Image.new("RGB", (1164, 1), (255, 255, 255))], "102")


# ---------------------------------------------------------------------------
# Raster stream structure
# ---------------------------------------------------------------------------

class TestRasterStream(unittest.TestCase):

    def _white(self, w, h):
        return Image.new("RGB", (w, h), (255, 255, 255))

    def test_preamble_bytes(self):
        data = rasterize([self._white(696, 1)], "62")
        # ESC i a 01
        self.assertEqual(data[0:4], b"\x1b\x69\x61\x01")
        # 200 null bytes (invalidate)
        self.assertEqual(data[4:204], b"\x00" * 200)
        # ESC @ (initialize)
        self.assertEqual(data[204:206], b"\x1b\x40")
        # ESC i a 01 again
        self.assertEqual(data[206:210], b"\x1b\x69\x61\x01")

    def test_per_image_commands_present(self):
        data = rasterize([self._white(696, 1)], "62")
        self.assertIn(b"\x1b\x69\x53", data)        # ESC i S: status request
        self.assertIn(b"\x1b\x69\x7a", data)        # ESC i z: media/quality
        self.assertIn(b"\x1b\x69\x4d\x40", data)   # ESC i M: autocut on
        self.assertIn(b"\x1b\x69\x41\x01", data)   # ESC i A: cut every 1
        self.assertIn(b"\x1b\x69\x4b", data)        # ESC i K: expanded mode
        self.assertIn(b"\x1b\x69\x64", data)        # ESC i d: margins

    def test_ends_with_print_cut(self):
        data = rasterize([self._white(696, 1)], "62")
        self.assertEqual(data[-1], 0x1A)

    def test_row_count_matches_image_height(self):
        h = 25
        data = rasterize([self._white(696, h)], "62")
        self.assertEqual(data.count(b"\x67\x00"), h)

    def test_row_length_is_device_pixel_width_over_8(self):
        # Each row: header(2) + len_byte(1) + data(DEVICE_PIXEL_WIDTH/8)
        expected_row_bytes = DEVICE_PIXEL_WIDTH // 8  # 90
        data = rasterize([self._white(696, 1)], "62")
        idx = data.index(b"\x67\x00")
        row_len = data[idx + 2]
        self.assertEqual(row_len, expected_row_bytes)

    def test_two_color_rows_interleaved(self):
        # Each image row produces one black (0x77 0x01) and one red (0x77 0x02) row
        h = 10
        img = Image.new("RGB", (696, h), (255, 0, 0))  # solid red
        data = rasterize([img], "62red", red=True)
        self.assertEqual(data.count(b"\x77\x01"), h)
        self.assertEqual(data.count(b"\x77\x02"), h)

    def test_single_color_has_no_two_color_headers(self):
        data = rasterize([self._white(696, 5)], "62")
        self.assertNotIn(b"\x77\x01", data)
        self.assertNotIn(b"\x77\x02", data)

    def test_multi_image_print_commands(self):
        # N images: (N-1) form-feeds (0x0C), 1 print+cut (0x1A)
        imgs = [self._white(696, 1) for _ in range(3)]
        data = rasterize(imgs, "62")
        self.assertEqual(data.count(b"\x0c"), 2)
        self.assertEqual(data[-1], 0x1A)

    def test_multi_image_status_requests(self):
        # Each image gets its own ESC i S
        imgs = [self._white(696, 1) for _ in range(3)]
        data = rasterize(imgs, "62")
        self.assertEqual(data.count(b"\x1b\x69\x53"), 3)

    def test_die_cut_correct_dimensions(self):
        w, h = label_dims("29x90")
        img = Image.new("RGB", (w, h), (255, 255, 255))
        data = rasterize([img], "29x90")
        self.assertEqual(data.count(b"\x67\x00"), h)

    def test_die_cut_wrong_dimensions_raises(self):
        with self.assertRaises(ValueError):
            rasterize([self._white(306, 500)], "29x90")

    def test_cut_flag_in_expanded_mode(self):
        # ESC i K byte: bit 3 = cut_at_end
        data_cut    = rasterize([self._white(696, 1)], "62", cut=True)
        data_no_cut = rasterize([self._white(696, 1)], "62", cut=False)
        idx_cut    = data_cut.index(b"\x1b\x69\x4b")
        idx_no_cut = data_no_cut.index(b"\x1b\x69\x4b")
        self.assertTrue(data_cut[idx_cut + 3]    & 0x08)
        self.assertFalse(data_no_cut[idx_no_cut + 3] & 0x08)

    def test_two_color_flag_in_expanded_mode(self):
        # ESC i K byte: bit 0 = two_color_printing
        data_red    = rasterize([Image.new("RGB", (696, 1), (255, 0, 0))], "62red", red=True)
        data_black  = rasterize([Image.new("RGB", (696, 1), (0, 0, 0))],   "62",    red=False)
        idx_red   = data_red.index(b"\x1b\x69\x4b")
        idx_black = data_black.index(b"\x1b\x69\x4b")
        self.assertTrue(data_red[idx_red + 3]     & 0x01)
        self.assertFalse(data_black[idx_black + 3] & 0x01)

    def test_endless_auto_resize(self):
        # An image narrower than dots_printable should be resized, not error
        narrow = Image.new("RGB", (300, 50), (255, 255, 255))
        data = rasterize([narrow], "62")
        self.assertGreater(len(data), 0)
        self.assertEqual(data[-1], 0x1A)


# ---------------------------------------------------------------------------
# Color separation
# ---------------------------------------------------------------------------

class TestColorSeparation(unittest.TestCase):

    def _thresh(self, t=70.0):
        return min(255, max(0, int((100.0 - t) / 100.0 * 255)))

    def test_solid_red_goes_to_red_pass(self):
        img = Image.new("RGB", (720, 1), (255, 0, 0))
        black, red = _split_two_color(img, self._thresh())
        black_pixels = list(black.getdata())
        red_pixels   = list(red.getdata())
        self.assertTrue(any(p for p in red_pixels),   "red pass should have ink")
        self.assertFalse(any(p for p in black_pixels), "black pass should be empty for pure red")

    def test_solid_black_goes_to_black_pass(self):
        img = Image.new("RGB", (720, 1), (0, 0, 0))
        black, red = _split_two_color(img, self._thresh())
        black_pixels = list(black.getdata())
        red_pixels   = list(red.getdata())
        self.assertTrue(any(p for p in black_pixels), "black pass should have ink")
        self.assertFalse(any(p for p in red_pixels),  "red pass should be empty for pure black")

    def test_white_produces_no_ink(self):
        img = Image.new("RGB", (720, 1), (255, 255, 255))
        black, red = _split_two_color(img, self._thresh())
        self.assertFalse(any(list(black.getdata())))
        self.assertFalse(any(list(red.getdata())))

    def test_black_single_color_threshold(self):
        # Pure black → all ink; pure white → no ink
        black_img = Image.new("RGB", (720, 1), (0, 0, 0))
        white_img = Image.new("RGB", (720, 1), (255, 255, 255))
        bk = _to_1bit(black_img, self._thresh(), dither=False)
        wh = _to_1bit(white_img, self._thresh(), dither=False)
        self.assertTrue(all(list(bk.getdata())))
        self.assertFalse(any(list(wh.getdata())))


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

class TestRender(unittest.TestCase):

    def test_render_text_endless_width(self):
        img = render_text("Hello", label_width_px=696)
        self.assertEqual(img.width, 696)
        self.assertGreater(img.height, 0)

    def test_render_text_die_cut_exact_height(self):
        img = render_text("Hello", label_width_px=306, label_height_px=991)
        self.assertEqual(img.size, (306, 991))

    def test_render_for_label_endless(self):
        img = render_for_label("Hello", "62")
        self.assertEqual(img.width, 696)

    def test_render_for_label_die_cut(self):
        w, h = label_dims("29x90")
        img = render_for_label("Hello", "29x90")
        self.assertEqual(img.size, (w, h))

    def test_render_text_color_red(self):
        img = render_for_label("X", "62red", text_color=(255, 0, 0), font_size=200)
        pixels = list(img.getdata())
        red_pixels = [p for p in pixels if p[0] > 200 and p[1] < 50 and p[2] < 50]
        self.assertGreater(len(red_pixels), 0, "No red pixels found in red-text render")

    def test_render_text_default_is_black(self):
        img = render_for_label("X", "62", font_size=200)
        pixels = list(img.getdata())
        dark_pixels = [p for p in pixels if max(p) < 50]
        self.assertGreater(len(dark_pixels), 0, "No dark pixels in default (black) render")


# ---------------------------------------------------------------------------
# Status parsing
# ---------------------------------------------------------------------------

# Live QL-800 status packet (62mm continuous, two-color tape, ready)
_LIVE_PACKET = bytes.fromhex(
    "802042343830000000003e0a0000230000000000000000000081000000000000"
)

class TestStatusParsing(unittest.TestCase):

    def test_valid_packet_parsed(self):
        st = parse_status(_LIVE_PACKET)
        self.assertTrue(st["valid"])
        self.assertEqual(st["model_code"], "48")
        self.assertEqual(st["media_width_mm"], 62)
        self.assertEqual(st["media_type"], "continuous")
        self.assertEqual(st["status_type"], "ready")
        self.assertEqual(st["phase"], "receiving")
        self.assertTrue(st["two_color_tape"])
        self.assertEqual(st["errors"], [])

    def test_empty_returns_invalid(self):
        st = parse_status(b"")
        self.assertFalse(st["valid"])

    def test_wrong_header_returns_invalid(self):
        bad = bytearray(_LIVE_PACKET)
        bad[0] = 0x00
        self.assertFalse(parse_status(bytes(bad))["valid"])

    def test_wrong_size_byte_returns_invalid(self):
        bad = bytearray(_LIVE_PACKET)
        bad[1] = 0x10
        self.assertFalse(parse_status(bytes(bad))["valid"])

    def test_error_bits_decoded(self):
        pkt = bytearray(_LIVE_PACKET)
        pkt[8] = 0x01  # no_media
        pkt[9] = 0x08  # cover_open
        st = parse_status(bytes(pkt))
        self.assertIn("no_media", st["errors"])
        self.assertIn("cover_open", st["errors"])

    def test_die_cut_media_length(self):
        pkt = bytearray(_LIVE_PACKET)
        pkt[11] = 0x0B  # die-cut
        pkt[17] = 90    # 90mm length
        st = parse_status(bytes(pkt))
        self.assertEqual(st["media_type"], "die_cut")
        self.assertEqual(st["media_length_mm"], 90)

    def test_no_media_type(self):
        pkt = bytearray(_LIVE_PACKET)
        pkt[11] = 0x00
        st = parse_status(bytes(pkt))
        self.assertEqual(st["media_type"], "no_media")


# ---------------------------------------------------------------------------
# Preflight validation
# ---------------------------------------------------------------------------

class TestPreflight(unittest.TestCase):

    def _status(self, **overrides):
        base = {
            "valid": True,
            "errors": [],
            "two_color_tape": False,
            "text_color": 0x01,
        }
        base.update(overrides)
        return base

    def test_clean_status_passes(self):
        validate_preflight(self._status(), red=False, label="62")

    def test_error_bits_raise(self):
        with self.assertRaises(StatusError):
            validate_preflight(self._status(errors=["no_media"]), red=False, label="62")

    def test_two_color_tape_without_red_raises(self):
        with self.assertRaises(TapeMismatchError):
            validate_preflight(
                self._status(two_color_tape=True, text_color=0x81),
                red=False,
                label="62",
            )

    def test_two_color_tape_with_red_passes(self):
        validate_preflight(
            self._status(two_color_tape=True, text_color=0x81),
            red=True,
            label="62red",
        )

    def test_invalid_status_raises(self):
        with self.assertRaises(StatusError):
            validate_preflight({"valid": False, "errors": []}, red=False, label="62")


if __name__ == "__main__":
    unittest.main()
