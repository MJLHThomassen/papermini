from __future__ import annotations

import cv2
import numpy as np

from .morphology import Morphology


class ArtComposer:
    """Paints a figure's artwork onto the color of its margin."""

    def __init__(self, morphology: Morphology):
        self._morph = morphology

    def compose(
        self,
        img: np.ndarray,
        fig: np.ndarray,
        sil: np.ndarray,
        paper: tuple[int, int, int],
        pxmm: float,
        image_margin: bool,
    ) -> np.ndarray:
        """Return the artwork on the margin color ``paper``.

        ``img`` is RGB, or premultiplied RGBA for images with transparency (used as
        real transparency, never flattened onto white).

        The inside of the drawing keeps its own colors (a white ghost stays white).
        Around its edge - a thin rim inside the outline and a 0.25 mm band beyond it,
        kept so stray pencil strokes are not clipped - the picture is printed like ink
        on the margin color: the source's white paper becomes the margin color and
        dark strokes stay dark. On a white margin this is exactly the plain picture;
        on a dark one it removes the white halo around the figure.
        """
        P = np.array(paper, np.float32)
        S = img[..., :3].astype(np.float32)  # (premultiplied) color
        a = img[..., 3:4].astype(np.float32) / 255.0 if img.shape[2] == 4 else 1.0
        if image_margin:
            w = (sil > 0).astype(np.float32)[..., None]
            art = w * S + (1.0 - w) * a * P
        else:
            sigma = max(0.5, 0.12 * pxmm)
            soft = lambda m: cv2.GaussianBlur(
                m.astype(np.float32) / 255.0, (0, 0), sigma
            )[..., None]
            core = soft(self._morph.erode(fig, 0.2 * pxmm))  # the drawing itself
            band = np.maximum(
                soft(self._morph.dilate(fig, 0.25 * pxmm)), fig[..., None] / 255.0
            )
            ink = S * (P / 255.0)  # printed on the margin
            # inside the drawing, transparency shows as it does on white paper (a
            # translucent ghost stays light); at the edge and beyond, it lets the margin
            # color through
            inside = S + (1.0 - a) * 255.0
            edge = band * ink + (1.0 - band) * a * P + (1.0 - a) * P
            art = core * inside + (1.0 - core) * edge
            return np.clip(art + 0.5, 0, 255).astype(np.uint8)
        art = art + (1.0 - a) * P  # transparent -> margin
        return np.clip(art + 0.5, 0, 255).astype(np.uint8)
