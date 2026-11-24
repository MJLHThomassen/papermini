from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .cut_path import CutPath
from .layout import Layout
from .morphology import Morphology


class DebugWriter:
    """Saves a build's intermediate masks and a preview of what is cut away, for
    debugging."""

    def __init__(self, morphology: Morphology):
        self._morph = morphology

    def write(
        self, out: Path, stem: str, stages, lay: Layout, path_px: CutPath
    ) -> None:
        """Save the intermediate masks plus a red-overlay preview (what gets cut away is
        red)."""
        out.mkdir(parents=True, exist_ok=True)
        for name, m in (stages or {}).items():
            cv2.imwrite(str(out / f"{stem}_{name}.png"), m)
        cv2.imwrite(str(out / f"{stem}_5_cut.png"), lay.cut)
        over = self.overlay(lay, path_px)
        cv2.imwrite(
            str(out / f"{stem}_overlay.png"), cv2.cvtColor(over, cv2.COLOR_RGB2BGR)
        )

    def overlay(self, lay: Layout, path_px: CutPath) -> np.ndarray:
        """Return an RGB preview: red = cut away, light blue = the margin around the
        figure, black = cut line, green = fold lines."""
        rgb = lay.rgb
        outside = (lay.cut == 0)[..., None]
        margin = ((lay.cut > 0) & (lay.figure == 0))[..., None]
        red = cv2.addWeighted(rgb, 0.45, np.full_like(rgb, (255, 60, 60)), 0.55, 0)
        blue = cv2.addWeighted(rgb, 0.8, np.full_like(rgb, (120, 200, 255)), 0.2, 0)
        over = np.where(outside, red, np.where(margin, blue, rgb))
        pts = np.round(path_px.flatten() - 0.5).astype(np.int32)
        t = max(1, round(0.3 * lay.px_per_mm))
        cv2.polylines(over, [pts], True, (0, 0, 0), t, cv2.LINE_AA)
        for x0, x1, y in lay.folds:
            cv2.line(
                over,
                (int(x0), int(y)),
                (int(x1), int(y)),
                (60, 160, 60),
                t,
                cv2.LINE_AA,
            )
        x0, y0, x1, y1 = self._morph.bbox(lay.cut)
        b = int(5 * lay.px_per_mm)
        return np.ascontiguousarray(
            over[max(0, y0 - b) : y1 + b, max(0, x0 - b) : x1 + b]
        )
