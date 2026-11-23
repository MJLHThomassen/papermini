from __future__ import annotations

from .panel import Panel
from .picture_composer import PictureComposer
from .shot_context import STAT_BLOCK, ShotContext
from .window_driver import WindowDriver


class CropShot:
    """The picture of cropping: a box around the dragon in a stat block, and the
    miniature that leaves out the stat block outside it."""

    def __init__(
        self, ctx: ShotContext, windows: WindowDriver, composer: PictureComposer
    ):
        self._ctx = ctx
        self._windows = windows
        self._composer = composer

    def run(self) -> None:
        """Save the picture of cropping."""
        w = self._windows.open("light")
        self._windows.show(w, STAT_BLOCK, w.SOURCE)
        crop_box = self._composer.view_shot(w.crop_view, w.crop_view.image_rect())
        self._windows.show(w, STAT_BLOCK, w.MINI)
        cropped = self._composer.view_shot(
            w.mini_view, w.mini_view.scene().itemsBoundingRect(), pad=8
        )
        self._windows.close(w)
        self._ctx.save(
            self._composer.panels(
                [
                    Panel(
                        crop_box, "Drag a box around the dragon", "in step 1, Source"
                    ),
                    Panel(cropped, "The miniature", "only what is inside the box"),
                ]
            ),
            "crop",
        )
