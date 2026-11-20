from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MaskOptions:
    """The options background removal finds a figure with (see ``FigureSettings``
    for each one's meaning)."""

    model: str  # a model name, "alpha", "auto" or the path of a .onnx file
    mask_path: Path | None  # a mask image file, used instead of the model
    crop: Any  # the region the model looks at (see ``parse_crop``), or None
    threshold: int  # the raw mask's cut-off, 0-254
    close_px: int | None  # the closing radius; None scales it with the image
    keep_all: bool  # keep detached parts, not only the largest
    min_area: int  # with keep_all: the smallest part kept, in px
