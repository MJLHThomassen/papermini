from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ..support.stage_caches import StageCaches
from .figure_mask import FigureMask
from .image_loader import ImageLoader
from .mask_cleaner import MaskCleaner
from .mask_options import MaskOptions
from .read_only import ReadOnly
from .segmentation.background_remover import BackgroundRemover
from .segmentation.cancellation import Cancellation
from .segmentation.download_hooks import DownloadHooks
from .segmentation.segment import DEFAULT_MODEL


class FigureMasker:
    """Finds the figure in an image: the raw mask from a model, the image's
    transparency or a mask file, then the clean-up. The steps are cached."""

    def __init__(
        self,
        images: ImageLoader,
        remover: BackgroundRemover,
        cleaner: MaskCleaner,
        cancellation: Cancellation,
        caches: StageCaches,
    ):
        self._images = images
        self._remover = remover
        self._cleaner = cleaner
        self._cancellation = cancellation
        self._caches = caches

    def find(
        self,
        image_path: Path,
        mask_options: MaskOptions,
        *,
        use_cache: bool = True,
        debug: bool = False,
        log=print,
        on_stage=None,
        downloads: DownloadHooks | None = None,
    ) -> FigureMask:
        """Find the figure in an image (steps 1 and 2 of a build). ``on_stage`` hears
        ``("segment", model)`` before a model runs and ``("outline", (contours,
        close_px))`` once the figure is found. ``downloads`` asks before a built-in
        model downloads, and hears its progress."""
        image_path = Path(image_path)
        stage = on_stage or (lambda *_: None)
        fkey = StageCaches.file_key(image_path)
        im, data, rgb, transparent = self._caches.images.get_or_make(
            fkey, lambda: self._images.load_pixels(image_path)
        )
        W, H = im.size
        box = MaskOptions.parse_crop(mask_options.crop, W, H)

        # 1. raw mask - cached per image, mask source and crop (the AI model also on
        # disk)
        source, method = self._source(image_path, mask_options, transparent, log)
        raw_key = (fkey, source, box)
        raw = self._caches.raw_masks.get(raw_key) if use_cache else None
        if raw is None:
            raw = self._raw_mask(
                im, data, box, method, mask_options, use_cache, stage, downloads
            )
            raw = self._caches.raw_masks.put(raw_key, ReadOnly.array(raw))

        self._cancellation.check()

        # 2. clean-up
        clean_key = (
            raw_key,
            mask_options.threshold,
            mask_options.close_px,
            mask_options.keep_all,
            mask_options.min_area if mask_options.keep_all else None,
        )
        if debug:
            stages: dict[str, np.ndarray] | None = {"0_raw": raw}
            clean = self._cleaner.clean(raw, mask_options, stages)
        else:
            stages = None
            clean = self._caches.clean_masks.get_or_make(
                clean_key,
                lambda: ReadOnly.array(self._cleaner.clean(raw, mask_options)),
            )

        close_used = self._cleaner.close_px(raw, mask_options)
        contours = self._cleaner.outline(clean)
        stage("outline", (contours, close_used))
        return FigureMask(
            im, rgb, clean, contours, close_used, method, clean_key, stages
        )

    @staticmethod
    def _source(
        image_path: Path, mask_options: MaskOptions, transparent: bool, log
    ) -> tuple[tuple, str]:
        """Return what the raw mask comes from, as part of its cache key, and how it is
        found: "mask" (a mask file), "alpha" (the image's transparency) or the model
        that runs."""
        if mask_options.mask_path is not None:
            source: tuple = ("mask",) + StageCaches.file_key(mask_options.mask_path)
            method = "mask"
        else:
            model = mask_options.model
            if model == "auto":
                model = "alpha" if transparent else DEFAULT_MODEL
                if model == "alpha":
                    log(
                        f"  {image_path.name}: has transparency, using its alpha "
                        "channel as mask"
                    )
            source = ("model", model)
            method = model
            if model.lower().endswith(".onnx") and Path(model).exists():
                source += StageCaches.file_key(model)
        return source, method

    def _raw_mask(
        self,
        im,
        data,
        box,
        method: str,
        mask_options: MaskOptions,
        use_cache,
        stage,
        downloads: DownloadHooks | None,
    ) -> np.ndarray:
        """Make the raw mask: read from the mask file, or from the image's
        transparency or a model."""
        if mask_options.mask_path is not None:
            W, H = im.size
            raw = np.asarray(
                Image.open(mask_options.mask_path)
                .convert("L")
                .resize((W, H), Image.BILINEAR)
            )
            if box:
                x0, y0, x1, y1 = box
                keep = np.zeros_like(raw)
                keep[y0:y1, x0:x1] = raw[y0:y1, x0:x1]
                raw = keep
            return raw
        if method != "alpha":
            stage("segment", method)
        return self._remover.mask(
            im, method, box, use_cache=use_cache, image_bytes=data, downloads=downloads
        )
