from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QToolButton, QWidget


class EditWithButton(QWidget):
    """A line edit with a small button beside it."""

    def __init__(self, button: str, placeholder: str, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.button = QToolButton()
        self.button.setText(button)
        h.addWidget(self.edit)
        h.addWidget(self.button)
