"""Tests for address parsing, formatting, and rendering."""

import sys
import unittest
from io import StringIO
from unittest.mock import patch

from ohbrother.address import format_address, looks_like_address
from ohbrother.render import label_dims, render_address


class TestFormatAddress(unittest.TestCase):

    def test_recipient_street_city_state_zip(self):
        result = format_address("jane smith 123 main st springfield il 62701")
        lines = result.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("Jane Smith", lines[0])
        self.assertIn("123", lines[1])
        self.assertIn("Main", lines[1])
        self.assertIn("62701", lines[2])

    def test_no_recipient(self):
        result = format_address("123 main st springfield il 62701")
        lines = result.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("123", lines[0])
        self.assertIn("Springfield", lines[1])

    def test_no_zip(self):
        result = format_address("jane smith 123 main st springfield il")
        lines = result.splitlines()
        self.assertIn("Jane Smith", lines[0])
        self.assertIn("Springfield", lines[-1])
        self.assertNotIn("None", result)

    def test_all_caps_input_is_title_cased(self):
        result = format_address("123 MAIN ST SPRINGFIELD IL 62701")
        self.assertIn("Main", result)
        self.assertIn("Springfield", result)
        self.assertNotIn("MAIN", result)
        self.assertNotIn("SPRINGFIELD", result)

    def test_state_abbreviation_uppercased(self):
        result = format_address("123 main st springfield il 62701")
        self.assertIn("IL", result)

    def test_long_state_name_title_cased(self):
        result = format_address("123 main st springfield illinois 62701")
        self.assertIn("Illinois", result)
        self.assertNotIn("ILLINOIS", result)

    def test_occupancy_included(self):
        result = format_address("john doe 456 oak ave apt 3b chicago il 60601")
        self.assertIn("Apt", result)
        self.assertIn("3B", result)

    def test_unparseable_raises_value_error(self):
        with self.assertRaises(ValueError):
            format_address("the quick brown fox jumps over the lazy dog")

    def test_output_has_no_none_tokens(self):
        result = format_address("123 main st springfield il 62701")
        self.assertNotIn("None", result)


class TestLooksLikeAddress(unittest.TestCase):

    def test_street_address_returns_true(self):
        self.assertTrue(looks_like_address("123 main st springfield il 62701"))

    def test_street_address_with_name_returns_true(self):
        self.assertTrue(looks_like_address("jane smith 123 main st springfield il"))

    def test_plain_sentence_returns_false(self):
        self.assertFalse(looks_like_address("the quick brown fox jumps over the lazy dog"))

    def test_empty_string_returns_false(self):
        self.assertFalse(looks_like_address(""))

    def test_never_raises(self):
        # Should never raise regardless of input
        for bad in ["", "   ", "!@#$%", "a", "1234"]:
            try:
                looks_like_address(bad)
            except Exception as e:
                self.fail(f"looks_like_address raised {e!r} for {bad!r}")


class TestRenderAddress(unittest.TestCase):

    def test_29x90_returns_correct_dimensions(self):
        img = render_address("jane smith 123 main st springfield il 62701", "29x90")
        w, h = label_dims("29x90")
        self.assertEqual(img.size, (w, h))

    def test_62x100_returns_correct_dimensions(self):
        img = render_address("jane smith 123 main st springfield il 62701", "62x100")
        w, h = label_dims("62x100")
        self.assertEqual(img.size, (w, h))

    def test_default_label_is_29x90(self):
        img = render_address("jane smith 123 main st springfield il 62701")
        w, h = label_dims("29x90")
        self.assertEqual(img.size, (w, h))


class TestPrintHint(unittest.TestCase):

    def test_hint_printed_to_stderr_for_address_input(self):
        from ohbrother.cli import _cmd_print
        import argparse

        args = argparse.Namespace(
            text="123 main st springfield il 62701",
            image=None,
            printer=None,
            model="QL-800",
            label="62",
            rotate="auto",
            dpi_600=False,
            hq=True,
            cut=True,
            dither=False,
            threshold=70.0,
            red=False,
            font_size=90,
            font=None,
            padding=10,
            text_color="black",
            dry_run=True,
        )

        stderr_capture = StringIO()
        with patch("sys.stderr", stderr_capture):
            _cmd_print(args)

        self.assertIn("ohbrother address", stderr_capture.getvalue())

    def test_no_hint_for_plain_text(self):
        from ohbrother.cli import _cmd_print
        import argparse

        args = argparse.Namespace(
            text="Hello World",
            image=None,
            printer=None,
            model="QL-800",
            label="62",
            rotate="auto",
            dpi_600=False,
            hq=True,
            cut=True,
            dither=False,
            threshold=70.0,
            red=False,
            font_size=90,
            font=None,
            padding=10,
            text_color="black",
            dry_run=True,
        )

        stderr_capture = StringIO()
        with patch("sys.stderr", stderr_capture):
            _cmd_print(args)

        self.assertNotIn("ohbrother address", stderr_capture.getvalue())


if __name__ == "__main__":
    unittest.main()
