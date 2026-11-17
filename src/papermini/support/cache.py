"""Small thread-safe in-memory LRU caches for the pipeline stages.

Stages and what invalidates them:

* image     - the file (path, size, mtime)
* raw mask  - image + model (auto/alpha/AI model/mask file) + crop
* clean     - raw mask + strength, gap filling, keep-all, min-area
* working   - clean + figure height (bounded working resolution)
* layout    - working + shape settings (margin, tab, ...) -> cut shape and path

so a geometry-only change (height, margin, tab, label...) never redoes the
mask stages, and the AI model never runs twice for the same image and crop.
"""

from __future__ import annotations

from pathlib import Path

from .lru import LRU

MB = 1 << 20


images = LRU(400 * MB)


raw_masks = LRU(200 * MB)


clean_masks = LRU(200 * MB)


working = LRU(300 * MB)


adjusted = LRU(200 * MB)  # the working picture with color adjustments


layouts = LRU(300 * MB)


def file_key(path) -> tuple[str, int, int]:
    """Identity of a file's current contents (path, size, mtime)."""
    p = Path(path).resolve()
    st = p.stat()
    return str(p), st.st_size, st.st_mtime_ns


def clear_all() -> None:
    for c in (images, raw_masks, clean_masks, working, adjusted, layouts):
        c.clear()
