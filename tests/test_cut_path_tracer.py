"""Tests of tracing the cut path, on layouts of synthetic masks."""

import cv2
import numpy as np
import pytest


@pytest.mark.parametrize("smooth", [False, True])
def test_cut_path_is_closed_single_path_outside_drawing(
    pipeline, ghost, rgb_like, smooth, params, mask_options
):
    clean = pipeline.cleaner.clean(ghost(touch_border=True), mask_options(close_px=9))
    lay = pipeline.layouts.build(clean, rgb_like(clean), params())
    path = pipeline.tracer.trace(lay.cut, lay.px_per_mm, 0.15, smooth)
    inside = pipeline.tracer.rasterize(path, lay.cut.shape, antialias=False)
    n, _ = cv2.connectedComponents(inside)
    assert n == 2  # one filled region
    assert not np.any((lay.figure > 0) & (inside == 0))  # drawing never cut


def test_bezier_stays_close_to_polygon(pipeline, ghost, rgb_like, params, mask_options):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    lay = pipeline.layouts.build(clean, rgb_like(clean), params())
    poly = pipeline.tracer.trace(lay.cut, lay.px_per_mm, 0.15, smooth=False)
    curve = pipeline.tracer.trace(lay.cut, lay.px_per_mm, 0.15, smooth=True)
    poly_c = poly.points.astype(np.float32).reshape(-1, 1, 2)
    dev = [
        abs(cv2.pointPolygonTest(poly_c, (float(x), float(y)), True))
        for x, y in curve.flatten(16)
    ]
    assert max(dev) / lay.px_per_mm < 0.3


@pytest.mark.parametrize("simplify_mm", [0.01, 0.15])
@pytest.mark.parametrize("double", [False, True])
def test_round_tab_cut_line_is_a_true_circle(
    pipeline, ghost, rgb_like, simplify_mm, double, params, mask_options
):
    """Regression: at a fine simplify setting the round tab traced the pixel staircase
    and came out lumpy (up to 0.2 mm off)."""
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    lay = pipeline.layouts.build(
        clean,
        rgb_like(clean),
        params(tab_shape="round", tab_radius_mm=12.5, double_sided=double),
    )
    path = pipeline.tracer.trace(
        lay.cut, lay.px_per_mm, simplify_mm, True, lay.tab_circles
    )
    pts = path.flatten(24)
    assert len(lay.tab_circles) == (2 if double else 1)
    for ccx, ccy, r, side in lay.tab_circles:
        arc = pts[(side * (pts[:, 1] - ccy) > 0.2 * r)]  # well inside the half disc
        err = np.abs(np.hypot(arc[:, 0] - ccx, arc[:, 1] - ccy) - r) / lay.px_per_mm
        assert len(arc) > 20 and err.max() < 0.02  # mm
