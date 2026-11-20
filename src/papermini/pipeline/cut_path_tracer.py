from __future__ import annotations

import cv2
import numpy as np

from .cut_path import CutPath


class CutPathTracer:
    """Traces a cut shape into a smooth vector cut path, and fills a path back into a
    mask."""

    def trace(
        self,
        cut: np.ndarray,
        px_per_mm: float,
        simplify_mm: float = 0.15,
        smooth: bool = True,
        circles=(),
    ) -> CutPath:
        """Trace the outer contour of the cut shape as one closed (optionally Bézier)
        path.

        ``circles`` (cx, cy, r, side): outline points on the given half circle are
        moved exactly onto it, so round tabs come out perfectly round.
        """
        cs, _ = cv2.findContours(cut, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not cs:
            raise ValueError("empty cut shape")
        c = max(cs, key=cv2.contourArea)[:, 0, :].astype(np.float64)
        c = self._smooth_closed(c, 1.5)
        c = cv2.approxPolyDP(
            c.astype(np.float32).reshape(-1, 1, 2),
            max(0.5, simplify_mm * px_per_mm),
            True,
        )[:, 0, :].astype(np.float64)
        # findContours traces pixel centres; shift to pixel-edge coordinates.
        c += 0.5
        tol = max(2.0, 0.3 * px_per_mm)
        on_circle = np.full(len(c), -1)
        for k, (ccx, ccy, r, side) in enumerate(circles):
            v = c - (ccx, ccy)
            dist = np.hypot(v[:, 0], v[:, 1])
            on = (side * v[:, 1] > 0.5) & (np.abs(dist - r) < tol)
            c[on] = (ccx, ccy) + v[on] * (r / dist[on])[:, None]
            on_circle[on] = k
        ctrl = (
            self._bezier_controls(c, max_handle=0.8 * px_per_mm)
            if smooth and len(c) >= 4
            else None
        )
        if ctrl is not None:
            # segments between two points on the same circle get the exact arc handles
            for i in range(len(c)):
                j = (i + 1) % len(c)
                k = on_circle[i]
                if k < 0 or on_circle[j] != k:
                    continue
                ccx, ccy, r, _ = circles[k]
                a0 = np.arctan2(c[i, 1] - ccy, c[i, 0] - ccx)
                a1 = np.arctan2(c[j, 1] - ccy, c[j, 0] - ccx)
                da = (a1 - a0 + np.pi) % (2 * np.pi) - np.pi
                h = 4.0 / 3.0 * np.tan(da / 4.0) * r  # signed handle length
                ctrl[i, 0] = c[i] + h * np.array([-np.sin(a0), np.cos(a0)])
                ctrl[i, 1] = c[j] - h * np.array([-np.sin(a1), np.cos(a1)])
        return CutPath(c, ctrl)

    def rasterize(
        self, path: CutPath, shape: tuple[int, int], antialias: bool = True
    ) -> np.ndarray:
        """Fill ``path`` (pixel coordinates, edge convention) into a uint8 mask."""
        out = np.zeros(shape, np.uint8)
        pts = np.round((path.flatten() - 0.5) * 16).astype(np.int32)
        cv2.fillPoly(
            out, [pts], 255, lineType=cv2.LINE_AA if antialias else cv2.LINE_8, shift=4
        )
        return out

    @staticmethod
    def _bezier_controls(
        P: np.ndarray, corner_deg: float = 55.0, max_handle: float = np.inf
    ) -> np.ndarray:
        """Return smooth cubic handles through ``P``; sharp turns stay sharp corners.

        Handles are a third of the adjacent segment length, capped at
        ``max_handle``, which keeps the curve close to the polygon (long straight
        runs stay straight, no overshoot on unevenly spaced points).
        """
        nxt = np.roll(P, -1, axis=0)
        prv = np.roll(P, 1, axis=0)
        d_out, d_in = nxt - P, P - prv
        l_out = np.linalg.norm(d_out, axis=1, keepdims=True) + 1e-9
        l_in = np.linalg.norm(d_in, axis=1, keepdims=True) + 1e-9
        u_out, u_in = d_out / l_out, d_in / l_in
        tang = u_in + u_out
        tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-9
        cosang = np.clip((u_in * u_out).sum(1), -1, 1)
        corner = (np.degrees(np.arccos(cosang)) > corner_deg)[:, None]
        t_out = np.where(corner, u_out, tang)
        t_in = np.where(corner, u_in, tang)
        h = np.minimum(l_out / 3, max_handle)
        c1 = P + t_out * h
        c2 = nxt - np.roll(t_in, -1, axis=0) * h
        return np.stack([c1, c2], axis=1)

    @staticmethod
    def _smooth_closed(pts: np.ndarray, sigma: float) -> np.ndarray:
        """Gaussian-smooth a closed point sequence (wraps around).

        A traced pixel outline moves in 1-pixel stair steps; at a fine simplify
        setting the cut line would follow every step and its curves would overshoot
        them (lumps on a round tab). Smoothing over ~1.5 px removes the stairs and
        moves the outline by well under a pixel.
        """
        n = len(pts)
        r = int(np.ceil(3 * sigma))
        if n < 2 * r + 3:
            return pts
        k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
        k /= k.sum()
        ext = np.concatenate([pts[-r:], pts, pts[:r]])
        return np.stack(
            [np.convolve(ext[:, i], k, mode="valid") for i in range(2)], axis=1
        )
