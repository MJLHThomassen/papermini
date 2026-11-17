from __future__ import annotations

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QDoubleSpinBox

from .wheel_guard import _WheelGuard


def _point_locale() -> QLocale:
    """Numbers with a "." decimal point and no thousands separators, whatever the
    system locale: the same as the command line, project files and crop field."""
    loc = QLocale.c()
    loc.setNumberOptions(QLocale.OmitGroupSeparator | QLocale.RejectGroupSeparator)
    return loc


class DoubleSpinBox(_WheelGuard, QDoubleSpinBox):
    """Shows and accepts "." as the decimal point; a typed "," becomes "." too."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_guard()
        self.setLocale(_point_locale())
        self.setKeyboardTracking(False)
        self.lineEdit().setTextMargins(5, 0, 0, 0)  # line up with combo box text

    def validate(self, text, pos):
        return super().validate(text.replace(",", "."), pos)

    def fixup(self, text):
        return super().fixup(text.replace(",", "."))

    def valueFromText(self, text):
        return super().valueFromText(text.replace(",", "."))
