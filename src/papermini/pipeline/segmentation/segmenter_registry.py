from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from ...support.cache_folder import CacheFolder
from . import segment
from .cancellation import Cancellation
from .download_hooks import DownloadHooks
from .downloader import Downloader
from .model_error import ModelError
from .onnx_segmenter import OnnxSegmenter

logger = logging.getLogger("papermini.segment")


class SegmenterRegistry:
    """Keeps the segmentation models: the built-in models' files, downloaded on demand,
    and one loaded segmenter per model.

    ``make_segmenter`` makes a segmenter from a model file, as ``OnnxSegmenter`` does.
    """

    def __init__(
        self,
        downloader: Downloader,
        cancellation: Cancellation,
        make_segmenter=OnnxSegmenter,
    ):
        self._downloader = downloader
        self._cancellation = cancellation
        self._make_segmenter = make_segmenter
        self._model_locks = {name: threading.Lock() for name in segment.ONNX_MODELS}
        self._segmenters: dict = {}
        self._segmenters_lock = threading.Lock()

    # region the built-in models

    @staticmethod
    def path(model: str) -> Path:
        """Return where the built-in ``model`` is (or will be) stored."""
        return CacheFolder.path() / segment.ONNX_MODELS[model]["file"]

    @staticmethod
    def non_commercial(model: str) -> bool:
        """Tell whether the built-in ``model`` may only be used non-commercially."""
        return not segment.ONNX_MODELS.get(model, {}).get("commercial", True)

    @staticmethod
    def licence_notice(model: str) -> str:
        """Explain in words what a user of a non-commercial built-in ``model`` is
        responsible for."""
        title = segment.ONNX_MODELS[model]["title"]
        free = " or ".join(
            s["title"] for s in segment.ONNX_MODELS.values() if s.get("commercial")
        )
        return (
            f"{title} is licensed for non-commercial use only. You are responsible for "
            f"not using it commercially, for example to make minis you sell. For "
            f"commercial use, pick {free} (MIT licence)."
        )

    def fetch(
        self,
        model: str,
        force: bool = False,
        progress=None,
        cancel: threading.Event | None = None,
    ) -> Path:
        """Download the built-in ``model`` unless it is already there (always with
        ``force``, e.g. to replace a damaged file). One download per model at a time."""
        with self._model_locks[model]:
            path = self.path(model)
            existed = path.exists()
            if force or not existed:
                logger.info("Downloading the %s model", model)
                self._downloader.download(
                    segment.ONNX_MODELS[model]["url"],
                    path,
                    progress=progress,
                    cancel=cancel,
                )
                logger.info("Downloaded the %s model", model)
                # (a missing file has no loaded session; and the build thread may hold
                # the segmenter lock while it asks)
                if existed:
                    self._forget(model)
            return path

    def delete(self, model: str) -> None:
        """Remove the downloaded file of the built-in ``model``."""
        with self._model_locks[model]:
            self._forget(model)
            self.path(model).unlink(missing_ok=True)

    # endregion

    # region loaded segmenters

    def is_loaded(self, model: str) -> bool:
        """Tell whether ``model`` is loaded (its next run starts at once)."""
        return model in self._segmenters

    def get(self, model: str, downloads: DownloadHooks | None = None):
        """Return the segmenter of ``model``, created (and downloaded) only once,
        thread-safely. ``downloads`` asks before a built-in model downloads, and hears
        its progress."""
        with self._segmenters_lock:
            if model not in self._segmenters:
                self._segmenters[model] = self._load(
                    model, downloads or DownloadHooks()
                )
            return self._segmenters[model]

    def _forget(self, model: str) -> None:
        with self._segmenters_lock:
            self._segmenters.pop(model, None)

    def _load(self, model: str, downloads: DownloadHooks):
        """Make the segmenter of ``model``: a built-in model, downloaded first if it is
        missing, or a .onnx file."""
        if model in segment.ONNX_MODELS:
            spec = segment.ONNX_MODELS[model]
            path = self.path(model)
            if not path.exists():
                confirm = downloads.confirm
                if confirm is not None and not confirm(model):
                    raise ModelError(
                        f"the {model} model is not downloaded. Download it in "
                        "Preferences… > Models and cache in the menu, or pick "
                        "another model."
                    )
                stderr = sys.stderr
                if (
                    confirm is None
                    and self.non_commercial(model)
                    and stderr is not None
                ):
                    # (the command line)
                    print(f"Note: {self.licence_notice(model)}", file=sys.stderr)
                self.fetch(model, progress=downloads.progress)
            logger.info("Loading the %s model", model)
            return self._make_segmenter(
                path,
                spec["size"],
                spec["mean"],
                spec["std"],
                spec["post"],
                cancellation=self._cancellation,
            )
        if model.lower().endswith(".onnx"):
            path = Path(model).expanduser()
            if not path.exists():
                raise ModelError(f"model file not found: {path}")
            logger.info("Loading the model %s", path)
            return self._make_segmenter(path, cancellation=self._cancellation)
        known = ", ".join(list(segment.ONNX_MODELS) + ["alpha", "<file>.onnx"])
        raise ModelError(f"unknown model {model!r} (known: {known})")

    # endregion
