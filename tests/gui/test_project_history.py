"""Tests of the project's undo history on its own: which changes become steps, how
quick edits merge, the names of the steps and how many steps it keeps. Without a
window: the project is a snapshot that the tests replace."""

from dataclasses import replace

import pytest

pytest.importorskip("PySide6")

from papermini.gui.history.project_history import ProjectHistory
from papermini.gui.history.project_snapshot import ProjectSnapshot
from papermini.project import sizes
from papermini.project.figure_settings import FigureSettings
from papermini.project.sheet_settings import SheetSettings

pytestmark = pytest.mark.usefixtures("app")


class Project:
    """A project as the history sees it, with a clock the tests move."""

    def __init__(self, figures: int = 2, steps: int = 100):
        settings = {uid: FigureSettings() for uid in range(figures)}
        self.state = ProjectSnapshot(
            tuple(settings), settings, SheetSettings(), sizes.BUILTIN
        )
        self.now = 0.0
        self.steps = steps
        self.history = ProjectHistory(
            lambda: self.state, self._restore, lambda: self.steps, lambda: self.now
        )
        self.on_restore = lambda: None  # the window's reaction to a restore

    def _restore(self, target: ProjectSnapshot) -> None:
        self.state = target
        self.on_restore()

    def edit(self, uid: int, after: float = 0.0, **changes) -> None:
        """Change settings of the figure ``uid``, ``after`` seconds after the last
        edit."""
        self.now += after
        with self.history.change():
            settings = dict(self.state.settings)
            settings[uid] = replace(settings[uid], **changes)
            self.state = replace(self.state, settings=settings)

    def edit_sheet(self, after: float = 0.0, **changes) -> None:
        self.now += after
        with self.history.change():
            self.state = replace(self.state, sheet=replace(self.state.sheet, **changes))

    def height(self, uid: int = 0) -> float | None:
        return self.state.settings[uid].height_mm

    @property
    def stack(self):
        return self.history.stack


def test_a_change_becomes_a_step_that_undo_and_redo_put_back():
    p = Project()
    p.edit(0, height_mm=40.0)
    assert p.stack.count() == 1
    p.stack.undo()
    assert p.height() == 32.0
    p.stack.redo()
    assert p.height() == 40.0


def test_a_block_that_changes_nothing_is_no_step():
    p = Project()
    with p.history.change("doing nothing", "Did nothing"):
        pass
    assert p.stack.count() == 0


def test_quick_edits_of_the_same_setting_are_one_step():
    """A slider drag or typing a number sends many edits within a moment."""
    p = Project()
    for h in (33.0, 34.0, 35.0):
        p.edit(0, after=0.2, height_mm=h)
    assert p.stack.count() == 1
    p.stack.undo()
    assert p.height() == 32.0


def test_edits_far_apart_in_time_are_steps_of_their_own():
    p = Project()
    p.edit(0, height_mm=33.0)
    p.edit(0, after=5.0, height_mm=34.0)
    assert p.stack.count() == 2


def test_quick_edits_of_other_settings_or_figures_are_steps_of_their_own():
    p = Project()
    p.edit(0, height_mm=33.0)
    p.edit(0, after=0.1, margin_mm=2.0)
    p.edit(1, after=0.1, margin_mm=2.0)
    p.edit_sheet(after=0.1, gap_mm=9.0)
    assert p.stack.count() == 4


def test_an_edit_that_changes_another_setting_too_still_merges():
    """A typed height that also makes the size custom merges with the next keys."""
    p = Project()
    p.edit(0, height_mm=3.0, size="custom")
    p.edit(0, after=0.1, height_mm=35.0)
    assert p.stack.count() == 1


def test_quick_edits_that_end_where_they_began_leave_no_step():
    p = Project()
    p.edit(0, height_mm=33.0)
    p.edit(0, after=0.1, height_mm=32.0)
    assert p.stack.count() == 0


def test_a_named_step_never_merges():
    """Each crop box drawn is a step, however quickly the next one follows."""
    p = Project()
    for crop in ([0.1, 0.1, 0.9, 0.9], [0.2, 0.2, 0.8, 0.8]):
        with p.history.change("change to the crop", "Changed the crop"):
            p.edit(0, crop=crop)
    assert p.stack.count() == 2


def test_a_block_inside_another_is_part_of_its_step():
    p = Project()
    with p.history.change("applying settings", "Applied settings"):
        p.edit(0, height_mm=40.0)
        p.edit(1, height_mm=40.0)
    assert p.stack.count() == 1
    assert p.stack.text(0) == "Applied settings"
    assert p.stack.undoText() == "applying settings"


def test_changes_made_while_undoing_are_not_recorded():
    p = Project()
    p.edit(0, height_mm=40.0)
    p.on_restore = lambda: p.edit(1, margin_mm=3.0)
    p.stack.undo()
    assert p.stack.count() == 1


@pytest.mark.parametrize(
    ("edit", "listed", "action"),
    [
        (
            lambda p: p.edit(0, height_mm=40.0),
            "Changed Figure height",
            "change to Figure height",
        ),
        (
            lambda p: p.edit(0, height_mm=40.0, margin_mm=3.0),
            "Changed Figure height and Margin",
            "change to Figure height and Margin",
        ),
        (lambda p: p.edit_sheet(gap_mm=9.0), "Changed Gap", "change to Gap"),
        (
            lambda p: p.edit(0, height_mm=40.0, margin_mm=3.0, smooth_mm=1.0),
            "Changed settings",
            "settings change",
        ),
    ],
)
def test_an_unnamed_step_is_named_after_the_settings_it_changes(edit, listed, action):
    p = Project()
    edit(p)
    assert p.stack.text(0) == listed
    assert p.stack.undoText() == action


def test_the_history_keeps_as_many_steps_as_asked():
    p = Project(steps=10)
    for n in range(15):
        p.edit(0, after=5.0, height_mm=40.0 + n)
    assert p.stack.count() == 10


def test_a_new_number_of_steps_waits_for_an_empty_history():
    """Qt takes a new limit only while the history is empty."""
    p = Project(steps=10)
    p.edit(0, height_mm=40.0)
    p.steps = 20
    p.history.follow_steps()
    assert p.stack.undoLimit() == 10
    p.history.clear()
    assert p.stack.count() == 0 and p.stack.undoLimit() == 20
