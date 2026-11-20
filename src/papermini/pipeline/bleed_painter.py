from __future__ import annotations

import cv2
import numpy as np

from .morphology import Morphology

MAX_BLEED_MM = 5.0  # the widest bleed a figure is printed with


class BleedPainter:
    """Prints a piece's colors beyond its cut line, so a slightly misaligned machine cut
    never shows white paper."""

    def __init__(self, morphology: Morphology):
        self._morph = morphology

    def add(self, rgb: np.ndarray, alpha: np.ndarray, bleed_px: float):
        """Extend the colors at the cut edge outwards by ``bleed_px`` (each new pixel
        takes the color of the nearest pixel inside). Returns (rgb, alpha)."""
        inside = alpha > 127
        if bleed_px <= 0 or not inside.any():
            return rgb, alpha
        # take the colors from just inside the edge: right at the cut line a pixel can
        # still hold a neighbouring color (raster fill vs. the exact vector cut line)
        e = 2
        core = cv2.erode(inside.astype(np.uint8), self._morph.disk(e)) > 0
        if not core.any():
            core, e = inside, 0
        dist, lab = cv2.distanceTransformWithLabels(
            np.where(core, 0, 255).astype(np.uint8),
            cv2.DIST_L2,
            cv2.DIST_MASK_5,
            labelType=cv2.DIST_LABEL_PIXEL,
        )
        ys, xs = np.nonzero(core)  # every core pixel has its own label
        n = int(lab.max()) + 1
        near_y = np.zeros(n, np.int32)
        near_x = np.zeros(n, np.int32)
        near_y[lab[ys, xs]], near_x[lab[ys, xs]] = ys, xs
        ext = rgb[near_y[lab], near_x[lab]]
        # anti-aliased outer edge
        ring = np.clip(bleed_px + e + 0.5 - dist, 0.0, 1.0) * 255.0
        return ext, np.maximum(alpha, ring.astype(np.uint8))
