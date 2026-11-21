from __future__ import annotations

import re

import numpy as np

from ..pipeline.cut_path import CutPath

NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"  # a number in SVG attributes


class SvgFormat:
    """Writes numbers and cut paths the way papermini's SVG files hold them, and reads
    the paths back."""

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

    @staticmethod
    def parse_path_d(d: str) -> CutPath:
        """Parse the absolute M/L/C/Z paths written by ``path_d``."""
        tokens = re.findall(rf"[MLCZmlcz]|{NUMBER}", d)
        pts: list[list[float]] = []
        ctrls: list[list[list[float]]] = []
        has_curve = False
        i, cmd = 0, None
        while i < len(tokens):
            t = tokens[i]
            if t.isalpha():
                cmd = t
                i += 1
                if cmd in "Zz":
                    break
                continue
            if cmd in ("m", "l", "c"):
                raise ValueError(
                    "relative path commands are not supported; use a papermini SVG"
                )
            if cmd in ("M", "L"):
                p = [float(tokens[i]), float(tokens[i + 1])]
                if pts:
                    ctrls.append([pts[-1], p])  # straight: handles on the endpoints
                pts.append(p)
                i += 2
            elif cmd == "C":
                v = [float(x) for x in tokens[i : i + 6]]
                ctrls.append([v[0:2], v[2:4]])
                pts.append(v[4:6])
                has_curve = True
                i += 6
            else:
                raise ValueError(f"unexpected path data near {t!r}")
        P = np.array(pts, float)
        if len(P) > 1 and np.allclose(P[0], P[-1]):
            P = P[:-1]  # closing segment came back to the start
        elif ctrls:
            ctrls.append([pts[-1], pts[0]])  # implicit closing line
        if not has_curve:
            return CutPath(P)
        return CutPath(P, np.array(ctrls[: len(P)], float))
