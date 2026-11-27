"""Tests of style presets: what they hold, and how they give figures their style."""

import pytest

from papermini.project.figure_settings import STYLE_KEYS, FigureSettings
from papermini.project.style_preset import StylePreset
from papermini.project.styles import BUILTIN_STYLES


def test_a_preset_holds_the_style_settings_that_differ_from_the_defaults():
    settings = FigureSettings(
        tab_color="#000000", margin_mm=2.0, label="Ogre", height_mm=48, copies=3
    )
    assert StylePreset.of("Dark tabs", settings).values == {
        "tab_color": "#000000",
        "margin_mm": 2.0,
    }


def test_a_style_leaves_out_the_size_the_text_and_the_source():
    assert {"kind", "tab_color", "font", "dpi"} <= set(STYLE_KEYS)
    left_out = {"size", "height_mm", "tab_width_mm", "token_diameter_mm", "label"}
    left_out |= {"back_label", "back_text", "token_area", "copies", "crop", "mask"}
    assert not left_out & set(STYLE_KEYS)


def test_applying_a_preset_resets_the_style_it_does_not_hold():
    figure = FigureSettings(
        tab_shape="round", margin_mm=3.0, label="Ogre", size="large"
    )
    styled = StylePreset("Dark tabs", {"tab_color": "#000000"}).applied_to(figure)
    assert styled.tab_color == "#000000"
    assert (styled.tab_shape, styled.margin_mm) == ("square", 1.6)  # the defaults
    assert (styled.label, styled.size) == ("Ogre", "large")  # not part of a style


def test_a_figure_matches_the_preset_whose_style_it_has():
    preset = StylePreset("Dark tabs", {"tab_color": "#000000"})
    assert preset.matches(FigureSettings(tab_color="#000000", label="Ogre"))
    assert not preset.matches(FigureSettings(tab_color="#000000", fold_mm=1.0))
    assert not preset.matches(FigureSettings())


def test_presets_read_back_as_they_were_written():
    presets = [
        StylePreset("Dark tabs", {"tab_color": "#000000"}),
        StylePreset("Plain", {}),
    ]
    assert StylePreset.all_from_dict(StylePreset.dict_of(presets)) == presets


def test_a_preset_setting_written_with_a_dash_is_read():
    (preset,) = StylePreset.all_from_dict({"Dark": {"tab-color": "#000000"}})
    assert preset.values == {"tab_color": "#000000"}


@pytest.mark.parametrize(
    ("presets", "error"),
    [
        ({"Big": {"height_mm": 50}}, "style preset Big: height_mm is not part of a "),
        ({"Odd": {"tab_shape": "star"}}, "style preset Odd: "),
        ({"  ": {}}, "a style preset needs a name"),
        ({"Dark": {}, " Dark ": {}}, "there are two style presets called Dark"),
        (["Dark"], "presets must give each style preset's name and settings"),
    ],
)
def test_presets_that_are_not_valid_are_refused(presets, error):
    with pytest.raises(ValueError, match=error):
        StylePreset.all_from_dict(presets)


def test_the_first_built_in_preset_is_the_defaults():
    assert BUILTIN_STYLES[0].matches(FigureSettings())
    assert [p.name for p in BUILTIN_STYLES] == [
        "Standing mini",
        "Standing mini - dark mode",
        "Token",
    ]
