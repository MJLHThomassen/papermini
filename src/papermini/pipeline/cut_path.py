from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class CutPath:
    """Closed path: ``points`` (N x 2) and optional cubic ``controls`` (N x 2 x 2).

    Segment i runs from points[i] to points[(i+1) % N], with control points
    controls[i, 0] and controls[i, 1] when ``controls`` is set, else straight.
    """

    points: np.ndarray
    controls: np.ndarray | None = None

    def transformed(self, scale: float, dx: float = 0.0, dy: float = 0.0) -> CutPath:
        f = lambda a: (a - np.array([dx, dy])) * scale
        return CutPath(
            f(self.points), None if self.controls is None else f(self.controls)
        )

    def flatten(self, steps: int = 12) -> np.ndarray:
        """Polyline approximation (closed, last point not repeated)."""
        if self.controls is None:
            return self.points.copy()
        p0 = self.points
        p3 = np.roll(self.points, -1, axis=0)
        c1, c2 = self.controls[:, 0], self.controls[:, 1]
        t = np.linspace(0, 1, steps, endpoint=False)[None, :, None]
        mt = 1 - t
        pts = (
            mt**3 * p0[:, None]
            + 3 * mt**2 * t * c1[:, None]
            + 3 * mt * t**2 * c2[:, None]
            + t**3 * p3[:, None]
        )
        return pts.reshape(-1, 2)

    def extent(self) -> tuple[float, float, float, float]:
        a = self.flatten()
        return (
            float(a[:, 0].min()),
            float(a[:, 1].min()),
            float(a[:, 0].max()),
            float(a[:, 1].max()),
        )
