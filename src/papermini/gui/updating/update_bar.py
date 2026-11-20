from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton


class UpdateBar(QFrame):
    """The bar under the window's header that announces a new version or a downloaded
    update, with buttons for the release page and for updating or restarting."""

    releasePageRequested = Signal()
    actionRequested = Signal()  # the update or restart button was clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UpdateBar")
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 6, 10, 6)
        h.setSpacing(10)
        self._text = QLabel()
        self._text.setObjectName("UpdateText")
        h.addWidget(self._text, 1)
        notes = QPushButton("What's new")
        notes.clicked.connect(self.releasePageRequested)
        self._action = QPushButton("Restart now")
        self._action.setProperty("primary", True)
        self._action.clicked.connect(self.actionRequested)
        close = QToolButton()
        close.setText("✕")
        close.setToolTip("Hide")
        close.clicked.connect(self.hide)
        for w in (notes, self._action, close):
            w.setCursor(Qt.PointingHandCursor)
            h.addWidget(w)
        self.hide()

    def show_available(self, version: str) -> None:
        """Announce papermini ``version``, with a button to update to it."""
        self._text.setText(f"papermini {version} is available.")
        self._action.setText("Update…")
        self.show()

    def show_ready(self, version: str) -> None:
        """Announce that papermini ``version`` is installed on closing, with a button
        to restart now."""
        self._action.setText("Restart now")
        self._text.setText(
            f"papermini {version} is ready: it is installed when you close papermini."
        )
        self.show()
