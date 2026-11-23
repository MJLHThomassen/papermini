"""Tests of the shape operations on synthetic masks."""

import cv2
import numpy as np
import pytest

from papermini.pipeline.morphology import MAX_PARTS
from papermini.pipeline.nothing_found_error import NothingFoundError
from papermini.pipeline.too_many_parts_error import TooManyPartsError


def test_an_empty_mask_says_no_figure_was_found(pipeline):
    with pytest.raises(NothingFoundError, match="found no figure"):
        pipeline.morphology.bbox(np.zeros((40, 40), np.uint8))


def test_too_many_separate_parts_to_bridge(pipeline):
    m = np.zeros((400, 400), np.uint8)
    for i in range(MAX_PARTS + 1):
        cv2.circle(m, (20 + (i % 10) * 36, 20 + (i // 10) * 50), 5, 255, -1)
    with pytest.raises(TooManyPartsError, match="too many to join"):
        pipeline.morphology.connect_components(m, 4)
