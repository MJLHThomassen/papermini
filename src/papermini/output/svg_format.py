from __future__ import annotations

from decimal import Decimal

import svg as svgpy

from ..pipeline.cut_path import CutPath

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'


class SvgFormat:
    """Writes numbers, text and cut paths the way papermini's SVG files hold them."""

    @staticmethod
    def number(v: float) -> Decimal:
        """``v`` with at most three decimals and no trailing zeros."""
        s = f"{v:.3f}".rstrip("0").rstrip(".")
        return Decimal("0" if s in ("-0", "") else s)

    @staticmethod
    def attribute(text: str) -> str:
        """``text`` made safe to stand in an attribute between double quotes."""
        return svgpy.escape(text).replace('"', "&quot;")

    @staticmethod
    def document(root: svgpy.SVG) -> str:
        """The SVG file of ``root``, as text."""
        return f"{XML_DECLARATION}\n{root}\n"

    @staticmethod
    def path_d(p: CutPath) -> list[svgpy.PathData]:
        """The cut path as SVG path data: absolute M, L or C commands, closed with Z."""
        f = SvgFormat.number
        pts = p.points
        d: list[svgpy.PathData] = [svgpy.MoveTo(f(pts[0, 0]), f(pts[0, 1]))]
        n = len(pts)
        for i in range(n):
            q = pts[(i + 1) % n]
            if p.controls is None:
                if i < n - 1:
                    d.append(svgpy.LineTo(f(q[0]), f(q[1])))
            else:
                c1, c2 = p.controls[i]
                d.append(
                    svgpy.CubicBezier(
                        f(c1[0]), f(c1[1]), f(c2[0]), f(c2[1]), f(q[0]), f(q[1])
                    )
                )
        d.append(svgpy.ClosePath())
        return d
