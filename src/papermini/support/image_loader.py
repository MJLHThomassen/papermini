from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .read_only import ReadOnly


class ImageLoader:
    """Loads image files for the pipeline."""

    def load(self, path: Path) -> tuple[Image.Image, bytes]:
        """Return the image in ``path``, turned upright, and the file's bytes."""
        data = Path(path).read_bytes()
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)
        return im, data

    def load_pixels(self, path: Path):
        """Return (PIL image, file bytes, pixels, has transparency) of an image file.

        Pixels are RGB, or for images with transparency premultiplied RGBA: never
        flattened onto white, so a cut-out's soft edge blends into the margin color
        instead of leaving a white fringe (and scales without bleeding).
        """
        im, data = self.load(path)
        im.load()
        transparent = self.has_alpha(im)
        if transparent:
            a = np.asarray(im.convert("RGBA")).astype(np.float32)
            a[..., :3] *= a[..., 3:4] / 255.0
            px = np.clip(a + 0.5, 0, 255).astype(np.uint8)
        else:
            px = np.asarray(im.convert("RGB"))
        return im, data, ReadOnly.array(px), transparent

    def has_alpha(self, im: Image.Image) -> bool:
        """Tell whether ``im`` has a transparent pixel."""
        if im.mode not in ("RGBA", "LA", "PA") and not (
            im.mode == "P" and "transparency" in im.info
        ):
            return False
        return bool(np.asarray(im.convert("RGBA").getchannel("A")).min() < 255)
