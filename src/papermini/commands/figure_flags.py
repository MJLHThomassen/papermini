from __future__ import annotations

import argparse
from typing import Any

from ..project.figure_settings import FIGURE_OPTIONS, FigureSettings
from ..project.option_flags import OptionFlags
from ..project.size_calculator import SizeCalculator
from ..project.size_table import GRID_MM, SizeTable
from ..support.font_library import FontLibrary

# the figure settings with a flag, in the order the help lists them
FIGURE_FLAGS = (
    "copies",
    "kind",
    "size",
    "height_mm",
    "width_mm",
    "margin_mm",
    "smooth_mm",
    "margin_fill",
    "margin_color",
    "tab_shape",
    "tab_color",
    "tab_width_mm",
    "tab_radius_mm",
    "tab_height_mm",
    "tab_overlap_mm",
    "fold_mm",
    "no_tab",
    "double_sided",
    "back",
    "back_text",
    "back_color",
    "back_text_color",
    "token_diameter_mm",
    "token_area",
    "token_fill",
    "token_fill_color",
    "token_border_mm",
    "token_border_color",
    "token_cut_line",
    "token_outline",
    "token_text",
    "token_text_style",
    "token_text_color",
    "token_text_mm",
    "greyscale",
    "brightness",
    "contrast",
    "saturation",
    "hue",
    "model",
    "mask",
    "crop",
    "strength",
    "fill_gaps",
    "keep_all",
    "min_area",
    "label",
    "tab_front",
    "tab_back",
    "dpi",
    "simplify_mm",
    "no_smooth",
    "cut_color",
    "cut_width_mm",
    "label_color",
    "label_size_mm",
    "back_label",
    "back_label_color",
    "back_label_size_mm",
)


class FigureFlags:
    """Adds the flags of a figure's settings to a command, and turns the flags given
    into settings, the creature size filling in the rest with ``size_calculator``."""

    def __init__(self, size_calculator: SizeCalculator):
        self._size_calculator = size_calculator

    def add_to(self, parser: argparse.ArgumentParser) -> OptionFlags:
        """Add the figure flags and the grid flag to ``parser``. Every flag is None
        unless given."""
        flags = OptionFlags(parser, FigureSettings)
        flags.add(*FIGURE_FLAGS[: FIGURE_FLAGS.index("height_mm")])
        flags.group_of("size").add_argument(
            "--grid-mm",
            type=float,
            help=flags.with_default(
                "grid square for --size: the bases and heights scale with it",
                GRID_MM,
                "mm",
            ),
        )
        flags.add(*FIGURE_FLAGS[FIGURE_FLAGS.index("height_mm") :])
        flags.add_one(
            "font",
            ". A bundled font ("
            + ", ".join(FontLibrary.BUNDLED)
            + ") or a TrueType font installed on this computer",
        )
        return flags

    def given(self, args: argparse.Namespace) -> dict[str, Any]:
        """The figure settings whose flags ``args`` gives."""
        return {
            name: getattr(args, name)
            for name in FIGURE_OPTIONS
            if getattr(args, name, None) is not None
        }

    def table(self, args: argparse.Namespace, table: SizeTable) -> SizeTable:
        """``table``, or the built-in table on the grid ``args`` gives."""
        if args.grid_mm is None:
            return table
        if args.grid_mm <= 0:
            raise SystemExit("--grid-mm must be above 0")
        return self._size_calculator.for_grid(args.grid_mm)

    def settings(self, args: argparse.Namespace, table: SizeTable) -> FigureSettings:
        """A figure's settings from the flags ``args`` gives, the size from ``table``
        filling in the rest."""
        return self._size_calculator.settings_with_size(self.given(args), table)
