"""ZoomBar: floating zoom controls for the canvas."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton

from .. import theme


class ZoomBar(QFrame):
    """Floating zoom controls for the canvas."""

    zoomIn = Signal()
    zoomOut = Signal()
    fit = Signal()
    actual = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ZoomBar")
        h = QHBoxLayout(self)
        h.setContentsMargins(4, 3, 4, 3)
        h.setSpacing(0)
        self.buttons = {}
        for name, tip, sig in (("zoom_out", "Zoom out", self.zoomOut),):
            h.addWidget(self._button(name, tip, sig))
        self.label = QLabel("100%")
        self.label.setMinimumWidth(44)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setToolTip("Zoom (100% = actual size)")
        h.addWidget(self.label)
        for name, tip, sig in (
            ("zoom_in", "Zoom in", self.zoomIn),
            ("fit", "Fit to window  (Ctrl+0)", self.fit),
        ):
            h.addWidget(self._button(name, tip, sig))
        one = QToolButton()
        one.setText("1:1")
        one.setToolTip("Actual size  (Ctrl+1)")
        one.setAccessibleName("Actual size")
        one.clicked.connect(self.actual)
        one.setCursor(Qt.PointingHandCursor)
        h.addWidget(one)

    def _button(self, name, tip, sig):
        b = QToolButton()
        b.setToolTip(tip)
        b.setAccessibleName(tip.split("  (")[0])
        b.setIconSize(QSize(16, 16))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(sig)
        self.buttons[name] = b
        return b

    def refresh_icons(self):
        for name, b in self.buttons.items():
            b.setIcon(theme.icon(name, theme.current.text, 16))

    def set_zoom(self, z: float):
        self.label.setText(f"{z * 100:.0f}%")
