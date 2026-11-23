from __future__ import annotations

from ..pipeline.cut_path import CutPath


class SvgFormat:
    """Writes numbers and cut paths the way papermini's SVG files hold them."""

    @staticmethod
    def number(v: float) -> str:
        """``v`` with at most three decimals and no trailing zeros."""
        s = f"{v:.3f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s

    @staticmethod
    def path_d(p: CutPath) -> str:
        """The cut path as SVG path data: absolute M, L or C commands, closed with Z."""
        f = SvgFormat.number
        pts = p.points
        parts = [f"M{f(pts[0, 0])},{f(pts[0, 1])}"]
        n = len(pts)
        for i in range(n):
            q = pts[(i + 1) % n]
            if p.controls is None:
                if i < n - 1:
                    parts.append(f"L{f(q[0])},{f(q[1])}")
            else:
                c1, c2 = p.controls[i]
                parts.append(
                    f"C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(q[0])},{f(q[1])}"
                )
        return " ".join(parts) + " Z"
