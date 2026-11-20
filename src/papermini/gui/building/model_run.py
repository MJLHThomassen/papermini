from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRun:
    """A model run in progress: the figure ``uid`` it removes the background for, that
    figure's ``mask_key()`` when the build started, the ``model``, and when the run
    started (``time.monotonic``)."""

    uid: int
    mask_key: str
    model: str
    started: float

    def seconds(self) -> float:
        """Return how long the model has been running."""
        return time.monotonic() - self.started
