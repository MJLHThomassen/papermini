from dataclasses import dataclass

import numpy as np
from PIL import Image

from papermini.support.lru import LRU


@dataclass
class _Pair:
    a: np.ndarray
    b: bytes


def test_the_least_recently_used_value_goes_first_when_the_budget_is_full():
    cache = LRU(250)
    cache.put("a", np.zeros(100, np.uint8))
    cache.put("b", np.zeros(100, np.uint8))
    assert cache.get("a") is not None  # "a" is now the most recently used
    cache.put("c", np.zeros(100, np.uint8))
    assert cache.get("b") is None
    assert cache.get("a") is not None and cache.get("c") is not None


def test_a_value_larger_than_the_budget_is_returned_but_not_kept():
    cache = LRU(10)
    value = np.zeros(11, np.uint8)
    assert cache.put("big", value) is value
    assert cache.get("big") is None


def test_values_are_measured_by_their_bytes():
    """Arrays count their bytes, tuples and dataclasses the sum of their parts, a PIL
    image its pixels times its bands, and anything else a small fixed size."""
    cases = [
        (np.zeros(40, np.uint16), 80),
        ((np.zeros(30, np.uint8), b"x" * 20), 50),
        (_Pair(np.zeros(25, np.uint8), b"y" * 5), 30),
        (Image.new("RGB", (4, 5)), 60),
        (object(), 64),
    ]
    for value, size in cases:
        cache = LRU(size)
        cache.put("fits", value)
        assert cache.get("fits") is value
        cache = LRU(size - 1)
        cache.put("too big", value)
        assert cache.get("too big") is None


def test_get_or_make_makes_a_value_once():
    cache = LRU(1000)
    made = []

    def make():
        made.append(1)
        return b"value"

    assert cache.get_or_make("k", make) == b"value"
    assert cache.get_or_make("k", make) == b"value"
    assert made == [1] and (cache.hits, cache.misses) == (1, 1)


def test_clear_empties_the_cache():
    cache = LRU(1000)
    cache.put("k", b"value")
    cache.clear()
    assert cache.get("k") is None
