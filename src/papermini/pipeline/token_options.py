from __future__ import annotations

import math
from dataclasses import dataclass

CURVED_TEXT = (
    0.72  # curved text: its height as a share of the narrowest ring that holds it
)


@dataclass(frozen=True)
class TokenOptions:
    """The options a token is made from (see ``FigureSettings`` for each one's meaning)."""

    diameter_mm: float = 25.0
    border_mm: float = 2.0
    border_color: str = "#000000"
    fill: str = "color"
    fill_color: str = "#ffffff"
    outline: bool = False  # an outline around the figure, made like a mini's margin
    margin_mm: float = 1.6
    margin_fill: str = "color"
    margin_color: str = "#ffffff"
    smooth_mm: float = 0.6
    area: tuple[float, float, float, float] | None = None
    text: str = "none"
    text_style: str = "nameplate"
    text_mm: float = 2.5  # the text's size (the nameplate shrinks a long label)
    text_color: str = "#ffffff"

    @property
    def curved(self) -> bool:
        """Text curved along the ring (the ring then has a minimum width)."""
        return self.text != "none" and self.text_style == "curved"

    def ring_mm(self) -> float:
        """The ring's width as printed: never below what curved text needs."""
        return (
            max(self.border_mm, min_ring_mm(self.text_mm))
            if self.curved
            else self.border_mm
        )


def min_ring_mm(text_mm: float) -> float:
    """The narrowest ring that holds curved text of this size (to 0.1 mm, rounded up)."""
    return math.ceil(round(text_mm / CURVED_TEXT * 10, 6)) / 10
