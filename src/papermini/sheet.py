"""Print sheet: shelf-pack miniatures onto A4/Letter pages, write PDF (+ PNG preview).

Cut by hand, the PDF has the cut lines. Cut by machine, the PDF has none: it gets
alignment marks instead, and a cut file (SVG, one per page) holds the cut lines and
the same marks, to line up in the cutting machine's software.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

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
INSTRUCTIONS_MACHINE = [
    INSTRUCTIONS[0],
    "Cut by machine: line up the cut file's marks with these marks. Fold along the dashed lines.",
]
INSTRUCTIONS_MACHINE_NO_MARKS = [
    INSTRUCTIONS[0],
    "Cut by machine: line up the cut file with this page. Fold along the dashed lines.",
]

CUT_MODES = ("hand", "machine")    # how the pieces are cut: decides what the PDF holds
MARKS = ("corners", "silhouette", "none")  # alignment marks for cutting by machine
MARK_LINE_MM = 0.5     # thickness of the marks
MARK_CLEAR_MM = 6.0    # the header and the pieces keep this far from the marks
CUT_FILE_STYLE = {"cut": ("#ff0000", 0.1), "fold": ("#0000ff", 0.1)}  # stroke, width (mm)


def registration_marks(paper: Tuple[float, float], kind: str,
                       inset: float) -> List[Tuple[float, float, float, float]]:
    """The alignment marks of a page as filled rectangles (x, y, w, h) in mm, the same
    in the PDF and the cut file.

    ``corners``: an L in each corner, ``inset`` from the paper edges, plus a small
    square inside the top-left one, so the page cannot be lined up the wrong way round.
    ``silhouette``: Silhouette Studio's "Type 1" layout: a filled 5 mm square top-left
    and an L with 20 mm arms top-right and bottom-left, all ``inset`` from the edges;
    set the same length (20 mm), thickness (0.5 mm) and inset in the software.
    ``none``: no marks (the cut file is lined up with the page itself).
    """
    if kind not in MARKS:
        raise ValueError(f"marks must be one of {', '.join(MARKS)}, not {kind!r}")
    if kind == "none":
        return []
    pw, ph = paper
    t = MARK_LINE_MM

    def ell(cx, cy, dx, dy, arm):  # an L with its outer corner at (cx, cy), arms inwards
        bars = [(cx, cy, dx * arm, dy * t), (cx, cy, dx * t, dy * arm)]
        return [(min(x, x + w), min(y, y + h), abs(w), abs(h)) for x, y, w, h in bars]

    if kind == "corners":
        arm = 10.0
        out = (ell(inset, inset, 1, 1, arm) + ell(pw - inset, inset, -1, 1, arm)
               + ell(inset, ph - inset, 1, -1, arm) + ell(pw - inset, ph - inset, -1, -1, arm))
        return out + [(inset + 1.5, inset + 1.5, 3.0, 3.0)]
    arm = 20.0
    return ([(inset, inset, 5.0, 5.0)] + ell(pw - inset, inset, -1, 1, arm)
            + ell(inset, ph - inset, 1, -1, arm))


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
    margin_mm: float = 12.0          # the page margin: where the header and the pieces start
    cut: str = "hand"                # "hand" (cut lines on the sheet) or "machine"
    marks: Optional[str] = None      # alignment marks (cut by machine)
    mark_inset: float = 0.0          # distance of the marks from the paper edges
    header_x: float = 0.0            # left of the header (right of a top-left mark)
    header_right: float = 0.0        # right end of the header (left of a top-right mark)

    @property
    def machine(self) -> bool:
        return self.cut == "machine"

    def mark_rects(self) -> List[Tuple[float, float, float, float]]:
        return registration_marks(self.paper, self.marks, self.mark_inset) if self.marks else []

    def instructions(self) -> List[str]:
        double = any(len(p.mini.labels) > 1 or len(p.mini.folds) > 1 for p in self.placements)
        lines = list(INSTRUCTIONS if not self.machine else INSTRUCTIONS_MACHINE_NO_MARKS
                     if self.marks == "none" else INSTRUCTIONS_MACHINE)
        return lines + ([INSTRUCTIONS_DOUBLE] if double else [])


def _hits(x: float, y: float, w: float, h: float, keep) -> Optional[Tuple]:
    """The first keep-out rectangle (x0, y0, x1, y1) that the box x, y, w, h overlaps."""
    for k in keep:
        if x < k[2] and k[0] < x + w and y < k[3] and k[1] < y + h:
            return k
    return None


def pack(minis: Sequence[Tuple[Mini, int]], paper: str = "a4", margin_mm: float = 12.0,
         gap_mm: float = 7.0, header_mm: float = 24.0, cut: str = "hand",
         marks: str = "corners") -> SheetLayout:
    """Simple shelf packing: rows left to right, tallest pieces first.

    Cut by machine, the alignment marks sit in the corners, ``margin_mm`` from the paper
    edges. The pieces keep ``MARK_CLEAR_MM`` away from them (a piece that would come too
    close moves along its row), and the header starts beside the top-left mark.
    """
    if cut not in CUT_MODES:
        raise ValueError(f"cut must be one of {', '.join(CUT_MODES)}, not {cut!r}")
    pw, ph = PAPER[paper.lower()]
    machine = cut == "machine"
    rects = registration_marks((pw, ph), marks, margin_mm) if machine else []  # (checks kind)
    c = MARK_CLEAR_MM
    keep = [(x - c, y - c, x + w + c, y + h + c) for x, y, w, h in rects]
    band = (0, margin_mm, pw, margin_mm + header_mm)  # the header's rows of the page
    header_x = max([margin_mm] + [k[2] for k in keep if k[0] < pw / 2 and _hits(
        band[0], band[1], pw / 2, header_mm, [k])])
    header_right = min([pw - margin_mm] + [k[0] for k in keep if k[0] > pw / 2 and _hits(
        pw / 2, band[1], pw / 2, header_mm, [k])])
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
        on_page = sum(p.page == page for p in placements)
        while True:
            if x > margin_mm and x + m.width_mm > pw - margin_mm:  # next row
                x, y, row_h = margin_mm, y + row_h + gap_mm, 0.0
            if y + m.height_mm > bottom:  # next page
                if not on_page:  # (an empty page and still no room: the marks are in the way)
                    raise ValueError(f"{m.name} does not fit on {paper.upper()} between the "
                                     "alignment marks; make it smaller (--height-mm)")
                page, x, y, row_h, on_page = page + 1, margin_mm, top, 0.0, 0
            hit = _hits(x, y, m.width_mm, m.height_mm, keep)
            if hit is None:
                break
            x = hit[2]  # past the mark, on this row (or the next, if it no longer fits)
        placements.append(Placement(m, page, x, y))
        x += m.width_mm + gap_mm
        row_h = max(row_h, m.height_mm)
    return SheetLayout((pw, ph), placements, page + 1 if items else 0, header_mm, margin_mm,
                       cut, marks if machine else None, margin_mm if machine else 0.0,
                       header_x, header_right)


# --------------------------------------------------------------------------- PDF

def write_pdf(layout: SheetLayout, out: Path, title: str = TITLE) -> Path:
    """The sheet as a PDF. Cut by machine: without cut lines but with alignment marks
    (``write_cut_files`` writes the matching cut files)."""
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
    margin_mm, hx = layout.margin_mm, layout.header_x

    for page in range(layout.pages):
        c.setFillColorRGB(0, 0, 0)
        for x, y, w, h in layout.mark_rects():  # alignment marks (cut by machine)
            c.rect(X(x), Y(y + h), w * mm, h * mm, stroke=0, fill=1)
        # header
        c.setFont("Helvetica-Bold", 11)
        c.drawString(X(hx), Y(margin_mm + 4), title)
        c.setFont("Helvetica", 7.5)
        for i, line in enumerate(layout.instructions()):
            c.drawString(X(hx), Y(margin_mm + 8.5 + 3.4 * i), line)
        if layout.pages > 1:
            c.drawRightString(X(layout.header_right), Y(margin_mm + 4),
                              f"page {page + 1}/{layout.pages}")
        # 50 mm calibration bar
        cy = margin_mm + layout.header_mm - 4
        c.setLineWidth(0.4 * mm)
        c.line(X(hx), Y(cy), X(hx + 50), Y(cy))
        c.setLineWidth(0.2 * mm)
        for t in range(0, 51, 10):
            h = 1.6 if t % 50 == 0 else 1.0
            c.line(X(hx + t), Y(cy - h), X(hx + t), Y(cy + h))
        c.setFont("Helvetica", 7)
        c.drawString(X(hx + 52), Y(cy + 1), "50 mm")

        for p in layout.placements:
            if p.page == page:
                _draw_mini(c, p, X, Y, mm, ImageReader, cut_line=not layout.machine)
        c.showPage()
    c.save()
    return out


def _draw_mini(c, p: Placement, X, Y, mm, ImageReader, cut_line: bool = True) -> None:
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
    if not cut_line:
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
            path.curveTo(X(p.x + c1[0]), Y(p.y + c1[1]), X(p.x + c2[0]), Y(p.y + c2[1]),
                         X(p.x + q[0]), Y(p.y + q[1]))
    path.close()
    c.saveState()
    c.setStrokeColor(HexColor(st.cut_color))
    c.setLineWidth(st.cut_width_mm * mm)
    c.setLineJoin(1)
    c.drawPath(path, stroke=1, fill=0)
    c.restoreState()


# --------------------------------------------------------------------------- cut files

def default_cut_file(pdf: Path) -> Path:
    """The cut file that goes with the sheet ``pdf`` by default: ``name-cut.svg``."""
    pdf = Path(pdf)
    return pdf.with_name(f"{pdf.stem}-cut.svg")


def cut_file_paths(svg: Path, pages: int) -> List[Path]:
    """The cut files of a sheet, one per page: ``svg`` itself, then ``name-2.svg`` and
    so on for further pages (like the PNG previews)."""
    svg = Path(svg)
    return [svg if i == 0 else svg.with_name(f"{svg.stem}-{i + 1}{svg.suffix or '.svg'}")
            for i in range(pages)]


def cut_file_svg(layout: SheetLayout, page: int, folds: bool = False, title: str = TITLE) -> str:
    """One page's cut file, the size of the page in mm: the alignment marks, the cut
    line of every piece where it is on the page, and optionally the fold lines."""
    from xml.sax.saxutils import escape

    from .svg import SVG_NS, _f, path_d

    pw, ph = layout.paper
    W, H = _f(pw), _f(ph)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="{SVG_NS}" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
           f"<title>{escape(title)}: cut file, page {page + 1} of {layout.pages}</title>",
           '<g id="registration" fill="#000000" stroke="none">']
    out += [f'<rect x="{_f(x)}" y="{_f(y)}" width="{_f(w)}" height="{_f(h)}"/>'
            for x, y, w, h in layout.mark_rects()]
    color, width = CUT_FILE_STYLE["cut"]
    out += ["</g>", f'<g id="cut" fill="none" stroke="{color}" stroke-width="{_f(width)}" '
                    'stroke-linejoin="round">']
    here = [p for p in layout.placements if p.page == page]
    out += [f'<path d="{path_d(p.mini.cut.transformed(1.0, -p.x, -p.y))}"/>' for p in here]
    out.append("</g>")
    if folds:
        color, width = CUT_FILE_STYLE["fold"]
        out.append(f'<g id="fold" fill="none" stroke="{color}" stroke-width="{_f(width)}">')
        out += [f'<line x1="{_f(p.x + x0)}" y1="{_f(p.y + y)}" x2="{_f(p.x + x1)}" '
                f'y2="{_f(p.y + y)}"/>' for p in here for x0, x1, y in p.mini.folds]
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def write_cut_files(layout: SheetLayout, svg: Path, folds: bool = False,
                    title: str = TITLE) -> List[Path]:
    """Write the sheet's cut files: ``svg`` for the first page, ``name-2.svg`` and so on
    for the others (see ``cut_file_paths``)."""
    paths = cut_file_paths(svg, layout.pages)
    for page, path in enumerate(paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cut_file_svg(layout, page, folds, title), encoding="utf-8")
    return paths


# --------------------------------------------------------------------------- PNG preview

def _font(size_px: int, serif: bool = False):
    for name in (["times.ttf", "DejaVuSerif.ttf"] if serif else ["arial.ttf", "DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(name, size_px)
        except OSError:
            continue
    return ImageFont.load_default()


def write_previews(layout: SheetLayout, out: Path, dpi: int = 100,
                   title: str = TITLE) -> List[Path]:
    """One PNG per page (``out`` or ``out-2.png`` ...) for a quick look."""
    out = Path(out)
    s = dpi / 25.4
    pw, ph = layout.paper
    margin_mm, hx = layout.margin_mm, layout.header_x
    paths = []
    for page in range(layout.pages):
        im = Image.new("RGB", (round(pw * s), round(ph * s)), "white")
        d = ImageDraw.Draw(im)
        for x, y, w, h in layout.mark_rects():
            d.rectangle([x * s, y * s, (x + w) * s, (y + h) * s], fill="black")
        d.text((hx * s, (margin_mm) * s), title, fill="black", font=_font(round(4 * s)))
        for i, line in enumerate(layout.instructions()):
            d.text((hx * s, (margin_mm + 6 + 3.4 * i) * s), line, fill="black",
                   font=_font(round(2.6 * s)))
        cy = (margin_mm + layout.header_mm - 4) * s
        d.line([(hx * s, cy), ((hx + 50) * s, cy)], fill="black", width=max(1, round(0.4 * s)))
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
            if not layout.machine:
                pts = [(ox + x * s, oy + y * s) for x, y in m.cut.flatten(6)]
                d.line(pts + pts[:1], fill=m.style.cut_color,
                       width=max(1, round(m.style.cut_width_mm * s)))
        path = out if page == 0 else out.with_name(f"{out.stem}-{page + 1}{out.suffix}")
        im.save(path)
        paths.append(path)
    return paths
