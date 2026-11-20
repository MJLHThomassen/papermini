from __future__ import annotations

from enum import Enum


class UpdateState(Enum):
    """A step of checking for, downloading or installing an update. Each state comes
    with the payload named beside it."""

    CHECKING = "checking"  # None
    LATEST = "latest"  # the latest Release, which is not newer
    AVAILABLE = "available"  # an AvailableUpdate
    DOWNLOADING = "downloading"  # the Release being downloaded
    PROGRESS = "progress"  # a DownloadProgress
    VERIFYING = "verifying"  # the Release being downloaded
    UNPACKING = "unpacking"  # the Release being downloaded
    READY = "ready"  # a ReadyUpdate
    ERROR = "error"  # the message, a str

    @property
    def busy(self) -> bool:
        """Return whether a download is under way in this state."""
        return self in (
            UpdateState.DOWNLOADING,
            UpdateState.PROGRESS,
            UpdateState.VERIFYING,
            UpdateState.UNPACKING,
        )
