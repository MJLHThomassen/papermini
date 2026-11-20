"""Tests of the recent projects. Off-screen, no model."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

pytestmark = pytest.mark.usefixtures("no_builds")


def _projects(tmp_path, *names):
    paths = []
    for n in names:
        p = tmp_path / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("figures: []\n")
        paths.append(p)
    return paths


def test_recent_projects_are_newest_first_and_at_most_ten(
    prefs, settings_store, tmp_path
):
    paths = _projects(tmp_path, *[f"p{i}.yaml" for i in range(12)])
    for p in paths:
        prefs.add_recent(p)
    assert prefs.recent_projects() == list(reversed(paths))[: prefs.RECENT_MAX]
    prefs.add_recent(paths[5])  # opened again: back on top, not twice
    got = prefs.recent_projects()
    assert got[0] == paths[5] and got.count(paths[5]) == 1 and len(got) == 10
    paths[11].unlink()  # gone: left out, and forgotten
    assert paths[11] not in prefs.recent_projects()
    assert len(settings_store.value("recent_projects")) == 9
    prefs.clear_recent()
    assert prefs.recent_projects() == []


def test_one_recent_project_is_read_back_as_a_list(prefs, settings_store, tmp_path):
    """QSettings hands back a list of one as a plain string."""
    (p,) = _projects(tmp_path, "only.yaml")
    settings_store.setValue("recent_projects", str(p))
    assert prefs.recent_projects() == [p]


def test_opening_and_saving_count_as_recent(window, prefs, tmp_path, project_store):
    from papermini.project.project import Project

    a = tmp_path / "D&D" / "a.yaml"
    a.parent.mkdir()
    project_store.save(Project(path=a), a)
    window.load(a)
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


def test_the_open_recent_menu_opens_a_project(window, prefs, tmp_path, monkeypatch):
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


def test_a_recent_project_that_is_gone_warns(window, tmp_path, monkeypatch):
    from papermini.gui.window import main_window

    warned = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text: warned.append(text)),
    )
    window.empty.recentClicked.emit(str(tmp_path / "gone.yaml"))  # a start screen row
    assert warned and "is no longer there" in warned[0]


def test_a_start_screen_row_opens_from_anywhere_on_it(app, tmp_path):
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
