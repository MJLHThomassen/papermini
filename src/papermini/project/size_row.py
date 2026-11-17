from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SizeRow:
    """What one size fills in: the figure height, the round base's diameter (also a
    token's diameter) and the stand tab (square tab) width and height, in mm."""

    height_mm: float
    base_mm: float
    tab_width_mm: float
    tab_height_mm: float

    def values(self) -> dict[str, float]:
        """The figure settings this row fills in."""
        return {
            "height_mm": self.height_mm,
            "tab_radius_mm": self.base_mm / 2,
            "tab_width_mm": self.tab_width_mm,
            "tab_height_mm": self.tab_height_mm,
            "token_diameter_mm": self.base_mm,
        }
