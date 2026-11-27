"""Tests of continuing a picture past its edges with its background."""

import numpy as np

from papermini.pipeline.image_extender import ImageExtender
from papermini.pipeline.morphology import Morphology

SKY = (120, 160, 220)
RED = (200, 30, 30)
PXMM = 10.0


def _window():
    """A 100 x 100 window whose left 30 columns lie outside the picture: a sky with a
    red figure that touches the picture's left edge."""
    img = np.full((100, 100, 3), 255, np.uint8)
    img[:, 30:] = SKY
    img[40:60, 30:50] = RED
    fig = np.zeros((100, 100), np.uint8)
    fig[40:60, 30:50] = 255
    return img, fig, (30, 0, 100, 100)


def test_the_picture_goes_on_past_its_edge_with_its_background():
    img, fig, inside = _window()
    out = ImageExtender(Morphology()).extend(img, fig, inside, PXMM)
    outside = out[:, :30].reshape(-1, 3).astype(int)
    assert np.abs(outside - SKY).max() <= 2  # the sky, never white
    assert np.array_equal(out[:, 30:], img[:, 30:])  # the picture itself unchanged


def test_the_figure_is_not_repeated_past_the_edge():
    """Regression: mirroring the picture as it is repeated a figure that touches the
    edge in the margin beyond it."""
    img, fig, inside = _window()
    out = ImageExtender(Morphology()).extend(img, fig, inside, PXMM)
    assert not (out[:, :30] == RED).all(axis=2).any()


def test_a_window_inside_the_picture_is_left_alone():
    img, fig, _ = _window()
    out = ImageExtender(Morphology()).extend(img, fig, (0, 0, 100, 100), PXMM)
    assert out is img
