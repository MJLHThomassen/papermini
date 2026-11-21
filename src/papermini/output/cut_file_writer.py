from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from .sheet_layout import TITLE, SheetLayout
from .svg_format import SvgFormat
from .svg_writer import SVG_NS

CUT_FILE_STYLE = {
    "cut": ("#ff0000", 0.1),
    "fold": ("#0000ff", 0.1),
}  # stroke, width (mm)


class CutFileWriter:
    """Writes the cut files of a sheet cut by machine: one SVG per page, the size of
    the page, with the cut lines and the alignment marks of the PDF, to line up in the
    cutting machine's software."""

    def default_path(self, pdf: Path) -> Path:
        """The cut file that goes with the sheet ``pdf`` by default: ``name-cut.svg``."""
        pdf = Path(pdf)
        return pdf.with_name(f"{pdf.stem}-cut.svg")

    def paths(self, svg: Path, pages: int) -> list[Path]:
        """The cut files of a sheet, one per page: ``svg`` itself, then ``name-2.svg``
        and so on for further pages (like the PNG previews)."""
        svg = Path(svg)
        return [
            svg
            if i == 0
            else svg.with_name(f"{svg.stem}-{i + 1}{svg.suffix or '.svg'}")
            for i in range(pages)
        ]

    def svg(
        self, layout: SheetLayout, page: int, folds: bool = False, title: str = TITLE
    ) -> str:
        """One page's cut file, the size of the page in mm: the alignment marks, the cut
        line of every piece where it is on the page, and optionally the fold lines."""
        f = SvgFormat.number
        pw, ph = layout.paper
        W, H = f(pw), f(ph)
        out = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="{SVG_NS}" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
            f"<title>{escape(title)}: cut file, page {page + 1} of {layout.pages}</title>",
            '<g id="registration" fill="#000000" stroke="none">',
        ]
        out += [
            f'<rect x="{f(x)}" y="{f(y)}" width="{f(w)}" height="{f(h)}"/>'
            for x, y, w, h in layout.mark_rects()
        ]
        color, width = CUT_FILE_STYLE["cut"]
        out += [
            "</g>",
            (
                f'<g id="cut" fill="none" stroke="{color}" stroke-width="{f(width)}" '
                'stroke-linejoin="round">'
            ),
        ]
        here = [p for p in layout.placements if p.page == page]
        out += [
            f'<path d="{SvgFormat.path_d(p.mini.cut.transformed(1.0, -p.x, -p.y))}"/>'
            for p in here
        ]
        out.append("</g>")
        if folds:
            color, width = CUT_FILE_STYLE["fold"]
            out.append(
                f'<g id="fold" fill="none" stroke="{color}" stroke-width="{f(width)}">'
            )
            out += [
                f'<line x1="{f(p.x + x0)}" y1="{f(p.y + y)}" x2="{f(p.x + x1)}" '
                f'y2="{f(p.y + y)}"/>'
                for p in here
                for x0, x1, y in p.mini.folds
            ]
            out.append("</g>")
        out.append("</svg>")
        return "\n".join(out) + "\n"

    def write(
        self, layout: SheetLayout, svg: Path, folds: bool = False, title: str = TITLE
    ) -> list[Path]:
        """Write the sheet's cut files: ``svg`` for the first page, ``name-2.svg`` and so
        on for the others (see ``paths``)."""
        paths = self.paths(svg, layout.pages)
        for page, path in enumerate(paths):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.svg(layout, page, folds, title), encoding="utf-8")
        return paths
