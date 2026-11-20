"""Tests of calculating size tables and the values a creature size fills in."""

from dataclasses import replace

import pytest

from papermini.project import sizes
from papermini.project.figure_settings import FigureSettings
from papermini.project.size_row import SizeRow


def test_calculating_a_table(size_calculator):
    t = size_calculator.calculate(30, 40)
    assert t.row("medium") == SizeRow(40, 29.53, 29.53, 14.77)
    assert t.row("large").height_mm == 60 and t.row("tiny").base_mm == 14.76
    assert t.name == "" and t.calculated()
    g = size_calculator.for_grid(30)  # the command line's --grid-mm: heights scale too
    assert g.medium_mm == pytest.approx(32 * 30 / 25.4)
    assert g.row("huge").base_mm == round(3 * 30 * 25 / 25.4, 2)


def test_a_size_fills_in_and_a_hand_edit_makes_it_custom(size_calculator):
    s = size_calculator.apply(FigureSettings(), "huge")
    assert (s.size, s.height_mm, s.tab_radius_mm, s.tab_width_mm, s.tab_height_mm) == (
        "huge",
        64,
        37.5,
        75,
        37.5,
    )
    assert size_calculator.matches(s)
    edited = size_calculator.reconcile(s, replace(s, tab_width_mm=70))
    assert edited.size == "custom" and edited.tab_width_mm == 70
    picked = size_calculator.reconcile(edited, replace(edited, size="small"))
    assert (picked.size, picked.height_mm, picked.tab_width_mm) == ("small", 24, 25)
    assert size_calculator.reconcile(picked, replace(picked, label="X")).size == "small"
    assert (
        size_calculator.apply(replace(s, width_mm=80), "large").width_mm is None
    )  # width follows
    assert not size_calculator.matches(replace(picked, width_mm=30))
    assert size_calculator.apply(edited, "custom") == edited  # custom keeps the values
    big = size_calculator.apply(
        FigureSettings(), "large", size_calculator.calculate(30, 40)
    )
    assert big.height_mm == 60 and big.tab_radius_mm == 29.53


def test_footprint_and_width_warning(size_calculator):
    t = sizes.BUILTIN
    assert size_calculator.footprint_text("large", t) == "2 × 2 squares · 50 mm base"
    assert size_calculator.footprint_text("medium", t) == "1 × 1 square · 25 mm base"
    assert size_calculator.footprint_text("tiny", t) == "½ × ½ square · 12.5 mm base"
    assert size_calculator.footprint_text("custom", t) == ""
    assert size_calculator.width_warning("large", 50, t) == ""
    assert size_calculator.width_warning("large", 96, t) == (
        "This figure is 96 mm wide, wider than its 2 squares (50.8 mm): set a width or "
        "pick a bigger size."
    )
    assert "half a square (12.7 mm)" in size_calculator.width_warning("tiny", 20, t)
    assert (
        size_calculator.width_warning("custom", 500, t) == ""
        and size_calculator.width_warning("large", 0, t) == ""
    )


def test_the_creature_size_fills_in_the_diameter(size_calculator):
    assert (
        size_calculator.settings_with_size(
            {"kind": "token", "size": "large"}
        ).token_diameter_mm
        == 50
    )
    assert (
        size_calculator.settings_with_size(
            {"kind": "token", "size": "huge"}
        ).token_diameter_mm
        == 75
    )
    edited = size_calculator.settings_with_size(
        {"kind": "token", "size": "large", "token_diameter_mm": 40}
    )
    assert edited.size == "custom" and edited.token_diameter_mm == 40


def test_settings_with_size_fills_in_the_size(size_calculator):
    assert size_calculator.settings_with_size({}) == size_calculator.apply(
        FigureSettings(), "medium"
    )
    s = size_calculator.settings_with_size({"size": "large"})
    assert (s.size, s.height_mm, s.tab_width_mm) == ("large", 48, 50)
    s = size_calculator.settings_with_size(
        {"size": "large", "height-mm": 60}
    )  # its own height: custom
    assert (s.size, s.height_mm, s.tab_width_mm) == ("custom", 60, 50)
    s = size_calculator.settings_with_size(
        {"width_mm": 30}
    )  # regression: a width alone scales by width
    assert (s.height_mm, s.width_mm, s.size) == (None, 30, "custom")
    assert s.tab_width_mm == 25
    assert (
        size_calculator.settings_with_size(
            {"size": "large"}, size_calculator.calculate(30, 40)
        ).height_mm
        == 60
    )
    with pytest.raises(ValueError, match="size must be one of"):
        size_calculator.settings_with_size({"size": "colossal"})
