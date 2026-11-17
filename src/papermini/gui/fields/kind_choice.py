from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QRadioButton, QWidget


class KindChoice(QWidget):
    """Standing mini or token: two radio buttons in a row."""

    valueChanged = Signal(str)
    KINDS = (("mini", "Standing mini"), ("token", "Token"))

    def __init__(self, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for value, text in self.KINDS:
            b = QRadioButton(text)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b)
            self.buttons[value] = b
            h.addWidget(b)
            b.toggled.connect(lambda on, v=value: on and self.valueChanged.emit(v))
        h.addStretch(1)
        self.buttons["mini"].setChecked(True)

    def value(self) -> str:
        return next(v for v, b in self.buttons.items() if b.isChecked())

    def setValue(self, v: str) -> None:
        self.buttons.get(v, self.buttons["mini"]).setChecked(True)
