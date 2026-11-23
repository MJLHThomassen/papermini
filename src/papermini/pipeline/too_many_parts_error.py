from __future__ import annotations


class TooManyPartsError(ValueError):
    """The figure has too many separate parts to join into one piece."""
