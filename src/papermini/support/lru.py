from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any

import numpy as np


def _nbytes(v: Any) -> int:
    if isinstance(v, np.ndarray):
        return v.nbytes
    if isinstance(v, (tuple, list)):
        return sum(_nbytes(x) for x in v)
    if hasattr(v, "__dataclass_fields__"):  # e.g. a Layout
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
        self._d: OrderedDict[Hashable, tuple[Any, int]] = OrderedDict()
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
