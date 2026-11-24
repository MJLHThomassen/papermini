from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

# The mixin's host is a widget; the type checker sees that through this base.
_Host = QWidget if TYPE_CHECKING else object


class _WheelGuard(_Host):
    """Only react to the mouse wheel when focused, so scrolling the settings
    panel never changes a value by accident (and the panel scrolls instead)."""

    def _init_guard(self):
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()
