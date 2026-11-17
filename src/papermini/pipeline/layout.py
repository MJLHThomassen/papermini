from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Layout:
    """Result of :func:`build_layout`, all in pixels of one canvas."""

    rgb: np.ndarray  # HxWx3 artwork (white outside the figure)
    cut: np.ndarray  # HxW 0/255 cut shape
    figure: np.ndarray  # HxW 0/255 clean figure mask (drawing that must not be cut)
    px_per_mm: float
    folds: list[tuple[float, float, float]] = field(default_factory=list)  # (x0, x1, y)
    labels: list[tuple[float, float, float]] = field(
        default_factory=list
    )  # (cx, cy, rot)
    tab_width_px: float = 0.0
    tab_height_px: float = 0.0
    figure_height_px: int = 0  # one side, also for double-sided layouts
    # double-sided with a back of text or a number: where it may go (cx, cy, max_w, max_h), px
    back_box: tuple[float, float, float, float] | None = None
    # False when the tab's overlap lies entirely inside the silhouette (a figure whose
    # bottom is wider than the tab), i.e. tab_overlap_mm has no visible effect
    tab_overlap_used: bool = True
    tab_joint_px: float = (
        0.0  # width of paper joining tab and figure, just above the fold
    )
    label_max_w_px: float = 0.0  # room for the tab label (depends on the tab shape)
    # round tabs: exact circles (cx, cy, r, side) in pixel-edge coordinates; side +1 =
    # the half below cy, -1 = above (the mirrored back). The traced cut line is snapped
    # onto them so a round tab is a true circle, not a traced pixel staircase.
    tab_circles: list[tuple[float, float, float, int]] = field(default_factory=list)
    label_max_h_px: float = 0.0
    paper: tuple[int, int, int] = (255, 255, 255)  # margin color, RGB
    tabfill: np.ndarray | None = None  # HxW bool: tab area (painted in the tab color)
    # where this canvas lies in the image given to build_layout, for the front side:
    # (sx, sy, dx, dy) with image pixel = ((x - dx) * sx, (y - dy) * sy)
    src: tuple[float, float, float, float] = (1.0, 1.0, 0.0, 0.0)
    front_top: float = 0.0  # canvas row where the front starts (double-sided: the fold)
