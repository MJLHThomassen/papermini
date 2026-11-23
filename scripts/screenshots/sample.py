from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF

from papermini.pipeline.mini import Mini


@dataclass(frozen=True)
class Sample:
    """One miniature of a comparison, with the title and caption above it. ``rect``
    is the part of it shown, in mm; None shows all of it."""

    mini: Mini
    title: str
    caption: str
    rect: QRectF | None = None
