from __future__ import annotations

MARKS = ("corners", "silhouette", "none")  # alignment marks for cutting by machine
MARK_LINE_MM = 0.5  # thickness of the marks


class RegistrationMarks:
    """The alignment marks of a sheet cut by machine, the same in the PDF and the cut
    file."""

    @staticmethod
    def rects(
        paper: tuple[float, float], kind: str, inset: float
    ) -> list[tuple[float, float, float, float]]:
        """The alignment marks of a page as filled rectangles (x, y, w, h) in mm.

        ``corners``: an L in each corner, ``inset`` from the paper edges, plus a small
        square inside the top-left one, so the page cannot be lined up the wrong way
        round. ``silhouette``: Silhouette Studio's "Type 1" layout: a filled 5 mm square
        top-left and an L with 20 mm arms top-right and bottom-left, all ``inset`` from
        the edges; set the same length (20 mm), thickness (0.5 mm) and inset in the
        software. ``none``: no marks (the cut file is lined up with the page itself).
        """
        if kind not in MARKS:
            raise ValueError(f"marks must be one of {', '.join(MARKS)}, not {kind!r}")
        if kind == "none":
            return []
        pw, ph = paper
        ell = RegistrationMarks._ell
        if kind == "corners":
            arm = 10.0
            out = (
                ell(inset, inset, 1, 1, arm)
                + ell(pw - inset, inset, -1, 1, arm)
                + ell(inset, ph - inset, 1, -1, arm)
                + ell(pw - inset, ph - inset, -1, -1, arm)
            )
            return out + [(inset + 1.5, inset + 1.5, 3.0, 3.0)]
        arm = 20.0
        return (
            [(inset, inset, 5.0, 5.0)]
            + ell(pw - inset, inset, -1, 1, arm)
            + ell(inset, ph - inset, 1, -1, arm)
        )

    @staticmethod
    def _ell(
        cx: float, cy: float, dx: int, dy: int, arm: float
    ) -> list[tuple[float, float, float, float]]:
        """An L with its outer corner at (cx, cy) and its arms inwards, in the
        directions ``dx`` and ``dy``."""
        t = MARK_LINE_MM
        bars = [(cx, cy, dx * arm, dy * t), (cx, cy, dx * t, dy * arm)]
        return [(min(x, x + w), min(y, y + h), abs(w), abs(h)) for x, y, w, h in bars]
