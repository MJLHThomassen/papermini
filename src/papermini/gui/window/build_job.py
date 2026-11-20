from __future__ import annotations

import logging
import time
import traceback

from PySide6.QtCore import QRunnable

from ...pipeline.pipeline import Pipeline
from ...pipeline.segmentation.cancelled import Cancelled
from ...pipeline.segmentation.model_error import ModelError
from ...project.settings import build_mini
from ...support import log
from .figure import Figure
from .signals import Signals

logger = logging.getLogger("papermini.build")


class BuildJob(QRunnable):
    """Builds one miniature in the thread pool."""

    def __init__(self, sig: Signals, fig: Figure, is_current, pipeline: Pipeline):
        super().__init__()
        self.pipeline = pipeline
        self.sig, self.uid = sig, fig.uid
        self.image, self.settings, self.key = (
            fig.entry.image,
            fig.entry.settings,
            fig.key(),
        )
        self.bleed_mm = fig.bleed_mm
        self.mask_key = fig.mask_key()
        self.is_current = is_current

    def run(self):
        if not self.is_current(self.uid, self.key):
            return  # settings changed while queued, or the user cancelled it
        self.sig.status.emit(f"Building {self.image.name}…")
        logger.debug("Building %s", self.image.name)
        t0 = time.perf_counter()
        try:
            # Cancel also stops it while the model loads
            with self.pipeline.cancellation.cancellable():
                m = build_mini(
                    self.image,
                    self.settings,
                    pipeline=self.pipeline,
                    bleed_mm=self.bleed_mm,
                    log=lambda *_: None,
                    on_stage=lambda name, data: self.sig.stage.emit(
                        self.uid, self.key, self.mask_key, name, data
                    ),
                )
        except Cancelled:
            self.sig.cancelled.emit(self.uid, self.key)
        except Exception as e:
            expected = (ValueError, FileNotFoundError, ModelError)
            if isinstance(e, expected):
                msg = str(e)
                logger.warning(
                    "Building %s failed: %s (%s)",
                    self.image.name,
                    e,
                    log.settings_text(self.settings.to_dict(with_size=False)),
                )
            else:
                msg = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
                logger.exception(
                    "Building %s failed unexpectedly (%s)",
                    self.image.name,
                    log.settings_text(self.settings.to_dict(with_size=False)),
                )
            self.sig.failed.emit(self.uid, self.key, msg)
        else:
            logger.debug(
                "Built %s in %.1f s", self.image.name, time.perf_counter() - t0
            )
            self.sig.done.emit(self.uid, self.key, m)
