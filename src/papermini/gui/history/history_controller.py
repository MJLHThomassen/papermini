from __future__ import annotations

import logging
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractButton, QAbstractSpinBox, QSplitter

from ..preferences import Preferences
from ..theme_service import ThemeService
from .history_pane import HistoryPane
from .project_history import ProjectHistory
from .project_snapshot import ProjectSnapshot
from .undo_keys import UndoKeys

ui_log = logging.getLogger("papermini.ui")  # what the user does

HISTORY_SPLIT_PX = 400  # the figure list and the history start equally tall
FIGURES_MIN_PX = 200  # the figure list keeps this much when the history opens
UNDO_KEY = "Ctrl+Z"
REDO_KEY = "Ctrl+Y"


class HistoryController(QObject):
    """The undo history of the window's project, with what the user sees of it: the
    undo and redo actions and buttons, the history pane at the bottom of the left
    panel, and the status messages of undo and redo.

    ``snapshot`` takes a snapshot of the project and ``restore`` puts one back.
    """

    status = Signal(str)  # a message for the status bar
    modifiedChanged = Signal(bool)  # whether the project differs from its saved state

    def __init__(
        self,
        snapshot: Callable[[], ProjectSnapshot],
        restore: Callable[[ProjectSnapshot], None],
        prefs: Preferences,
        themes: ThemeService,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._prefs = prefs
        self._history = ProjectHistory(snapshot, restore, prefs.undo_steps, parent=self)
        self.stack = self._history.stack
        self.pane = HistoryPane(self.stack, themes)
        self.pane.openChanged.connect(self._opened)
        self._undo_keys = UndoKeys(self)
        self._split: QSplitter | None = None
        self._open_px = HISTORY_SPLIT_PX  # the pane's height when open
        self._undo_action: QAction | None = None
        self._undo_button: QAbstractButton | None = None
        self._redo_action: QAction | None = None
        self._redo_button: QAbstractButton | None = None
        self._toggle: QAction | None = None
        self.stack.cleanChanged.connect(
            lambda clean: self.modifiedChanged.emit(not clean)
        )
        for signal in (
            self.stack.indexChanged,
            self.stack.undoTextChanged,
            self.stack.redoTextChanged,
        ):
            signal.connect(self._sync)

    # region recording
    @contextmanager
    def change(self, action: str = "", done: str = "") -> Generator[None]:
        """Record the changes made in the block as one step (see
        ``ProjectHistory.change``)."""
        with self._history.change(action, done):
            yield

    def reset(self, start: str) -> None:
        """Forget every step, for a new or opened project, and name the project
        before any change ``start``."""
        self._history.clear()
        self.pane.set_start(start)

    def mark_saved(self) -> None:
        """Mark the current state as the one saved."""
        self.stack.setClean()

    def follow_steps(self) -> None:
        """Take a new number of steps to keep now, when the history is empty."""
        self._history.follow_steps()

    # endregion

    # region undo and redo
    def undo(self) -> None:
        """Undo the last change to the project."""
        if not self.stack.canUndo():
            self.status.emit("Nothing to undo")
            return
        text = self.stack.undoText()
        self.stack.undo()
        ui_log.info("Undid %s", text)
        self.status.emit(f"Undid {text}")

    def redo(self) -> None:
        """Redo the last undone change to the project."""
        if not self.stack.canRedo():
            self.status.emit("Nothing to redo")
            return
        text = self.stack.redoText()
        self.stack.redo()
        ui_log.info("Redid %s", text)
        self.status.emit(f"Redid {text}")

    def bind(
        self,
        undo: QAction,
        redo: QAction,
        undo_button: QAbstractButton,
        redo_button: QAbstractButton,
        toggle: QAction,
    ) -> None:
        """Keep the undo and redo actions and buttons named after the next step and
        enabled when there is one, and ``toggle`` checked while the pane is open."""
        self._undo_action, self._undo_button = undo, undo_button
        self._redo_action, self._redo_button = redo, redo_button
        self._toggle = toggle
        self._sync()
        toggle.setChecked(self.pane.is_open())

    def guard(self, boxes: Iterable[QAbstractSpinBox]) -> None:
        """Make the undo and redo keys undo and redo changes to the project in
        ``boxes`` too, instead of their typing."""
        for box in boxes:
            box.installEventFilter(self._undo_keys)

    def _sync(self, *_) -> None:
        stack = self.stack
        if self._undo_action is not None and self._undo_button is not None:
            step = stack.undoText() if stack.canUndo() else ""
            self._name(self._undo_action, self._undo_button, "Undo", UNDO_KEY, step)
        if self._redo_action is not None and self._redo_button is not None:
            step = stack.redoText() if stack.canRedo() else ""
            self._name(self._redo_action, self._redo_button, "Redo", REDO_KEY, step)

    @staticmethod
    def _name(
        action: QAction, button: QAbstractButton, word: str, key: str, step: str
    ) -> None:
        """Name ``action`` and ``button`` after the next ``step`` and enable them, or
        disable them when there is no step."""
        name = f"{word} {step}" if step else word
        action.setText(name)
        action.setEnabled(bool(step))
        button.setEnabled(bool(step))
        button.setToolTip(f"{name}  ({key})")

    # endregion

    # region the pane
    def attach(self, split: QSplitter) -> None:
        """Put the pane under the figure list, the first widget of ``split``, half
        and half."""
        self._split = split
        split.addWidget(self.pane)
        split.setCollapsible(0, False)
        split.setCollapsible(1, False)
        split.setSizes([HISTORY_SPLIT_PX, HISTORY_SPLIT_PX])
        split.splitterMoved.connect(self._dragged)

    def set_open(self, open_: bool) -> None:
        """Open the pane, or fold it to its header."""
        self.pane.set_open(open_)
        self._opened(open_)

    def restore_open(self) -> None:
        """Open or fold the pane as the user left it."""
        self.set_open(self._prefs.history_open())

    def refresh_icons(self) -> None:
        self.pane.refresh_icons()

    def _opened(self, open_: bool) -> None:
        """Give the pane back its height when it opens, and keep its handle still
        while it is folded."""
        if self._split is not None:
            handle = self._split.handle(1)
            if handle is not None:
                handle.setEnabled(open_)
            if open_:
                total = sum(self._split.sizes())
                h = min(self._open_px, max(total - FIGURES_MIN_PX, 0))
                self._split.setSizes([total - h, h])
        if self._toggle is not None:
            self._toggle.setChecked(open_)
        self._prefs.set_history_open(open_)

    def _dragged(self, *_) -> None:
        if self._split is not None and self.pane.is_open():
            self._open_px = self._split.sizes()[1]

    # endregion
