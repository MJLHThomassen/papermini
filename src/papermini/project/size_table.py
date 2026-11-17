from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .size_row import SizeRow

GRID_MM = 25.4  # a 1-inch grid
MEDIUM_MM = 32.0  # a "heroic" scale human
FIELDS = ("height_mm", "base_mm", "tab_width_mm", "tab_height_mm")


@dataclass(frozen=True)
class SizeTable:
    """The grid, Medium's height (what the table was calculated from), each size's row, and
    the name of the preset the table is or came from ("" for none)."""

    grid_mm: float = GRID_MM
    medium_mm: float = MEDIUM_MM
    rows: dict[str, SizeRow] = field(default_factory=dict)
    name: str = ""

    def __post_init__(self):
        from .sizes import SIZES, calculate_row

        missing = {
            s: calculate_row(s, self.grid_mm, self.medium_mm)
            for s in SIZES
            if s not in self.rows
        }
        if missing:
            object.__setattr__(
                self, "rows", {s: self.rows.get(s) or missing[s] for s in SIZES}
            )

    def row(self, size: str) -> SizeRow:
        return self.rows[size]

    def squares_mm(self, size: str) -> float:
        """The width of a size's squares on the grid."""
        from .sizes import SQUARES

        return SQUARES[size] * self.grid_mm

    def calculated(self) -> bool:
        """Whether every row is what the grid and Medium's height give."""
        from .sizes import SIZES, calculate_row

        return all(
            self.rows[s] == calculate_row(s, self.grid_mm, self.medium_mm)
            for s in SIZES
        )

    def same_values(self, other: SizeTable) -> bool:
        """Whether ``other`` has the same grid, Medium height and rows (names aside)."""
        return replace(self, name="") == replace(other, name="")

    def to_dict(self) -> dict[str, Any]:
        """The table as a project stores it."""
        from .sizes import SIZES

        return {
            **({"preset": self.name} if self.name else {}),
            "grid_mm": self.grid_mm,
            "medium_mm": self.medium_mm,
            **{s: {k: getattr(self.rows[s], k) for k in FIELDS} for s in SIZES},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> SizeTable:
        """A table from a project (``None``: the built-in one). Sizes left out are
        calculated from the grid and Medium's height."""
        from .sizes import BUILTIN, SIZES, calculate_row

        if not d:
            return BUILTIN
        if not isinstance(d, dict):
            raise ValueError(
                "sizes must be a table of preset, grid_mm, medium_mm and the sizes"
            )
        d = {str(k).replace("-", "_"): v for k, v in d.items()}
        unknown = set(d) - set(SIZES) - {"preset", "grid_mm", "medium_mm"}
        if unknown:
            raise ValueError(
                f"unknown sizes entr{'y' if len(unknown) == 1 else 'ies'} "
                f"{', '.join(sorted(unknown))}"
            )
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
                raise ValueError(
                    f"unknown sizes {s} entr{'y' if len(unknown) == 1 else 'ies'} "
                    f"{', '.join(sorted(unknown))}"
                )
            calc = calculate_row(s, grid, medium)
            rows[s] = SizeRow(
                *(
                    _positive(r.get(k, getattr(calc, k)), f"sizes {s} {k}")
                    for k in FIELDS
                )
            )
        return cls(grid, medium, rows, name.strip())


def _positive(v: Any, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        raise ValueError(f"{what} must be a number above 0, not {v!r}")
    return float(v)
