"""Tests of building a mini from a figure's settings."""

import pytest

from papermini.project.figure_settings import FigureSettings


def test_the_mask_model_needs_a_mask_image(hero_figure):
    from papermini.project.settings import build_mini

    img, mask = hero_figure
    m = build_mini(
        img, FigureSettings(model="mask", mask=str(mask)), log=lambda *_: None
    )
    assert m.figure_height_mm == pytest.approx(32, abs=0.05)  # Medium
    with pytest.raises(ValueError, match="needs a mask image"):
        build_mini(img, FigureSettings(model="mask"), log=lambda *_: None)
