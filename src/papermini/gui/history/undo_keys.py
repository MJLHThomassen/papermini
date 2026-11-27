from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QKeyEvent, QKeySequence


class UndoKeys(QObject):
    """An event filter that leaves the undo and redo keys to the window's shortcuts.

    A number box handles those keys itself, as an undo of its typing. Installed on
    one, the filter turns that down, so the keys undo and redo changes to the project
    there too.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.ShortcutOverride
            and isinstance(event, QKeyEvent)
            and (
                event.matches(QKeySequence.StandardKey.Undo)
                or event.matches(QKeySequence.StandardKey.Redo)
            )
        ):
            event.ignore()
            return True
        return super().eventFilter(watched, event)
