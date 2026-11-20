from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadProgress:
    """How much of an update is downloaded, in bytes."""

    done: int
    total: int  # 0 when the size is not known
