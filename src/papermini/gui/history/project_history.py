from __future__ import annotations

import time
from collections.abc import Callable, Generator
from contextlib import contextmanager

from PySide6.QtCore import QObject
from PySide6.QtGui import QUndoStack

from ...project.figure_settings import FigureSettings
from ...project.sheet_settings import SheetSettings
from .project_change import ProjectChange
from .project_snapshot import ProjectSnapshot


class ProjectHistory(QObject):
    """The undo history of the open project, on a ``QUndoStack``.

    The window wraps each change to the project in ``change()``. The history takes a
    snapshot of the project before and after it and pushes the pair as one step.
    Undo and redo hand a snapshot to ``restore``, which puts the project back as it
    was; changes the window makes meanwhile are not recorded.

    Each step has two names: one for the Undo and Redo actions, such as "change to
    Margin", and one for the list of changes, such as "Changed Margin".
    ``steps`` returns how many steps the history keeps. Qt takes a new number only
    while the history is empty.
    """

    def __init__(
        self,
        snapshot: Callable[[], ProjectSnapshot],
        restore: Callable[[ProjectSnapshot], None],
        steps: Callable[[], int],
        clock: Callable[[], float] = time.monotonic,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._snapshot = snapshot
        self._restore = restore
        self._steps = steps
        self._clock = clock
        self._depth = 0  # how many change() blocks are open
        self._restoring = False
        self.stack = QUndoStack(self)
        self.stack.setUndoLimit(steps())

    @contextmanager
    def change(self, action: str = "", done: str = "") -> Generator[None]:
        """Record the changes made in the block as one step, named ``action`` on the
        Undo and Redo actions and ``done`` in the list of changes. A named step stays
        a step of its own. Without names, the step is named after the settings it
        changes, and may merge with the step before it (see ``ProjectChange``). A
        block inside another is part of the outer block's step."""
        outer = self._depth == 0 and not self._restoring
        before = self._snapshot() if outer else None
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
        if before is not None:
            self._record(before, action, done)

    def clear(self) -> None:
        """Forget every step, for a new or opened project, and take the number of
        steps to keep."""
        self.stack.clear()
        self.stack.setUndoLimit(self._steps())

    def follow_steps(self) -> None:
        """Take a new number of steps to keep now, when the history is empty."""
        if self.stack.count() == 0:
            self.stack.setUndoLimit(self._steps())

    def _record(self, before: ProjectSnapshot, action: str, done: str) -> None:
        after = self._snapshot()
        if after == before:
            return
        merges = not action
        if merges:
            action, done = self._describe(before, after)
        self.stack.push(
            ProjectChange(
                f"{done}\n{action}",
                before,
                after,
                self._clock(),
                self._apply,
                merges,
            )
        )

    def _apply(self, target: ProjectSnapshot) -> None:
        self._restoring = True
        try:
            self._restore(target)
        finally:
            self._restoring = False

    @staticmethod
    def _describe(before: ProjectSnapshot, after: ProjectSnapshot) -> tuple[str, str]:
        """Name a change to settings after the labels of the settings it changes."""
        changed = after.changed_figures(before)
        sheet = after.changed_sheet_names(before)
        if len(changed) == 1 and not sheet:
            options = FigureSettings.options()
            names = after.changed_names(before, changed[0])
        elif sheet and not changed:
            options, names = SheetSettings.options(), sheet
        else:
            return "settings change", "Changed settings"
        labels = sorted(options[n].label for n in names if n in options)
        if len(labels) == 1:
            what = labels[0]
        elif len(labels) == 2:
            what = f"{labels[0]} and {labels[1]}"
        else:
            return "settings change", "Changed settings"
        return f"change to {what}", f"Changed {what}"
