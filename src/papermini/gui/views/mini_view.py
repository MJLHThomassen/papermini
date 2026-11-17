from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
)

from .crop_style import _HANDLE_CURSORS, CROP_COLOR, DRAG_PX, GRAB_PX, HANDLE_PX
from .zoom_view import ZoomView


class MiniView(ZoomView):
    """The Miniature view. For a token it also frames the figure in the circle: a box
    around the figure with a handle on each corner. Drag inside the circle to move the
    figure, drag a corner to make it bigger or smaller (around the box's centre). On
    release the view emits the token area that frames the figure that way; while dragging,
    the figure (cut out of the picture, on the token's background) moves with the mouse.
    Esc cancels a drag, a click changes nothing; elsewhere the view pans and zooms as usual.
    """

    areaChanged = Signal(object)  # the token area [x0, y0, x1, y1] (fractions)

    CORNERS = ("tl", "tr", "br", "bl")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._token = None  # the shown token's TokenInfo (None: not a token)
        self._box: QRectF | None = None  # the figure's box, mm
        self._box_item = None
        self._handles: dict = {}
        self._drag = None  # (part, press scene pos, box at the press)
        self._press = None
        self._moved = False
        self._picture = None  # (picture, image size, figure outline, background)
        self._preview = None  # the figure shown while dragging

    def set_token(self, info, picture=None, size=None, outline=None, fill=None) -> None:
        """Show the framing of a token (its ``TokenInfo``), or none (``None``). ``picture``
        (a QImage of the image, or a smaller preview of an image of ``size``), the figure's
        ``outline`` (point arrays, image pixels) and ``fill`` (the token's background:
        ("color", "#rrggbb") or ("image", ...)) show the figure while it is dragged. Call
        after each redraw of the scene: the handles are scene items."""
        self._token = info
        self._drag = None
        self._box_item = None
        self._handles = {}
        self._preview = None
        self._picture = None
        if picture is not None and not picture.isNull():
            self._picture = (
                picture,
                tuple(size) if size else (picture.width(), picture.height()),
                outline or [],
                fill or ("color", "#ffffff"),
            )
        if info is None or info.figure_box is None:
            self._box = None
            self.viewport().unsetCursor()
            return
        x0, y0, x1, y1 = info.figure_box
        self._box = QRectF(QPointF(x0, y0), QPointF(x1, y1))
        sc = self.scene()
        pen = QPen(QColor(CROP_COLOR), 1.5)
        pen.setCosmetic(True)
        pen.setStyle(Qt.DashLine)
        self._box_item = sc.addRect(self._box, pen)
        self._box_item.setZValue(5)
        for name in self.CORNERS:
            h = sc.addRect(
                QRectF(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX),
                QPen(QColor("#222"), 1),
                QBrush(QColor(CROP_COLOR)),
            )
            h.setFlag(
                QGraphicsRectItem.ItemIgnoresTransformations
            )  # constant screen size
            h.setZValue(6)
            self._handles[name] = h
        self._show_box(self._box)

    def _corners(self, r: QRectF) -> dict:
        return {
            "tl": r.topLeft(),
            "tr": r.topRight(),
            "br": r.bottomRight(),
            "bl": r.bottomLeft(),
        }

    def _show_box(self, r: QRectF) -> None:
        if self._box_item is None:
            return
        self._box_item.setRect(r)
        for name, pos in self._corners(r).items():
            self._handles[name].setPos(pos)

    def _hit(self, view_pos) -> str | None:
        """What a drag from ``view_pos`` would do: a corner, "move", or None (pan)."""
        if self._box is None:
            return None
        for name, p in self._corners(self._box).items():
            v = self.mapFromScene(p)
            if max(abs(v.x() - view_pos.x()), abs(v.y() - view_pos.y())) <= GRAB_PX:
                return name
        t = self._token
        s = self.mapToScene(view_pos)
        if (s.x() - t.cx) ** 2 + (s.y() - t.cy) ** 2 <= t.radius_mm**2:
            return "move"
        return None

    def _dragged(self, scene_pos: QPointF) -> QRectF:
        part, start, box0 = self._drag
        if part == "move":
            return box0.translated(scene_pos - start)
        c = box0.center()
        d0 = max(1e-6, (self._corners(box0)[part] - c).manhattanLength())
        k = max(0.05, (scene_pos - c).manhattanLength() / d0)
        w, h = box0.width() * k, box0.height() * k
        return QRectF(c.x() - w / 2, c.y() - h / 2, w, h)

    def _show_preview(self, box: QRectF) -> None:
        """The figure in ``box`` while dragging: the picture cut out along the figure's
        outline, on the token's background, inside the ring."""
        if self._picture is None:
            return
        picture, (W, H), outline, (fill, color) = self._picture
        t = self._token
        if self._preview is None:
            circle = QPainterPath()
            circle.addEllipse(QPointF(t.cx, t.cy), t.inner_mm, t.inner_mm)
            clip = QGraphicsPathItem(circle)
            clip.setPen(QPen(Qt.NoPen))
            clip.setBrush(QColor(color) if fill == "color" else QColor("#ffffff"))
            clip.setFlag(QGraphicsItem.ItemClipsChildrenToShape)
            clip.setZValue(4)
            if fill == "color" and outline:
                figure = QPainterPath()
                figure.setFillRule(Qt.OddEvenFill)
                for c in outline:
                    figure.moveTo(*c[0])
                    for x, y in c[1:]:
                        figure.lineTo(x, y)
                    figure.closeSubpath()
                holder = QGraphicsPathItem(figure, clip)
            else:  # (the picture is the background too)
                holder = QGraphicsRectItem(QRectF(0, 0, W, H), clip)
            holder.setPen(QPen(Qt.NoPen))
            holder.setFlag(QGraphicsItem.ItemClipsChildrenToShape)
            pix = QGraphicsPixmapItem(QPixmap.fromImage(picture), holder)
            pix.setTransformationMode(Qt.SmoothTransformation)
            pix.setTransform(
                QTransform.fromScale(W / picture.width(), H / picture.height())
            )
            self.scene().addItem(clip)
            self._preview = (clip, holder)
        a = self.area_for(box)
        side = 2 * t.inner_mm
        sx, sy = side / ((a[2] - a[0]) * W), side / ((a[3] - a[1]) * H)
        self._preview[1].setTransform(
            QTransform(
                sx,
                0,
                0,
                sy,
                t.cx - t.inner_mm - a[0] * W * sx,
                t.cy - t.inner_mm - a[1] * H * sy,
            )
        )

    def _end_preview(self) -> None:
        if self._preview is not None:
            self.scene().removeItem(self._preview[0])
            self._preview = None

    def area_for(self, box: QRectF) -> list:
        """The token area that shows the figure in ``box`` (mm on the piece), where the
        shown area shows it in the box the token was built with."""
        t = self._token
        b0 = self._box
        k = box.width() / max(b0.width(), 1e-9)
        d = (box.center().x() - b0.center().x(), box.center().y() - b0.center().y())
        c0 = (b0.center().x(), b0.center().y())
        side = 2 * t.inner_mm
        left = (t.cx - t.inner_mm, t.cy - t.inner_mm)  # the circle's square, top-left
        out = []
        for i, (a0, a1) in enumerate(((t.area[0], t.area[2]), (t.area[1], t.area[3]))):
            aw = a1 - a0
            awn = aw / k
            # a picture point P (fraction) shows at k * ((P - a0) / aw * side + left - c0)
            # + c0 + d; in the new area that is (P - a0n) / awn * side + left
            off = k * (-a0 / aw * side + left[i] - c0[i]) + c0[i] + d[i] - left[i]
            a0n = -awn * off / side
            out.append((a0n, a0n + awn))
        (x0, x1), (y0, y1) = out
        return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        part = self._hit(pos) if e.button() == Qt.LeftButton else None
        if part is not None:
            self._drag = (part, self.mapToScene(pos), QRectF(self._box))
            self._press, self._moved = pos, False
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._drag is not None:
            if not self._moved:  # not a drag until the mouse really moves
                d = pos - self._press
                if max(abs(d.x()), abs(d.y())) < DRAG_PX:
                    return
                self._moved = True
            box = self._dragged(self.mapToScene(pos))
            self._show_box(box)
            self._show_preview(box)
            return
        part = self._hit(pos)
        if part is None:
            self.viewport().unsetCursor()
        else:
            self.viewport().setCursor(_HANDLE_CURSORS.get(part, Qt.SizeAllCursor))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._drag is not None:
            box = self._dragged(self.mapToScene(e.position().toPoint()))
            moved = self._moved
            self._drag = None
            if not moved:  # a click: never a change
                self._show_box(self._box)
                return
            # (the preview stays until the rebuilt token replaces it)
            self.areaChanged.emit(self.area_for(box))
            return
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self._drag is not None:
            self._drag = None
            self._show_box(self._box)
            self._end_preview()
            return
        super().keyPressEvent(e)
