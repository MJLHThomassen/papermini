"""Tests of style preset files, and finding a preset by its name or file."""

import pytest

from papermini import __version__
from papermini.project.style_preset import StylePreset
from papermini.project.style_preset_file import StylePresetFile

DARK = StylePreset("Dark tabs", {"tab_color": "#000000", "label_color": "#ffffff"})


@pytest.fixture
def files():
    return StylePresetFile()


def test_a_preset_file_reads_back_as_it_was_saved(files, tmp_path):
    plain = StylePreset("Plain", {})
    path = files.save([DARK, plain], tmp_path / "presets.yaml")
    assert path.read_text(encoding="utf-8").startswith(
        f"papermini: {__version__}\nformat: 1\npresets:\n"
    )
    assert files.load(path) == [DARK, plain]


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("figures: []\n", "is not a papermini style preset file"),
        ("format: 2\npresets: {Dark: {}}\n", "made by a newer papermini"),
        ("presets: {}\n", "holds no style presets"),
        ("presets: {Big: {height_mm: 50}}\n", "p.yaml: style preset Big: height_mm"),
    ],
)
def test_a_file_that_is_not_a_valid_preset_file_is_refused(
    files, tmp_path, text, error
):
    path = tmp_path / "p.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        files.load(path)


def test_a_preset_is_found_by_its_name_in_any_case(files):
    assert files.find("token").name == "Token"
    assert files.find("dark tabs", [DARK]) == DARK


def test_a_known_preset_wins_over_a_built_in_one_of_its_name(files):
    mine = StylePreset("Token", {"kind": "token"})
    assert files.find("Token", [mine]) is mine


def test_a_preset_is_found_by_its_file(files, tmp_path):
    path = files.save([DARK], tmp_path / "dark.yaml")
    assert files.find(str(path)) == DARK


def test_a_file_with_more_than_one_preset_is_refused(files, tmp_path):
    path = files.save([DARK, StylePreset("Plain", {})], tmp_path / "two.yaml")
    with pytest.raises(ValueError, match="holds 2 style presets"):
        files.find(str(path))


def test_an_unknown_preset_names_the_presets_there_are(files, tmp_path):
    with pytest.raises(ValueError, match=r"no style preset called 'Gold'.*Token"):
        files.find("Gold")
