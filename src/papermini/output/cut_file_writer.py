from __future__ import annotations

from pathlib import Path

import svg as svgpy

from .sheet_layout import TITLE, SheetLayout
from .svg_format import SvgFormat

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
        here = [p for p in layout.placements if p.page == page]
        cut_color, cut_width = CUT_FILE_STYLE["cut"]
        groups: list[svgpy.Element] = [
            svgpy.Title(
                text=svgpy.escape(
                    f"{title}: cut file, page {page + 1} of {layout.pages}"
                )
            ),
            svgpy.G(
                id="registration",
                fill="#000000",
                stroke="none",
                elements=[
                    svgpy.Rect(x=f(x), y=f(y), width=f(w), height=f(h))
                    for x, y, w, h in layout.mark_rects()
                ],
            ),
            svgpy.G(
                id="cut",
                fill="none",
                stroke=cut_color,
                stroke_width=f(cut_width),
                extra={"stroke-linejoin": "round"},
                elements=[
                    svgpy.Path(
                        d=SvgFormat.path_d(p.mini.cut.transformed(1.0, -p.x, -p.y))
                    )
                    for p in here
                ],
            ),
        ]
        if folds:
            fold_color, fold_width = CUT_FILE_STYLE["fold"]
            groups.append(
                svgpy.G(
                    id="fold",
                    fill="none",
                    stroke=fold_color,
                    stroke_width=f(fold_width),
                    elements=[
                        svgpy.Line(
                            x1=f(p.x + x0), y1=f(p.y + y), x2=f(p.x + x1), y2=f(p.y + y)
                        )
                        for p in here
                        for x0, x1, y in p.mini.folds
                    ],
                )
            )
        root = svgpy.SVG(
            width=svgpy.mm(W),
            height=svgpy.mm(H),
            viewBox=svgpy.ViewBoxSpec(0, 0, W, H),
            elements=groups,
        )
        return SvgFormat.document(root)

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
