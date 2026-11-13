"""The Preferences window: the creature size presets, the project's size table and the
figures that follow it, and the other pages. Off-screen, no model."""

import json
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from papermini import sizes
from papermini.settings import FigureSettings


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    from PySide6.QtCore import QSettings

    # keep the tests away from the user's real preferences
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                      str(tmp_path_factory.mktemp("settings")))
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def no_presets(app):
    """Every test starts without presets of its own."""
    from papermini.gui import prefs

    prefs.store().remove("sizes")
    yield
    prefs.store().remove("sizes")


@pytest.fixture
def window(app, monkeypatch):
    """The main window; figures fail to build at once (no model in these tests)."""
    from papermini.gui import window as window_mod

    monkeypatch.setattr(window_mod, "build_mini", lambda *a, **k: (_ for _ in ()).throw(
        ValueError("not built in this test")))
    w = window_mod.MainWindow()
    yield w
    w._modified = False  # (no "Save changes?" question)
    w.close()


def _image(path):
    im = np.full((300, 200, 3), 255, np.uint8)
    im[60:240, 50:150] = 40
    Image.fromarray(im).save(path)
    return path


def _names(page):
    """The list as shown: (name, notes) per entry."""
    out = []
    for i in range(page.list.count()):
        item = page.list.item(i)
        label = page.list.itemWidget(item)
        out.append((label.name.text(), label.notes.text().replace("\n", " · ")))
    return out


def _answer(monkeypatch, name):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (name, True)))


def test_presets_in_the_preferences(app):
    from papermini.gui import prefs, preferences

    assert preferences.presets() == [sizes.BUILTIN]
    assert preferences.default_table() == sizes.BUILTIN
    mine = replace(sizes.calculate(30), name="Mine")
    preferences.save_user_presets([mine])
    preferences.set_default_name("Mine")
    assert preferences.presets() == [sizes.BUILTIN, mine]
    assert preferences.default_table() == mine
    assert preferences.preset_of(mine) == "Mine"
    assert preferences.preset_of(replace(mine, medium_mm=40)) == ""  # changed since
    assert preferences.table_label(mine) == "Mine"
    assert preferences.table_label(sizes.calculate(28)) == "this project's table"
    # entries that cannot be read, or would hide the built-in one, are left out
    good = mine.to_dict()
    prefs.store().setValue(preferences.PRESETS_KEY, json.dumps(
        [good, {"grid_mm": -1, "preset": "Bad"}, "x", {**good, "preset": "Standard 1-inch"},
         {**good}]))
    assert preferences.user_presets() == [mine]
    prefs.store().setValue(preferences.PRESETS_KEY, "not json")
    assert preferences.user_presets() == [] and preferences.default_table() == sizes.BUILTIN


def test_the_builtin_preset_is_read_only(app):
    from papermini.gui.preferences import SizesPage

    page = SizesPage(sizes.BUILTIN)
    assert _names(page) == [("Standard 1-inch",
                             "Built-in · Used in this project · Default for new projects")]
    assert not page.grid.isEnabled() and not page.spins["large", "height_mm"].isEnabled()
    assert not page.b_rename.isEnabled() and not page.b_delete.isEnabled()
    assert not page.b_use.isEnabled() and not page.b_default.isEnabled()
    assert not page.b_save.isVisibleTo(page)
    assert "can't be changed" in page.status.text()
    page.spins["large", "height_mm"].setValue(70)  # (disabled; ignored all the same)
    assert page.project_table() == sizes.BUILTIN


def test_own_presets_copy_rename_use_default_edit_delete(app, monkeypatch):
    from papermini.gui import preferences
    from papermini.gui.preferences import SizesPage

    page = SizesPage(sizes.BUILTIN)
    page.copy_preset()
    assert _names(page)[1] == ("Standard 1-inch copy", "")
    page.grid.setValue(30)
    page.calculate()
    assert page.spins["large", "base_mm"].value() == pytest.approx(59.06)
    _answer(monkeypatch, "My 30 mm grid")
    page.rename_preset()
    assert [t.name for t in preferences.user_presets()] == ["My 30 mm grid"]
    assert preferences.user_presets()[0].grid_mm == 30  # saved at once
    page.use_in_project()
    page.make_default()
    assert _names(page) == [("Standard 1-inch", "Built-in"),
                            ("My 30 mm grid", "Used in this project · Default for new projects")]
    assert page.project_table().name == "My 30 mm grid"
    assert preferences.default_name() == "My 30 mm grid"
    assert "uses this preset" in page.status.text()
    # editing the project's preset changes the project too
    page.spins["large", "tab_width_mm"].setValue(52)
    assert page.project_table().row("large").tab_width_mm == 52
    assert preferences.user_presets()[0].row("large").tab_width_mm == 52
    # a name in use is refused
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a: warned.append(a[2])))
    page.new_preset()
    assert _names(page)[2][0] == "New preset"
    _answer(monkeypatch, "My 30 mm grid")
    page.rename_preset()
    assert warned == ["There is already a preset called My 30 mm grid."]
    # renaming the project's preset renames the project's table; deleting it leaves the
    # project its own copy, and the default goes back to the built-in one
    page.list.setCurrentRow(1)
    _answer(monkeypatch, "Club")
    page.rename_preset()
    assert page.project_table().name == "Club" and preferences.default_name() == "Club"
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    page.delete_preset()
    assert preferences.default_name() == "Standard 1-inch"
    assert page.project_table().name == "Club"  # (the project keeps its copy)
    assert _names(page)[-1] == ("This project's table", "Not a preset · Used in this project")
    assert "not on this computer" in page.status.text()


