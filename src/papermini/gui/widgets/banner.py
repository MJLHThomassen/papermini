from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from .. import theme


class Banner(QFrame):
    """A message card on top of the canvas (e.g. why a miniature could not be built)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ErrorBanner")
        self.setMaximumWidth(560)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 16, 12)
        h.setSpacing(12)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignTop)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        h.addWidget(self.icon)
        h.addWidget(self.text, 1)

    def show_message(self, title: str, body: str):
        self.icon.setPixmap(theme.pixmap("warning", theme.current.danger, 20))
        self.text.setText(
            f"<p style='margin:0'><b>{title}</b></p>{body}"
        )  # (a list may follow)
        self.show()
