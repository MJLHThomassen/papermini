from __future__ import annotations

import numpy as np
from PIL import Image

from ...support.image_loader import ImageLoader
from .cancellation import Cancellation
from .download_hooks import DownloadHooks
from .mask_store import MaskStore
from .model_error import ModelError
from .segment import DEFAULT_MODEL, Box
from .segmenter_registry import SegmenterRegistry


class BackgroundRemover:
    """Turns an image into a greyscale foreground mask (0-255), with a model or the
    image's own transparency."""

    def __init__(
        self,
        images: ImageLoader,
        segmenters: SegmenterRegistry,
        masks: MaskStore,
        cancellation: Cancellation,
    ):
        self._images = images
        self._segmenters = segmenters
        self._masks = masks
        self._cancellation = cancellation

    def mask(
        self,
        im: Image.Image,
        model: str = DEFAULT_MODEL,
        crop: Box | None = None,
        use_cache: bool = True,
        image_bytes: bytes | None = None,
        downloads: DownloadHooks | None = None,
    ) -> np.ndarray:
        """Return a full-size greyscale mask (uint8 0-255) for ``im``.

        With ``crop`` the model only sees that region and the result is pasted into
        an otherwise empty mask - this is what makes busy backgrounds work.
        Results are kept on disk by image content, model and crop. ``downloads``
        asks before a built-in model downloads, and hears its progress.
        """
        W, H = im.size
        if model == "alpha":
            return self._alpha_mask(im, crop)

        cache_file = None
        if use_cache and image_bytes is not None:
            cache_file = self._masks.file(image_bytes, model, crop)
            cached = self._masks.read(cache_file, (H, W))
            if cached is not None:
                return cached

        self._cancellation.check()
        # loading cannot be interrupted: stop right after
        seg = self._segmenters.get(model, downloads)
        self._cancellation.check()
        rgb = im.convert("RGB")
        if self._images.has_alpha(im):
            # the model sees a cut-out on white, not its hidden pixel colors
            rgb = Image.alpha_composite(
                Image.new("RGBA", im.size, (255, 255, 255, 255)), im.convert("RGBA")
            ).convert("RGB")
        if crop:
            x0, y0, x1, y1 = crop
            full = np.zeros((H, W), np.uint8)
            full[y0:y1, x0:x1] = seg(rgb.crop(crop))
        else:
            full = seg(rgb)

        if cache_file is not None:
            self._masks.write(cache_file, full)
        return full

    def _alpha_mask(self, im: Image.Image, crop: Box | None) -> np.ndarray:
        """Return the image's own transparency as the mask, cropped to ``crop``."""
        if not self._images.has_alpha(im):
            raise ModelError(
                "model 'alpha' needs an image with transparency; "
                "this one has none - pick another model"
            )
        full = np.asarray(im.convert("RGBA").getchannel("A")).copy()
        if crop:
            keep = np.zeros_like(full)
            x0, y0, x1, y1 = crop
            keep[y0:y1, x0:x1] = full[y0:y1, x0:x1]
            full = keep
        return full
