"""Tests of undo and redo in the main window: what they put back, where they take
the user, the unsaved mark, the shortcuts and the history pane. Off-screen, no
model."""

from dataclasses import replace

import pytest
from PIL import Image

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QModelIndex, Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QAbstractSpinBox

from papermini.gui.step import Step

pytestmark = pytest.mark.usefixtures("fake_default_model")


@pytest.fixture
def two(new_window, tmp_path):
    """A window with two figures, a and b, and the history that adding them left."""
    for n in "ab":
        Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / f"{n}.png")
    w = new_window()
    w.add_images([tmp_path / "a.png", tmp_path / "b.png"])
    return w


def _names(w):
    return [f.entry.image.name for f in w.figures]


def _set(w, fig, **changes):
    """Change settings of ``fig`` in its settings panel."""
    w.list.setCurrentRow(w.figures.index(fig))
    w.panel.changed.emit(replace(fig.entry.settings, **changes))


def test_adding_figures_can_be_undone_and_redone(two):
    w = two
    assert w.a_undo.text() == "Undo adding 2 images"
    w.a_undo.trigger()
    assert w.figures == [] and w.list.count() == 0
    w.a_redo.trigger()
    assert _names(w) == ["a.png", "b.png"] and w.list.count() == 2


def test_undo_selects_the_figure_and_shows_the_step_of_the_setting(two):
    w = two
    a = w.figures[0]
    _set(w, a, height_mm=40.0)
    w.list.setCurrentRow(1)
    w.tabs.setCurrentIndex(Step.SOURCE)
    w.a_undo.trigger()
    assert a.entry.settings.height_mm == 32.0
    assert w.current() is a and w.tabs.currentIndex() == Step.MINIATURE
    w.a_redo.trigger()
    assert a.entry.settings.height_mm == 40.0


def test_undoing_a_sheet_setting_shows_the_print_sheet(two):
    w = two
    gap = w.project.sheet.gap_mm
    w.sheet_panel.changed.emit(replace(w.project.sheet, gap_mm=gap + 3))
    w.tabs.setCurrentIndex(Step.SOURCE)
    w.a_undo.trigger()
    assert w.project.sheet.gap_mm == gap and w.tabs.currentIndex() == Step.SHEET


def test_a_removed_figure_comes_back_as_it_was(two):
    w = two
    a, b = w.figures
    _set(w, a, margin_mm=3.0)
    w.list.setCurrentRow(0)
    w.remove_current()
    assert w.figures == [b]
    w.a_undo.trigger()
    assert w.figures == [a, b] and a.entry.settings.margin_mm == 3.0
    assert w.list.count() == 2 and w.current() is a


def test_reordering_can_be_undone(two):
    w = two
    w.list.model().moveRow(QModelIndex(), 0, QModelIndex(), 2)
    assert _names(w) == ["b.png", "a.png"]
    w.a_undo.trigger()
    assert _names(w) == ["a.png", "b.png"]
    item = w.list.item(0)
    assert item is not None and item.data(Qt.ItemDataRole.UserRole) == w.figures[0].uid


def test_applying_to_all_figures_is_one_step(two):
    w = two
    a, b = w.figures
    _set(w, a, margin_mm=3.0)
    w.list.setCurrentRow(0)
    w.panel.applyToAll.emit(None)
    assert b.entry.settings.margin_mm == 3.0
    w.a_undo.trigger()
    assert b.entry.settings.margin_mm == 1.6 and a.entry.settings.margin_mm == 3.0


def test_undoing_back_to_the_saved_state_clears_the_unsaved_mark(two, tmp_path):
    w = two
    w.project.path = tmp_path / "proj.yaml"
    assert w.save()
    assert " * " not in w.windowTitle()
    _set(w, w.figures[0], margin_mm=3.0)
    assert " * " in w.windowTitle()
    w.a_undo.trigger()
    assert " * " not in w.windowTitle()
    w.a_redo.trigger()
    assert " * " in w.windowTitle()


def test_undo_and_redo_are_disabled_with_nothing_to_do(new_window):
    w = new_window()
    assert not w.a_undo.isEnabled() and not w.a_redo.isEnabled()
    assert not w.btn_undo.isEnabled()
    w.undo()  # from the keyboard: nothing happens
    assert w.figures == []


def test_a_new_project_starts_with_an_empty_history(two, monkeypatch):
    w = two
    monkeypatch.setattr(w, "_maybe_save", lambda: True)
    w.new_project()
    assert not w.a_undo.isEnabled() and w.history.stack.count() == 0


def test_the_shortcuts_are_the_usual_ones(new_window):
    w = new_window()
    assert QKeySequence(QKeySequence.StandardKey.Undo) in w.a_undo.shortcuts()
    assert {s.toString() for s in w.a_redo.shortcuts()} >= {"Ctrl+Y", "Ctrl+Shift+Z"}


@pytest.mark.parametrize(
    ("key", "mods", "taken_by_box"),
    [
        (Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier, False),
        (Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier, False),
        (Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier, True),
    ],
)
def test_number_boxes_leave_undo_and_redo_to_the_window(
    app, new_window, key, mods, taken_by_box
):
    """A number box keeps its own undo for Ctrl+Z; it hands it to the window's
    undo instead, and keeps its other keys."""
    w = new_window()
    box = w.findChildren(QAbstractSpinBox)[0]
    event = QKeyEvent(QEvent.Type.ShortcutOverride, key, mods)
    app.sendEvent(box, event)
    assert event.isAccepted() is taken_by_box


def test_the_history_pane_lists_the_steps_and_jumps_to_one(two):
    w = two
    a = w.figures[0]
    _set(w, a, margin_mm=3.0)
    view = w.history_pane.view
    model = view.model()
    rows = [model.index(r, 0).data() for r in range(model.rowCount())]
    assert rows == ["New project", "Added 2 images", "Changed Margin"]
    view.setCurrentIndex(model.index(0, 0))
    assert w.figures == []
    view.setCurrentIndex(model.index(2, 0))
    assert a.entry.settings.margin_mm == 3.0


def test_the_history_pane_folds_to_its_header_and_stays_so(app, new_window, prefs):
    w = new_window()
    pane = w.history_pane
    pane.header.click()
    assert not pane.view.isVisibleTo(w) and pane.header.isVisibleTo(w)
    assert not w.a_history.isChecked() and prefs.history_open() is False
    again = new_window()
    assert not again.history_pane.is_open()
    again.a_history.trigger()
    assert again.history_pane.view.isVisibleTo(again)
    assert prefs.history_open() is True
