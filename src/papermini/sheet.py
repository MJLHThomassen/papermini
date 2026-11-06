"""Print sheet: shelf-pack miniatures onto A4/Letter pages, write PDF (+ PNG preview)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from .mini import Mini

PAPER = {"a4": (210.0, 297.0), "letter": (215.9, 279.4)}

TITLE = "Paper miniatures"
INSTRUCTIONS = [
    "Print at 100% / actual size (no 'fit to page'). Check: the bar below must measure 50 mm.",
    "Cut along the solid line and fold along the dashed lines. Square tabs slot into a stand; "
    "round tabs fold outwards into a base.",
]
INSTRUCTIONS_DOUBLE = "Double-sided: fold at the top dashed line and glue the halves back to back."


@dataclass
class Placement:
    mini: Mini
    page: int
    x: float  # mm, top-left of the piece
    y: float


@dataclass
class SheetLayout:
    paper: Tuple[float, float]
    placements: List[Placement]
    pages: int
    header_mm: float


def pack(minis: Sequence[Tuple[Mini, int]], paper: str = "a4", margin_mm: float = 12.0,
         gap_mm: float = 7.0, header_mm: float = 24.0) -> SheetLayout:
    """Simple shelf packing: rows left to right, tallest pieces first."""
    pw, ph = PAPER[paper.lower()]
    items = [m for m, n in minis for _ in range(max(0, n))]
    items.sort(key=lambda m: (-m.height_mm, m.name))
    avail_w = pw - 2 * margin_mm
    top = margin_mm + header_mm
    bottom = ph - margin_mm
    for m in items:
        if m.width_mm > avail_w or m.height_mm > bottom - top:
            raise ValueError(
                f"{m.name} ({m.width_mm:.0f} x {m.height_mm:.0f} mm) does not fit on "
                f"{paper.upper()} with {margin_mm:g} mm margins; make it smaller (--height-mm)"
            )
    placements: List[Placement] = []
    page, x, y, row_h = 0, margin_mm, top, 0.0
    for m in items:
        if x > margin_mm and x + m.width_mm > pw - margin_mm:  # next row
            x, y, row_h = margin_mm, y + row_h + gap_mm, 0.0
        if y + m.height_mm > bottom:  # next page
            page, x, y, row_h = page + 1, margin_mm, top, 0.0
        placements.append(Placement(m, page, x, y))
        x += m.width_mm + gap_mm
        row_h = max(row_h, m.height_mm)
    return SheetLayout((pw, ph), placements, page + 1 if items else 0, header_mm)


# --------------------------------------------------------------------------- PDF

def write_pdf(layout: SheetLayout, out: Path, margin_mm: float = 12.0, title: str = TITLE) -> Path:
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    pw, ph = layout.paper
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=(pw * mm, ph * mm))
    c.setTitle(title)
    c.setCreator("papermini")
    X = lambda v: v * mm  # noqa: E731
    Y = lambda v: (ph - v) * mm  # noqa: E731
    double = any(len(p.mini.labels) > 1 or len(p.mini.folds) > 1 for p in layout.placements)

    for page in range(layout.pages):
        # header
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(X(margin_mm), Y(margin_mm + 4), title)
        c.setFont("Helvetica", 7.5)
        lines = INSTRUCTIONS + ([INSTRUCTIONS_DOUBLE] if double else [])
        for i, line in enumerate(lines):
            c.drawString(X(margin_mm), Y(margin_mm + 8.5 + 3.4 * i), line)
        if layout.pages > 1:
            c.drawRightString(X(pw - margin_mm), Y(margin_mm + 4), f"page {page + 1}/{layout.pages}")
        # 50 mm calibration bar
        cy = margin_mm + layout.header_mm - 4
        c.setLineWidth(0.4 * mm)
        c.line(X(margin_mm), Y(cy), X(margin_mm + 50), Y(cy))
        c.setLineWidth(0.2 * mm)
        for t in range(0, 51, 10):
            h = 1.6 if t % 50 == 0 else 1.0
            c.line(X(margin_mm + t), Y(cy - h), X(margin_mm + t), Y(cy + h))
        c.setFont("Helvetica", 7)
        c.drawString(X(margin_mm + 52), Y(cy + 1), "50 mm")

        for p in layout.placements:
            if p.page == page:
                _draw_mini(c, p, X, Y, mm, ImageReader)
        c.showPage()
    c.save()
    return out


def _draw_mini(c, p: Placement, X, Y, mm, ImageReader) -> None:
    from reportlab.lib.colors import HexColor

    m, st = p.mini, p.mini.style
    c.drawImage(ImageReader(m.art), X(p.x), Y(p.y + m.height_mm),
                width=m.width_mm * mm, height=m.height_mm * mm, mask="auto")
    # fold lines
    c.saveState()
    c.setStrokeColor(HexColor(st.fold_color))
    c.setLineWidth(st.fold_width_mm * mm)
    c.setDash([1.2 * mm, 0.8 * mm])
    for x0, x1, y in m.folds:
        c.line(X(p.x + x0), Y(p.y + y), X(p.x + x1), Y(p.y + y))
    c.restoreState()
    # labels
    if m.label:
        c.saveState()
        c.setFillColor(HexColor(st.label_color))
        c.setFont("Times-Roman", m.label_size_mm * mm)
        for cx, cy, rot in m.labels:
            c.saveState()
            c.translate(X(p.x + cx), Y(p.y + cy))
            c.rotate(-rot)
            c.drawCentredString(0, -0.35 * m.label_size_mm * mm, m.label)
            c.restoreState()
        c.restoreState()
    # extra text (e.g. the back of a double-sided mini)
    if m.texts:
        c.saveState()
        c.setFillColor(HexColor(st.back_text_color))
        for text, cx, cy, rot, size in m.texts:
            c.saveState()
            c.setFont("Times-Roman", size * mm)
            c.translate(X(p.x + cx), Y(p.y + cy))
            c.rotate(-rot)
            c.drawCentredString(0, -0.35 * size * mm, text)
            c.restoreState()
        c.restoreState()
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
            path.curveTo(X(p.x + c1[0]), Y(p.y + c1[1]), X(p.x + c2[0]), Y(p.y + c2[1]),
                         X(p.x + q[0]), Y(p.y + q[1]))
    path.close()
    c.saveState()
    c.setStrokeColor(HexColor(st.cut_color))
    c.setLineWidth(st.cut_width_mm * mm)
    c.setLineJoin(1)
    c.drawPath(path, stroke=1, fill=0)
    c.restoreState()


# --------------------------------------------------------------------------- PNG preview

def _font(size_px: int, serif: bool = False):
    for name in (["times.ttf", "DejaVuSerif.ttf"] if serif else ["arial.ttf", "DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(name, size_px)
        except OSError:
            continue
    return ImageFont.load_default()


def write_previews(layout: SheetLayout, out: Path, dpi: int = 100,
                   margin_mm: float = 12.0, title: str = TITLE) -> List[Path]:
    """One PNG per page (``out`` or ``out-2.png`` ...) for a quick look."""
    out = Path(out)
    s = dpi / 25.4
    pw, ph = layout.paper
    paths = []
    for page in range(layout.pages):
        im = Image.new("RGB", (round(pw * s), round(ph * s)), "white")
        d = ImageDraw.Draw(im)
        d.text((margin_mm * s, (margin_mm) * s), title, fill="black", font=_font(round(4 * s)))
        for i, line in enumerate(INSTRUCTIONS):
            d.text((margin_mm * s, (margin_mm + 6 + 3.4 * i) * s), line, fill="black",
                   font=_font(round(2.6 * s)))
        cy = (margin_mm + layout.header_mm - 4) * s
        d.line([(margin_mm * s, cy), ((margin_mm + 50) * s, cy)], fill="black", width=max(1, round(0.4 * s)))
        for p in layout.placements:
            if p.page != page:
                continue
            m = p.mini
            ox, oy = p.x * s, p.y * s
            art = m.art.resize((max(1, round(m.width_mm * s)), max(1, round(m.height_mm * s))),
                               Image.LANCZOS)
            im.paste(art, (round(ox), round(oy)), art)
            for x0, x1, y in m.folds:
                d.line([(ox + x0 * s, oy + y * s), (ox + x1 * s, oy + y * s)], fill=m.style.fold_color)
            if m.label:
                f = _font(max(6, round(m.label_size_mm * s)), serif=True)
                for cx, cy2, rot in m.labels:
                    if rot:
                        continue
                    d.text((ox + cx * s, oy + cy2 * s), m.label, fill=m.style.label_color,
                           font=f, anchor="mm")
            pts = [(ox + x * s, oy + y * s) for x, y in m.cut.flatten(6)]
            d.line(pts + pts[:1], fill=m.style.cut_color, width=max(1, round(m.style.cut_width_mm * s)))
        path = out if page == 0 else out.with_name(f"{out.stem}-{page + 1}{out.suffix}")
        im.save(path)
        paths.append(path)
    return paths
