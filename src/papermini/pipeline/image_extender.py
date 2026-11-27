from __future__ import annotations

import cv2
import numpy as np

from .morphology import Morphology

BLUR_MM = 1.0  # how far the background's colors spread over the figure
FIGURE_GAP_MM = 0.3  # the figure's edge, kept out of the background too
SPREADS = (1, 4, 16, 64)  # how many times further the colors spread, while missing
ENOUGH_BACKGROUND = 0.05  # the least share of background a blurred color is made of


class ImageExtender:
    """Continues a picture past its edges with its own background, mirrored, so the
    figure itself is never repeated."""

    def __init__(self, morphology: Morphology):
        self._morph = morphology

    def extend(
        self,
        img: np.ndarray,
        fig: np.ndarray,
        inside: tuple[int, int, int, int],
        pxmm: float,
    ) -> np.ndarray:
        """Return the RGB ``img`` with its part outside ``inside`` (x0, y0, x1, y1, the
        part that comes from the picture) filled in.

        The figure ``fig`` (0/255) is first painted over with the colors of the
        background around it, blurred; that background is then mirrored at the
        picture's edges.
        """
        h, w = img.shape[:2]
        x0, y0, x1, y1 = inside
        if (x0, y0, x1, y1) == (0, 0, w, h) or x1 <= x0 or y1 <= y0:
            return img
        core = img[y0:y1, x0:x1]
        figure = self._morph.dilate(fig[y0:y1, x0:x1], FIGURE_GAP_MM * pxmm) > 0
        background = self._background(core, figure, BLUR_MM * pxmm)
        out = cv2.copyMakeBorder(
            background, y0, h - y1, x0, w - x1, cv2.BORDER_REFLECT_101
        )
        out[y0:y1, x0:x1] = core
        return out

    @staticmethod
    def _background(core: np.ndarray, figure: np.ndarray, sigma: float) -> np.ndarray:
        """Return ``core`` with the ``figure`` painted over in the blurred colors of the
        background around it. Where the background is far away, its colors spread
        further (white where there is no background at all)."""
        weight = (~figure).astype(np.float32)
        colors = core.astype(np.float32) * weight[..., None]
        fill = np.full(core.shape, 255.0, np.float32)
        todo = figure.copy()
        for scale in SPREADS:
            if not todo.any():
                break
            spread = cv2.GaussianBlur(colors, (0, 0), sigma * scale)
            total = cv2.GaussianBlur(weight, (0, 0), sigma * scale)
            known = todo & (total > ENOUGH_BACKGROUND)
            fill[known] = spread[known] / total[known][:, None]
            todo &= ~known
        out = core.copy()
        out[figure] = np.clip(fill[figure] + 0.5, 0, 255).astype(np.uint8)
        return out
