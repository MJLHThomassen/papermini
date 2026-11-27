from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Font:
    """A font papermini can print with: its name, its regular and bold files, and
    whether it is a sans-serif. Both files are None for a font PDF readers have built
    in: Times, or Helvetica for a sans-serif. Without a bold file, bold uses the regular
    one."""

    name: str
    regular: Path | None = None
    bold: Path | None = None
    bundled: bool = False
    sans: bool = False
