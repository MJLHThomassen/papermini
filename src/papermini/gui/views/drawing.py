"""Draws miniatures and sheets in mm, as they print, and prints the sheet."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
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

from ... import fonts
from ...geometry import CutPath
from ...mini import Mini
from ...sheet import SheetLayout
from .images import pil_to_qimage
from .paper_item import PaperItem


def print_sheet(printer, lay: SheetLayout, title: str) -> int:
    """Print the sheet at its real size (1 mm on the sheet = 1 mm on paper), the pages
    chosen in the print dialog or all of them. Returns the number of pages printed.

    ``printer`` must be set to full page, so the drawing starts at the paper's corner
    like the PDF; scaling to the printable area would make the minis the wrong size.
    """
    from PySide6.QtWidgets import QGraphicsScene

    scene = QGraphicsScene()
    pages = draw_sheet(scene, lay, title)
    first, last = printer.fromPage(), printer.toPage()  # 1-based; 0 = all pages
    chosen = [
        r
        for i, r in enumerate(pages, 1)
        if not first or first <= i <= (last or len(pages))
    ]
    k = printer.resolution() / 25.4  # device pixels per mm
    p = QPainter()
    if not chosen or not p.begin(printer):
        return 0
    try:
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        for n, r in enumerate(chosen):
            if n:
                printer.newPage()
            scene.render(p, QRectF(0, 0, r.width() * k, r.height() * k), r)
    finally:
        p.end()
    return len(chosen)


PAGE_GAP_MM = 12.0


_qt_families: dict = {}


def qt_family(name: str) -> str:
    """The font family Qt draws a miniature's font with: Times New Roman for Times, else
    the font's own files (registered once), so the app shows what the PDF prints."""
    if name not in _qt_families:
        font, _ = fonts.resolve(name)
        family = "Times New Roman"
        if font.regular is not None:
            found = []
            for path in (font.regular, font.bold):
                if path is not None:
                    fid = QFontDatabase.addApplicationFont(str(path))
                    found += (
                        QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                    )
            family = found[0] if found else font.name
        _qt_families[name] = family
    return _qt_families[name]


def _text(
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
):
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


def draw_mini(
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
    pm = pixmap or QPixmap.fromImage(pil_to_qimage(m.art))
    art = QGraphicsPixmapItem(pm)
    art.setTransformationMode(Qt.SmoothTransformation)
    art.setTransform(
        QTransform.fromScale(m.width_mm / pm.width(), m.height_mm / pm.height())
    )
    art.setPos(x, y)
    scene.addItem(art)

    pen = QPen(QColor(st.fold_color), st.fold_width_mm)
    pen.setDashPattern([1.2 / st.fold_width_mm, 0.8 / st.fold_width_mm])
    for x0, x1, fy in m.folds:
        scene.addLine(x + x0, y + fy, x + x1, y + fy, pen)
    family = qt_family(st.font)
    for t in m.text_items():  # labels, numbers and the back text
        _text(
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
    cut = QGraphicsPathItem(cut_painter_path(m, x, y))
    pen = QPen(QColor(st.cut_color), st.cut_width_mm)
    pen.setJoinStyle(Qt.RoundJoin)
    cut.setPen(pen)
    scene.addItem(cut)


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


def draw_sheet(
    scene: QGraphicsScene, lay: SheetLayout, title: str, pixmaps: dict | None = None
) -> list[QRectF]:
    """All pages of the sheet stacked vertically, as the PDF prints them; returns the
    page rectangles."""
    scene.clear()
    pw, ph = lay.paper
    margin_mm, hx = lay.margin_mm, lay.header_x
    pages = []
    for page in range(lay.pages):
        oy = page * (ph + PAGE_GAP_MM)
        r = QRectF(0, oy, pw, ph)
        _paper(scene, r)
        pages.append(r)
        for x, y, w, h in lay.mark_rects():  # alignment marks (cut by machine)
            scene.addRect(
                QRectF(x, oy + y, w, h), QPen(Qt.NoPen), QBrush(QColor("#000"))
            )
        _text(
            scene,
            title,
            3.9,
            "#000",
            "Arial",
            hx,
            oy + margin_mm + 4,
            anchor="left",
            bold=True,
        )
        for i, line in enumerate(lay.instructions()):
            _text(
                scene,
                line,
                2.6,
                "#000",
                "Arial",
                hx,
                oy + margin_mm + 8.5 + 3.4 * i,
                anchor="left",
            )
        if lay.pages > 1:
            _text(
                scene,
                f"page {page + 1}/{lay.pages}",
                2.6,
                "#000",
                "Arial",
                lay.header_right - 16,
                oy + margin_mm + 4,
                anchor="left",
            )
        cy = oy + margin_mm + lay.header_mm - 4
        pen = QPen(QColor("#000"), 0.4)
        scene.addLine(hx, cy, hx + 50, cy, pen)
        thin = QPen(QColor("#000"), 0.2)
        for t in range(0, 51, 10):
            h = 1.6 if t % 50 == 0 else 1.0
            scene.addLine(hx + t, cy - h, hx + t, cy + h, thin)
        _text(scene, "50 mm", 2.4, "#000", "Arial", hx + 52, cy + 1, anchor="left")
    for p in lay.placements:
        pm = (pixmaps or {}).get(id(p.mini.art))  # (numbered copies share their art)
        draw_mini(
            scene,
            p.mini,
            p.x,
            p.page * (ph + PAGE_GAP_MM) + p.y,
            pm,
            cut_line=not lay.machine,
        )
    return pages
