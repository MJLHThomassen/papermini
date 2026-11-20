from __future__ import annotations

import os
from pathlib import Path


class CacheFolder:
    """The user's cache folder, where models, masks and other downloads are kept."""

    @staticmethod
    def path() -> Path:
        """Return the cache folder (``$PAPERMINI_CACHE`` or ``~/.cache/papermini``),
        made if it is missing."""
        d = Path(
            os.environ.get("PAPERMINI_CACHE", Path.home() / ".cache" / "papermini")
        )
        d.mkdir(parents=True, exist_ok=True)
        return d
