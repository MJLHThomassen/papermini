from __future__ import annotations

from dataclasses import dataclass

TAB_SHOWS = ("label", "number", "label_number", "none")  # what a tab shows
LABEL_SHOWS = ("label", "label_number")  # what a tab shows with its label
NUMBER_SHOWS = ("number", "label_number")  # what a tab shows with its copy number


@dataclass(frozen=True)
class TabLabel:
    """What one tab of a standing mini prints: its label, its copy number or both, the
    label's text and largest size, and the color of both."""

    shows: str = "label"  # one of TAB_SHOWS
    text: str | None = None  # None: the file name
    size_mm: float = 3.4
    color: str = "#000000"
