"""Label specifications for Brother QL-series printers.

All pixel dimensions are at 300 dpi. The QL-800 has a device pixel width of
720 (90 bytes × 8 bits); printable areas are centered within that canvas
using right_margin_dots as the right offset.
"""

from __future__ import annotations
from dataclasses import dataclass

DEVICE_PIXEL_WIDTH = 720  # QL-800: 90 bytes × 8 bits


@dataclass(frozen=True)
class Label:
    identifier: str
    name: str
    form_factor: str            # "endless", "die_cut", "round_die_cut"
    tape_size: tuple[int, int]  # mm (width, height); height=0 for endless
    dots_printable: tuple[int, int]  # px; height=0 for endless
    right_margin_dots: int
    feed_margin: int            # dots; used in ESC i d
    two_color: bool = False


LABELS: dict[str, Label] = {
    "12":     Label("12",     "12mm endless",             "endless",       (12,  0),   (106,    0),   29,  35),
    "29":     Label("29",     "29mm endless",             "endless",       (29,  0),   (306,    0),    6,  35),
    "38":     Label("38",     "38mm endless",             "endless",       (38,  0),   (413,    0),   12,  35),
    "50":     Label("50",     "50mm endless",             "endless",       (50,  0),   (554,    0),   12,  35),
    "54":     Label("54",     "54mm endless",             "endless",       (54,  0),   (590,    0),    0,  35),
    "62":     Label("62",     "62mm endless",             "endless",       (62,  0),   (696,    0),   12,  35),
    "62red":  Label("62red",  "62mm endless black/red",   "endless",       (62,  0),   (696,    0),   12,  35, two_color=True),
    "102":    Label("102",    "102mm endless",            "endless",       (102, 0),   (1164,   0),   12,  35),
    "17x54":  Label("17x54",  "17mm x 54mm die-cut",      "die_cut",       (17,  54),  (165,  566),    0,   0),
    "17x87":  Label("17x87",  "17mm x 87mm die-cut",      "die_cut",       (17,  87),  (165,  956),    0,   0),
    "23x23":  Label("23x23",  "23mm x 23mm die-cut",      "die_cut",       (23,  23),  (202,  202),   42,   0),
    "29x42":  Label("29x42",  "29mm x 42mm die-cut",      "die_cut",       (29,  42),  (306,  425),    6,   0),
    "29x90":  Label("29x90",  "29mm x 90mm die-cut",      "die_cut",       (29,  90),  (306,  991),    6,   0),
    "39x90":  Label("39x90",  "38mm x 90mm die-cut",      "die_cut",       (38,  90),  (413,  991),   12,   0),
    "39x48":  Label("39x48",  "39mm x 48mm die-cut",      "die_cut",       (39,  48),  (425,  495),    6,   0),
    "52x29":  Label("52x29",  "52mm x 29mm die-cut",      "die_cut",       (52,  29),  (578,  271),    0,   0),
    "62x29":  Label("62x29",  "62mm x 29mm die-cut",      "die_cut",       (62,  29),  (696,  271),   12,   0),
    "62x100": Label("62x100", "62mm x 100mm die-cut",     "die_cut",       (62, 100),  (696, 1109),   12,   0),
    "102x51": Label("102x51", "102mm x 51mm die-cut",     "die_cut",       (102, 51),  (1164, 526),   12,   0),
    "102x152":Label("102x152","102mm x 153mm die-cut",    "die_cut",       (102,153),  (1164,1660),   12,   0),
    "d12":    Label("d12",    "12mm round die-cut",        "round_die_cut", (12,  12),  (94,    94),  113,  35),
    "d24":    Label("d24",    "24mm round die-cut",        "round_die_cut", (24,  24),  (236,  236),   42,   0),
    "d58":    Label("d58",    "58mm round die-cut",        "round_die_cut", (58,  58),  (618,  618),   51,   0),
}
