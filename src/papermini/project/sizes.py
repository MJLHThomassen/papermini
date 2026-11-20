"""Creature sizes: the D&D sizes (Tiny to Gargantuan) as figure heights, round bases and
stand tabs, from a size table.

A size fills in a figure's values (``height_mm``, ``tab_radius_mm``, ``tab_width_mm``,
``tab_height_mm`` and a token's ``token_diameter_mm``), which stay editable: a figure
whose values differ from its size's row is ``custom``. A table is calculated from a grid size and Medium's height, and each row
can be edited afterwards. The built-in table (a 1-inch grid, Medium 32 mm) gives the
defaults of a figure and is what a project without a table of its own uses.
``SizeCalculator`` does the calculations; this module holds the sizes and the built-in
table.
"""

from __future__ import annotations

from .size_table import SizeTable

SIZES = ("tiny", "small", "medium", "large", "huge", "gargantuan")
CUSTOM = "custom"
SIZE_CHOICES = SIZES + (CUSTOM,)
LABELS = {s: s.capitalize() for s in SIZE_CHOICES}
DEFAULT_SIZE = "medium"
SQUARES = {"tiny": 0.5, "small": 1, "medium": 1, "large": 2, "huge": 3, "gargantuan": 4}

HEIGHT_RATIO = {
    "tiny": 0.5,
    "small": 0.75,
    "medium": 1,
    "large": 1.5,
    "huge": 2,
    "gargantuan": 2.5,
}

BUILTIN_NAME = "Standard 1-inch"

BASE_FIT = (
    25 / 25.4
)  # bases a little under the grid, so they fit side by side (25 mm per inch)

BUILTIN = SizeTable(name=BUILTIN_NAME)  # the read-only built-in preset, all calculated
