"""Tests of the layout of a mini, on synthetic masks (no model needed)."""

import cv2
import numpy as np
import pytest


def test_keep_all_bridges_a_separate_prop_into_one_cut_shape(
    pipeline, ghost, rgb_like, params, mask_options
):
    m = ghost()
    cv2.circle(m, (980, 800), 50, 255, -1)  # a prop beside the robe
    clean = pipeline.cleaner.clean(
        m, mask_options(close_px=5, keep_all=True, min_area=1000)
    )
    prm = params(keep_all=True, tab=False)
    lay = pipeline.layouts.build(clean, rgb_like(clean), prm)
    n_cut, _ = cv2.connectedComponents((lay.cut > 0).astype(np.uint8))
    n_fig, _ = cv2.connectedComponents((lay.figure > 0).astype(np.uint8))
    assert n_cut - 1 == 1  # one shape to cut out
    assert n_fig - 1 == 2  # the drawing itself is not joined
    # halfway between the figure and the prop only the bridge is cut, bridge_mm wide
    # (measured across it: the bridge may run at an angle)
    cols = np.flatnonzero(lay.figure.any(axis=0))
    gap = int(np.argmax(np.diff(cols)))
    mid = (cols[gap] + cols[gap + 1]) // 2
    rows = np.flatnonzero(lay.cut[:, mid])
    assert len(rows) and rows[-1] - rows[0] + 1 == len(rows)  # one solid band
    inside = cv2.distanceTransform(lay.cut, cv2.DIST_L2, 5)
    width_mm = 2 * inside[rows, mid].max() / lay.px_per_mm
    assert width_mm == pytest.approx(prm.bridge_mm, abs=0.25)


@pytest.mark.parametrize("height_mm", [34.0, 42.0, 56.0])
def test_mm_scaling(pipeline, ghost, rgb_like, height_mm, params, mask_options):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    lay = pipeline.layouts.build(clean, rgb_like(clean), params(height_mm=height_mm))
    _x0, y0, _x1, y1 = pipeline.morphology.bbox(lay.figure)
    assert (y1 - y0 + 1) / lay.px_per_mm == pytest.approx(height_mm, abs=1e-9)


def test_margin_width(pipeline, ghost, rgb_like, params, mask_options):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    prm = params(margin_mm=1.6, tab=False)
    lay = pipeline.layouts.build(clean, rgb_like(clean), prm)
    # distance from every cut-shape boundary pixel to the figure, in mm
    dist = cv2.distanceTransform(255 - lay.figure, cv2.DIST_L2, 5) / lay.px_per_mm
    edge = lay.cut - cv2.erode(lay.cut, np.ones((3, 3), np.uint8))
    d = dist[edge > 0]
    assert d.min() > 1.0  # never closer than ~margin minus smoothing
    assert np.median(d) == pytest.approx(1.6, abs=0.25)


def test_tab_placement(pipeline, ghost, rgb_like, params, mask_options):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    prm = params(tab_width_mm=22, tab_height_mm=12, fold_mm=1.0)
    lay = pipeline.layouts.build(clean, rgb_like(clean), prm)
    pxmm = lay.px_per_mm
    ((fx0, fx1, fy),) = lay.folds
    assert (fx1 - fx0) / pxmm == pytest.approx(22, abs=0.05)
    # centred on the figure's bottom
    fig_x0, _, fig_x1, fig_y1 = pipeline.morphology.bbox(lay.figure)
    assert (fx0 + fx1) / 2 == pytest.approx((fig_x0 + fig_x1) / 2, abs=2)
    # fold 1 mm above the silhouette's lowest point = (margin - 1) mm below the figure
    assert (fy - fig_y1) / pxmm == pytest.approx(1.6 - 1.0, abs=0.15)
    # tab reaches 12 mm below the fold
    _, _, _, cut_y1 = pipeline.morphology.bbox(lay.cut)
    assert (cut_y1 - fy) / pxmm == pytest.approx(12, abs=0.1)
    ((_lx, ly, rot),) = lay.labels
    assert rot == 0 and (ly - fy) / pxmm == pytest.approx(6, abs=0.05)


