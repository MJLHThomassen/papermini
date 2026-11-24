from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel

from ..theme_service import ThemeService


class RecentProject(QLabel):
    """One of the start screen's recent projects: its name in the accent color and its
    folder, dimmed and shortened in the middle to fit. The whole row opens it; the name is
    underlined under the mouse."""

    clicked = Signal(str)  # the project's path

    def __init__(self, themes: ThemeService, path, parent=None):
        super().__init__(parent)
        self._themes = themes
        self.path = path
        self._hover = False
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setToolTip(str(path))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(1)  # (the folder shrinks; the row never widens the card)
        self._show(False)

    def _show(self, hover: bool) -> None:
        self._hover = hover
        t = self._themes.current
        fm = self.fontMetrics()
        room = self.width() - fm.horizontalAdvance(self.path.name + "\u00a0\u00a0") - 8
        folder = fm.elidedText(
            str(self.path.parent), Qt.TextElideMode.ElideMiddle, max(40, room)
        )
        line = "underline" if hover else "none"
        self.setText(
            f"<span style='color:{t.accent}; text-decoration:{line}'>"
            f"{html.escape(self.path.name)}</span>&nbsp;&nbsp;"
            f"<span style='color:{t.muted}'>{html.escape(folder)}</span>"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show(self._hover)

    def enterEvent(self, event):
        self._show(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._show(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit(str(self.path))
        super().mouseReleaseEvent(event)
