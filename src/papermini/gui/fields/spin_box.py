from __future__ import annotations

from PySide6.QtWidgets import QSpinBox

from .wheel_guard import _WheelGuard


class SpinBox(_WheelGuard, QSpinBox):
    """A whole-number field that ignores the mouse wheel until it has focus."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_guard()
        self.setKeyboardTracking(False)
        self.lineEdit().setTextMargins(5, 0, 0, 0)  # line up with combo box text