def test_border_touching_figure_gets_margin_beyond_old_edge(
    pipeline, ghost, rgb_like, params, mask_options
):
    clean = pipeline.cleaner.clean(ghost(touch_border=True), mask_options(close_px=9))
    assert clean[:, 0].any()  # touches the left edge
    lay = pipeline.layouts.build(clean, rgb_like(clean), params(margin_mm=1.6))
    fx0 = pipeline.morphology.bbox(lay.figure)[0]
    cx0 = pipeline.morphology.bbox(lay.cut)[0]
    assert (fx0 - cx0) / lay.px_per_mm == pytest.approx(1.6, abs=0.3)


def test_double_sided_is_mirror_symmetric(
    pipeline, ghost, rgb_like, params, mask_options
):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    lay = pipeline.layouts.build(clean, rgb_like(clean), params(double_sided=True))
    assert np.array_equal(lay.cut, lay.cut[::-1])
    assert len(lay.folds) == 3 and len(lay.labels) == 2
    n, _ = cv2.connectedComponents(lay.cut)
    assert n == 2


def test_top_fold_is_where_a_raised_wing_meets_the_fold(
    pipeline, rgb_like, params, mask_options
):
    # a body with a wing raised high on the left and the head lower on the right:
    # the halves meet at the wing, so the bridge and the fold belong there, not in
    # the gap between wing and head
    m = np.zeros((1400, 1100), np.uint8)
    cv2.rectangle(m, (300, 500), (800, 1300), 255, -1)  # body
    cv2.fillPoly(
        m, [np.array([(300, 700), (150, 100), (350, 100), (450, 600)])], 255
    )  # wing
    cv2.circle(m, (750, 330), 100, 255, -1)  # head
    clean = pipeline.cleaner.clean(m, mask_options(close_px=9))
    lay = pipeline.layouts.build(clean, rgb_like(clean), params(double_sided=True))
    h = int(lay.front_top)
    top = [(a, b) for a, b, y in lay.folds if y == h]
    paper = np.flatnonzero(lay.cut[h])
    assert all(
        any(a <= x < b for a, b in top) for x in paper
    )  # the fold spans the joint
    first = (
        h + np.flatnonzero(lay.figure[h:].any(axis=1))[0]
    )  # the figure's highest row
    tip = np.flatnonzero(lay.figure[first])
    wing_x = (tip.min() + tip.max()) / 2  # the wing tip
    assert len(top) == 1 and top[0][0] < wing_x < top[0][1]
    assert (
        abs((top[0][0] + top[0][1]) / 2 - wing_x) < 2 * lay.px_per_mm
    )  # centred on it


@pytest.mark.parametrize("back", ["mirror", "blank", "text"])
def test_double_sided_back_modes(pipeline, ghost, rgb_like, back, params, mask_options):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    rgb = rgb_like(clean)
    lay = pipeline.layouts.build(clean, rgb, params(double_sided=True, back=back))
    h = lay.cut.shape[0] // 2
    assert np.array_equal(lay.cut, lay.cut[::-1])  # shape always mirrored
    back_half = lay.rgb[:h][lay.cut[:h] > 0]
    if back == "mirror":
        assert np.array_equal(lay.rgb[:h], lay.rgb[h:][::-1]) and back_half.min() < 255
        assert lay.back_box is None
    else:
        assert back_half.min() == 255  # plain paper on the back
        assert lay.rgb[h:][lay.figure[h:] > 0].min() < 255  # front keeps the drawing
    if back == "text":
        cx, cy, w, hh = lay.back_box
        assert cy < h and lay.figure[int(cy), int(cx)] > 0  # inside the back silhouette
        assert 0 < w < lay.cut.shape[1] and 0 < hh < h
    else:
        assert lay.back_box is None


