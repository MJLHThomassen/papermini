"""Tests of adding a folder of images in the app. Off-screen, no model."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMessageBox

pytestmark = pytest.mark.usefixtures("no_builds")


def test_subfolders_are_added_by_default(prefs):
    assert prefs.add_subfolders() is True  # on by default
    prefs.set_add_subfolders(False)
    assert prefs.add_subfolders() is False


def test_adding_a_folder_adds_its_images(window, monsters, monkeypatch):
    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.No),
    )
    assert window.add_folder(monsters) == 5
    assert [f.entry.display_name for f in window.figures] == [
        "leader",
        "goblin 2",
        "goblin 10",
        "goblins-leader",
        "orcs-leader",
    ]
    assert (
        window.statusBar().currentMessage()
        == "Added 5 images from Monsters (2 other files skipped)"
    )
    assert not asked

    # again: asks, and No leaves them out
    assert window.add_folder(monsters) == 0
    assert asked == [
        ("5 of the images in Monsters are already in the project. Add them again?")
    ]
    assert len(window.figures) == 5
    assert (
        window.statusBar().currentMessage()
        == "No images added from Monsters (2 other files skipped, 5 already in the project)"
    )

    # Yes adds them all again
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes)
    )
    assert window.add_folder(monsters) == 5 and len(window.figures) == 10


def test_a_folder_can_be_added_without_its_subfolders(window, monsters, prefs):
    prefs.set_add_subfolders(False)
    assert window.add_folder(monsters) == 1
    assert (
        window.statusBar().currentMessage()
        == "Added 1 image from Monsters (1 other file skipped)"
    )


def test_a_folder_without_images_says_so(window, tmp_path, monkeypatch):
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "notes.txt").write_text("x")
    told = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: told.append(a[2]))
    )
    assert window.add_folder(tmp_path / "empty") == 0
    assert told and told[0].startswith("empty has no images papermini can read")
    assert not window.figures


def test_dropping_a_folder_adds_its_images(window, monsters):
    window.open_paths([str(monsters)])
    assert len(window.figures) == 5


def test_add_folder_is_in_the_menu_and_the_figure_list(window):
    texts = [a.text() for a in window.menu.actions()]
    assert texts.index("Add folder…") == texts.index("Add images…") + 1
    assert texts.index("Open recent") == texts.index("Open…") + 1
    assert window.a_add_folder.shortcut().toString() == "Ctrl+Shift+I"
    assert window.empty.folder_button.text() == "or add a folder…"
