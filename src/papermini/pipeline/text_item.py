from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TextItem:
    """One piece of text on a miniature, as every output draws it: centred on (cx, cy) mm,
    rotated ``rot`` degrees, ``size_mm`` high. ``kind``: "label", "number" or "backtext"."""

    kind: str
    text: str
    cx: float
    cy: float
    rot: float
    size_mm: float
    color: str
    bold: bool = False