def test_bad_back_mode(pipeline, ghost, rgb_like, params, mask_options):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    with pytest.raises(ValueError, match="back must be"):
        pipeline.layouts.build(
            clean, rgb_like(clean), params(double_sided=True, back="nope")
        )


def test_tab_overlap_only_matters_for_narrow_bottoms(
    pipeline, rgb_like, params, mask_options
):
    # wide bottom (a ~30 mm robe, wider than the 22 mm tab): overlap changes nothing
    wide = np.zeros((1400, 1100), np.uint8)
    cv2.ellipse(wide, (550, 450), (300, 260), 0, 0, 360, 255, -1)
    cv2.rectangle(wide, (190, 450), (910, 1200), 255, -1)
    clean = pipeline.cleaner.clean(wide, mask_options(close_px=9))
    robe = {"height_mm": 42.0, "tab_width_mm": 22.0}
    areas = [
        int(
            (
                pipeline.layouts.build(
                    clean, rgb_like(clean), params(tab_overlap_mm=ov, **robe)
                ).cut
                > 0
            ).sum()
        )
        for ov in (0, 3, 10)
    ]
    assert len(set(areas)) == 1
    lay = pipeline.layouts.build(clean, rgb_like(clean), params(**robe))
    assert not lay.tab_overlap_used

    # narrow 'leg': more overlap = more paper joining tab and figure
    m = np.zeros((1400, 1000), np.uint8)
    cv2.ellipse(m, (500, 500), (250, 350), 0, 0, 360, 255, -1)
    cv2.rectangle(m, (470, 800), (530, 1250), 255, -1)
    lays = [
        pipeline.layouts.build(m, rgb_like(m), params(tab_overlap_mm=ov))
        for ov in (1, 3, 10)
    ]
    areas = [int((lay.cut > 0).sum()) for lay in lays]
    assert areas[0] < areas[1] < areas[2]
    assert all(lay.tab_overlap_used for lay in lays)
    # the drawing is never cut, whatever the overlap
    for lay in lays:
        assert not np.any((lay.figure > 0) & (lay.cut == 0))


def test_round_tab_is_a_half_disc(pipeline, ghost, rgb_like, params, mask_options):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    lay = pipeline.layouts.build(
        clean, rgb_like(clean), params(tab_shape="round", tab_radius_mm=12.5)
    )
    pxmm = lay.px_per_mm
    ((fx0, fx1, fy),) = lay.folds
    r = 12.5 * pxmm
    _, _, _, cut_y1 = pipeline.morphology.bbox(lay.cut)
    assert (cut_y1 - fy) / pxmm == pytest.approx(12.5, abs=0.2)  # depth = radius
    (fx0 + fx1) / 2
    for frac in (0.3, 0.6, 0.9):  # chord widths of a circle
        y = round(fy + frac * r)
        cols = np.flatnonzero(lay.cut[y])
        width = (cols[-1] - cols[0] + 1) / pxmm
        assert width == pytest.approx(2 * 12.5 * np.sqrt(1 - frac**2), abs=0.6)
    assert not np.any((lay.figure > 0) & (lay.cut == 0))


def test_tab_and_margin_colors(pipeline, ghost, rgb_like, params, mask_options):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    rgb = rgb_like(clean)
    lay = pipeline.layouts.build(
        clean, rgb, params(tab_color="#3b6e2a", margin_color="#f3e6c8")
    )
    ((_fx0, _fx1, fy),) = lay.folds
    below = lay.rgb[int(fy) + 3 :][lay.cut[int(fy) + 3 :] > 0]
    assert (below == (0x3B, 0x6E, 0x2A)).all()  # tab in the tab color
    margin = (lay.cut > 0) & (
        pipeline.morphology.dilate(lay.figure, 0.6 * lay.px_per_mm) == 0
    )
    margin[int(fy) :] = False
    assert (lay.rgb[margin] == (0xF3, 0xE6, 0xC8)).all()  # margin in the margin color
    # with the original image in the margin, the tab background is plain white
    lay = pipeline.layouts.build(
        clean, rgb, params(margin_fill="image", margin_color="#000000")
    )
    ((_fx0, _fx1, fy),) = lay.folds
    assert (lay.rgb[int(fy) + 3 :][lay.cut[int(fy) + 3 :] > 0] == 255).all()


