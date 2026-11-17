from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem, QGraphicsView

from .. import theme
from .crop_style import (
    _HANDLE_CURSORS,
    CROP_COLOR,
    CROP_HINT,
    DRAG_PX,
    GRAB_PX,
    HANDLE_PX,
    WASH_ALPHA,
)
from .paper_item import PaperItem
from .zoom_view import ZoomView


class CropView(ZoomView):
    """Source image with the detected figure outlined and an editable crop box.

    The outline is what background removal found, before any margin or tab (those
    belong to the miniature); everything outside it is washed out. While a model runs
    (``set_busy``) the image is dimmed and the old outline hidden.

    Drag on the image to draw a box. Afterwards drag its corner/edge handles to
    resize it, drag inside it to move it, or drag outside it to draw a new one.
    Delete/Backspace clears it, Esc cancels a drag. Wheel zooms, middle mouse
    button pans.

    So this is clear without reading a manual: while there is no box, a hint on the
    image says to drag one; under the mouse, guide lines show where a new box would
    start, and the part of the box that a drag would grab (a handle, an edge, or the
    whole box) lights up. A click, or a press that barely moves, changes nothing.
    """

    cropChanged = Signal(object)  # [x0, y0, x1, y1] fractions, or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._img_size = None
        self._pix_item = None  # the picture (its pixmap may be smaller)
        self._box: QRectF | None = None  # image pixels
        self._rect_item: QGraphicsRectItem | None = None
        self._shade: QGraphicsPathItem | None = None
        self._handles: dict = {}
        self._drag = None  # (mode, start scene pos, box at start)
        self._pan = None
        self._outline = None  # list of point arrays, image pixels
        self._outline_items: list = []
        self._busy = False
        self._hover = None  # view position of the mouse over the image, or None
        self._hover_part = None  # what a drag from there would grab (see _hit)
        self._press = None  # view position of the left press, for DRAG_PX
        self._moved = False  # the press became a drag
        self.viewport().setCursor(Qt.CrossCursor)

    # region image / box
    def set_image(self, img: QImage | None, size=None):
        """Show ``img``; ``size`` (w, h) is the original image's, when ``img`` is a smaller
        preview of it: the view keeps working in the original's pixels (crop, outline)."""
        sc = self.scene()
        sc.clear()
        self._rect_item = self._shade = None
        self._handles = {}
        self._outline, self._outline_items = (
            None,
            [],
        )  # a new image: its outline comes later
        self._box = None
        self._drag = None
        if img is None or img.isNull():
            self._img_size = None
            return
        self._img_size = tuple(size) if size else (img.width(), img.height())
        # on paper with a soft shadow, like the Miniature and Print sheet views (the
        # reach in image pixels: enough for the shadow at the fitted zoom)
        sc.addItem(
            PaperItem(QRectF(0, 0, *self._img_size), reach=0.05 * max(self._img_size))
        )
        self._pix_item = sc.addPixmap(QPixmap())
        self._pix_item.setTransformationMode(Qt.SmoothTransformation)
        self.replace_picture(img)
        sc.setSceneRect(QRectF(0, 0, *self._img_size))
        self.refit_on_next_show()
        self.fit()

    def replace_picture(self, img: QImage):
        """Show another picture of the same image (e.g. with other color adjustments),
        keeping the crop box, outline and zoom; drawn at the original's size."""
        if self._img_size is None or img is None or img.isNull():
            return
        self._pix_item.setPixmap(QPixmap.fromImage(img))
        W, H = self._img_size
        self._pix_item.setTransform(
            QTransform.fromScale(W / img.width(), H / img.height())
        )

    def picture_size(self):
        """Size of the picture shown (smaller than the image for an adjusted preview)."""
        pm = self._pix_item.pixmap() if self._img_size is not None else None
        return None if pm is None or pm.isNull() else (pm.width(), pm.height())

    # endregion

    # region outline
    def set_outline(self, contours):
        """Show the detected figure: outer edges and holes as point arrays in image
        pixels, or None (not known yet)."""
        self._outline = (
            None if contours is None else [np.asarray(c, float) for c in contours]
        )
        self._draw_outline()

    def set_busy(self, busy: bool):
        """Background removal is running: dim the image, hide the outdated outline."""
        if busy != self._busy:
            self._busy = busy
            self._draw_outline()

    def refresh_theme(self):
        self._draw_outline()

    def _draw_outline(self):
        sc = self.scene()
        for it in self._outline_items:
            sc.removeItem(it)
        self._outline_items = []
        if self._img_size is None:
            return
        t = theme.current
        W, H = self._img_size
        area = QPainterPath()
        area.addRect(QRectF(0, 0, W, H))
        wash = QColor(t.canvas)
        if self._busy or not self._outline:
            if self._busy:
                wash.setAlpha(110)
                dim = sc.addPath(area, QPen(Qt.NoPen), QBrush(wash))
                dim.setZValue(0.5)
                self._outline_items = [dim]
            return
        figure = QPainterPath()
        figure.setFillRule(
            Qt.OddEvenFill
        )  # holes are separate contours inside the outline
        for c in self._outline:
            figure.moveTo(*c[0])
            for x, y in c[1:]:
                figure.lineTo(x, y)
            figure.closeSubpath()
        wash.setAlpha(WASH_ALPHA)
        shade = sc.addPath(area.subtracted(figure), QPen(Qt.NoPen), QBrush(wash))
        shade.setZValue(0.5)
        pen = QPen(QColor(t.accent), 2)
        pen.setCosmetic(True)
        pen.setJoinStyle(Qt.RoundJoin)
        line = sc.addPath(figure, pen)
        line.setZValue(0.6)
        self._outline_items = [shade, line]

    def set_crop(self, crop):
        """Show ``crop`` (fractions/px list or string); ignored while dragging."""
        from ...pipeline.segmentation.segment import parse_crop

        if self._img_size is None or self._drag is not None:
            return
        W, H = self._img_size
        try:
            box = parse_crop(crop, W, H)
        except ValueError:
            box = None
        self._set_box(
            QRectF(box[0], box[1], box[2] - box[0], box[3] - box[1]) if box else None
        )

    def crop_box(self) -> QRectF | None:
        return QRectF(self._box) if self._box is not None else None

    def _set_box(self, r: QRectF | None):
        self._box = r
        if self._img_size is None:
            return
        if r is None:
            for it in [self._rect_item, self._shade, *self._handles.values()]:
                if it is not None:
                    it.setVisible(False)
            return
        sc = self.scene()
        if self._shade is None:
            self._shade = sc.addPath(
                QPainterPath(), QPen(Qt.NoPen), QBrush(QColor(0, 0, 0, 120))
            )
            self._shade.setZValue(1)
            pen = QPen(QColor(CROP_COLOR), 2)
            pen.setCosmetic(True)
            pen.setStyle(Qt.DashLine)
            self._rect_item = sc.addRect(QRectF(), pen)
            self._rect_item.setZValue(2)
            for name in ("tl", "t", "tr", "r", "br", "b", "bl", "l"):
                h = sc.addRect(
                    QRectF(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX),
                    QPen(QColor("#222"), 1),
                    QBrush(QColor(CROP_COLOR)),
                )
                h.setFlag(
                    QGraphicsRectItem.ItemIgnoresTransformations
                )  # constant screen size
                h.setZValue(3)
                self._handles[name] = h
        outer = QPainterPath()
        outer.addRect(QRectF(0, 0, *self._img_size))
        inner = QPainterPath()
        inner.addRect(r)
        self._shade.setPath(outer.subtracted(inner))
        self._rect_item.setRect(r)
        for name, pos in self._handle_points(r).items():
            self._handles[name].setPos(pos)
        for it in [self._rect_item, self._shade, *self._handles.values()]:
            it.setVisible(True)

    @staticmethod
    def _handle_points(r: QRectF) -> dict:
        c = r.center()
        return {
            "tl": r.topLeft(),
            "t": QPointF(c.x(), r.top()),
            "tr": r.topRight(),
            "r": QPointF(r.right(), c.y()),
            "br": r.bottomRight(),
            "b": QPointF(c.x(), r.bottom()),
            "bl": r.bottomLeft(),
            "l": QPointF(r.left(), c.y()),
        }

    # endregion

    # region hit testing
    def _hit(self, view_pos) -> str:
        """Part of the box under ``view_pos``: a handle name, "move" or "new"."""
        if self._box is None:
            return "new"
        best, best_d = None, GRAB_PX + 1
        for name, p in self._handle_points(self._box).items():
            v = self.mapFromScene(p)
            d = max(abs(v.x() - view_pos.x()), abs(v.y() - view_pos.y()))
            if d < best_d:
                best, best_d = name, d
        if best is not None:
            return best
        # anywhere along an edge also grabs that edge
        tl = self.mapFromScene(self._box.topLeft())
        br = self.mapFromScene(self._box.bottomRight())
        x, y = view_pos.x(), view_pos.y()
        along_x = tl.x() - GRAB_PX <= x <= br.x() + GRAB_PX
        along_y = tl.y() - GRAB_PX <= y <= br.y() + GRAB_PX
        if along_y and abs(x - tl.x()) <= GRAB_PX:
            return "l"
        if along_y and abs(x - br.x()) <= GRAB_PX:
            return "r"
        if along_x and abs(y - tl.y()) <= GRAB_PX:
            return "t"
        if along_x and abs(y - br.y()) <= GRAB_PX:
            return "b"
        if tl.x() < x < br.x() and tl.y() < y < br.y():
            return "move"
        return "new"

    def _clamp_point(self, p: QPointF) -> QPointF:
        W, H = self._img_size
        return QPointF(min(max(p.x(), 0.0), W), min(max(p.y(), 0.0), H))

    def _dragged_box(self, scene_pos: QPointF) -> QRectF:
        mode, start, box0 = self._drag
        W, H = self._img_size
        p = self._clamp_point(scene_pos)
        if mode == "new" or box0 is None:
            return QRectF(self._clamp_point(start), p).normalized()
        if mode == "move":
            r = box0.translated(scene_pos - start)
            dx = -r.left() if r.left() < 0 else (W - r.right() if r.right() > W else 0)
            dy = -r.top() if r.top() < 0 else (H - r.bottom() if r.bottom() > H else 0)
            return r.translated(dx, dy)
        left, top, right, bottom = box0.left(), box0.top(), box0.right(), box0.bottom()
        if "l" in mode:
            left = p.x()
        if "r" in mode:
            right = p.x()
        if "t" in mode:
            top = p.y()
        if "b" in mode:
            bottom = p.y()
        return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()

    # endregion

    # region mouse / keys
    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        if e.button() == Qt.MiddleButton:
            self._pan = pos
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if e.button() == Qt.LeftButton and self._img_size:
            box0 = QRectF(self._box) if self._box is not None else None
            self._drag = (self._hit(pos), self.mapToScene(pos), box0)
            self._press, self._moved = pos, False
            self.viewport().update()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._pan is not None:
            d = pos - self._pan
            self._pan = pos
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - d.x()
            )
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            return
        if self._drag is not None:
            if not self._moved:  # not a drag until the mouse really moves
                d = pos - self._press
                if max(abs(d.x()), abs(d.y())) < DRAG_PX:
                    return
                self._moved = True
            self._set_box(self._dragged_box(self.mapToScene(pos)))
            return
        if self._img_size:
            part = self._hit(pos)
            self.viewport().setCursor(_HANDLE_CURSORS.get(part, Qt.CrossCursor))
            on_image = self._image_view_rect().contains(QPointF(pos))
            self._hover = pos if on_image or part != "new" else None
            self._hover_part = part if self._hover is not None else None
            self.viewport().update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._hover = self._hover_part = None
        self.viewport().update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton and self._pan is not None:
            self._pan = None
            self.viewport().setCursor(Qt.CrossCursor)
            return
        if e.button() == Qt.LeftButton and self._drag is not None:
            r = self._dragged_box(self.mapToScene(e.position().toPoint()))
            old = self._drag[2]
            self._drag = None
            self.viewport().update()
            if not self._moved:  # a click: never a change (and never a model run)
                self._set_box(old)
                return
            if r.width() < 10 or r.height() < 10:
                self._set_box(old)  # a click or a tiny box: keep what was there
                return
            self._set_box(r)
            if old is None or r != old:
                self.cropChanged.emit(self._fractions(r))
            return
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self._box is not None:
            self._drag = None
            self._set_box(None)
            self.cropChanged.emit(None)
            return
        if e.key() == Qt.Key_Escape and self._drag is not None:
            old = self._drag[2]
            self._drag = None
            self._set_box(old)
            self.viewport().update()
            return
        super().keyPressEvent(e)

    # endregion

    # region guidance
    def _image_view_rect(self) -> QRectF:
        """The image on screen (view coordinates)."""
        if self._img_size is None:
            return QRectF()
        return QRectF(self.mapFromScene(QRectF(0, 0, *self._img_size)).boundingRect())

    def show_hint(self) -> bool:
        """The "drag a box" hint is shown: an image without a crop box, not dragging."""
        return self._img_size is not None and self._box is None and self._drag is None

    def drawForeground(self, painter: QPainter, rect: QRectF):
        if self._img_size is None:
            return
        painter.save()
        painter.resetTransform()  # screen pixels: lines and text keep their size at any zoom
        painter.setRenderHint(QPainter.Antialiasing)
        img = self._image_view_rect().intersected(QRectF(self.viewport().rect()))
        part = self._hover_part if self._drag is None else None
        if part == "new" and self._hover is not None:
            # where a new box would start: guide lines across the image
            c = QColor(CROP_COLOR)
            c.setAlpha(200)
            painter.setPen(QPen(c, 1, Qt.DashLine))
            x, y = self._hover.x() + 0.5, self._hover.y() + 0.5
            painter.drawLine(QPointF(img.left(), y), QPointF(img.right(), y))
            painter.drawLine(QPointF(x, img.top()), QPointF(x, img.bottom()))
        elif part and self._box is not None:
            # the part of the box a drag would grab
            box = QRectF(self.mapFromScene(self._box).boundingRect())
            hi = QColor(CROP_COLOR)
            if part == "move":
                hi.setAlpha(45)
                painter.fillRect(box, hi)
            else:
                painter.setPen(QPen(hi, 3))
                edges = {
                    "l": (box.topLeft(), box.bottomLeft()),
                    "r": (box.topRight(), box.bottomRight()),
                    "t": (box.topLeft(), box.topRight()),
                    "b": (box.bottomLeft(), box.bottomRight()),
                }
                if part in edges:
                    painter.drawLine(*edges[part])
                pt = QPointF(self.mapFromScene(self._handle_points(self._box)[part]))
                painter.setPen(QPen(QColor("#ffffff"), 2))
                painter.setBrush(Qt.NoBrush)
                h = HANDLE_PX / 2 + 4
                painter.drawRect(QRectF(pt.x() - h, pt.y() - h, 2 * h, 2 * h))
        if self.show_hint() and not img.isEmpty():
            pill = self.hint_rect()
            t = theme.current
            painter.setFont(self._hint_font())
            painter.setPen(QPen(QColor(t.border), 1))
            painter.setBrush(QColor(t.surface))
            painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            painter.setPen(QColor(t.text))
            painter.drawText(pill, int(Qt.AlignCenter), CROP_HINT)
        painter.restore()

    def _hint_font(self) -> QFont:
        f = QFont(self.font())
        f.setPointSizeF(f.pointSizeF() * 1.05)
        return f

    def hint_rect(self) -> QRectF:
        """Where the "drag a box" hint goes (view coordinates): just above the image,
        so it never covers it; below it when there is no room above; on top of it
        only when the image fills the whole view."""
        from PySide6.QtGui import QFontMetricsF

        fm = QFontMetricsF(self._hint_font())
        w, h = fm.horizontalAdvance(CROP_HINT) + 28, fm.height() + 14
        img, vp, gap = self._image_view_rect(), QRectF(self.viewport().rect()), 8
        if img.top() - gap - h >= vp.top() + 4:
            y = img.top() - gap - h  # above the image
        elif img.bottom() + gap + h <= vp.bottom() - 4:
            y = img.bottom() + gap  # below it
        else:
            y = max(img.top(), vp.top()) + 16  # no room outside: on the image
        cx = img.intersected(vp).center().x()
        return QRectF(cx - w / 2, y, w, h)

    def _fractions(self, r: QRectF) -> list:
        W, H = self._img_size
        return [
            round(r.left() / W, 4),
            round(r.top() / H, 4),
            round(r.right() / W, 4),
            round(r.bottom() / H, 4),
        ]

    # endregion
