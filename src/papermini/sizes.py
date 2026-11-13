"""Creature sizes: the D&D sizes (Tiny to Gargantuan) as figure heights, round bases and
stand tabs, from a size table.

A size fills in a figure's values (``height_mm``, ``tab_radius_mm``, ``tab_width_mm``,
``tab_height_mm``), which stay editable: a figure whose values differ from its size's row
is ``custom``. A table is calculated from a grid size and Medium's height, and each row
can be edited afterwards. The built-in table (a 1-inch grid, Medium 32 mm) gives the
defaults of a figure and is what a project without a table of its own uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional

SIZES = ("tiny", "small", "medium", "large", "huge", "gargantuan")
CUSTOM = "custom"
SIZE_CHOICES = SIZES + (CUSTOM,)
DEFAULT_SIZE = "medium"
SQUARES = {"tiny": 0.5, "small": 1, "medium": 1, "large": 2, "huge": 3, "gargantuan": 4}
HEIGHT_RATIO = {"tiny": 0.5, "small": 0.75, "medium": 1, "large": 1.5, "huge": 2,
                "gargantuan": 2.5}
GRID_MM = 25.4        # a 1-inch grid
MEDIUM_MM = 32.0      # a "heroic" scale human
BUILTIN_NAME = "Standard 1-inch"
BASE_FIT = 25 / 25.4  # bases a little under the grid, so they fit side by side (25 mm per inch)
FIELDS = ("height_mm", "base_mm", "tab_width_mm", "tab_height_mm")
# the figure settings a size fills in
FILLS = ("height_mm", "tab_radius_mm", "tab_width_mm", "tab_height_mm")


@dataclass(frozen=True)
class SizeRow:
    """What one size fills in: the figure height, the round base's diameter and the stand
    tab (square tab) width and height, in mm."""

    height_mm: float
    base_mm: float
    tab_width_mm: float
    tab_height_mm: float

    def values(self) -> Dict[str, float]:
        """The figure settings this row fills in."""
        return {"height_mm": self.height_mm, "tab_radius_mm": self.base_mm / 2,
                "tab_width_mm": self.tab_width_mm, "tab_height_mm": self.tab_height_mm}


def _mm(v: float) -> float:
    return round(float(v), 2)


def calculate_row(size: str, grid_mm: float, medium_mm: float) -> SizeRow:
    """A size's row calculated from the grid and Medium's height: the height scales from
    Medium, the base covers its squares (a little under the grid) and the stand tab is as
    wide as the base and half as deep."""
    base = _mm(SQUARES[size] * grid_mm * BASE_FIT)
    return SizeRow(_mm(medium_mm * HEIGHT_RATIO[size]), base, base, _mm(base / 2))


@dataclass(frozen=True)
class SizeTable:
    """The grid, Medium's height (what the table was calculated from), each size's row, and
    the name of the preset the table is or came from ("" for none)."""

    grid_mm: float = GRID_MM
    medium_mm: float = MEDIUM_MM
    rows: Dict[str, SizeRow] = field(default_factory=dict)
    name: str = ""

    def __post_init__(self):
        missing = {s: calculate_row(s, self.grid_mm, self.medium_mm)
                   for s in SIZES if s not in self.rows}
        if missing:
            object.__setattr__(self, "rows", {s: self.rows.get(s) or missing[s] for s in SIZES})

    def row(self, size: str) -> SizeRow:
        return self.rows[size]

    def squares_mm(self, size: str) -> float:
        """The width of a size's squares on the grid."""
        return SQUARES[size] * self.grid_mm

    def calculated(self) -> bool:
        """Whether every row is what the grid and Medium's height give."""
        return all(self.rows[s] == calculate_row(s, self.grid_mm, self.medium_mm)
                   for s in SIZES)

    def same_values(self, other: "SizeTable") -> bool:
        """Whether ``other`` has the same grid, Medium height and rows (names aside)."""
        return replace(self, name="") == replace(other, name="")

    def to_dict(self) -> Dict[str, Any]:
        """The table as a project stores it."""
        return {**({"preset": self.name} if self.name else {}),
                "grid_mm": self.grid_mm, "medium_mm": self.medium_mm,
                **{s: {k: getattr(self.rows[s], k) for k in FIELDS} for s in SIZES}}

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "SizeTable":
        """A table from a project (``None``: the built-in one). Sizes left out are
        calculated from the grid and Medium's height."""
        if not d:
            return BUILTIN
        if not isinstance(d, dict):
            raise ValueError("sizes must be a table of preset, grid_mm, medium_mm and the sizes")
        d = {str(k).replace("-", "_"): v for k, v in d.items()}
        unknown = set(d) - set(SIZES) - {"preset", "grid_mm", "medium_mm"}
        if unknown:
            raise ValueError(f"unknown sizes entr{'y' if len(unknown) == 1 else 'ies'} "
                             f"{', '.join(sorted(unknown))}")
        name = d.get("preset", "")
        if not isinstance(name, str):
            raise ValueError(f"sizes preset must be a name, not {name!r}")
        grid = _positive(d.get("grid_mm", GRID_MM), "sizes grid_mm")
        medium = _positive(d.get("medium_mm", MEDIUM_MM), "sizes medium_mm")
        rows = {}
        for s in SIZES:
            if s not in d:
                continue
            r = d[s]
            if not isinstance(r, dict):
                raise ValueError(f"sizes {s} must give {', '.join(FIELDS)}")
            unknown = set(r) - set(FIELDS)
            if unknown:
                raise ValueError(f"unknown sizes {s} entr{'y' if len(unknown) == 1 else 'ies'} "
                                 f"{', '.join(sorted(unknown))}")
            calc = calculate_row(s, grid, medium)
            rows[s] = SizeRow(*(_positive(r.get(k, getattr(calc, k)), f"sizes {s} {k}")
                                for k in FIELDS))
        return cls(grid, medium, rows, name.strip())


