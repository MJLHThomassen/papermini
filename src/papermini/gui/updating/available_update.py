from __future__ import annotations

from dataclasses import dataclass

from ...support.release import Release


@dataclass(frozen=True)
class AvailableUpdate:
    """A newer release, and why this copy cannot install it, if it cannot."""

    release: Release
    why: str | None
