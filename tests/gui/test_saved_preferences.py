"""Tests of the preferences the app saves: each one keeps its key and its default, so
what users saved before is read back. Off-screen, no model."""

import json

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QByteArray

from papermini.project.size_table import SizeTable

CLUB = SizeTable(grid_mm=30.0, name="Club")

# (preference, its key, its default, a value, the value as stored)
SAVED = [
    ("theme", "theme", "system", "dark", "dark"),
    (
        "splitter_state",
        "layout/splitter",
        None,
        QByteArray(b"state"),
        QByteArray(b"state"),
    ),
    ("left_panel_width", "layout/left_width", 0, 420, 420),
    ("right_panel_width", "layout/right_width", 0, 380, 380),
    ("add_subfolders", "add_subfolders", True, False, False),
    ("png_px_per_square", "png_px_per_square", 256, 100, 100),
    ("png_size_mode", "png_size", "square", "dpi", "dpi"),
    ("png_dpi", "png_dpi", 300, 600, 600),
    ("user_presets", "sizes/presets", [], [CLUB], json.dumps([CLUB.to_dict()])),
    ("default_preset_name", "sizes/default_preset", "Standard 1-inch", "Club", "Club"),
    ("export_pdf", "export/pdf", True, False, False),
    ("export_cut", "export/cut", True, False, False),
    ("last_update_check", "updates/last_check", 0.0, 1.7e9, 1.7e9),
    ("auto_updates", "updates/auto", True, False, False),
    ("history_open", "layout/history_open", True, False, False),
    ("undo_steps", "history/undo_steps", 100, 250, 250),
]
SETTERS = {
    "add_subfolders": "set_add_subfolders",
    "user_presets": "save_user_presets",
}


@pytest.mark.parametrize(("name", "key", "default", "value", "stored"), SAVED)
def test_each_preference_keeps_its_key_and_default(
    prefs, settings_store, name, key, default, value, stored
):
    get = getattr(prefs, name)
    assert get() == default
    getattr(prefs, SETTERS.get(name, f"set_{name}"))(value)
    assert settings_store.value(key) == stored
    settings_store.clear()
    settings_store.setValue(key, stored)
    assert get() == value


def test_a_section_keeps_its_key_and_is_open_by_default(prefs, settings_store):
    assert prefs.section_open("Size") is True
    prefs.set_section_open("Size", False)
    assert settings_store.value("sections/Size") is False
    assert prefs.section_open("Size") is False and prefs.section_open("Crop") is True


def test_the_recent_projects_keep_their_key(prefs, settings_store, tmp_path):
    project = tmp_path / "project.yaml"
    project.write_text("figures: []\n")
    assert prefs.recent_projects() == []
    settings_store.setValue("recent_projects", [str(project)])
    assert prefs.recent_projects() == [project]


@pytest.mark.parametrize(
    ("name", "key", "stored", "read"),
    [
        ("png_px_per_square", "png_px_per_square", 10, 256),
        ("png_px_per_square", "png_px_per_square", "many", 256),
        ("png_dpi", "png_dpi", 5000, 300),
        ("png_size_mode", "png_size", "huge", "square"),
        ("undo_steps", "history/undo_steps", 5, 100),
    ],
)
def test_a_stored_value_that_does_not_fit_reads_as_the_default(
    prefs, settings_store, name, key, stored, read
):
    settings_store.setValue(key, stored)
    assert getattr(prefs, name)() == read


def test_adding_subfolders_saved_as_text_is_read_back(prefs, settings_store):
    settings_store.setValue("add_subfolders", "false")
    assert prefs.add_subfolders() is False
    settings_store.setValue("add_subfolders", "True")
    assert prefs.add_subfolders() is True


def test_the_png_scale_follows_the_size_mode(prefs):
    prefs.set_png_px_per_square(254)
    assert prefs.png_px_per_mm(25.4) == pytest.approx(10)
    prefs.set_png_size_mode("dpi")
    prefs.set_png_dpi(254)
    assert prefs.png_px_per_mm(50) == pytest.approx(10)
