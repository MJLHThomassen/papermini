"""WorkCard: a card on the canvas for slow work, with a Cancel button."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import theme
from .elided_label import ElidedLabel
from .spinner import Spinner


class WorkCard(QFrame):
    """A card in the middle of the canvas for slow work: what is happening, how long
    it has taken, and a button (Cancel while working, Run again once cancelled)."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WorkCard")
        self.setMinimumWidth(440)  # room for a figure name before it ends in "…"
        self.setMaximumWidth(520)
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 14, 14, 14)
        h.setSpacing(14)
        self.spinner = Spinner()
        self.icon = QLabel()
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = ElidedLabel()  # (a long figure name ends in "…")
        self.title.setObjectName("WorkTitle")
        self.detail = ElidedLabel()
        self.detail.setObjectName("Muted")
        text.addWidget(self.title)
        text.addWidget(self.detail)
        self.button = QPushButton()
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.clicked)
        h.addWidget(self.spinner, 0, Qt.AlignVCenter)
        h.addWidget(self.icon, 0, Qt.AlignVCenter)
        h.addLayout(text, 1)
        h.addWidget(self.button, 0, Qt.AlignVCenter)

    def show_working(self, title: str, detail: str, button: str = "Cancel"):
        self.spinner.show()
        self.icon.hide()
        self._set(title, detail, button)

    def show_stopped(self, title: str, detail: str, button: str):
        self.spinner.hide()
        self.icon.setPixmap(theme.pixmap("warning", theme.current.muted, 20))
        self.icon.show()
        self._set(title, detail, button)

    def _set(self, title: str, detail: str, button: str):
        self.title.setText(title)
        self.detail.setText(detail)
        self.button.setText(button)
