"""ComboBox: a drop-down list that ignores the mouse wheel until it has focus."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox

from .wheel_guard import _WheelGuard


class ComboBox(_WheelGuard, QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_guard()
        # long item names must not widen the settings panel (the list still shows them)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)
