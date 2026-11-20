"""Tests of opening and saving projects in the app."""

import cv2
import numpy as np
import pytest
from PIL import Image

pytest.importorskip("PySide6")


pytestmark = pytest.mark.usefixtures("fake_default_model")


def _answer(monkeypatch, button):
    """Answers the main window's questions with ``button``; returns the questions."""
    from papermini.gui.window import main_window

    asked = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "question",
        lambda *a, **k: asked.append(a[2]) or button,
    )
    return asked


def _names(w):
    return [f.entry.image.stem for f in w.figures]


def _saved_names(project_store, path):
    return [f.image.stem for f in project_store.load(path).figures]


@pytest.fixture
def three_figures(app, tmp_path, monkeypatch, new_window, wait):
    """Opens a window with figures a, b and c, and a project file to save to.
    The project has unsaved changes. A message box the test did not expect fails it."""
    from papermini.gui.window import main_window

    def unexpected(*a, **k):
        raise AssertionError(f"unexpected message box: {a[2]!r}")

    for kind in ("question", "warning", "information"):
        monkeypatch.setattr(main_window.QMessageBox, kind, unexpected)
    im = np.full((300, 200, 3), 255, np.uint8)
    cv2.ellipse(im, (100, 150), (60, 110), 0, 0, 360, (60, 60, 60), -1)
    for name in "abc":
        Image.fromarray(im).save(tmp_path / f"{name}.png")
    w = new_window()
    w.add_images([tmp_path / f"{name}.png" for name in "abc"])
    # (only the shown figure, the last one added, builds)
    assert wait(lambda: w.figures[-1].up_to_date)
    w.project.path = tmp_path / "proj.yaml"
    return w


@pytest.mark.parametrize("button", ["Cancel", "Discard", "Save"])
def test_a_new_project_asks_to_save_unsaved_changes(
    three_figures,
    monkeypatch,
    button,
    unsaved,
    project_store,
):
    from PySide6.QtWidgets import QMessageBox

    w, path = three_figures, three_figures.project.path
    asked = _answer(monkeypatch, getattr(QMessageBox.StandardButton, button))
    w.new_project()
    assert asked == ["Save changes to the project?"]
    if button == "Cancel":  # nothing happens
        assert _names(w) == ["a", "b", "c"] and unsaved(w)
    else:
        assert _names(w) == [] and w.windowTitle().startswith("untitled —")
    assert path.exists() == (button == "Save")
    if button == "Save":
        assert _saved_names(project_store, path) == ["a", "b", "c"]


def test_a_saved_project_does_not_ask(three_figures, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    w = three_figures
    asked = _answer(monkeypatch, QMessageBox.StandardButton.Cancel)
    assert w.save()
    w.new_project()
    assert asked == [] and _names(w) == []


def test_closing_with_unsaved_changes_can_be_cancelled(three_figures, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    w = three_figures
    asked = _answer(monkeypatch, QMessageBox.StandardButton.Cancel)
    assert not w.close()  # the window stays open
    assert asked == ["Save changes to the project?"] and _names(w) == ["a", "b", "c"]


def _warnings(monkeypatch):
    """Records the main window's warnings instead of showing them; returns them."""
    from papermini.gui.window import main_window

    warned = []
    monkeypatch.setattr(
        main_window.QMessageBox, "warning", lambda *a: warned.append(a[2])
    )
    return warned


def test_a_save_that_fails_warns_and_keeps_the_changes(
    three_figures, monkeypatch, tmp_path, unsaved
):
    from PySide6.QtWidgets import QMessageBox

    w = three_figures
    w.project.path = tmp_path / "no such folder" / "proj.yaml"
    warned = _warnings(monkeypatch)
    assert not w.save()
    assert len(warned) == 1 and unsaved(w)
    # nor does a new project discard them when the save fails
    _answer(monkeypatch, QMessageBox.StandardButton.Save)
    w.new_project()
    assert len(warned) == 2 and _names(w) == ["a", "b", "c"]


def test_save_as_asks_for_a_file(
    three_figures, monkeypatch, tmp_path, unsaved, project_store
):
    from papermini.gui.window import main_window

    w = three_figures
    w.project.path = None
    chosen = [""]
    monkeypatch.setattr(
        main_window.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (chosen[0], ""),
    )
    assert not w.save()  # no file chosen: nothing is saved
    assert w.project.path is None and unsaved(w)
    chosen[0] = str(tmp_path / "picked.yaml")
    assert w.save()
    assert w.windowTitle().startswith("picked.yaml —")
    assert _saved_names(project_store, tmp_path / "picked.yaml") == ["a", "b", "c"]


def test_moving_a_figure_changes_the_saved_order(three_figures, unsaved, project_store):
    from PySide6.QtCore import QModelIndex

    w = three_figures
    assert w.save()
    assert w.list.model().moveRow(QModelIndex(), 2, QModelIndex(), 0)  # c to the top
    assert _names(w) == ["c", "a", "b"] and unsaved(w)
    assert w.save()
    assert _saved_names(project_store, w.project.path) == ["c", "a", "b"]


def test_opening_a_project_asks_to_save_unsaved_changes(three_figures, monkeypatch):
    from PySide6.QtCore import QModelIndex
    from PySide6.QtWidgets import QMessageBox

    w = three_figures
    assert w.save()
    w.list.model().moveRow(QModelIndex(), 2, QModelIndex(), 0)
    asked = _answer(monkeypatch, QMessageBox.StandardButton.Cancel)
    w.load(w.project.path)
    assert asked == ["Save changes to the project?"] and _names(w) == ["c", "a", "b"]


def test_a_project_that_cannot_be_read_warns_and_keeps_the_open_one(
    three_figures, monkeypatch, tmp_path
):
    w = three_figures
    assert w.save()
    broken = tmp_path / "broken.yaml"
    broken.write_text("figures: [\n", encoding="utf-8")
    warned = _warnings(monkeypatch)
    w.load(broken)
    assert len(warned) == 1 and warned[0].startswith(f"Could not open {broken}")
    assert _names(w) == ["a", "b", "c"] and w.project.path == tmp_path / "proj.yaml"


def test_a_project_with_missing_images_opens_without_them(
    three_figures, monkeypatch, tmp_path
):
    w = three_figures
    assert w.save()
    (tmp_path / "b.png").unlink()
    warned = _warnings(monkeypatch)
    w.load(w.project.path)
    assert warned == ["Missing images:\nb.png"] and _names(w) == ["a", "c"]
