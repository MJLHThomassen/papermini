from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene

from ...output.sheet_layout import (
    BAR_ABOVE_MM,
    BAR_END_TICK_MM,
    BAR_LABEL,
    BAR_LABEL_DROP_MM,
    BAR_LABEL_GAP_MM,
    BAR_MM,
    BAR_TICK_MM,
    BAR_TICK_STEP_MM,
    BAR_TICK_WIDTH_MM,
    BAR_WIDTH_MM,
    INSTRUCTIONS_BASELINE_MM,
    INSTRUCTIONS_LINE_MM,
    TITLE_BASELINE_MM,
    SheetLayout,
)
from .mini_renderer import MiniRenderer


class SheetRenderer:
    """Draws the sheet in a scene in mm, as the PDF prints it, and prints it."""

    PAGE_GAP_MM = 12.0

    def __init__(self, minis: MiniRenderer) -> None:
        self._minis = minis

    def draw(
        self,
        scene: QGraphicsScene,
        lay: SheetLayout,
        title: str,
        pixmaps: dict | None = None,
    ) -> list[QRectF]:
        """Draw all pages of the sheet stacked vertically, as the PDF prints them, and
        return the page rectangles."""
        scene.clear()
        pw, ph = lay.paper
        pages = []
        for page in range(lay.pages):
            r = QRectF(0, page * (ph + self.PAGE_GAP_MM), pw, ph)
            self._draw_page(scene, lay, title, page, r)
            pages.append(r)
        for p in lay.placements:
            pm = (pixmaps or {}).get(
                id(p.mini.art)
            )  # (numbered copies share their art)
            self._minis.draw(
                scene,
                p.mini,
                p.x,
                p.page * (ph + self.PAGE_GAP_MM) + p.y,
                pm,
                cut_line=not lay.machine,
            )
        return pages

    def print_sheet(self, printer, lay: SheetLayout, title: str) -> int:
        """Print the sheet at its real size (1 mm on the sheet = 1 mm on paper), the
        pages chosen in the print dialog or all of them. Return the number of pages
        printed.

        ``printer`` must be set to full page, so the drawing starts at the paper's corner
        like the PDF; scaling to the printable area would make the minis the wrong size.
        """
        scene = QGraphicsScene()
        pages = self.draw(scene, lay, title)
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

    def _draw_page(
        self, scene: QGraphicsScene, lay: SheetLayout, title: str, page: int, r: QRectF
    ) -> None:
        """Draw the paper of ``page`` in ``r``, with its marks, header and scale bar."""
        margin_mm, hx, oy = lay.margin_mm, lay.header_x, r.top()
        text = self._minis.add_text
        self._minis.add_paper(scene, r)
        for x, y, w, h in lay.mark_rects():  # alignment marks (cut by machine)
            scene.addRect(
                QRectF(x, oy + y, w, h), QPen(Qt.NoPen), QBrush(QColor("#000"))
            )
        text(
            scene,
            title,
            3.9,
            "#000",
            "Arial",
            hx,
            oy + margin_mm + TITLE_BASELINE_MM,
            anchor="left",
            bold=True,
        )
        for i, line in enumerate(lay.instructions()):
            text(
                scene,
                line,
                2.6,
                "#000",
                "Arial",
                hx,
                oy + margin_mm + INSTRUCTIONS_BASELINE_MM + INSTRUCTIONS_LINE_MM * i,
                anchor="left",
            )
        if lay.pages > 1:
            text(
                scene,
                f"page {page + 1}/{lay.pages}",
                2.6,
                "#000",
                "Arial",
                lay.header_right - 16,
                oy + margin_mm + TITLE_BASELINE_MM,
                anchor="left",
            )
        cy = oy + margin_mm + lay.header_mm - BAR_ABOVE_MM
        pen = QPen(QColor("#000"), BAR_WIDTH_MM)
        scene.addLine(hx, cy, hx + BAR_MM, cy, pen)
        thin = QPen(QColor("#000"), BAR_TICK_WIDTH_MM)
        for t in range(0, BAR_MM + 1, BAR_TICK_STEP_MM):
            h = BAR_END_TICK_MM if t % BAR_MM == 0 else BAR_TICK_MM
            scene.addLine(hx + t, cy - h, hx + t, cy + h, thin)
        text(
            scene,
            BAR_LABEL,
            2.4,
            "#000",
            "Arial",
            hx + (BAR_MM + BAR_LABEL_GAP_MM),
            cy + BAR_LABEL_DROP_MM,
            anchor="left",
        )
