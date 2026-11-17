from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider

from .. import theme
from .wheel_guard import _WheelGuard

SNAP_PX = 6  # a dragged centred slider snaps to its centre within this many pixels


class Slider(_WheelGuard, QSlider):
    """A horizontal slider. With a ``centre`` (a range from below to above it, like
    -100..100 around 0) it fills from that centre instead of from the left, marks it with
    a short vertical line, snaps to it while dragged close by, and goes back to it on a
    double-click."""

    def __init__(self, parent=None, centre=None):
        super().__init__(Qt.Horizontal, parent)
        self._init_guard()
        self.centre = centre
        if centre is not None:
            self.setProperty(
                "centred", True
            )  # the style sheet leaves the fill to paintEvent
            self.actionTriggered.connect(self._snap)

    def _snap(self, action: int) -> None:
        if action != QSlider.SliderMove.value or not self.isSliderDown():  # (an int)
            return  # keys, clicks on the track and typed values are taken as they are
        span = max(1, self.width() - self._handle_rect(self.minimum()).width())
        reach = SNAP_PX * (self.maximum() - self.minimum()) / span
        if abs(self.sliderPosition() - self.centre) <= reach:
            self.setSliderPosition(self.centre)

    def mouseDoubleClickEvent(self, e):
        if self.centre is not None and e.button() == Qt.LeftButton:
            self.setValue(self.centre)
            e.accept()
        else:
            super().mouseDoubleClickEvent(e)

    def _option(self, position=None) -> QStyleOptionSlider:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        if position is not None:
            opt.sliderPosition = opt.sliderValue = position
        return opt

    def _handle_rect(self, position):
        return self.style().subControlRect(
            QStyle.CC_Slider, self._option(position), QStyle.SC_SliderHandle, self
        )

    def centre_x(self) -> float:
        return self._handle_rect(self.centre).center().x() + 0.5

    def paintEvent(self, e):
        if self.centre is None:
            return super().paintEvent(e)
        st, p = self.style(), QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        opt = self._option()
        opt.subControls = QStyle.SC_SliderGroove
        st.drawComplexControl(QStyle.CC_Slider, opt, p, self)
        t = theme.current
        cy = self.rect().center().y() + 0.5
        cx = self.centre_x()
        vx = self._handle_rect(self.sliderPosition()).center().x() + 0.5
        fill = QColor(t.accent if self.isEnabled() else t.muted)
        p.fillRect(QRectF(min(cx, vx), cy - 2, abs(vx - cx), 4), fill)
        p.setPen(QPen(QColor(t.muted), 1.5))
        p.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))  # the centre mark
        opt.subControls = QStyle.SC_SliderHandle
        st.drawComplexControl(QStyle.CC_Slider, opt, p, self)
        p.end()
