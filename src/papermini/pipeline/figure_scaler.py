from __future__ import annotations

import cv2
import numpy as np

from .morphology import Morphology


class FigureScaler:
    """Works out a figure's printed size, and resizes its mask and image to match."""

    def __init__(self, morphology: Morphology):
        self._morph = morphology

    def size(
        self, w_px: int, h_px: int, height_mm: float | None, width_mm: float | None
    ) -> tuple[float, float]:
        """Return (height in mm, horizontal stretch) for a ``w_px`` x ``h_px`` drawing.

        Height only or width only keep the drawing's proportions; both stretch it
        sideways to that width (the height sets the scale).
        """
        if not height_mm and not width_mm:
            raise ValueError("give a figure height, a width or both")
        if not width_mm:
            return float(height_mm), 1.0
        if not height_mm:
            return width_mm * h_px / w_px, 1.0
        return float(height_mm), (width_mm / height_mm) / (w_px / h_px)

    def stretch_x(
        self, clean: np.ndarray, rgb: np.ndarray, f: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return the mask and image ``f`` times as wide (see :meth:`size`)."""
        size = (max(1, round(clean.shape[1] * f)), clean.shape[0])
        interp = cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR
        mask = ((cv2.resize(clean, size, interpolation=interp) > 127) * 255).astype(
            np.uint8
        )
        return mask, cv2.resize(rgb, size, interpolation=interp)

    def limit_resolution(
        self, clean: np.ndarray, rgb: np.ndarray, height_mm: float, max_px_per_mm: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Downscale mask and image so the figure has at most ``max_px_per_mm``.

        A small figure from a big image would otherwise make the padded canvas and
        every morphology step grow with (px per mm)^2.
        """
        _x0, y0, _x1, y1 = self._morph.bbox(clean)
        pxmm = (y1 - y0 + 1) / height_mm
        if pxmm <= max_px_per_mm:
            return clean, rgb
        f = max_px_per_mm / pxmm
        size = (max(1, round(clean.shape[1] * f)), max(1, round(clean.shape[0] * f)))
        small = (
            (cv2.resize(clean, size, interpolation=cv2.INTER_AREA) > 127) * 255
        ).astype(np.uint8)
        if not small.any():
            return clean, rgb
        return small, cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
