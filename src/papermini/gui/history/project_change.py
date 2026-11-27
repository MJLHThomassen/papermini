from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QUndoCommand

from .project_snapshot import ProjectSnapshot

MERGE_ID = 1  # the command id of changes that may merge with the one before
MERGE_S = 1.0  # how close in time two edits of the same settings must be to merge


class ProjectChange(QUndoCommand):
    """One step in the undo history: the project before and after a change.

    A change that ``merges`` merges into the change before it when both edit
    settings of the same figure, or of the sheet, at least one setting is the same,
    and it comes within ``MERGE_S`` of the last edit. A slider drag or a typed
    number is then one step, even when its first edit also changed another setting,
    such as a typed height that makes the creature size custom.
    """

    def __init__(
        self,
        text: str,
        before: ProjectSnapshot,
        after: ProjectSnapshot,
        at: float,
        restore: Callable[[ProjectSnapshot], None],
        merges: bool = True,
    ):
        super().__init__(text)
        self.before = before
        self.after = after
        self._at = at  # when the last edit in this step happened, in seconds
        self._key = after.merge_key(before) if merges else None
        self._restore = restore
        self._pushed = False

    def id(self) -> int:
        return -1 if self._key is None else MERGE_ID

    def redo(self) -> None:
        # the stack calls redo when the change is pushed, after the window made it
        if self._pushed:
            self._restore(self.after)
        self._pushed = True

    def undo(self) -> None:
        self._restore(self.before)

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not (
            isinstance(other, ProjectChange)
            and self._key is not None
            and other._key is not None
            and self._key.overlaps(other._key)
            and other._at - self._at <= MERGE_S
        ):
            return False
        self._key = self._key.joined(other._key)
        self.after = other.after
        self._at = other._at
        self.setObsolete(self.after == self.before)
        return True
