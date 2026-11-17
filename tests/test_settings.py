"""Tests of building a mini from a figure's settings, and of filling in the
settings of a creature size."""

import pytest

from papermini.project import sizes
from papermini.project.figure_settings import FigureSettings
from papermini.project.settings import settings_with_size


def test_the_mask_model_needs_a_mask_image(hero_figure):
    from papermini.project.figure_settings import FigureSettings
    from papermini.project.settings import build_mini

    img, mask = hero_figure
    m = build_mini(
        img, FigureSettings(model="mask", mask=str(mask)), log=lambda *_: None
    )
    assert m.figure_height_mm == pytest.approx(32, abs=0.05)  # Medium
    with pytest.raises(ValueError, match="needs a mask image"):
        build_mini(img, FigureSettings(model="mask"), log=lambda *_: None)


def test_the_creature_size_fills_in_the_diameter():
    assert (
        settings_with_size({"kind": "token", "size": "large"}).token_diameter_mm == 50
    )
    assert settings_with_size({"kind": "token", "size": "huge"}).token_diameter_mm == 75
    edited = settings_with_size(
        {"kind": "token", "size": "large", "token_diameter_mm": 40}
    )
    assert edited.size == "custom" and edited.token_diameter_mm == 40


def test_settings_with_size_fills_in_the_size():
    assert settings_with_size({}) == sizes.apply(FigureSettings(), "medium")
    s = settings_with_size({"size": "large"})
    assert (s.size, s.height_mm, s.tab_width_mm) == ("large", 48, 50)
    s = settings_with_size({"size": "large", "height-mm": 60})  # its own height: custom
    assert (s.size, s.height_mm, s.tab_width_mm) == ("custom", 60, 50)
    s = settings_with_size(
        {"width_mm": 30}
    )  # regression: a width alone scales by width
    assert (s.height_mm, s.width_mm, s.size) == (None, 30, "custom")
    assert s.tab_width_mm == 25
    assert (
        settings_with_size({"size": "large"}, sizes.calculate(30, 40)).height_mm == 60
    )
    with pytest.raises(ValueError, match="size must be one of"):
        settings_with_size({"size": "colossal"})
