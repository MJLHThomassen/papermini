from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenInfo:
    """Where a token's parts are on its piece (mm, origin top-left), for its text and for
    framing it in the app."""

    cx: float
    cy: float
    radius_mm: float  # the cut line
    inner_mm: float  # inside the ring
    text: str = "none"
    text_style: str = "nameplate"
    color: str = "#ffffff"  # the text's color
    size_mm: float = 0.0  # the text's height (nameplate: at most)
    plate: tuple[float, float, float, float] | None = (
        None  # the label's box (cx, cy, w, h)
    )
    badge: tuple[float, float, float] | None = None  # the number badge (cx, cy, r)
    # the square of the picture that fills the circle, as fractions of the image (what
    # token_area holds), and the figure's box on the piece (mm)
    area: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    figure_box: tuple[float, float, float, float] | None = None
