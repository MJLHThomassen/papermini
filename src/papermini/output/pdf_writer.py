from __future__ import annotations

from pathlib import Path

from ..pipeline.style import FOLD_DASH_MM, FOLD_GAP_MM
from ..pipeline.text_item import TEXT_BASELINE_DROP
from ..support.font_library import FontLibrary
from .placement import Placement
from .sheet_layout import (
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
    TITLE,
    TITLE_BASELINE_MM,
    SheetLayout,
)


class PdfWriter:
    """Writes a sheet as a PDF to print, the pieces' text in their fonts from
    ``fonts``.

    Cut by hand, the PDF has the cut lines. Cut by machine, it has none: it gets
    alignment marks instead, and ``CutFileWriter`` writes the cut lines and the same
    marks to line up in the cutting machine's software.
    """

    def __init__(self, fonts: FontLibrary):
        self._fonts = fonts

    def write(self, layout: SheetLayout, out: Path, title: str = TITLE) -> Path:
        """Write the sheet to the PDF ``out``."""
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        pw, ph = layout.paper
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        c = canvas.Canvas(str(out), pagesize=(pw * mm, ph * mm))
        c.setTitle(title)
        c.setCreator("papermini")
        X = lambda v: v * mm
        Y = lambda v: (ph - v) * mm
        margin_mm, hx = layout.margin_mm, layout.header_x

        for page in range(layout.pages):
            c.setFillColorRGB(0, 0, 0)
            for x, y, w, h in layout.mark_rects():  # alignment marks (cut by machine)
                c.rect(X(x), Y(y + h), w * mm, h * mm, stroke=0, fill=1)
            # header
            c.setFont("Helvetica-Bold", 11)
            c.drawString(X(hx), Y(margin_mm + TITLE_BASELINE_MM), title)
            c.setFont("Helvetica", 7.5)
            for i, line in enumerate(layout.instructions()):
                c.drawString(
                    X(hx),
                    Y(margin_mm + INSTRUCTIONS_BASELINE_MM + INSTRUCTIONS_LINE_MM * i),
                    line,
                )
            if layout.pages > 1:
                c.drawRightString(
                    X(layout.header_right),
                    Y(margin_mm + TITLE_BASELINE_MM),
                    f"page {page + 1}/{layout.pages}",
                )
            # calibration bar
            cy = margin_mm + layout.header_mm - BAR_ABOVE_MM
            c.setLineWidth(BAR_WIDTH_MM * mm)
            c.line(X(hx), Y(cy), X(hx + BAR_MM), Y(cy))
            c.setLineWidth(BAR_TICK_WIDTH_MM * mm)
            for t in range(0, BAR_MM + 1, BAR_TICK_STEP_MM):
                h = BAR_END_TICK_MM if t % BAR_MM == 0 else BAR_TICK_MM
                c.line(X(hx + t), Y(cy - h), X(hx + t), Y(cy + h))
            c.setFont("Helvetica", 7)
            c.drawString(
                X(hx + (BAR_MM + BAR_LABEL_GAP_MM)),
                Y(cy + BAR_LABEL_DROP_MM),
                BAR_LABEL,
            )

            for p in layout.placements:
                if p.page == page:
                    self._draw_mini(
                        c, p, X, Y, mm, ImageReader, cut_line=not layout.machine
                    )
            c.showPage()
        c.save()
        return out

    def _draw_mini(
        self, c, p: Placement, X, Y, mm, ImageReader, cut_line: bool = True
    ) -> None:
        from reportlab.lib.colors import HexColor

        m, st = p.mini, p.mini.style
        c.drawImage(
            ImageReader(m.art),
            X(p.x),
            Y(p.y + m.height_mm),
            width=m.width_mm * mm,
            height=m.height_mm * mm,
            mask="auto",
        )
        # fold lines
        c.saveState()
        c.setStrokeColor(HexColor(st.fold_color))
        c.setLineWidth(st.fold_width_mm * mm)
        c.setDash([FOLD_DASH_MM * mm, FOLD_GAP_MM * mm])
        for x0, x1, y in m.folds:
            c.line(X(p.x + x0), Y(p.y + y), X(p.x + x1), Y(p.y + y))
        c.restoreState()
        # labels, numbers and the back text
        for t in m.text_items(self._fonts):
            c.saveState()
            c.setFillColor(HexColor(t.color))
            c.setFont(self._fonts.pdf_name(st.font, t.bold), t.size_mm * mm)
            c.translate(X(p.x + t.cx), Y(p.y + t.cy))
            c.rotate(-t.rot)
            c.drawCentredString(0, -TEXT_BASELINE_DROP * t.size_mm * mm, t.text)
            c.restoreState()
        if not cut_line or not st.cut_line:
            return
        # cut line
        pts = m.cut.points
        path = c.beginPath()
        path.moveTo(X(p.x + pts[0, 0]), Y(p.y + pts[0, 1]))
        n = len(pts)
        for i in range(n):
            q = pts[(i + 1) % n]
            if m.cut.controls is None:
                path.lineTo(X(p.x + q[0]), Y(p.y + q[1]))
            else:
                c1, c2 = m.cut.controls[i]
                path.curveTo(
                    X(p.x + c1[0]),
                    Y(p.y + c1[1]),
                    X(p.x + c2[0]),
                    Y(p.y + c2[1]),
                    X(p.x + q[0]),
                    Y(p.y + q[1]),
                )
        path.close()
        c.saveState()
        c.setStrokeColor(HexColor(st.cut_color))
        c.setLineWidth(st.cut_width_mm * mm)
        c.setLineJoin(1)
        c.drawPath(path, stroke=1, fill=0)
        c.restoreState()
