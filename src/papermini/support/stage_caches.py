from __future__ import annotations

from pathlib import Path

from .lru import LRU

MB = 1 << 20


class StageCaches:
    """Small thread-safe in-memory LRU caches for the pipeline stages.

    Stages and what invalidates them:

    * image     - the file (path, size, mtime)
    * raw mask  - image + model (auto/alpha/AI model/mask file) + crop
    * clean     - raw mask + strength, gap filling, keep-all, min-area
    * working   - clean + figure height (bounded working resolution)
    * adjusted  - working + color adjustments (brightness, contrast, saturation, hue,
      greyscale)
    * layout    - working + color adjustments + shape settings (margin, tab, ...)
      -> cut shape and path

    so a geometry-only change (height, margin, tab, label...) or a color adjustment
    never redoes the mask stages, and the AI model never runs twice for the same
    image and crop.
    """

    def __init__(self):
        self.images = LRU(400 * MB)
        self.raw_masks = LRU(200 * MB)
        self.clean_masks = LRU(200 * MB)
        self.working = LRU(300 * MB)
        self.adjusted = LRU(200 * MB)  # the working picture with color adjustments
        self.layouts = LRU(300 * MB)

    @staticmethod
    def file_key(path) -> tuple[str, int, int]:
        """Identity of a file's current contents (path, size, mtime)."""
        p = Path(path).resolve()
        st = p.stat()
        return str(p), st.st_size, st.st_mtime_ns