def test_a_project_table_that_matches_no_preset(app, monkeypatch):
    from papermini.gui import preferences
    from papermini.gui.preferences import SizesPage

    preferences.save_user_presets([replace(sizes.calculate(30), name="Club")])
    page = SizesPage(replace(sizes.calculate(28), name="Club"))  # Club, changed since
    assert _names(page)[-1] == ("This project's table", "Not a preset · Used in this project")
    assert page.list.currentRow() == 2 and "values are different now" in page.status.text()
    assert page.b_save.isVisibleTo(page) and not page.b_default.isEnabled()
    page.spins["huge", "height_mm"].setValue(70)  # edits change only the project
    assert page.project_table().row("huge").height_mm == 70
    assert preferences.user_presets()[0].row("huge").height_mm != 70
    _answer(monkeypatch, "Club 28 mm")
    page.save_as_preset()
    assert page.project_table().name == "Club 28 mm"
    assert [n for n, _ in _names(page)] == ["Standard 1-inch", "Club", "Club 28 mm"]
    assert _names(page)[2][1] == "Used in this project"
    # Use in this project picks a preset again
    page.list.setCurrentRow(0)
    page.use_in_project()
    assert page.project_table() == sizes.BUILTIN


def test_closing_preferences_gives_the_project_its_table(window, tmp_path, monkeypatch):
    from papermini.gui.preferences import PreferencesDialog

    w = window
    w.add_images([_image(tmp_path / "a.png"), _image(tmp_path / "b.png"),
                  _image(tmp_path / "c.png")])
    big, small, own = w.figures
    big.entry.settings = sizes.apply(big.entry.settings, "large")
    own.entry.settings = replace(own.entry.settings, size="custom", height_mm=40)
    w._modified = False
    mine = replace(sizes.calculate(30, 40), name="Mine")

    def pick(dlg):
        dlg.sizes._add(mine)
        dlg.sizes.use_in_project()
        return 0

    monkeypatch.setattr(PreferencesDialog, "exec", pick)
    w.show_preferences()
    assert w.project.sizes == mine and w._modified
    assert (big.entry.settings.size, big.entry.settings.height_mm) == ("large", 60)
    assert small.entry.settings.height_mm == 40 and small.entry.settings.tab_width_mm == 29.53
    assert own.entry.settings.height_mm == 40 and own.entry.settings.tab_width_mm == 25
    w.list.setCurrentRow(0)
    assert w.panel.size_hint.text() == "2 × 2 squares · 59.06 mm base · Mine"


def test_a_new_project_starts_with_the_default_preset(window):
    from papermini.gui import preferences

    mine = replace(sizes.calculate(30), name="Mine")
    preferences.save_user_presets([mine])
    preferences.set_default_name("Mine")
    window.new_project()
    assert window.project.sizes == mine


def test_picking_a_size_fills_in_and_an_edit_makes_it_custom(window, tmp_path):
    w = window
    w.add_images([_image(tmp_path / "a.png")])
    fig = w.current()
    assert fig.entry.settings.size == "medium" and fig.entry.settings.height_mm == 32
    combo = w.panel._w["size"][1]
    assert [combo.itemData(i) for i in range(combo.count())] == list(sizes.SIZE_CHOICES)
    assert w.panel.size_hint.text() == "1 × 1 square · 25 mm base · Standard 1-inch"
    combo.setCurrentIndex(combo.findData("huge"))
    s = fig.entry.settings
    assert (s.size, s.height_mm, s.tab_radius_mm, s.tab_width_mm) == ("huge", 64, 37.5, 75)
    assert w.panel.size_field.h.value() == 64 and w.panel._w["tab_width_mm"][1].value() == 75
    assert w.panel.size_hint.text().startswith("3 × 3 squares · 75 mm base")
    w.panel.size_field.h.setValue(50)
    assert fig.entry.settings.size == "custom" and fig.entry.settings.height_mm == 50
    assert combo.currentData() == "custom" and w.panel.size_hint.isHidden()


def test_the_width_warning(window, tmp_path):
    w = window
    w.add_images([_image(tmp_path / "a.png")], sizes.apply(FigureSettings(), "large"))
    w.panel.set_figure_width(96)
    assert not w.panel.size_warning.isHidden()
    assert "96 mm wide, wider than its 2 squares (50.8 mm)" in w.panel.size_warning.text()
    w.panel.set_figure_width(40)
    assert w.panel.size_warning.isHidden()


def test_the_other_pages(window):
    from papermini.gui import prefs
    from papermini.gui.preferences import PreferencesDialog

    dlg = PreferencesDialog(window, "appearance")
    assert [dlg.nav.item(i).text() for i in range(dlg.nav.count())] == [
        "Creature sizes", "Appearance", "Updates", "Logging", "Models and cache"]
    assert dlg.stack.currentIndex() == 1
    dark = [b for b in dlg.theme_group.buttons() if b.text() == "Dark"][0]
    dark.setChecked(True)
    assert window._theme_mode == "dark" and prefs.store().value("theme") == "dark"
    [b for b in dlg.theme_group.buttons() if b.text() == "Follow system"][0].setChecked(True)
    assert window._theme_mode == "system"
    dlg.show_page("nothing")  # (an unknown page: the first)
    assert dlg.stack.currentIndex() == 0
    dlg.close()
