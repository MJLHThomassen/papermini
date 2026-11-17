from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel

from .. import theme
from .crop_style import CROP_COLOR, WASH_ALPHA


class SourceLegend(QFrame):
    """What the marks on the Source view mean, drawn with the same colors: the
    detected outline, the faded background and the crop area. The texts never change
    (how to draw a crop box is the hint on the view itself)."""

    SW = 26  # swatch width (px)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Legend")
        g = QGridLayout(self)
        g.setContentsMargins(10, 8, 12, 8)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(4)
        self.swatches, self.texts = [], []
        for row, text in enumerate(
            ("Detected outline", "Removed background", "Crop area")
        ):
            sw, lab = QLabel(), QLabel(text)
            g.addWidget(sw, row, 0)
            g.addWidget(lab, row, 1)
            self.swatches.append(sw)
            self.texts.append(lab)
        self.refresh_theme()

    def refresh_theme(self):
        t = theme.current
        dpr = self.devicePixelRatioF() or 1.0
        for i, sw in enumerate(self.swatches):
            pm = QPixmap(int(self.SW * dpr), int(14 * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            r = QRectF(2, 2, self.SW - 4, 10)
            if i == 0:  # the outline, in the accent color
                pen = QPen(QColor(t.accent), 2)
                p.setPen(pen)
                p.drawRoundedRect(r, 4, 4)
            elif i == 1:  # an image, faded the way the background is
                p.setPen(Qt.NoPen)
                for k, c in enumerate(("#7a9e5a", "#c9a46a", "#6b8fbf")):
                    p.setBrush(QColor(c))
                    p.drawRect(
                        QRectF(
                            r.left() + k * r.width() / 3,
                            r.top(),
                            r.width() / 3,
                            r.height(),
                        )
                    )
                wash = QColor(t.canvas)
                wash.setAlpha(WASH_ALPHA)
                p.setBrush(wash)
                p.drawRect(r)
            else:  # the dashed crop box with a handle
                pen = QPen(QColor(CROP_COLOR), 1.5, Qt.DashLine)
                p.setPen(pen)
                p.drawRect(r)
                p.setPen(QPen(QColor("#222"), 1))
                p.setBrush(QColor(CROP_COLOR))
                p.drawRect(QRectF(r.right() - 2.5, r.bottom() - 2.5, 5, 5))
            p.end()
            sw.setPixmap(pm)
