from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class RenderedToken:
    """A token's pixels and where its parts are on them. Lengths are in mm unless the
    name says px."""

    rgba: np.ndarray  # n x n RGBA, at the token's working resolution
    side_px: int  # n
    ring_mm: float  # the ring's width as printed
    inner_mm: float  # the radius inside the ring
    text_mm: float  # the text's height (nameplate: at most)
    plate: tuple[float, float, float, float] | None  # the label's box (cx, cy, w, h)
    badge: tuple[float, float, float] | None  # the number badge (cx, cy, r)
    area: tuple[float, float, float, float]  # the framing, as a token area (fractions)
    figure_box: tuple[float, float, float, float]  # the figure's box on the piece
    # the framing: the picture's point at the centre (image px) and the scale in token
    # px per image px
    frame: tuple[float, float, float]
