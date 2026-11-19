"""The Preferences window: the creature size presets, the project's size table and the
figures that follow it, and the other pages. Off-screen, no model."""

import json
from dataclasses import replace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QInputDialog, QMessageBox

from papermini.project import sizes
from papermini.project.figure_settings import FigureSettings

pytestmark = pytest.mark.usefixtures("no_builds")


def _names(page):
    """The list as shown: (name, notes) per entry."""
    from papermini.gui.dialogs.sizes_page import NOTES_ROLE

    return [
        (
            page.list.item(i).text(),
            page.list.item(i).data(NOTES_ROLE).replace("\n", " · "),
        )
        for i in range(page.list.count())
    ]


def _answer(monkeypatch, name):
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: (name, True))
    )


def test_presets_in_the_preferences(prefs, settings_store):
    assert prefs.presets() == [sizes.BUILTIN]
    assert prefs.default_table() == sizes.BUILTIN
    mine = replace(sizes.calculate(30), name="Mine")
    prefs.save_user_presets([mine])
    prefs.set_default_preset_name("Mine")
    assert prefs.presets() == [sizes.BUILTIN, mine]
    assert prefs.default_table() == mine
    assert prefs.preset_of(mine) == "Mine"
    assert prefs.preset_of(replace(mine, medium_mm=40)) == ""  # changed since
    assert prefs.table_label(mine) == "Mine"
    assert prefs.table_label(sizes.calculate(28)) == "this project's table"
    # entries that cannot be read, or would hide the built-in one, are left out
    good = mine.to_dict()
    settings_store.setValue(
        "sizes/presets",
        json.dumps(
            [
                good,
                {"grid_mm": -1, "preset": "Bad"},
                "x",
                {**good, "preset": "Standard 1-inch"},
                {**good},
            ]
        ),
    )
    assert prefs.user_presets() == [mine]
    settings_store.setValue("sizes/presets", "not json")
    assert prefs.user_presets() == [] and prefs.default_table() == sizes.BUILTIN


def test_the_builtin_preset_is_read_only(prefs):
    from papermini.gui.dialogs.sizes_page import SizesPage

    page = SizesPage(prefs, sizes.BUILTIN)
    assert _names(page) == [
        (
            "Standard 1-inch",
            "Built-in · Used in this project · Default for new projects",
        )
    ]
    assert (
        not page.grid.isEnabled() and not page.spins["large", "height_mm"].isEnabled()
    )
    assert not page.b_rename.isEnabled() and not page.b_delete.isEnabled()
    assert not page.b_use.isEnabled() and not page.b_default.isEnabled()
    assert not page.b_save.isVisibleTo(page)
    assert "can't be changed" in page.status.text()
    page.spins["large", "height_mm"].setValue(70)  # (disabled; ignored all the same)
    assert page.project_table() == sizes.BUILTIN


def test_own_presets_copy_rename_use_default_edit_delete(prefs, monkeypatch):
    from papermini.gui.dialogs.sizes_page import SizesPage

    page = SizesPage(prefs, sizes.BUILTIN)
    page.copy_preset()
    assert _names(page)[1] == ("Standard 1-inch copy", "")
    page.grid.setValue(30)
    page.calculate()
    assert page.spins["large", "base_mm"].value() == pytest.approx(59.06)
    _answer(monkeypatch, "My 30 mm grid")
    page.rename_preset()
    assert [t.name for t in prefs.user_presets()] == ["My 30 mm grid"]
    assert prefs.user_presets()[0].grid_mm == 30  # saved at once
    page.use_in_project()
    page.make_default()
    assert _names(page) == [
        ("Standard 1-inch", "Built-in"),
        ("My 30 mm grid", "Used in this project · Default for new projects"),
    ]
    assert page.project_table().name == "My 30 mm grid"
    assert prefs.default_preset_name() == "My 30 mm grid"
    assert "uses this preset" in page.status.text()
    # editing the project's preset changes the project too
    page.spins["large", "tab_width_mm"].setValue(52)
    assert page.project_table().row("large").tab_width_mm == 52
    assert prefs.user_presets()[0].row("large").tab_width_mm == 52
    # a name in use is refused
    warned = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a: warned.append(a[2]))
    )
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
    assert page.project_table().name == "Club" and prefs.default_preset_name() == "Club"
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes)
    )
    page.delete_preset()
    assert prefs.default_preset_name() == "Standard 1-inch"
    assert page.project_table().name == "Club"  # (the project keeps its copy)
    assert _names(page)[-1] == (
        "This project's table",
        "Not a preset · Used in this project",
    )
    assert "not on this computer" in page.status.text()


