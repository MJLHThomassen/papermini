from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider

from ..theme_service import ThemeService
from .wheel_guard import _WheelGuard

SNAP_PX = 6  # a dragged centred slider snaps to its centre within this many pixels
MARK_RADIUS_PX = 2.5  # the dot that marks each value of a slider with marks


class Slider(_WheelGuard, QSlider):
    """A horizontal slider. With a ``centre`` (a range from below to above it, like
    -100..100 around 0) it fills from that centre instead of from the left, marks it with
    a short vertical line, snaps to it while dragged close by, and goes back to it on a
    double-click. With ``marks`` each of its values gets a dot on the groove."""

    def __init__(
        self,
        themes: ThemeService,
        parent=None,
        centre: int | None = None,
        marks: bool = False,
    ):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._themes = themes
        self._init_guard()
        self.centre = centre
        self.marks = marks
        if centre is not None:
            self.setProperty(
                "centred", True
            )  # the style sheet leaves the fill to paintEvent
            self.actionTriggered.connect(self._snap)

    def _snap(self, action: int) -> None:
        if (
            action != QSlider.SliderAction.SliderMove.value or not self.isSliderDown()
        ):  # (an int)
            return  # keys, clicks on the track and typed values are taken as they are
        assert self.centre is not None  # (connected only with a centre)
        span = max(1, self.width() - self.handle_rect(self.minimum()).width())
        reach = SNAP_PX * (self.maximum() - self.minimum()) / span
        if abs(self.sliderPosition() - self.centre) <= reach:
            self.setSliderPosition(self.centre)

    def mouseDoubleClickEvent(self, e):
        if self.centre is not None and e.button() == Qt.MouseButton.LeftButton:
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

    def handle_rect(self, position):
        """Return the rectangle of the handle with the slider at ``position``."""
        return self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            self._option(position),
            QStyle.SubControl.SC_SliderHandle,
            self,
        )

    def centre_x(self) -> float:
        return self._value_x(self.centre)

    def _value_x(self, value) -> float:
        """Return the x of the middle of the handle with the slider at ``value``."""
        return self.handle_rect(value).center().x() + 0.5

    def paintEvent(self, e):
        if self.centre is None and not self.marks:
            return super().paintEvent(e)
        st, p = self.style(), QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        opt = self._option()
        opt.subControls = QStyle.SubControl.SC_SliderGroove
        st.drawComplexControl(QStyle.ComplexControl.CC_Slider, opt, p, self)
        t = self._themes.current
        cy = self.rect().center().y() + 0.5
        # the fill: from the centre, or from the lowest value
        start = self._value_x(self.minimum() if self.centre is None else self.centre)
        vx = self._value_x(self.sliderPosition())
        fill = QColor(t.accent if self.isEnabled() else t.muted)
        p.fillRect(QRectF(min(start, vx), cy - 2, abs(vx - start), 4), fill)
        if self.centre is not None:
            p.setPen(QPen(QColor(t.muted), 1.5))
            p.drawLine(
                QPointF(start, cy - 6), QPointF(start, cy + 6)
            )  # the centre mark
        if self.marks:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.muted))
            for value in range(self.minimum(), self.maximum() + 1):
                x = self._value_x(value)
                p.drawEllipse(QPointF(x, cy), MARK_RADIUS_PX, MARK_RADIUS_PX)
        opt.subControls = QStyle.SubControl.SC_SliderHandle
        st.drawComplexControl(QStyle.ComplexControl.CC_Slider, opt, p, self)
        p.end()
