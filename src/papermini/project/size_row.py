from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SizeRow:
    """The values one size fills in: the figure height, the round base's diameter (also a
    token's diameter) and the stand tab (square tab) width and height, in mm."""

    height_mm: float
    base_mm: float
    tab_width_mm: float
    tab_height_mm: float

    @classmethod
    def calculated(cls, size: str, grid_mm: float, medium_mm: float) -> SizeRow:
        """A size's row calculated from the grid and Medium's height: the height scales
        from Medium, the base covers its squares (a little under the grid) and the stand
        tab is as wide as the base and half as deep."""
        from .sizes import BASE_FIT, HEIGHT_RATIO, SQUARES

        base = cls._mm(SQUARES[size] * grid_mm * BASE_FIT)
        return cls(
            cls._mm(medium_mm * HEIGHT_RATIO[size]), base, base, cls._mm(base / 2)
        )

    @staticmethod
    def _mm(v: float) -> float:
        return round(float(v), 2)

    def values(self) -> dict[str, float]:
        """The figure settings this row fills in."""
        return {
            "height_mm": self.height_mm,
            "tab_radius_mm": self.base_mm / 2,
            "tab_width_mm": self.tab_width_mm,
            "tab_height_mm": self.tab_height_mm,
            "token_diameter_mm": self.base_mm,
        }
