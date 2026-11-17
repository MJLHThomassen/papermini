from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout

from .model_info import _label


class CacheCard(QFrame):
    """A kind of cached file on the Models and cache page: what it is, how much there
    is, and Clear."""

    def __init__(self, title: str, about: str, clear):
        super().__init__()
        self.setObjectName("ModelCard")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 14, 12)
        h.setSpacing(14)
        v = QVBoxLayout()
        v.setSpacing(3)
        v.addWidget(_label(f"<b>{html.escape(title)}</b>"))
        v.addWidget(_label(html.escape(about), "Muted"))
        self.state = _label("", "Hint")
        v.addWidget(self.state)
        h.addLayout(v, 1)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setAccessibleName(f"Clear {title.lower()}")
        self.btn_clear.clicked.connect(clear)
        h.addWidget(self.btn_clear, 0, Qt.AlignVCenter)

    def show_state(self, text: str, can_clear: bool):
        self.state.setText(text)
        self.btn_clear.setEnabled(can_clear)
