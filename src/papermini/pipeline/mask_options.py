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

    @staticmethod
    def parse_crop(spec, width: int, height: int) -> tuple[int, int, int, int] | None:
        """Parse ``x0,y0,x1,y1`` (fractions 0-1 or pixels) into a pixel box.

        ``spec`` may be a string or a sequence of four numbers. If every value is
        <= 1 the values are fractions of the image size, otherwise pixels.
        """
        if spec is None or spec == "":
            return None
        if isinstance(spec, str):
            vals = [float(v) for v in spec.replace(" ", "").split(",")]
        else:
            vals = [float(v) for v in spec]
        if len(vals) != 4:
            raise ValueError(f"crop needs 4 values x0,y0,x1,y1, got {spec!r}")
        if all(v <= 1.0 for v in vals):
            vals = [
                vals[0] * width,
                vals[1] * height,
                vals[2] * width,
                vals[3] * height,
            ]
        x0, y0, x1, y1 = (round(v) for v in vals)
        x0, x1 = max(0, min(x0, x1)), min(width, max(x0, x1))
        y0, y1 = max(0, min(y0, y1)), min(height, max(y0, y1))
        if x1 - x0 < 8 or y1 - y0 < 8:
            raise ValueError(f"crop {spec!r} is empty for a {width}x{height} image")
        return x0, y0, x1, y1
