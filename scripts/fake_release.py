from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FakeRelease:
    """A fake, signed release that ``make_release`` made on this computer."""

    env: dict[str, str]  # the environment variables that point papermini at it
    installed: Path | None  # the pretend installed copy it updates, if it made one
    folder: Path  # the folder with the release's files
