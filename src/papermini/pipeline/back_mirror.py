from __future__ import annotations

import numpy as np

from .layout import Layout
from .morphology import Morphology
from .params import BACK_MODES


class BackMirror:
    """Turns a layout into a double-sided one: the front, with its back mirrored above
    a fold."""

    def __init__(self, morphology: Morphology):
        self._morph = morphology

    def mirror(
        self,
        lay: Layout,
        y_top: int,
        back: str = "mirror",
        back_rgb: tuple[int, int, int] = (255, 255, 255),
    ) -> Layout:
        """Return the front plus its vertically mirrored back, joined at a fold through
        ``y_top``.

        The fold line runs across all the paper that joins the halves there (the top
        bridge, and a wing or head that reaches the fold beside it).
        The cut shape is always mirrored (so the halves line up when glued); with
        any other ``back`` the back half is filled with ``back_rgb`` instead of the
        mirrored drawing, except the tab, which keeps its color. "text", "number" and
        "text_number" also report where they fit (``back_box``).
        """
        if back not in BACK_MODES:
            raise ValueError(
                f"back must be one of {', '.join(BACK_MODES)}, not {back!r}"
            )

        def stack(a, blank=False):
            front = a[y_top:]
            if not blank:
                top = front[::-1]
            else:
                top = np.empty_like(front)
                top[:] = back_rgb
                if lay.tabfill is not None:  # the back tab keeps its color
                    keep = lay.tabfill[y_top:][::-1]
                    top[keep] = front[::-1][keep]
            return np.concatenate([top, front], axis=0)

        h = lay.cut.shape[0] - y_top  # rows of each half; fold is at row h
        folds = [(float(a), float(b), float(h)) for a, b in self._runs(lay.cut[y_top])]
        labels = []
        for fx0, fx1, fy in lay.folds:
            fy = fy - y_top
            folds += [(fx0, fx1, h + fy), (fx0, fx1, h - fy)]
        for lx, ly, _ in lay.labels:
            ly = ly - y_top
            labels += [(lx, h + ly, 0.0), (lx, h - ly, 180.0)]
        figure = stack(lay.figure)
        return Layout(
            rgb=stack(lay.rgb, blank=back != "mirror"),
            cut=stack(lay.cut),
            figure=figure,
            px_per_mm=lay.px_per_mm,
            folds=folds,
            labels=labels,
            tab_width_px=lay.tab_width_px,
            tab_height_px=lay.tab_height_px,
            figure_height_px=lay.figure_height_px,
            back_box=self._text_box(figure[:h])
            if back in ("text", "number", "text_number")
            else None,
            tab_overlap_used=lay.tab_overlap_used,
            tab_joint_px=lay.tab_joint_px,
            tab_circles=[
                c
                for x, y, r, d in lay.tab_circles
                for c in ((x, h + (y - y_top), r, d), (x, h - (y - y_top), r, -d))
            ],
            label_max_w_px=lay.label_max_w_px,
            label_max_h_px=lay.label_max_h_px,
            paper=lay.paper,
            tabfill=None if lay.tabfill is None else stack(lay.tabfill),
            # the front moved down by h - y_top rows (the mirrored back is above it)
            src=(*lay.src[:3], lay.src[3] + h - y_top),
            front_top=float(h),
        )

    @staticmethod
    def _runs(row: np.ndarray) -> list[tuple[int, int]]:
        """Return the (start, end) column pairs of the filled runs in a row, end
        exclusive."""
        d = np.diff(np.concatenate([[0], (row > 0).astype(np.int8), [0]]))
        return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))

    def _text_box(self, fig: np.ndarray) -> tuple[float, float, float, float]:
        """Return the room for text inside a figure silhouette: (cx, cy, max_w, max_h)
        in px.

        Centred on the figure; the width is what the silhouette offers through its
        middle (a narrow row there limits it), the height ~60% of the figure.
        """
        x0, y0, x1, y1 = self._morph.bbox(fig)
        cx, cy = (x0 + x1 + 1) / 2, (y0 + y1 + 1) / 2
        hh = (y1 - y0 + 1) * 0.3
        rows = fig[int(cy - hh / 2) : int(cy + hh / 2) + 1] > 0
        # centre on the body, not on the bounding box (an arm or prop would pull it
        # sideways)
        centres = []
        for r in rows:
            xs = np.flatnonzero(r)
            if len(xs):
                runs = np.split(xs, np.flatnonzero(np.diff(xs) > 1) + 1)
                body = max(runs, key=len)
                centres.append((body[0] + body[-1] + 1) / 2)
        if centres:
            cx = float(np.median(centres))
        widths: list[int] = []
        for r in rows:
            xs = np.flatnonzero(r)
            if len(xs):
                # the run through the centre column (holes/arms beside it do not count)
                c = int(np.clip(round(cx), xs[0], xs[-1]))
                left = c - np.argmin(r[c::-1]) + 1 if not r[c::-1].all() else 0
                right = c + np.argmin(r[c:]) if not r[c:].all() else len(r)
                widths.append(max(0, int(right - left)))
        w = float(np.percentile(widths, 20)) if widths else float(x1 - x0 + 1)
        return cx, cy, w * 0.82, (y1 - y0 + 1) * 0.6
