from __future__ import annotations


class UpdateError(Exception):
    """An update could not be checked, downloaded or verified (the message says why)."""