def _positive(v: Any, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        raise ValueError(f"{what} must be a number above 0, not {v!r}")
    return float(v)


def calculate(grid_mm: float = GRID_MM, medium_mm: float = MEDIUM_MM,
              name: str = "") -> SizeTable:
    """A table calculated from the grid and Medium's height."""
    return SizeTable(float(grid_mm), float(medium_mm),
                     {s: calculate_row(s, grid_mm, medium_mm) for s in SIZES}, name)


def for_grid(grid_mm: float) -> SizeTable:
    """The built-in table on another grid: bases and heights scale with it."""
    return calculate(grid_mm, MEDIUM_MM * grid_mm / GRID_MM)


BUILTIN = calculate(name=BUILTIN_NAME)  # the read-only built-in preset


def apply(settings, size: str, table: SizeTable = BUILTIN):
    """``settings`` with ``size`` and, for a creature size, the values its row fills in
    (a set width is cleared: it follows the height again)."""
    if size == CUSTOM:
        return replace(settings, size=CUSTOM)
    return replace(settings, size=size, width_mm=None, **table.row(size).values())


def matches(settings, table: SizeTable = BUILTIN) -> bool:
    """Whether a figure's values are its size's (always true for custom)."""
    if settings.size == CUSTOM:
        return True
    row = table.row(settings.size).values()
    return settings.width_mm is None and all(
        abs(getattr(settings, k) - v) < 0.005 for k, v in row.items())


def reconcile(old, new, table: SizeTable = BUILTIN):
    """The figure settings after a change from ``old`` to ``new``: a newly picked size
    fills in its values; a filled-in value edited by hand makes the figure custom."""
    if new.size != old.size:
        return apply(new, new.size, table)
    if not matches(new, table):
        return replace(new, size=CUSTOM)
    return new


def label(size: str) -> str:
    return size.capitalize()


def footprint_text(size: str, table: SizeTable) -> str:
    """A size's footprint and base in words, such as "2 × 2 squares · 50 mm base"."""
    if size == CUSTOM:
        return ""
    sq = SQUARES[size]
    squares = "½ × ½ square" if sq < 1 else f"{sq:g} × {sq:g} square{'s' if sq > 1 else ''}"
    return f"{squares} · {table.row(size).base_mm:g} mm base"


def width_warning(size: str, width_mm: float, table: SizeTable) -> str:
    """A warning when a figure is wider than its size's squares, else ""."""
    if size == CUSTOM or not width_mm:
        return ""
    room = table.squares_mm(size)
    if width_mm <= room + 0.05:
        return ""
    sq = SQUARES[size]
    squares = "half a square" if sq < 1 else f"{sq:g} square{'s' if sq > 1 else ''}"
    return (f"This figure is {width_mm:.0f} mm wide, wider than its {squares} "
            f"({round(room, 1):g} mm): set a width or pick a bigger size.")