def test_a_project_table_that_matches_no_preset(prefs, monkeypatch):
    from papermini.gui.dialogs.sizes_page import SizesPage

    prefs.save_user_presets([replace(sizes.calculate(30), name="Club")])
    changed = replace(sizes.calculate(28), name="Club")  # Club, changed since
    page = SizesPage(prefs, changed)
    assert _names(page)[-1] == (
        "This project's table",
        "Not a preset · Used in this project",
    )
    assert (
        page.list.currentRow() == 2 and "values are different now" in page.status.text()
    )
    assert page.b_save.isVisibleTo(page) and not page.b_default.isEnabled()
    page.spins["huge", "height_mm"].setValue(70)  # edits change only the project
    assert page.project_table().row("huge").height_mm == 70
    assert prefs.user_presets()[0].row("huge").height_mm != 70
    _answer(monkeypatch, "Club 28 mm")
    page.save_as_preset()
    assert page.project_table().name == "Club 28 mm"
    assert [n for n, _ in _names(page)] == ["Standard 1-inch", "Club", "Club 28 mm"]
    assert _names(page)[2][1] == "Used in this project"
    # Use in this project picks a preset again
    page.list.setCurrentRow(0)
    page.use_in_project()
    assert page.project_table() == sizes.BUILTIN


def test_closing_preferences_gives_the_project_its_table(
    window, prefs, tmp_path, monkeypatch, figure_image
):
    from papermini.gui.dialogs.preferences_dialog import PreferencesDialog

    w = window
    w.add_images(
        [
            figure_image(tmp_path / "a.png", (200, 300), mask=False)[0],
            figure_image(tmp_path / "b.png", (200, 300), mask=False)[0],
            figure_image(tmp_path / "c.png", (200, 300), mask=False)[0],
        ]
    )
    big, small, own = w.figures
    big.entry.settings = sizes.apply(big.entry.settings, "large")
    own.entry.settings = replace(own.entry.settings, size="custom", height_mm=40)
    w.project.path = tmp_path / "project.yaml"
    assert w.save()  # no unsaved changes
    mine = replace(sizes.calculate(30, 40), name="Mine")
    prefs.save_user_presets([mine])

    def pick(dlg):
        dlg.sizes.list.setCurrentRow(1)  # Mine, after the built-in preset
        dlg.sizes.b_use.click()
        return 0

    monkeypatch.setattr(PreferencesDialog, "exec", pick)
    w.show_preferences()
    assert w.project.sizes == mine and " * " in w.windowTitle()
    assert (big.entry.settings.size, big.entry.settings.height_mm) == ("large", 60)
    assert (
        small.entry.settings.height_mm == 40
        and small.entry.settings.tab_width_mm == 29.53
    )
    assert own.entry.settings.height_mm == 40 and own.entry.settings.tab_width_mm == 25
    w.list.setCurrentRow(0)
    assert w.panel.size_hint.text() == "2 × 2 squares · 59.06 mm base · Mine"


def test_a_new_project_starts_with_the_default_preset(window, prefs):
    mine = replace(sizes.calculate(30), name="Mine")
    prefs.save_user_presets([mine])
    prefs.set_default_preset_name("Mine")
    window.new_project()
    assert window.project.sizes == mine


