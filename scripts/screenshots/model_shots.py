from __future__ import annotations

from functools import partial

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen

from papermini.gui.window.main_window import MainWindow

from .panel import Panel
from .picture_composer import PictureComposer
from .shot_context import DRAGONS, RED, ShotContext
from .window_driver import WindowDriver

MODELS = {  # each model, with the caption under its name
    "rmbg-1.4": "keeps the ground at its feet",
    "birefnet-lite": "leaves background by the right wing",
    "birefnet": "a clean outline",
}
REFERENCE = "birefnet"  # what the others are compared with
HIGHLIGHT = "#0a84ff"
WINDOW_SIZE = (1100, 760)  # logical pixels
RING_PX = 14  # how far the ring stays outside what it circles
MIN_AREA = 0.002  # the least part of the image a leftover covers to be circled


class ModelShots:
    """The background removal models side by side on the red dragon. What a model kept
    that the reference model removed is circled."""

    def __init__(
        self, ctx: ShotContext, windows: WindowDriver, composer: PictureComposer
    ):
        self._ctx = ctx
        self._windows = windows
        self._composer = composer

    def run(self) -> None:
        """Save the picture of the models."""
        path = DRAGONS / "dragon.webp"
        im = Image.open(path)
        im.load()
        data = path.read_bytes()
        remover = self._ctx.pipeline.remover
        masks = {m: remover.mask(im, m, image_bytes=data) for m in MODELS}
        w = self._windows.open("light", WINDOW_SIZE)
        w.crop_view.set_hint_enabled(False)  # no hint in a comparison
        self._windows.show(w, RED, MainWindow.SOURCE)
        items = []
        for model, caption in MODELS.items():
            self._windows.change(w, model=model)
            circle = (
                None
                if model == REFERENCE
                else self._circle(w, self._leftovers(masks[model], masks[REFERENCE]))
            )
            items.append(
                Panel(
                    self._composer.view_shot(
                        w.crop_view,
                        w.crop_view.image_rect(),
                        paint=partial(self._ring, circle=circle),
                    ),
                    model,
                    caption,
                )
            )
        self._windows.close(w)
        self._ctx.save(self._composer.panels(items), "models")

    @staticmethod
    def _leftovers(mask: np.ndarray, ref: np.ndarray) -> np.ndarray:
        """Find the larger areas that ``mask`` keeps and the reference mask ``ref``
        removes."""
        extra = ((mask > 128) & (ref < 64)).astype(np.uint8)
        extra = cv2.morphologyEx(extra, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(extra)
        keep = [
            i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > MIN_AREA * extra.size
        ]
        return np.isin(labels, keep)

    @staticmethod
    def _circle(w: MainWindow, extra: np.ndarray) -> QRectF | None:
        """Return the ring around the pixels of ``extra`` in the crop view, or None
        when there are none."""
        if not extra.any():
            return None
        ys, xs = np.nonzero(extra)
        box = QRectF(QPointF(xs.min(), ys.min()), QPointF(xs.max(), ys.max()))
        circle = QRectF(w.crop_view.mapFromScene(box).boundingRect())
        circle.adjust(-RING_PX, -RING_PX, RING_PX, RING_PX)
        return circle

    @staticmethod
    def _ring(p: QPainter, circle: QRectF | None) -> None:
        if circle is not None:
            p.setPen(QPen(QColor(HIGHLIGHT), 3))
            p.drawEllipse(circle)
