from __future__ import annotations


class ModelError(RuntimeError):
    """The requested segmentation model cannot be used (unknown, missing, not installed)."""
