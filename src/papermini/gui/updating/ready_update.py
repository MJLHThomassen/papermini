from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReadyUpdate:
    """A downloaded and verified update, which is installed when papermini closes."""

    version: str
    app: Path  # the unpacked app, or the installer
    page: str  # the release page, or empty when not known
