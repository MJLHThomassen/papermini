from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QRadioButton, QWidget


class KindChoice(QWidget):
    """A radio button in a row for each kind of figure; the first is checked."""

    valueChanged = Signal(str)

    def __init__(self, kinds: Iterable[tuple[str, str]], parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for value, text in kinds:
            b = QRadioButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b)
            self.buttons[value] = b
            h.addWidget(b)
            b.toggled.connect(lambda on, v=value: on and self.valueChanged.emit(v))
        h.addStretch(1)
        self._first = next(iter(self.buttons))
        self.buttons[self._first].setChecked(True)

    def value(self) -> str:
        return next(v for v, b in self.buttons.items() if b.isChecked())

    def setValue(self, v: str) -> None:
        self.buttons.get(v, self.buttons[self._first]).setChecked(True)
