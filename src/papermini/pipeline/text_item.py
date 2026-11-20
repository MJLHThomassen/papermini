from __future__ import annotations

from dataclasses import dataclass

NUMBER_PLACEHOLDER = (
    "#"  # a figure's number where no copy number is known (the preview)
)
TEXT_BASELINE_DROP = 0.35  # the baseline lies this share of the size below the centre


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
