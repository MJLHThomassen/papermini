from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class FigureMask:
    """What background removal found in an image, for a mini or a token: the image, its
    pixels (RGB, or premultiplied RGBA), the clean 0/255 figure mask at the image's size,
    its outline, and how it was found."""

    image: Image.Image
    rgb: np.ndarray
    clean: np.ndarray
    contours: list[np.ndarray]
    close_px: int  # the closing radius used
    method: str  # "alpha", "mask" or the model that ran
    key: tuple  # identifies the clean mask in the caches
    stages: dict[str, np.ndarray] | None = None  # debug: the intermediate masks
