from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QTransform
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from ..theme_service import ThemeService


class ZoomView(QGraphicsView):
    """Wheel zoom around the cursor, fit-to-view and actual-size (1 scene unit = 1 mm).

    Draws a quiet dot grid behind the paper in the current theme's colors.
    """

    zoomChanged = Signal(float)  # 1.0 = actual size

    # how far the view zooms, in screen pixels per scene unit
    MIN_SCALE = 0.05
    MAX_SCALE = 400

    def __init__(self, themes: ThemeService, parent=None):
        super().__init__(parent)
        self._themes = themes
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )  # the dot grid is screen-fixed
        self._fit_pending = True

    def drawBackground(self, painter: QPainter, rect: QRectF):
        t = self._themes.current
        painter.save()
        painter.resetTransform()
        vp = self.viewport().rect()
        painter.fillRect(vp, QColor(t.canvas))
        pen = QPen(QColor(t.dots), 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        step = 18
        ox = -self.horizontalScrollBar().value() % step
        oy = -self.verticalScrollBar().value() % step
        pts = [
            QPointF(x, y)
            for y in range(oy, vp.height(), step)
            for x in range(ox, vp.width(), step)
        ]
        painter.drawPoints(pts)
        painter.restore()

    def zoom(self) -> float:
        return self.transform().m11() / (self.physicalDpiX() / 25.4)

    def _changed(self):
        self.zoomChanged.emit(self.zoom())

    def _can_scale_by(self, f: float) -> bool:
        return self.MIN_SCALE < self.transform().m11() * f < self.MAX_SCALE

    def zoom_by(self, f: float):
        if self._can_scale_by(f):
            anchor = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
            self.scale(f, f)
            self.setTransformationAnchor(anchor)
        self._fit_pending = False
        self._changed()

    def wheelEvent(self, e):
        f = 1.2 ** (e.angleDelta().y() / 120)
        if self._can_scale_by(f):
            self.scale(f, f)
        self._fit_pending = False
        self._changed()

    def fit(self):
        r = self.scene().itemsBoundingRect()
        if not r.isEmpty():
            m = max(r.width(), r.height()) * 0.06
            self.fitInView(r.adjusted(-m, -m, m, m), Qt.AspectRatioMode.KeepAspectRatio)
            self._changed()

    def actual_size(self):
        """1 mm in the scene = 1 mm on screen (as far as the OS reports the DPI)."""
        px_per_mm = self.physicalDpiX() / 25.4
        self.setTransform(QTransform.fromScale(px_per_mm, px_per_mm))
        self._fit_pending = False
        self._changed()

    def refit_on_next_show(self):
        self._fit_pending = True

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fit_pending:
            self.fit()

    def showEvent(self, e):
        super().showEvent(e)
        if self._fit_pending:
            self.fit()
