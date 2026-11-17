"""Spinner: a small turning arc that shows something is being worked on."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import theme


class Spinner(QWidget):
    """A small turning arc: something is being worked on. Turns only while shown."""

    def __init__(self, size: int = 22, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self, interval=50, timeout=self._turn)

    def _turn(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def showEvent(self, e):
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        track = QColor(theme.current.border)
        p.setPen(QPen(track, 3))
        p.drawEllipse(r)
        pen = QPen(QColor(theme.current.accent), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, -self._angle * 16, 100 * 16)
