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

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Hashable, Tuple

import numpy as np


def _nbytes(v: Any) -> int:
    if isinstance(v, np.ndarray):
        return v.nbytes
    if isinstance(v, (tuple, list)):
        return sum(_nbytes(x) for x in v)
    if hasattr(v, "__dataclass_fields__"):  # e.g. geometry.Layout
        return sum(_nbytes(getattr(v, f)) for f in v.__dataclass_fields__)
    if isinstance(v, (bytes, bytearray)):
        return len(v)
    size = getattr(v, "size", None)  # PIL image
    if isinstance(size, tuple) and len(size) == 2:
        return size[0] * size[1] * len(getattr(v, "getbands", lambda: "RGBA")())
    return 64


class LRU:
    """Least-recently-used cache bounded by an approximate byte budget."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self._d: "OrderedDict[Hashable, Tuple[Any, int]]" = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self.hits = self.misses = 0

    def get(self, key: Hashable, default=None):
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                self.hits += 1
                return self._d[key][0]
            self.misses += 1
            return default

    def put(self, key: Hashable, value: Any) -> Any:
        n = _nbytes(value)
        with self._lock:
            if key in self._d:
                self._bytes -= self._d.pop(key)[1]
            if n <= self.max_bytes:
                self._d[key] = (value, n)
                self._bytes += n
                while self._bytes > self.max_bytes and self._d:
                    self._bytes -= self._d.popitem(last=False)[1][1]
        return value

    def get_or_make(self, key: Hashable, make: Callable[[], Any]) -> Any:
        v = self.get(key, _MISSING)
        return self.put(key, make()) if v is _MISSING else v

    def clear(self) -> None:
        with self._lock:
            self._d.clear()
            self._bytes = 0


_MISSING = object()

MB = 1 << 20
images = LRU(400 * MB)
raw_masks = LRU(200 * MB)
clean_masks = LRU(200 * MB)
working = LRU(300 * MB)
adjusted = LRU(200 * MB)  # the working picture with color adjustments
layouts = LRU(300 * MB)


def file_key(path) -> Tuple[str, int, int]:
    """Identity of a file's current contents (path, size, mtime)."""
    p = Path(path).resolve()
    st = p.stat()
    return str(p), st.st_size, st.st_mtime_ns


def clear_all() -> None:
    for c in (images, raw_masks, clean_masks, working, adjusted, layouts):
        c.clear()
