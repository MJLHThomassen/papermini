from __future__ import annotations

from dataclasses import dataclass

FOLD_DASH_MM = 1.2  # a fold line is dashed: drawn this long...
FOLD_GAP_MM = 0.8  # ...then left out this long


@dataclass
class Style:
    cut_color: str = "#000000"
    cut_width_mm: float = 0.3
    fold_color: str = "#666666"
    fold_width_mm: float = 0.25
    label_color: str = "#2f5597"
    back_text_color: str = "#2f5597"
    label_size_mm: float = 3.4
    font: str = "Times"  # all of the piece's text (see FontLibrary)
    cut_line: bool = True  # print the cut line (a token's ring edge can do instead)
