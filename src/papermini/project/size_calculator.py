from __future__ import annotations

from dataclasses import replace
from typing import Any

from .figure_settings import FigureSettings
from .option import Option
from .size_table import GRID_MM, MEDIUM_MM, SizeTable
from .sizes import BUILTIN, CUSTOM, DEFAULT_SIZE, SIZES, SQUARES


class SizeCalculator:
    """Calculates size tables, and the values a creature size fills in for a figure."""

    def calculate(
        self, grid_mm: float = GRID_MM, medium_mm: float = MEDIUM_MM, name: str = ""
    ) -> SizeTable:
        """A table calculated from the grid and Medium's height."""
        return SizeTable(float(grid_mm), float(medium_mm), {}, name)

    def for_grid(self, grid_mm: float) -> SizeTable:
        """The built-in table on another grid: bases and heights scale with it."""
        return self.calculate(grid_mm, MEDIUM_MM * grid_mm / GRID_MM)

    def settings_with_size(
        self, options: dict[str, Any], table: SizeTable = BUILTIN
    ) -> FigureSettings:
        """Figure settings from ``options`` (a project's figure, or command-line flags):
        the figure's size fills in the values not given, from ``table``; a given value
        that differs from the size's makes the figure custom."""
        o = Option.norm_keys(options)
        size = o.get("size", DEFAULT_SIZE)
        if size in SIZES:
            fills = table.row(size).values()
            if o.get("width_mm") is not None and "height_mm" not in o:
                del fills[
                    "height_mm"
                ]  # (a width alone scales by width: no height to fill in)
            for k, v in fills.items():
                o.setdefault(k, v)
        s = FigureSettings.from_dict(o)
        return s if self.matches(s, table) else replace(s, size=CUSTOM)

    def apply(
        self, settings: FigureSettings, size: str, table: SizeTable = BUILTIN
    ) -> FigureSettings:
        """``settings`` with ``size`` and, for a creature size, the values its row fills
        in (a set width is cleared: it follows the height again)."""
        if size == CUSTOM:
            return replace(settings, size=CUSTOM)
        return replace(settings, size=size, width_mm=None, **table.row(size).values())

    def matches(self, settings: FigureSettings, table: SizeTable = BUILTIN) -> bool:
        """Whether a figure's values are its size's (always true for custom)."""
        if settings.size == CUSTOM:
            return True
        row = table.row(settings.size).values()
        return settings.width_mm is None and all(
            abs(getattr(settings, k) - v) < 0.005 for k, v in row.items()
        )

    def reconcile(
        self, old: FigureSettings, new: FigureSettings, table: SizeTable = BUILTIN
    ) -> FigureSettings:
        """The figure settings after a change from ``old`` to ``new``: a newly picked
        size fills in its values; a filled-in value edited by hand makes the figure
        custom."""
        if new.size != old.size:
            return self.apply(new, new.size, table)
        if not self.matches(new, table):
            return replace(new, size=CUSTOM)
        return new

    def footprint_text(self, size: str, table: SizeTable) -> str:
        """A size's footprint and base in words, such as "2 × 2 squares · 50 mm base"."""
        if size == CUSTOM:
            return ""
        sq = SQUARES[size]
        squares = (
            "½ × ½ square"
            if sq < 1
            else f"{sq:g} × {sq:g} square{'s' if sq > 1 else ''}"
        )
        return f"{squares} · {table.row(size).base_mm:g} mm base"

    def width_warning(self, size: str, width_mm: float, table: SizeTable) -> str:
        """A warning when a figure is wider than its size's squares, else ""."""
        if size == CUSTOM or not width_mm:
            return ""
        room = table.squares_mm(size)
        if width_mm <= room + 0.05:
            return ""
        sq = SQUARES[size]
        squares = "half a square" if sq < 1 else f"{sq:g} square{'s' if sq > 1 else ''}"
        return (
            f"This figure is {width_mm:.0f} mm wide, wider than its {squares} "
            f"({round(room, 1):g} mm): set a width or pick a bigger size."
        )
