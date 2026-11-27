from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QFrame, QPushButton, QUndoView, QVBoxLayout

from ..theme_service import ThemeService

CHEVRON_PX = 14
SAVED_ICON_PX = 14
NO_MAX_PX = 16777215  # Qt's QWIDGETSIZE_MAX: no maximum height


class HistoryPane(QFrame):
    """The undo history: every change to the project, with the current state
    selected and the saved state marked. Clicking a change goes back or forward to
    it. Clicking the header folds the pane to the header alone, or opens it."""

    openChanged = Signal(bool)

    def __init__(self, stack: QUndoStack, themes: ThemeService):
        super().__init__()
        self._themes = themes
        self.setObjectName("HistoryPane")
        self._box = v = QVBoxLayout(self)
        v.setContentsMargins(10, 0, 10, 6)
        v.setSpacing(0)
        self.header = QPushButton("History")
        self.header.setObjectName("SectionHeader")
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.header.setToolTip("Open or close the history")
        self.header.toggled.connect(self._toggle)
        v.addWidget(self.header)
        self.view = QUndoView(stack)
        self.view.setObjectName("History")
        self.view.setIconSize(QSize(SAVED_ICON_PX, SAVED_ICON_PX))
        v.addWidget(self.view, 1)
        self.refresh_icons()

    def is_open(self) -> bool:
        return self.header.isChecked()

    def set_open(self, open_: bool) -> None:
        """Open the pane, or fold it to its header."""
        if open_ == self.is_open():
            self._fit(open_)
        else:
            self.header.setChecked(open_)

    def set_start(self, text: str) -> None:
        """Name the first entry, the project before any change, ``text``."""
        self.view.setEmptyLabel(text)

    def refresh_icons(self) -> None:
        t = self._themes.current
        self.header.setIcon(
            self._themes.icon(
                "chevron_down" if self.is_open() else "chevron_right",
                t.muted,
                CHEVRON_PX,
            )
        )
        self.view.setCleanIcon(self._themes.icon("save", t.muted, SAVED_ICON_PX))

    def _toggle(self, open_: bool) -> None:
        self._fit(open_)
        self.refresh_icons()
        self.openChanged.emit(open_)

    def _fit(self, open_: bool) -> None:
        """Show the list, or hide it and keep the pane no taller than its header."""
        self.view.setVisible(open_)
        if open_:
            self.setMaximumHeight(NO_MAX_PX)
        else:
            m = self._box.contentsMargins()
            self.setMaximumHeight(
                self.header.sizeHint().height() + m.top() + m.bottom()
            )
