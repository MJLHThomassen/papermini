from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QPixmap


@dataclass(frozen=True)
class Panel:
    """One picture of a row of pictures, with the title and caption above it."""

    pixmap: QPixmap
    title: str
    caption: str
