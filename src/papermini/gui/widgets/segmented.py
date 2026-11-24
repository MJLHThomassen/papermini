from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton

from ..theme_service import ThemeService


class Segmented(QFrame):
    """A row of mutually exclusive buttons (a segmented control). With ``steps`` the
    buttons are numbered workflow steps with a chevron between them; any step can
    still be picked at any time."""

    changed = Signal(int)

    def __init__(self, themes: ThemeService, labels, parent=None, steps: bool = False):
        super().__init__(parent)
        self._themes = themes
        self.setObjectName("Segmented")
        h = QHBoxLayout(self)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._chevrons = []
        for i, (text, tip) in enumerate(labels):
            if steps and i:
                arrow = QLabel()
                arrow.setObjectName("StepArrow")
                self._chevrons.append(arrow)
                h.addWidget(arrow)
            b = QPushButton(f"{i + 1}  {text}" if steps else text)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.group.addButton(b, i)
            h.addWidget(b)
        self.group.idClicked.connect(self.changed)
        self.group.button(0).setChecked(True)
        self.refresh_icons()

    def refresh_icons(self):
        for arrow in self._chevrons:
            arrow.setPixmap(
                self._themes.pixmap("chevron_right", self._themes.current.muted, 14)
            )

    def set_index(self, i: int):
        self.group.button(i).setChecked(True)
