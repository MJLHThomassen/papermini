from __future__ import annotations

import cv2
import numpy as np

from .mask_options import MaskOptions
from .morphology import Morphology


class MaskCleaner:
    """Turns a raw greyscale mask into a clean 0/255 figure mask, and traces its
    outline."""

    def __init__(self, morphology: Morphology):
        self._morph = morphology

    def close_px(self, raw: np.ndarray, mask_options: MaskOptions) -> int:
        """Return the closing radius for ``raw``: the option's, or one that scales with
        the image when it is unset."""
        if mask_options.close_px is not None:
            return mask_options.close_px
        h, w = raw.shape
        return self._default_close_px(w, h)

    def clean(
        self,
        raw: np.ndarray,
        mask_options: MaskOptions,
        stages: dict[str, np.ndarray] | None = None,
    ) -> np.ndarray:
        """Threshold, close, fill holes and drop specks. Returns a 0/255 mask."""
        close_px = self.close_px(raw, mask_options)
        p = close_px + 2  # pad so closing/flood fill behave at the image border
        m = np.pad(((raw > mask_options.threshold) * 255).astype(np.uint8), p)
        if stages is not None:
            stages["1_threshold"] = m[p:-p, p:-p]
        if close_px > 0:
            m = self._morph.close(m, close_px)
        if stages is not None:
            stages["2_closed"] = m[p:-p, p:-p]
        m = self._morph.fill_holes(m)
        if stages is not None:
            stages["3_filled"] = m[p:-p, p:-p]
        m = (
            self._morph.filter_components(m, mask_options.min_area)
            if mask_options.keep_all
            else self._morph.largest_component(m)
        )
        m = m[p:-p, p:-p]
        if stages is not None:
            stages["4_clean"] = m
        return m

    def outline(self, clean: np.ndarray) -> list[np.ndarray]:
        """Trace the figure's outline (outer edges and holes) as point arrays, in pixels
        of ``clean``: what background removal found, before any margin."""
        cs, _ = cv2.findContours(clean, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS)
        return [c.reshape(-1, 2).astype(np.float64) + 0.5 for c in cs if len(c) >= 3]

    @staticmethod
    def _default_close_px(width: int, height: int) -> int:
        """Return a closing radius that scales with the image: ~9 px at 1400 px long
        side."""
        return max(1, round(9 * max(width, height) / 1400))
