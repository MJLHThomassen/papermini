"""ColorButton: a button that shows a color and opens a color picker."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QPushButton


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = "#000000"
        self.clicked.connect(self._pick)
        self.setFixedWidth(90)

    def color(self) -> str:
        return self._color

    def set_color(self, c: str):
        self._color = c
        fg = "#fff" if QColor(c).lightness() < 128 else "#000"
        self.setText(c)
        # scoped to this button: an unscoped style sheet is inherited by child widgets,
        # which painted the whole color dialog in the selected color
        self.setStyleSheet(
            f"QPushButton {{ background: {c}; color: {fg}; border-radius: 6px; "
            f"border: 1px solid rgba(128, 128, 128, 0.45); padding: 3px 8px; "
            f"font-family: Consolas, monospace; }}"
        )

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self.window(), "Color")
        if c.isValid():
            self.set_color(c.name())
            self.colorChanged.emit(c.name())
