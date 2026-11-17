from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .figure_settings import FigureSettings


def safe_name(stem: str) -> str:
    return (
        "".join(ch if ch.isalnum() or ch in "-_ ." else "_" for ch in stem).strip()
        or "mini"
    )


@dataclass
class FigureEntry:
    image: Path  # absolute (for a link: the downloaded copy)
    settings: FigureSettings = field(default_factory=FigureSettings)
    name: str | None = None  # output file name (default: label or image name)
    source: str | None = None  # the link the image came from; saved instead of the path

    def svg_name(self) -> str:
        return safe_name(self.name or self.settings.label or self.image.stem) + ".svg"

    @property
    def display_name(self) -> str:
        return self.name or self.settings.label or self.image.stem
