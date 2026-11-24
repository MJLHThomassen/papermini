from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from ...pipeline.cut_path import CutPath
from ...pipeline.mini import Mini
from ...pipeline.style import FOLD_DASH_MM, FOLD_GAP_MM
from ...support.font_library import FontLibrary
from ..theme_service import ThemeService
from .paper_item import PaperItem
from .qt_fonts import QtFonts
from .qt_images import QtImages


class MiniRenderer:
    """Draws miniatures in a scene in mm, as they print, and the paper and text around
    them."""

    PAGE_PAD_MM = 6.0  # the paper around a single miniature
    BAR_MM = 10  # the scale bar under a single miniature

    def __init__(
        self,
        fonts: FontLibrary,
        qt_fonts: QtFonts,
        themes: ThemeService,
        images: QtImages,
    ) -> None:
        self._fonts = fonts
        self._qt_fonts = qt_fonts
        self._themes = themes
        self._images = images

    def draw(
        self,
        scene: QGraphicsScene,
        m: Mini,
        x: float = 0.0,
        y: float = 0.0,
        pixmap: QPixmap | None = None,
        cut_line: bool = True,
    ) -> None:
        """Draw a miniature exactly as printed, top-left at (x, y) mm (on a sheet cut by
        machine without its cut line)."""
        st = m.style
        pm = pixmap or QPixmap.fromImage(self._images.from_pil(m.art))
        art = QGraphicsPixmapItem(pm)
        art.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        art.setTransform(
            QTransform.fromScale(m.width_mm / pm.width(), m.height_mm / pm.height())
        )
        art.setPos(x, y)
        scene.addItem(art)

        pen = QPen(QColor(st.fold_color), st.fold_width_mm)
        pen.setDashPattern(
            [FOLD_DASH_MM / st.fold_width_mm, FOLD_GAP_MM / st.fold_width_mm]
        )
        for x0, x1, fy in m.folds:
            scene.addLine(x + x0, y + fy, x + x1, y + fy, pen)
        family = self._qt_fonts.family(st.font)
        for t in m.text_items(self._fonts):  # labels, numbers and the back text
            self.add_text(
                scene,
                t.text,
                t.size_mm,
                t.color,
                family,
                x + t.cx,
                y + t.cy,
                t.rot,
                bold=t.bold,
            )
        if not cut_line or not st.cut_line:
            return
        cut = QGraphicsPathItem(self._cut_path(m.cut, x, y))
        pen = QPen(QColor(st.cut_color), st.cut_width_mm)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        cut.setPen(pen)
        scene.addItem(cut)

    def draw_page(self, scene: QGraphicsScene, m: Mini) -> None:
        """Draw a single miniature on a bit of white paper, with a scale bar under it."""
        scene.clear()
        pad = self.PAGE_PAD_MM
        self.add_paper(
            scene, QRectF(-pad, -pad, m.width_mm + 2 * pad, m.height_mm + 2 * pad)
        )
        self.draw(scene, m)
        yb = m.height_mm + pad * 0.55
        pen = QPen(QColor("#333"), 0.3)
        scene.addLine(0, yb, self.BAR_MM, yb, pen)
        for t in (0, self.BAR_MM):
            scene.addLine(t, yb - 0.8, t, yb + 0.8, pen)
        self.add_text(scene, "10 mm", 2.0, "#333", "Arial", 12, yb + 0.7, anchor="left")

    def add_paper(self, scene: QGraphicsScene, r: QRectF) -> QGraphicsRectItem:
        """Add a white sheet with a soft shadow, the rectangle ``r`` in mm."""
        item = PaperItem(self._themes, r)
        scene.addItem(item)
        return item

    def add_text(
        self,
        scene: QGraphicsScene,
        text: str,
        size_mm: float,
        color: str,
        family: str,
        x: float,
        y: float,
        rot: float = 0.0,
        anchor: str = "center",
        bold=False,
    ) -> QGraphicsSimpleTextItem:
        """Add text ``size_mm`` high at (x, y) in mm. anchor: center (middle) or left
        (baseline-ish)."""
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

    @staticmethod
    def _cut_path(cut: CutPath, x: float, y: float) -> QPainterPath:
        """Return a closed cut path as a QPainterPath, moved by (x, y)."""
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
                p.cubicTo(
                    x + c1[0], y + c1[1], x + c2[0], y + c2[1], x + q[0], y + q[1]
                )
        p.closeSubpath()
        return p