def test_double_sided_blank_back_keeps_tab_color(
    pipeline, ghost, rgb_like, params, mask_options
):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    lay = pipeline.layouts.build(
        clean,
        rgb_like(clean),
        params(double_sided=True, back="blank", tab_shape="round", tab_color="#3b6e2a"),
    )
    assert np.array_equal(lay.cut, lay.cut[::-1])
    green = (lay.rgb == (0x3B, 0x6E, 0x2A)).all(-1)
    h = lay.cut.shape[0] // 2
    assert green[:h].sum() == pytest.approx(
        green[h:].sum(), rel=0.02
    )  # both tabs colored


def test_margin_color_does_not_color_the_label_tab(
    pipeline, ghost, rgb_like, params, mask_options
):
    """Regression: the margin color used to show behind the tab label."""
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    rgb = rgb_like(clean)
    for tab_color, expected in (
        (None, (255, 255, 255)),
        ("#ddeeff", (0xDD, 0xEE, 0xFF)),
    ):
        kw = {"tab_color": tab_color} if tab_color else {}
        lay = pipeline.layouts.build(clean, rgb, params(margin_color="#f3e6c8", **kw))
        ((_fx0, _fx1, fy),) = lay.folds
        assert lay.labels  # the label is still printed on the tab
        tab = lay.rgb[int(fy) + 3 :][lay.cut[int(fy) + 3 :] > 0]
        assert (tab == expected).all()
        margin = (lay.cut > 0) & (
            pipeline.morphology.dilate(lay.figure, 0.6 * lay.px_per_mm) == 0
        )
        margin[int(fy) :] = False
        assert (
            lay.rgb[margin] == (0xF3, 0xE6, 0xC8)
        ).all()  # margin keeps its own color


def test_tab_joint_width_and_overlap(pipeline, rgb_like, params):
    """With fold and overlap at 0 a pointed bottom is joined to the tab by a sliver;
    the overlap widens that joint to the full tab."""
    m = np.zeros((1400, 1000), np.uint8)
    cv2.fillPoly(m, [np.array([[250, 300], [750, 300], [500, 1250]])], 255)
    rgb = rgb_like(m)
    thin = pipeline.layouts.build(m, rgb, params(tab_width_mm=22.0))
    wide = pipeline.layouts.build(m, rgb, params(tab_width_mm=22.0, tab_overlap_mm=3))
    assert thin.tab_joint_px / thin.px_per_mm < 8
    assert wide.tab_joint_px / wide.px_per_mm == pytest.approx(22, abs=0.5)


def test_blank_back_has_its_own_color(pipeline, ghost, rgb_like, params, mask_options):
    clean = pipeline.cleaner.clean(ghost(), mask_options(close_px=9))
    lay = pipeline.layouts.build(
        clean,
        rgb_like(clean),
        params(
            double_sided=True,
            back="blank",
            back_color="#202040",
            margin_color="#f3e6c8",
            tab_color="#3b6e2a",
        ),
    )
    h = lay.cut.shape[0] // 2
    back = lay.rgb[:h][lay.cut[:h] > 0]
    colors = {tuple(c) for c in back}
    assert (0x20, 0x20, 0x40) in colors and (
        0x3B,
        0x6E,
        0x2A,
    ) in colors  # back + its tab
    assert (0xF3, 0xE6, 0xC8) not in colors  # no margin color
