"""Tests of a figure's settings: their defaults, their checks and their
dictionary form."""

from dataclasses import replace

import pytest

from papermini.pipeline.adjustments import Adjustments
from papermini.project.figure_settings import FigureSettings


def test_token_settings_are_checked():
    d = FigureSettings()
    assert (d.kind, d.token_diameter_mm, d.token_border_mm, d.token_text) == (
        "mini",
        25,
        2,
        "none",
    )
    assert (d.token_text_mm, d.token_text_color, d.token_cut_line) == (
        2.5,
        "#ffffff",
        False,
    )
    for bad in (
        {"kind": "standee"},
        {"token_text": "name"},
        {"token_text_style": "wavy"},
        {"token_fill": "pattern"},
        {"token_text_mm": 0},
        {"token_border_mm": -1},
        {"token_diameter_mm": 0},
        {"token_border_color": "red"},
        {"token_area": [0, 0, 0.5]},
        {"token_area": [0.5, 0, 0.4, 1]},
    ):
        with pytest.raises(ValueError):
            FigureSettings.from_dict(bad)
    s = FigureSettings.from_dict({"token_area": "0.1, 0.2, 0.9, 1.0"})
    assert s.token_area == [0.1, 0.2, 0.9, 1.0]
    assert (
        FigureSettings.from_dict({"token_area": [-0.2, -0.1, 1.2, 1.3]}).token_area[0]
        == -0.2
    )


def test_the_tab_options_are_checked():
    s = FigureSettings.from_dict({"tab_front": "number", "tab_back": "label_number"})
    assert (s.tab_front, s.tab_back) == ("number", "label_number")
    assert s.to_dict(with_size=False) == {
        "tab_front": "number",
        "tab_back": "label_number",
    }
    assert (
        FigureSettings.from_dict({"back": "text_number"}).params().back == "text_number"
    )
    for bad in ({"tab_front": "digits"}, {"tab_back": ""}, {"back": "numbers"}):
        with pytest.raises(ValueError):
            FigureSettings.from_dict(bad)


def test_from_dict_accepts_dashes_and_rejects_unknown():
    s = FigureSettings.from_dict({"height-mm": 30, "strength": 60})
    assert s.height_mm == 30 and s.strength == 60
    with pytest.raises(ValueError, match="unknown"):
        FigureSettings.from_dict({"heigth_mm": 30})


def test_to_dict_only_non_defaults():
    """Only options not at their default, but always the creature size and the values
    it fills in (left out with ``with_size=False``, as the log does)."""
    medium = {
        "size": "medium",
        "height_mm": 32.0,
        "tab_radius_mm": 12.5,
        "tab_width_mm": 25.0,
        "tab_height_mm": 12.5,
    }
    assert FigureSettings().to_dict() == medium
    assert FigureSettings().to_dict(with_size=False) == {}
    assert FigureSettings(label="X", crop=[0, 0, 1, 0.5]).to_dict(with_size=False) == {
        "label": "X",
        "crop": [0, 0, 1, 0.5],
    }
    assert FigureSettings(label="X").to_dict() == {**medium, "label": "X"}


def test_minis_are_double_sided_by_default():
    assert FigureSettings().double_sided and FigureSettings().params().double_sided
    s = FigureSettings.from_dict({"double_sided": False})
    assert not s.params().double_sided
    assert s.to_dict(with_size=False) == {"double_sided": False}


def test_the_back_option_is_checked():
    assert (
        FigureSettings.from_dict({"double_sided": True, "back": "blank"}).params().back
        == "blank"
    )
    with pytest.raises(ValueError, match="back must be"):
        FigureSettings.from_dict({"back": "photo"})


def test_the_tab_and_margin_options_are_checked():
    p = FigureSettings.from_dict(
        {"tab_shape": "round", "tab_color": "#123456", "margin_fill": "image"}
    ).params()
    assert (p.tab_shape, p.tab_color, p.margin_fill) == ("round", "#123456", "image")
    for bad in (
        {"tab_shape": "oval"},
        {"margin_fill": "white"},
        {"tab_fill": "color"},
        {"tab_color": "green-ish"},
    ):
        with pytest.raises(ValueError):
            FigureSettings.from_dict(bad)


def test_the_font_option_is_kept_and_checked():
    s = FigureSettings.from_dict({"font": "Kalam"})
    assert s.style().font == "Kalam" and s.to_dict(with_size=False) == {"font": "Kalam"}
    assert FigureSettings().style().font == "Times"
    assert (
        FigureSettings.from_dict({"font": "No Such Font"}).font == "No Such Font"
    )  # (kept)
    for bad in ("", "  ", 12):
        with pytest.raises(ValueError, match="font must be"):
            FigureSettings.from_dict({"font": bad})


def test_the_adjustments_are_checked_and_round_trip():
    s = FigureSettings.from_dict({"greyscale": True, "brightness": 20, "hue": -45})
    assert s.adjustments() == Adjustments(brightness=20, hue=-45, greyscale=True)
    assert s.to_dict(with_size=False) == {
        "greyscale": True,
        "brightness": 20,
        "hue": -45,
    }
    for key, bad in (
        ("brightness", 101),
        ("hue", 181),
        ("contrast", 1.5),
        ("saturation", True),
    ):
        with pytest.raises(ValueError, match=key):
            FigureSettings.from_dict({key: bad})


def test_mask_inputs_change_only_with_the_settings_background_removal_uses():
    s = FigureSettings()
    for change in ({"model": "birefnet"}, {"mask": "m.png"}, {"crop": "0,0,0.5,1"}):
        assert replace(s, **change).mask_inputs() != s.mask_inputs()
    for change in ({"strength": 90}, {"margin_mm": 4}, {"label": "Hero"}):
        assert replace(s, **change).mask_inputs() == s.mask_inputs()
