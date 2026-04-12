"""Optional hardware print tests — requires a connected QL-800 with 62red tape.

Run with: pytest tests/test_print.py -v -s

All tests are skipped automatically when no usable printer is detected.
The suite assumes DK-22251 (62mm black+red) tape is loaded; it will fail
preflight if a different tape is installed.
"""

import unittest

from PIL import Image

from ohbrother.detect import discover
from ohbrother.printer import Printer, PrintOptions
from ohbrother.render import render_for_label


def _find_printer() -> str | None:
    devices = [d for d in discover() if d["usable"]]
    return devices[0]["identifier"] if devices else None


PRINTER_ID = _find_printer()
SKIP_REASON = "No usable Brother QL printer found"


@unittest.skipUnless(PRINTER_ID, SKIP_REASON)
class TestLivePrints(unittest.TestCase):
    """Three test prints against a live QL-800 with 62red tape."""

    def _opts(self, **kwargs) -> PrintOptions:
        return PrintOptions(label="62red", red=True, **kwargs)

    def _assert_clean_status(self, st: dict) -> None:
        self.assertTrue(st.get("valid"), f"Invalid status packet: {st.get('raw_hex')}")
        self.assertEqual(st.get("errors"), [], f"Post-print errors: {st['errors']}")

    def test_1_black_text(self):
        """Print black text on 62red tape."""
        img = render_for_label("ohbrother\ntest print 1", "62red",
                               text_color=(0, 0, 0), font_size=80)
        with Printer(PRINTER_ID, self._opts()) as p:
            st = p.print_images([img])
        self._assert_clean_status(st)

    def test_2_red_text(self):
        """Print red text on 62red tape (exercises two-color HSV path)."""
        img = render_for_label("RED TEXT\ntest print 2", "62red",
                               text_color=(255, 0, 0), font_size=80)
        with Printer(PRINTER_ID, self._opts()) as p:
            st = p.print_images([img])
        self._assert_clean_status(st)

    def test_3_cut(self):
        """Feed and cut without printing; printer should return to ready."""
        with Printer(PRINTER_ID, self._opts()) as p:
            p.cut()
            st = p.status()
        self.assertTrue(st.get("valid"), f"Invalid status after cut: {st.get('raw_hex')}")
        self.assertEqual(st.get("errors"), [], f"Errors after cut: {st['errors']}")


if __name__ == "__main__":
    unittest.main()
