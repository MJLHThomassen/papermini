from __future__ import annotations

from .model_error import ModelError


class Cancelled(ModelError):
    """A build was stopped: the window closed, or the user cancelled a model run."""
