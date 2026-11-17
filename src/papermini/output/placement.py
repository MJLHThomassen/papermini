from __future__ import annotations

from dataclasses import dataclass

from ..pipeline.mini import Mini


@dataclass
class Placement:
    mini: Mini
    page: int
    x: float  # mm, top-left of the piece
    y: float
