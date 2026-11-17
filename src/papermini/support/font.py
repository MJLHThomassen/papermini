from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Font:
    """A font papermini can print with: its name and its regular and bold files (both
    None for Times, which PDF readers have built in; no bold file: bold uses regular)."""

    name: str
    regular: Path | None = None
    bold: Path | None = None
    bundled: bool = False
