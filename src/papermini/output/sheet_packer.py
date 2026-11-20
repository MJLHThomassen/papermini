from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from ..pipeline.mini import Mini
from .paper_sizes import Paper, PaperSizes
from .placement import Placement
from .registration_marks import RegistrationMarks
from .sheet_layout import SheetLayout

CUT_MODES = ("hand", "machine")  # how the pieces are cut: decides what the PDF holds
MARK_CLEAR_MM = 6.0  # the header and the pieces keep this far from the marks

Box = tuple[float, float, float, float]  # a keep-out rectangle (x0, y0, x1, y1) in mm


class SheetPacker:
    """Packs miniatures onto the pages of a sheet."""

    def pack(
        self,
        minis: Sequence[tuple[Mini, int]],
        paper: Paper = "a4",
        margin_mm: float = 12.0,
        gap_mm: float = 7.0,
        header_mm: float = 24.0,
        cut: str = "hand",
        marks: str = "corners",
        orientation: str = "portrait",
        leave_out: bool = False,
    ) -> SheetLayout:
        """Simple shelf packing: rows left to right, tallest pieces first. ``paper``: a
        name in ``PaperSizes.PAPER`` (turned for ``orientation`` "landscape") or a
        custom (width, height) mm. A piece too big for the paper is an error, or with
        ``leave_out`` left off the sheet and listed in the layout's ``left_out``.

        Cut by machine, the alignment marks sit in the corners, ``margin_mm`` from the
        paper edges. The pieces keep ``MARK_CLEAR_MM`` away from them (a piece that
        would come too close moves along its row), and the header starts beside the
        top-left mark.
        """
        if cut not in CUT_MODES:
            raise ValueError(f"cut must be one of {', '.join(CUT_MODES)}, not {cut!r}")
        pw, ph = PaperSizes.size(paper, orientation)
        name = PaperSizes.text(paper, orientation)
        machine = cut == "machine"
        # (cut by machine, this also checks the kind of marks)
        rects = RegistrationMarks.rects((pw, ph), marks, margin_mm) if machine else []
        c = MARK_CLEAR_MM
        keep = [(x - c, y - c, x + w + c, y + h + c) for x, y, w, h in rects]
        header_x, header_right = self._header_span(keep, pw, margin_mm, header_mm)
        items = self._copies(minis)
        avail_w = pw - 2 * margin_mm
        top = margin_mm + header_mm
        bottom = ph - margin_mm
        left_out: list[Mini] = []

        def too_big(m: Mini, why: str) -> None:
            if not leave_out:
                raise ValueError(why)
            if not any(o.art is m.art for o in left_out):  # (one entry for all copies)
                left_out.append(m)

        fitting = []
        for m in items:
            if m.width_mm > avail_w or m.height_mm > bottom - top:
                too_big(
                    m,
                    f"{m.name} ({m.width_mm:.0f} x {m.height_mm:.0f} mm) does not fit "
                    f"on {name} with {margin_mm:g} mm margins; make it smaller "
                    "(--height-mm)",
                )
            else:
                fitting.append(m)
        placements: list[Placement] = []
        page, x, y, row_h = 0, margin_mm, top, 0.0
        for m in fitting:
            on_page = sum(p.page == page for p in placements)
            placed = True
            while True:
                if x > margin_mm and x + m.width_mm > pw - margin_mm:  # next row
                    x, y, row_h = margin_mm, y + row_h + gap_mm, 0.0
                if y + m.height_mm > bottom:  # next page
                    if not on_page:  # (an empty page and still no room: the marks)
                        too_big(
                            m,
                            f"{m.name} does not fit on {name} between the alignment "
                            "marks; make it smaller (--height-mm)",
                        )
                        placed = False
                        break
                    page, x, y, row_h, on_page = page + 1, margin_mm, top, 0.0, 0
                hit = self._hits(x, y, m.width_mm, m.height_mm, keep)
                if hit is None:
                    break
                # past the mark, on this row (or the next, if it no longer fits)
                x = hit[2]
            if not placed:
                continue
            placements.append(Placement(m, page, x, y))
            x += m.width_mm + gap_mm
            row_h = max(row_h, m.height_mm)
        return SheetLayout(
            (pw, ph),
            placements,
            page + 1 if placements else 0,
            header_mm,
            margin_mm,
            cut,
            marks if machine else None,
            margin_mm if machine else 0.0,
            header_x,
            header_right,
            name,
            left_out,
        )

    def _header_span(
        self, keep: list[Box], pw: float, margin_mm: float, header_mm: float
    ) -> tuple[float, float]:
        """The left and right ends of the header: inside the margins, and beside the
        keep-out rectangles of the marks in its rows of the page."""
        top = margin_mm
        left = max(
            [margin_mm]
            + [
                k[2]
                for k in keep
                if k[0] < pw / 2 and self._hits(0, top, pw / 2, header_mm, [k])
            ]
        )
        right = min(
            [pw - margin_mm]
            + [
                k[0]
                for k in keep
                if k[0] > pw / 2 and self._hits(pw / 2, top, pw / 2, header_mm, [k])
            ]
        )
        return left, right

    @staticmethod
    def _copies(minis: Sequence[tuple[Mini, int]]) -> list[Mini]:
        """Every copy of the minis, tallest first. Each copy of a numbered figure shows
        its own number, 1 to n."""
        items = [
            replace(m, number=i + 1) if m.numbered else m
            for m, n in minis
            for i in range(max(0, n))
        ]
        items.sort(key=lambda m: (-m.height_mm, m.name))
        return items

    @staticmethod
    def _hits(x: float, y: float, w: float, h: float, keep: list[Box]) -> Box | None:
        """The first keep-out rectangle that the box x, y, w, h overlaps."""
        for k in keep:
            if x < k[2] and k[0] < x + w and y < k[3] and k[1] < y + h:
                return k
        return None
