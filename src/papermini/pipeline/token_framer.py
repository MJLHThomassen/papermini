from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

# a fitted figure leaves this share of the inner diameter free on each side
FIT_FREE = 0.08

# working resolution of a token (about 400 dpi; the art is resized to dpi)
PX_PER_MM = 16.0


class TokenFramer:
    """Frames the picture in a token's circle: fitted around the figure, or as the
    square of the picture that fills the circle (its area). A framing is the picture's
    point at the circle's centre and a scale in token pixels per image pixel."""

    def fit(
        self, contours: Sequence[np.ndarray], inner_mm: float, outline_mm: float = 0.0
    ) -> tuple[float, float, float]:
        """Return the fitted framing: (cx, cy) in image pixels and the scale, so the
        whole figure (with its outline) sits in the circle with ``FIT_FREE`` of the
        inner diameter free on each side."""
        pts = [c for c in contours if len(c)]
        if not pts:
            raise ValueError(
                "background removal found no figure in this image: try a lower "
                "strength, a crop or another model"
            )
        (x, y), r = cv2.minEnclosingCircle(np.vstack(pts).astype(np.float32))
        room = max(0.3 * inner_mm, inner_mm * (1 - 2 * FIT_FREE) - outline_mm)
        return float(x), float(y), room * PX_PER_MM / max(float(r), 1.0)

    def from_area(
        self, area: Sequence[float], size: tuple[int, int], inner_mm: float
    ) -> tuple[float, float, float]:
        """Return the framing of a token ``area`` (fractions of a ``size`` = (w, h)
        picture): its centre and the scale that makes it fill the circle inside the
        ring."""
        W, H = size
        x0, y0, x1, y1 = area
        side = max((x1 - x0) * W, (y1 - y0) * H, 1.0)
        return (x0 + x1) / 2 * W, (y0 + y1) / 2 * H, 2 * inner_mm * PX_PER_MM / side

    def to_area(
        self, cx: float, cy: float, f: float, size: tuple[int, int], inner_mm: float
    ) -> tuple[float, float, float, float]:
        """Return the token area (fractions) of a framing: the square around (cx, cy)
        that fills the circle at scale ``f``."""
        W, H = size
        half = inner_mm * PX_PER_MM / f
        return (
            round((cx - half) / W, 4),
            round((cy - half) / H, 4),
            round((cx + half) / W, 4),
            round((cy + half) / H, 4),
        )