def test_picking_a_size_fills_in_and_an_edit_makes_it_custom(
    window, tmp_path, figure_image
):
    w = window
    w.add_images([figure_image(tmp_path / "a.png", (200, 300), mask=False)[0]])
    fig = w.current()
    assert fig.entry.settings.size == "medium" and fig.entry.settings.height_mm == 32
    combo = w.panel.field("size")
    assert [combo.itemData(i) for i in range(combo.count())] == list(sizes.SIZE_CHOICES)
    assert w.panel.size_hint.text() == "1 × 1 square · 25 mm base · Standard 1-inch"
    combo.setCurrentIndex(combo.findData("huge"))
    s = fig.entry.settings
    assert (s.size, s.height_mm, s.tab_radius_mm, s.tab_width_mm) == (
        "huge",
        64,
        37.5,
        75,
    )
    assert (
        w.panel.size_field.h.value() == 64
        and w.panel.field("tab_width_mm").value() == 75
    )
    assert w.panel.size_hint.text().startswith("3 × 3 squares · 75 mm base")
    w.panel.size_field.h.setValue(50)
    assert fig.entry.settings.size == "custom" and fig.entry.settings.height_mm == 50
    assert combo.currentData() == "custom" and w.panel.size_hint.isHidden()


def test_the_width_warning(window, tmp_path, figure_image):
    w = window
    w.add_images(
        [figure_image(tmp_path / "a.png", (200, 300), mask=False)[0]],
        sizes.apply(FigureSettings(), "large"),
    )
    w.panel.set_figure_width(96)
    assert not w.panel.size_warning.isHidden()
    assert (
        "96 mm wide, wider than its 2 squares (50.8 mm)" in w.panel.size_warning.text()
    )
    w.panel.set_figure_width(40)
    assert w.panel.size_warning.isHidden()


def test_the_other_pages(window, prefs):
    from papermini.gui import theme

    dlg = window.preferences_dialog("appearance")
    assert [dlg.nav.item(i).text() for i in range(dlg.nav.count())] == [
        "Creature sizes",
        "Images",
        "Appearance",
        "Updates",
        "Logging",
        "Models and cache",
    ]
    assert dlg.stack.currentIndex() == 2
    dark = next(b for b in dlg.theme_group.buttons() if b.text() == "Dark")
    dark.setChecked(True)
    assert theme.current is theme.DARK and prefs.theme() == "dark"
    next(
        b for b in dlg.theme_group.buttons() if b.text() == "Follow system"
    ).setChecked(True)
    assert prefs.theme() == "system"
    assert theme.current is theme.resolve("system")
    dlg.show_page("nothing")  # (an unknown page: the first)
    assert dlg.stack.currentIndex() == 0
    dlg.close()


def test_a_sizes_page_is_freed(prefs):
    """Regression: a lambda connected to the preset list kept every page alive until
    Python quit, after the QApplication was gone, and Python crashed on exit."""
    import gc
    import weakref

    from papermini.gui.dialogs.sizes_page import SizesPage

    page = SizesPage(prefs, sizes.BUILTIN)
    page.copy_preset()  # (the list is filled again)
    ref = weakref.ref(page)
    del page
    gc.collect()
    assert ref() is None


def test_the_images_page_sets_the_png_size(app, window, prefs):
    assert prefs.png_size_mode() == "square" and prefs.png_px_per_mm(25.4) == 256 / 25.4
    dlg = window.preferences_dialog("images")
    assert dlg.png_px.isEnabled() and not dlg.png_dpi.isEnabled()
    assert dlg.png_px.suffix() == ""  # (the unit is beside the box)
    dlg.png_buttons["dpi"].setChecked(True)
    assert prefs.png_size_mode() == "dpi" and dlg.png_dpi.isEnabled()
    dlg.png_dpi.setValue(600)
    assert prefs.png_px_per_mm(25.4) == pytest.approx(600 / 25.4)
    dlg.close()


def test_the_images_page_sets_whether_subfolders_are_added(window, prefs):
    dlg = window.preferences_dialog("images")
    assert dlg.subfolders.isChecked()
    dlg.subfolders.setChecked(False)
    assert prefs.add_subfolders() is False
    dlg.close()


def test_the_preferences_are_in_the_menu(app, new_window):
    """Preferences… is in the menu (Ctrl+,) and holds the settings that used to be menu
    items: the theme, automatic updates, the detailed log and cache management."""
    from PySide6.QtGui import QKeySequence

    w = new_window()
    assert w.a_prefs in w.menu.actions()
    assert w.a_prefs.shortcut() == QKeySequence("Ctrl+,")
    texts = [a.text() for a in w.menu.actions()]
    for gone in (
        "Theme",
        "Cache management…",
        "Creature sizes…",
        "Log",
        "Update automatically",
    ):
        assert gone not in texts
    assert "Open log folder" in texts
