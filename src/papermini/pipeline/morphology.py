from __future__ import annotations

import cv2
import numpy as np

from .nothing_found_error import NothingFoundError
from .too_many_parts_error import TooManyPartsError

MAX_PARTS = 60  # the most separate parts connect_components bridges


class Morphology:
    """Shape operations on 0/255 uint8 masks: growing, shrinking, filling, picking
    components and rounding outlines."""

    def disk(self, r: float) -> np.ndarray:
        """Return a disk-shaped structuring element of radius ``r`` px."""
        r = max(1, round(r))
        return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))

    def dilate(self, m: np.ndarray, r: float) -> np.ndarray:
        """Grow a 0/255 mask by a disk of radius ``r`` px.

        Large radii use a distance transform, whose cost does not depend on ``r``
        (a big structuring element makes cv2.dilate very slow).
        """
        if r <= 0:
            return m.copy()
        if r <= 6:
            return cv2.dilate(m, self.disk(r))
        d = cv2.distanceTransform(
            cv2.bitwise_not(m), cv2.DIST_L2, cv2.DIST_MASK_PRECISE
        )
        return ((d <= r) * 255).astype(np.uint8)

    def erode(self, m: np.ndarray, r: float) -> np.ndarray:
        """Shrink a 0/255 mask by a disk of radius ``r`` px (see :meth:`dilate`)."""
        if r <= 0:
            return m.copy()
        if r <= 6:
            return cv2.erode(m, self.disk(r))
        d = cv2.distanceTransform(m, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        return ((d > r) * 255).astype(np.uint8)

    def close(self, m: np.ndarray, r: float) -> np.ndarray:
        """Close a mask morphologically with a disk of radius ``r`` px."""
        return self.erode(self.dilate(m, r), r)

    def fill_holes(self, m: np.ndarray) -> np.ndarray:
        """Fill every background region that is not connected to the outside."""
        p = np.pad(m, 1)
        ff = p.copy()
        cv2.floodFill(
            ff, np.zeros((p.shape[0] + 2, p.shape[1] + 2), np.uint8), (0, 0), 255
        )
        return (p | cv2.bitwise_not(ff))[1:-1, 1:-1]

    def largest_component(self, m: np.ndarray) -> np.ndarray:
        """Keep only the largest connected component."""
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        if n <= 1:
            return m
        i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        return ((lab == i) * 255).astype(np.uint8)

    def filter_components(self, m: np.ndarray, min_area: int) -> np.ndarray:
        """Keep every component of at least ``min_area`` px (always keeps the largest)."""
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        if n <= 1:
            return m
        areas = st[1:, cv2.CC_STAT_AREA]
        keep = np.flatnonzero(areas >= min(min_area, areas.max())) + 1
        return (np.isin(lab, keep) * 255).astype(np.uint8)

    def bbox(self, m: np.ndarray) -> tuple[int, int, int, int]:
        """Return the (x0, y0, x1, y1) inclusive bounding box of the non-zero pixels."""
        ys, xs = np.nonzero(m)
        if len(ys) == 0:
            raise NothingFoundError("background removal found no figure in the image")
        return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

    def connect_components(self, m: np.ndarray, width_px: int) -> np.ndarray:
        """Join all components into one shape with straight bridges of ``width_px``.

        Bridges follow a minimum spanning tree over the parts (closest outline
        points), computed once - not one full-canvas pass per bridge.
        """
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        k = len(cs)
        if k <= 1:
            return m
        if k > MAX_PARTS:
            raise TooManyPartsError(
                f"the figure has {k} separate parts, too many to join into one "
                f"piece (at most {MAX_PARTS})"
            )
        pts = []
        for c in cs:  # outline points, thinned to bound the pairwise cost
            p = c[:, 0, :].astype(np.float32)
            pts.append(p[:: max(1, len(p) // 300)])
        edges = []
        for i in range(k):
            for j in range(i + 1, k):
                d = ((pts[i][:, None, :] - pts[j][None, :, :]) ** 2).sum(-1)
                a, b = np.unravel_index(int(np.argmin(d)), d.shape)
                edges.append((float(d[a, b]), i, j, pts[i][a], pts[j][b]))
        edges.sort(key=lambda e: e[0])
        parent = list(range(k))

        def root(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        m = m.copy()
        for _, i, j, a, b in edges:  # Kruskal
            ri, rj = root(i), root(j)
            if ri != rj:
                parent[ri] = rj
                cv2.line(
                    m,
                    (int(a[0]), int(a[1])),
                    (int(b[0]), int(b[1])),
                    255,
                    thickness=max(2, width_px),
                    lineType=cv2.LINE_8,
                )
        return m

    def smooth_outline(self, m: np.ndarray, sigma: float) -> np.ndarray:
        """Gaussian-blur a 0/255 mask and re-threshold at 50% (rounds the outline).

        Big sigmas are done at a reduced resolution, where they are cheap; the
        result is a smooth curve either way.
        """
        if sigma <= 0:
            return m
        if sigma <= 8:
            return ((cv2.GaussianBlur(m, (0, 0), sigma) > 127) * 255).astype(np.uint8)
        f = 8.0 / sigma
        h, w = m.shape
        small = cv2.resize(
            m,
            (max(1, round(w * f)), max(1, round(h * f))),
            interpolation=cv2.INTER_AREA,
        )
        small = cv2.GaussianBlur(small, (0, 0), 8.0)
        big = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
        return ((big > 127) * 255).astype(np.uint8)
