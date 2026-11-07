"""Graphics views: zoomable viewer, miniature/sheet drawing (in mm), crop editor."""

from __future__ import annotations

from typing import List, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QImageReader, QPainter, QPainterPath,
                           QPen, QPixmap, QTransform)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
                               QGraphicsView)

from . import theme

from ..geometry import CutPath
from ..mini import Mini
from ..sheet import INSTRUCTIONS, INSTRUCTIONS_DOUBLE, SheetLayout

PAGE_GAP_MM = 12.0


def pil_to_qimage(im) -> QImage:
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    return QImage(data, im.width, im.height, 4 * im.width, QImage.Format_RGBA8888).copy()


def array_to_qimage(a: np.ndarray) -> QImage:
    a = np.ascontiguousarray(a)
    h, w = a.shape[:2]
    if a.ndim == 2:
        return QImage(a.data, w, h, w, QImage.Format_Grayscale8).copy()
    return QImage(a.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def load_qimage(path) -> QImage:
    """Load an image with EXIF orientation applied (matches PIL's exif_transpose)."""
    r = QImageReader(str(path))
    r.setAutoTransform(True)
    return r.read()


# --------------------------------------------------------------------------- viewer

class ZoomView(QGraphicsView):
    """Wheel zoom around the cursor, fit-to-view and actual-size (1 scene unit = 1 mm).

    Draws a quiet dot grid behind the paper in the current theme's colours.
    """

    zoomChanged = Signal(float)  # 1.0 = actual size

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform
                            | QPainter.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)  # the dot grid is screen-fixed
        self._fit_pending = True

    def drawBackground(self, painter: QPainter, rect: QRectF):
        t = theme.current
        painter.save()
        painter.resetTransform()
        vp = self.viewport().rect()
        painter.fillRect(vp, QColor(t.canvas))
        pen = QPen(QColor(t.dots), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        step = 18
        ox = -self.horizontalScrollBar().value() % step
        oy = -self.verticalScrollBar().value() % step
        pts = [QPointF(x, y) for y in range(oy, vp.height(), step) for x in range(ox, vp.width(), step)]
        painter.drawPoints(pts)
        painter.restore()

    def zoom(self) -> float:
        return self.transform().m11() / (self.physicalDpiX() / 25.4)

    def _changed(self):
        self.zoomChanged.emit(self.zoom())

    def zoom_by(self, f: float):
        s = self.transform().m11() * f
        if 0.05 < s < 400:
            anchor = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
            self.scale(f, f)
            self.setTransformationAnchor(anchor)
        self._fit_pending = False
        self._changed()

    def wheelEvent(self, e):
        f = 1.2 ** (e.angleDelta().y() / 120)
        s = self.transform().m11() * f
        if 0.05 < s < 400:
            self.scale(f, f)
        self._fit_pending = False
        self._changed()

    def fit(self):
        r = self.scene().itemsBoundingRect()
        if not r.isEmpty():
            m = max(r.width(), r.height()) * 0.06
            self.fitInView(r.adjusted(-m, -m, m, m), Qt.KeepAspectRatio)
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


def _text(scene: QGraphicsScene, text: str, size_mm: float, color: str, family: str,
          x: float, y: float, rot: float = 0.0, anchor: str = "center", bold=False):
    """Add text ``size_mm`` high at (x, y) in mm. anchor: center (middle) or left (baseline-ish)."""
    item = QGraphicsSimpleTextItem(text)
    f = QFont(family)
    f.setPixelSize(100)
    f.setBold(bold)
    item.setFont(f)
    item.setBrush(QColor(color))
    br = item.boundingRect()
    k = size_mm / 100  # pixel size = em height, like the font size in the PDF/SVG
    t = QTransform()
    t.translate(x, y)
    t.rotate(rot)
    t.scale(k, k)
    if anchor == "center":
        t.translate(-br.width() / 2, -br.height() / 2)
    else:
        t.translate(0, -br.height() * 0.8)
    item.setTransform(t)
    scene.addItem(item)
    return item


def qpath(cut: CutPath, x: float = 0.0, y: float = 0.0) -> QPainterPath:
    """A closed cut path as a QPainterPath, moved by (x, y)."""
    p = QPainterPath()
    pts = cut.points
    p.moveTo(x + pts[0, 0], y + pts[0, 1])
    n = len(pts)
    for i in range(n):
        q = pts[(i + 1) % n]
        if cut.controls is None:
            p.lineTo(x + q[0], y + q[1])
        else:
            c1, c2 = cut.controls[i]
            p.cubicTo(x + c1[0], y + c1[1], x + c2[0], y + c2[1], x + q[0], y + q[1])
    p.closeSubpath()
    return p


def cut_painter_path(m: Mini, x: float = 0.0, y: float = 0.0) -> QPainterPath:
    return qpath(m.cut, x, y)


def draw_mini(scene: QGraphicsScene, m: Mini, x: float = 0.0, y: float = 0.0,
              pixmap: Optional[QPixmap] = None) -> None:
    """Draw a miniature exactly as printed, top-left at (x, y) mm."""
    st = m.style
    pm = pixmap or QPixmap.fromImage(pil_to_qimage(m.art))
    art = QGraphicsPixmapItem(pm)
    art.setTransformationMode(Qt.SmoothTransformation)
    art.setTransform(QTransform.fromScale(m.width_mm / pm.width(), m.height_mm / pm.height()))
    art.setPos(x, y)
    scene.addItem(art)

    pen = QPen(QColor(st.fold_color), st.fold_width_mm)
    pen.setDashPattern([1.2 / st.fold_width_mm, 0.8 / st.fold_width_mm])
    for x0, x1, fy in m.folds:
        scene.addLine(x + x0, y + fy, x + x1, y + fy, pen)
    if m.label:
        for cx, cy, rot in m.labels:
            _text(scene, m.label, m.label_size_mm, st.label_color, "Times New Roman",
                  x + cx, y + cy, rot)
    for text, cx, cy, rot, size in m.texts:
        _text(scene, text, size, st.back_text_color, "Times New Roman", x + cx, y + cy, rot)
    cut = QGraphicsPathItem(cut_painter_path(m, x, y))
    pen = QPen(QColor(st.cut_color), st.cut_width_mm)
    pen.setJoinStyle(Qt.RoundJoin)
    cut.setPen(pen)
    scene.addItem(cut)


class PaperItem(QGraphicsRectItem):
    """A white sheet with a soft shadow of constant on-screen size.

    The shadow is painted as a few stacked translucent rounded rectangles rather than
    with QGraphicsDropShadowEffect: an effect renders and blurs the whole item off-screen
    at the current zoom, which took seconds per repaint when zoomed in far.
    """

    BLUR_PX, OFFSET_PX, STEPS = 14.0, 3.0, 7
    MAX_MM = 8.0  # shadow never reaches further than this (bounding rect)

    def __init__(self, r: QRectF):
        super().__init__(r)
        self.setPen(QPen(Qt.NoPen))
        self.setBrush(QBrush(Qt.white))
        self.setZValue(-1)

    def boundingRect(self) -> QRectF:
        m = self.MAX_MM
        return self.rect().adjusted(-m, -m, m, m)

    def paint(self, p: QPainter, option, widget=None):
        s = max(abs(p.worldTransform().m11()), 1e-6)       # device px per mm
        blur = min(self.BLUR_PX / s, 0.7 * self.MAX_MM)
        off = min(self.OFFSET_PX / s, 0.3 * self.MAX_MM)
        h = theme.current.shadow.lstrip("#")              # RRGGBBAA
        total = int(h[6:8], 16) / 255.0
        a = 1.0 - (1.0 - total) ** (1.0 / self.STEPS)    # layers add up to ``total``
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


def _paper(scene: QGraphicsScene, r: QRectF) -> QGraphicsRectItem:
    """A white sheet with a soft shadow."""
    item = PaperItem(r)
    scene.addItem(item)
    return item


def draw_mini_page(scene: QGraphicsScene, m: Mini) -> None:
    """A single miniature on a bit of white paper."""
    scene.clear()
    pad = 6.0
    _paper(scene, QRectF(-pad, -pad, m.width_mm + 2 * pad, m.height_mm + 2 * pad))
    draw_mini(scene, m)
    # 10 mm scale bar under the piece
    yb = m.height_mm + pad * 0.55
    pen = QPen(QColor("#333"), 0.3)
    scene.addLine(0, yb, 10, yb, pen)
    for t in (0, 10):
        scene.addLine(t, yb - 0.8, t, yb + 0.8, pen)
    _text(scene, "10 mm", 2.0, "#333", "Arial", 12, yb + 0.7, anchor="left")


def draw_sheet(scene: QGraphicsScene, lay: SheetLayout, title: str,
               margin_mm: float = 12.0, pixmaps: Optional[dict] = None) -> List[QRectF]:
    """All pages of the sheet stacked vertically; returns the page rectangles."""
    scene.clear()
    pw, ph = lay.paper
    pages = []
    double = any(len(p.mini.labels) > 1 or len(p.mini.folds) > 1 for p in lay.placements)
    for page in range(lay.pages):
        oy = page * (ph + PAGE_GAP_MM)
        r = QRectF(0, oy, pw, ph)
        _paper(scene, r)
        pages.append(r)
        _text(scene, title, 3.9, "#000", "Arial", margin_mm, oy + margin_mm + 4,
              anchor="left", bold=True)
        lines = INSTRUCTIONS + ([INSTRUCTIONS_DOUBLE] if double else [])
        for i, line in enumerate(lines):
            _text(scene, line, 2.6, "#000", "Arial", margin_mm, oy + margin_mm + 8.5 + 3.4 * i,
                  anchor="left")
        if lay.pages > 1:
            _text(scene, f"page {page + 1}/{lay.pages}", 2.6, "#000", "Arial",
                  pw - margin_mm - 16, oy + margin_mm + 4, anchor="left")
        cy = oy + margin_mm + lay.header_mm - 4
        pen = QPen(QColor("#000"), 0.4)
        scene.addLine(margin_mm, cy, margin_mm + 50, cy, pen)
        thin = QPen(QColor("#000"), 0.2)
        for t in range(0, 51, 10):
            h = 1.6 if t % 50 == 0 else 1.0
            scene.addLine(margin_mm + t, cy - h, margin_mm + t, cy + h, thin)
        _text(scene, "50 mm", 2.4, "#000", "Arial", margin_mm + 52, cy + 1, anchor="left")
    for p in lay.placements:
        pm = (pixmaps or {}).get(id(p.mini))
        draw_mini(scene, p.mini, p.x, p.page * (ph + PAGE_GAP_MM) + p.y, pm)
    return pages


# --------------------------------------------------------------------------- crop editor

HANDLE_PX = 10  # handle size on screen
GRAB_PX = 8     # how close (on screen) the mouse must be to grab a handle or edge

_HANDLE_CURSORS = {
    "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
    "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
    "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
    "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
    "move": Qt.SizeAllCursor,
}


class CropView(ZoomView):
    """Source image with the cut line on it and an editable crop box.

    Outside the cut line the image is washed out: that is what gets cut away.

    Drag on the image to draw a box. Afterwards drag its corner/edge handles to
    resize it, drag inside it to move it, or drag outside it to draw a new one.
    Delete/Backspace clears it, Esc cancels a drag. Wheel zooms, middle mouse
    button pans.
    """

    cropChanged = Signal(object)  # [x0, y0, x1, y1] fractions, or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._img_size = None
        self._box: Optional[QRectF] = None         # image pixels
        self._rect_item: Optional[QGraphicsRectItem] = None
        self._shade: Optional[QGraphicsPathItem] = None
        self._handles: dict = {}
        self._drag = None                           # (mode, start scene pos, box at start)
        self._pan = None
        self._cut = None                            # (CutPath, folds) in image pixels
        self._cut_items: list = []
        self.viewport().setCursor(Qt.CrossCursor)

    # ----------------------------------------------------------------- image / box
    def set_image(self, img: Optional[QImage]):
        sc = self.scene()
        sc.clear()
        self._rect_item = self._shade = None
        self._handles = {}
        self._cut, self._cut_items = None, []  # a new image: its cut line comes with its build
        self._box = None
        self._drag = None
        if img is None or img.isNull():
            self._img_size = None
            return
        self._img_size = (img.width(), img.height())
        item = sc.addPixmap(QPixmap.fromImage(img))
        item.setTransformationMode(Qt.SmoothTransformation)
        sc.setSceneRect(QRectF(0, 0, *self._img_size))
        self.refit_on_next_show()
        self.fit()

    # ----------------------------------------------------------------- cut line
    def set_cut(self, cut: Optional[CutPath], folds=(), top: float = 0.0):
        """Show the cut line (and fold lines) of the built piece, in image pixels.
        Above row ``top`` the piece is a double-sided back, not this image."""
        self._cut = None if cut is None else (cut, list(folds), top)
        self._draw_cut()

    def refresh_theme(self):
        self._draw_cut()

    def _draw_cut(self):
        sc = self.scene()
        for it in self._cut_items:
            sc.removeItem(it)
        self._cut_items = []
        if self._img_size is None or self._cut is None:
            return
        cut, folds, top = self._cut
        t = theme.current
        W, H = self._img_size
        area = QPainterPath()
        area.addRect(QRectF(0, 0, W, H))
        front = QRectF(0, top, W, max(0.0, H - top))
        kept = QPainterPath()
        kept.addRect(front)
        inside = qpath(cut)
        wash = QColor(t.canvas)
        wash.setAlpha(200)
        shade = sc.addPath(area.subtracted(inside.intersected(kept)), QPen(Qt.NoPen),
                           QBrush(wash))
        shade.setZValue(0.5)
        # the cut line is clipped to the image (a tab can reach past its edge) and to
        # the front side: a double-sided back is the mirrored front, not this image
        clip = sc.addRect(front, QPen(Qt.NoPen))
        clip.setFlag(QGraphicsItem.ItemClipsChildrenToShape)
        clip.setZValue(0.6)
        pen = QPen(QColor(t.accent), 2)
        pen.setCosmetic(True)
        QGraphicsPathItem(inside, clip).setPen(pen)
        # folds on the image (the top fold of a double-sided piece lies on the clip edge,
        # so they are drawn unclipped, limited to the image width)
        fold = QPen(QColor(t.accent), 1.5, Qt.DashLine)
        fold.setCosmetic(True)
        lines = QPainterPath()
        for x0, x1, y in folds:
            if top - 0.5 <= y <= H and x1 > 0 and x0 < W:
                lines.moveTo(max(0.0, x0), y)
                lines.lineTo(min(float(W), x1), y)
        fold_item = sc.addPath(lines, fold)
        fold_item.setZValue(0.7)
        self._cut_items = [shade, clip, fold_item]

    def set_crop(self, crop):
        """Show ``crop`` (fractions/px list or string); ignored while dragging."""
        from ..segment import parse_crop

        if self._img_size is None or self._drag is not None:
            return
        W, H = self._img_size
        try:
            box = parse_crop(crop, W, H)
        except ValueError:
            box = None
        self._set_box(QRectF(box[0], box[1], box[2] - box[0], box[3] - box[1]) if box else None)

    def crop_box(self) -> Optional[QRectF]:
        return QRectF(self._box) if self._box is not None else None

    def _set_box(self, r: Optional[QRectF]):
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
            self._shade = sc.addPath(QPainterPath(), QPen(Qt.NoPen), QBrush(QColor(0, 0, 0, 120)))
            self._shade.setZValue(1)
            pen = QPen(QColor("#ffd400"), 2)
            pen.setCosmetic(True)
            pen.setStyle(Qt.DashLine)
            self._rect_item = sc.addRect(QRectF(), pen)
            self._rect_item.setZValue(2)
            for name in ("tl", "t", "tr", "r", "br", "b", "bl", "l"):
                h = sc.addRect(QRectF(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX),
                               QPen(QColor("#222"), 1), QBrush(QColor("#ffd400")))
                h.setFlag(QGraphicsRectItem.ItemIgnoresTransformations)  # constant screen size
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
        return {"tl": r.topLeft(), "t": QPointF(c.x(), r.top()), "tr": r.topRight(),
                "r": QPointF(r.right(), c.y()), "br": r.bottomRight(),
                "b": QPointF(c.x(), r.bottom()), "bl": r.bottomLeft(),
                "l": QPointF(r.left(), c.y())}

    # ----------------------------------------------------------------- hit testing
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

    # ----------------------------------------------------------------- mouse / keys
    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        if e.button() == Qt.MiddleButton:
            self._pan = pos
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if e.button() == Qt.LeftButton and self._img_size:
            box0 = QRectF(self._box) if self._box is not None else None
            self._drag = (self._hit(pos), self.mapToScene(pos), box0)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._pan is not None:
            d = pos - self._pan
            self._pan = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
            return
        if self._drag is not None:
            self._set_box(self._dragged_box(self.mapToScene(pos)))
            return
        if self._img_size:
            self.viewport().setCursor(_HANDLE_CURSORS.get(self._hit(pos), Qt.CrossCursor))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton and self._pan is not None:
            self._pan = None
            self.viewport().setCursor(Qt.CrossCursor)
            return
        if e.button() == Qt.LeftButton and self._drag is not None:
            r = self._dragged_box(self.mapToScene(e.position().toPoint()))
            old = self._drag[2]
            self._drag = None
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
            return
        super().keyPressEvent(e)

    def _fractions(self, r: QRectF) -> list:
        W, H = self._img_size
        return [round(r.left() / W, 4), round(r.top() / H, 4),
                round(r.right() / W, 4), round(r.bottom() / H, 4)]
