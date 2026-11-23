from __future__ import annotations

from .model_error import ModelError


class ModelNotDownloadedError(ModelError):
    """A built-in model is not downloaded, and the user chose not to download it."""
