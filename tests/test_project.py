"""Tests of a project: the style presets it keeps."""

from papermini.project.project import Project
from papermini.project.style_preset import StylePreset
from papermini.project.styles import BUILTIN_STYLES

DARK = StylePreset("Dark tabs", {"tab_color": "#000000"})


def test_a_project_keeps_a_preset_in_place_of_one_with_its_name():
    p = Project(presets=[DARK, StylePreset("Crypt", {})])
    darker = StylePreset("Dark tabs", {"tab_color": "#111111"})
    assert p.keep_preset(darker) is True  # (other settings)
    assert p.presets == [darker, StylePreset("Crypt", {})]
    assert p.keep_preset(darker) is False  # (the same settings)
    assert p.keep_preset(DARK) is True
    p.keep_preset(StylePreset("Lair", {"margin_mm": 3.0}))
    assert [q.name for q in p.presets] == ["Dark tabs", "Crypt", "Lair"]


def test_a_project_keeps_no_copy_of_an_unchanged_built_in_preset():
    token = next(q for q in BUILTIN_STYLES if q.name == "Token")
    changed = StylePreset("Token", {"kind": "token", "dpi": 150})
    p = Project(presets=[DARK])
    assert p.keep_preset(token) is False and p.presets == [DARK]
    p.keep_preset(changed)
    assert p.presets == [DARK, changed]
    p.keep_preset(token)
    assert p.presets == [DARK]
