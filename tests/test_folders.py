"""Adding a folder of images (in the app and with papermini make) and the recent projects.
Off-screen, no model."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from papermini import cli
from papermini.project.project_files import load_project
from papermini.support import remote

pytestmark = pytest.mark.usefixtures("no_builds")  # (no model in these tests)


@pytest.fixture
def monsters(tmp_path, figure_image) -> Path:
    """A folder with images directly in it and in subfolders, two files with the same
    name in different subfolders, a hidden folder and files that are not images."""
    root = tmp_path / "Monsters"
    for rel in (
        "leader.png",
        "goblins/goblin 10.png",
        "goblins/goblin 2.png",
        "goblins/leader.png",
        "orcs/leader.webp",
        ".hidden/x.png",
    ):
        figure_image(root / rel, (80, 120), mask=False)
    (root / "notes.txt").write_text("not an image")
    (root / "orcs" / "readme.md").write_text("not an image")
    return root


# region the folder's images
def test_natural_order():
    names = ["goblin 10", "Goblin 2", "goblin 1b", "ape"]
    assert sorted(names, key=remote.natural_key) == [
        "ape",
        "goblin 1b",
        "Goblin 2",
        "goblin 10",
    ]


def test_folder_images_own_first_then_subfolders(monsters):
    images, skipped = remote.folder_images(monsters)
    assert [p.relative_to(monsters).as_posix() for p in images] == [
        "leader.png",
        "goblins/goblin 2.png",
        "goblins/goblin 10.png",
        "goblins/leader.png",
        "orcs/leader.webp",
    ]
    assert (
        skipped == 2
    )  # notes.txt and orcs/readme.md; the hidden folder is not looked at
    only, skipped = remote.folder_images(monsters, subfolders=False)
    assert only == [monsters / "leader.png"] and skipped == 1


def test_same_names_get_their_subfolder(monsters):
    images, _ = remote.folder_images(monsters)
    assert remote.figure_names(images, monsters) == [
        None,
        None,
        None,
        "goblins-leader",
        "orcs-leader",
    ]  # leader.png keeps its name
    deep = [
        monsters / "a" / "b" / "x.png",
        monsters / "c" / "x.png",
        monsters / "y.png",
    ]
    assert remote.figure_names(deep, monsters) == ["a-b-x", "c-x", None]


# endregion


# region papermini make FOLDER
@pytest.fixture
def made(monkeypatch, square_mini):
    """papermini make without a model: each image becomes a plain square figure."""
    built = []

    def fake_build(img, s, **k):
        built.append(Path(img))
        return square_mini(Path(img).stem, 20.0, 30.0, px_per_mm=4)

    monkeypatch.setattr(cli, "build_mini", fake_build)
    return built


def test_make_a_folder_into_an_output_folder(monsters, tmp_path, made, capsys):
    out = tmp_path / "out"
    assert cli.main(["make", str(monsters), "-o", str(out)]) == 0
    assert "Monsters: 5 images (2 other files skipped)" in capsys.readouterr().out
    assert len(made) == 5
    svgs = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.svg"))
    assert svgs == [
        "goblins/goblin 10.svg",
        "goblins/goblin 2.svg",
        "goblins/leader.svg",
        "leader.svg",
        "orcs/leader.svg",
    ]  # the subfolders, inside -o DIR


def test_make_a_folder_next_to_its_images(monsters, made):
    assert cli.main(["make", str(monsters), "--no-subfolders"]) == 0
    assert made == [monsters / "leader.png"]
    assert (monsters / "leader.svg").is_file()


def test_make_an_empty_folder(tmp_path, made):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit, match="no images to make"):
        cli.main(["make", str(tmp_path / "empty")])


def test_a_project_cannot_list_a_folder(monsters, tmp_path):
    proj = tmp_path / "minis.yaml"
    proj.write_text("figures:\n  - image: Monsters\n")
    with pytest.raises(ValueError, match="Monsters is a folder"):
        load_project(proj)


# endregion


# region the app
def _projects(tmp_path, *names):
    paths = []
    for n in names:
        p = tmp_path / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("figures: []\n")
        paths.append(p)
    return paths


def test_recent_projects_newest_first_at_most_ten(prefs, tmp_path):
    paths = _projects(tmp_path, *[f"p{i}.yaml" for i in range(12)])
    for p in paths:
        prefs.add_recent(p)
    assert prefs.recent_projects() == list(reversed(paths))[: prefs.RECENT_MAX]
    prefs.add_recent(paths[5])  # opened again: back on top, not twice
    got = prefs.recent_projects()
    assert got[0] == paths[5] and got.count(paths[5]) == 1 and len(got) == 10
    paths[11].unlink()  # gone: left out, and forgotten
    assert paths[11] not in prefs.recent_projects()
    assert len(prefs.store().value(prefs.RECENT_KEY)) == 9
    prefs.clear_recent()
    assert prefs.recent_projects() == []


def test_one_recent_project_is_read_back_as_a_list(prefs, tmp_path):
    """QSettings hands back a list of one as a plain string."""
    (p,) = _projects(tmp_path, "only.yaml")
    prefs.store().setValue(prefs.RECENT_KEY, str(p))
    assert prefs.recent_projects() == [p]


def test_subfolders_preference(prefs):
    assert prefs.add_subfolders() is True  # on by default
    prefs.set_add_subfolders(False)
    assert prefs.add_subfolders() is False


def test_add_a_folder(window, monsters, monkeypatch):
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


def test_add_a_folder_without_its_subfolders(window, monsters, prefs):
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


def test_add_folder_in_the_menu_and_the_figure_list(window):
    texts = [a.text() for a in window.menu.actions()]
    assert texts.index("Add folder…") == texts.index("Add images…") + 1
    assert texts.index("Open recent") == texts.index("Open…") + 1
    assert window.a_add_folder.shortcut().toString() == "Ctrl+Shift+I"
    assert window.empty.folder_button.text() == "or add a folder…"


def test_opening_and_saving_count_as_recent(window, tmp_path):
    from papermini.project.project import Project
    from papermini.project.project_files import save_project

    a = tmp_path / "D&D" / "a.yaml"
    a.parent.mkdir()
    save_project(Project(path=a), a)
    window.load(a)
    from papermini.gui import prefs

    assert prefs.recent_projects() == [a.resolve()]
    b = tmp_path / "b.yaml"
    window.project.path = b
    assert window.save()
    assert prefs.recent_projects() == [b.resolve(), a.resolve()]
    # the start screen follows
    rows = [
        window.empty.recent_list.itemAt(i).widget()
        for i in range(window.empty.recent_list.count())
    ]
    assert [r.path for r in rows] == [b.resolve(), a.resolve()]


def test_open_recent_menu(window, tmp_path, monkeypatch):
    from papermini.gui import prefs

    window.menu.aboutToShow.emit()
    assert not window.recent_menu.menuAction().isEnabled()  # nothing yet
    a, b = _projects(tmp_path, "D&D/a.yaml", "b.yaml")
    prefs.add_recent(a)
    prefs.add_recent(b)
    window.menu.aboutToShow.emit()
    assert window.recent_menu.menuAction().isEnabled()
    window.recent_menu.aboutToShow.emit()
    acts = window.recent_menu.actions()
    assert [x.text().split("\t")[0] for x in acts if x.text()] == [
        "b.yaml",
        "a.yaml",
        "Clear list",
    ]
    assert "D&&D" in acts[1].text()  # (a single & would underline the next letter)
    opened = []
    monkeypatch.setattr(window, "load", opened.append)
    acts[1].trigger()
    assert opened == [a.resolve()]

    acts[-1].trigger()  # Clear list
    assert prefs.recent_projects() == [] and window.empty.recent_box.isHidden()


def test_a_recent_project_that_is_gone(window, tmp_path, monkeypatch):
    warned = []
    monkeypatch.setattr(window, "_warn", warned.append)
    window._open_recent(str(tmp_path / "gone.yaml"))
    assert warned and "is no longer there" in warned[0]


def test_start_screen_rows_open_from_anywhere(app, tmp_path):
    """Regression: only the name was a link, and a path with & (D&D) came back as
    &amp; and was not found."""
    from papermini.gui.widgets.empty_state import EmptyState

    paths = _projects(tmp_path, *[f"D&D/p{i}.yaml" for i in range(7)])
    e = EmptyState()
    e.resize(460, 700)
    e.set_recent(paths)
    assert e.recent_list.count() == EmptyState.RECENT_SHOWN
    e.show()
    got = []
    e.recentClicked.connect(got.append)
    row = e.recent_list.itemAt(0).widget()
    QTest.mouseClick(row, Qt.LeftButton, pos=QPoint(row.width() - 4, row.height() // 2))
    assert got == [str(paths[0])] and Path(got[0]).is_file()
    assert (
        row.sizeHint().width() <= e.maximumWidth()
    )  # (the folder is shortened to fit)
    e.set_recent([])
    assert e.recent_box.isHidden()
    e.close()


def test_preferences_images_page(window, prefs):
    from papermini.gui.dialogs.preferences_dialog import PreferencesDialog

    dlg = PreferencesDialog(window, "images")
    assert dlg.subfolders.isChecked()
    dlg.subfolders.setChecked(False)
    assert prefs.add_subfolders() is False
    dlg.close()


# endregion
