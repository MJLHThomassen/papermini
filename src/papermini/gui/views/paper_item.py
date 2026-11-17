from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsRectItem

from .. import theme


class PaperItem(QGraphicsRectItem):
    """A white sheet with a soft shadow of constant on-screen size.

    The shadow is painted as a few stacked translucent rounded rectangles rather than
    with QGraphicsDropShadowEffect: an effect renders and blurs the whole item off-screen
    at the current zoom, which took seconds per repaint when zoomed in far.
    """

    BLUR_PX, OFFSET_PX, STEPS = 14.0, 3.0, 7
    MAX_MM = 8.0  # shadow never reaches further than this (bounding rect)

    def __init__(self, r: QRectF, reach: float = MAX_MM):
        """``reach``: how far the shadow may go, in scene units (mm on the paper views,
        image pixels on the Source view)."""
        super().__init__(r)
        self._reach = reach
        self.setPen(QPen(Qt.NoPen))
        self.setBrush(QBrush(Qt.white))
        self.setZValue(-1)

    def boundingRect(self) -> QRectF:
        m = self._reach
        return self.rect().adjusted(-m, -m, m, m)

    def paint(self, p: QPainter, option, widget=None):
        s = max(abs(p.worldTransform().m11()), 1e-6)  # device px per scene unit
        blur = min(self.BLUR_PX / s, 0.7 * self._reach)
        off = min(self.OFFSET_PX / s, 0.3 * self._reach)
        h = theme.current.shadow.lstrip("#")  # RRGGBBAA
        total = int(h[6:8], 16) / 255.0
        a = 1.0 - (1.0 - total) ** (1.0 / self.STEPS)  # layers add up to ``total``
        c = QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        c.setAlphaF(a)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        r = self.rect().translated(0, off)
        for k in range(self.STEPS, 0, -1):
            e = blur * k / self.STEPS
            p.drawRoundedRect(r.adjusted(-e, -e, e, e), e, e)
        p.setBrush(Qt.white)
        p.drawRect(self.rect())
