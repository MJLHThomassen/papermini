"""Geometry tests on synthetic masks (no model needed)."""

import numpy as np
import cv2
import pytest

from papermini import geometry as geo


def ghost(h=1400, w=1100, touch_border=False, ring=False):
    """A blob figure; optional see-through 'ring' (hole) and border contact."""
    m = np.zeros((h, w), np.uint8)
    cv2.ellipse(m, (w // 2, 450), (220, 260), 0, 0, 360, 255, -1)        # head/body
    cv2.rectangle(m, (w // 2 - 160, 450), (w // 2 + 160, 1200), 255, -1)  # robe
    if ring:
        cv2.circle(m, (w // 2, 700), 90, 0, -1)                          # translucent hole
    if touch_border:
        cv2.rectangle(m, (0, 600), (w // 2, 680), 255, -1)                # arm to the left edge
    return m


def rgb_like(m):
    return np.dstack([255 - m // 2] * 3).astype(np.uint8)


def test_fill_holes_closes_translucent_areas():
    m = ghost(ring=True)
    assert m[700, 550] == 0
    clean = geo.clean_mask(m, threshold=40, close_px=9)
    assert clean[700, 550] == 255


def test_largest_component_drops_specks_and_keep_all_keeps_props():
    m = ghost()
    cv2.circle(m, (100, 100), 4, 255, -1)       # speck
    cv2.circle(m, (950, 300), 40, 255, -1)      # floating prop
    only = geo.clean_mask(m, close_px=5)
    assert only[300, 950] == 0 and only[100, 100] == 0
    both = geo.clean_mask(m, close_px=5, keep_all=True, min_area=1000)
    assert both[300, 950] == 255 and both[100, 100] == 0


@pytest.mark.parametrize("height_mm", [34.0, 42.0, 56.0])
def test_mm_scaling(height_mm):
    clean = geo.clean_mask(ghost(), close_px=9)
    lay = geo.build_layout(clean, rgb_like(clean), geo.Params(height_mm=height_mm))
    x0, y0, x1, y1 = geo.bbox(lay.figure)
    assert (y1 - y0 + 1) / lay.px_per_mm == pytest.approx(height_mm, abs=1e-9)


def test_margin_width():
    clean = geo.clean_mask(ghost(), close_px=9)
    prm = geo.Params(margin_mm=1.6, tab=False)
    lay = geo.build_layout(clean, rgb_like(clean), prm)
    # distance from every cut-shape boundary pixel to the figure, in mm
    dist = cv2.distanceTransform(255 - lay.figure, cv2.DIST_L2, 5) / lay.px_per_mm
    edge = lay.cut - cv2.erode(lay.cut, np.ones((3, 3), np.uint8))
    d = dist[edge > 0]
    assert d.min() > 1.0          # never closer than ~margin minus smoothing
    assert np.median(d) == pytest.approx(1.6, abs=0.25)


def test_tab_placement():
    clean = geo.clean_mask(ghost(), close_px=9)
    prm = geo.Params(tab_width_mm=22, tab_height_mm=12, fold_mm=1.0)
    lay = geo.build_layout(clean, rgb_like(clean), prm)
    pxmm = lay.px_per_mm
    (fx0, fx1, fy), = lay.folds
    assert (fx1 - fx0) / pxmm == pytest.approx(22, abs=0.05)
    # centred on the figure's bottom
    fig_x0, _, fig_x1, fig_y1 = geo.bbox(lay.figure)
    assert (fx0 + fx1) / 2 == pytest.approx((fig_x0 + fig_x1) / 2, abs=2)
    # fold 1 mm above the silhouette's lowest point = (margin - 1) mm below the figure
    assert (fy - fig_y1) / pxmm == pytest.approx(1.6 - 1.0, abs=0.15)
    # tab reaches 12 mm below the fold
    _, _, _, cut_y1 = geo.bbox(lay.cut)
    assert (cut_y1 - fy) / pxmm == pytest.approx(12, abs=0.1)
    (lx, ly, rot), = lay.labels
    assert rot == 0 and (ly - fy) / pxmm == pytest.approx(6, abs=0.05)


@pytest.mark.parametrize("smooth", [False, True])
def test_cut_path_is_closed_single_path_outside_drawing(smooth):
    clean = geo.clean_mask(ghost(touch_border=True), close_px=9)
    lay = geo.build_layout(clean, rgb_like(clean), geo.Params())
    path = geo.trace_cut(lay.cut, lay.px_per_mm, 0.15, smooth)
    inside = geo.rasterize(path, lay.cut.shape, antialias=False)
    n, _ = cv2.connectedComponents(inside)
    assert n == 2                                   # one filled region
    assert not np.any((lay.figure > 0) & (inside == 0))  # drawing never cut


def test_border_touching_figure_gets_margin_beyond_old_edge():
    clean = geo.clean_mask(ghost(touch_border=True), close_px=9)
    assert clean[:, 0].any()  # touches the left edge
    lay = geo.build_layout(clean, rgb_like(clean), geo.Params(margin_mm=1.6))
    fx0 = geo.bbox(lay.figure)[0]
    cx0 = geo.bbox(lay.cut)[0]
    assert (fx0 - cx0) / lay.px_per_mm == pytest.approx(1.6, abs=0.3)


def test_double_sided_is_mirror_symmetric():
    clean = geo.clean_mask(ghost(), close_px=9)
    lay = geo.build_layout(clean, rgb_like(clean), geo.Params(double_sided=True))
    assert np.array_equal(lay.cut, lay.cut[::-1])
    assert len(lay.folds) == 3 and len(lay.labels) == 2
    n, _ = cv2.connectedComponents(lay.cut)
    assert n == 2


def test_top_fold_is_where_a_raised_wing_meets_the_fold():
    # a body with a wing raised high on the left and the head lower on the right:
    # the halves meet at the wing, so the bridge and the fold belong there, not in
    # the gap between wing and head
    m = np.zeros((1400, 1100), np.uint8)
    cv2.rectangle(m, (300, 500), (800, 1300), 255, -1)                       # body
    cv2.fillPoly(m, [np.array([(300, 700), (150, 100), (350, 100), (450, 600)])], 255)  # wing
    cv2.circle(m, (750, 330), 100, 255, -1)                                  # head
    clean = geo.clean_mask(m, close_px=9)
    lay = geo.build_layout(clean, rgb_like(clean), geo.Params(double_sided=True))
    h = int(lay.front_top)
    top = [(a, b) for a, b, y in lay.folds if y == h]
    paper = np.flatnonzero(lay.cut[h])
    assert all(any(a <= x < b for a, b in top) for x in paper)  # the fold spans the joint
    first = h + np.flatnonzero(lay.figure[h:].any(axis=1))[0]  # the figure's highest row
    tip = np.flatnonzero(lay.figure[first])
    wing_x = (tip.min() + tip.max()) / 2  # the wing tip
    assert len(top) == 1 and top[0][0] < wing_x < top[0][1]
    assert abs((top[0][0] + top[0][1]) / 2 - wing_x) < 2 * lay.px_per_mm  # centred on it


def test_bezier_stays_close_to_polygon():
    clean = geo.clean_mask(ghost(), close_px=9)
    lay = geo.build_layout(clean, rgb_like(clean), geo.Params())
    poly = geo.trace_cut(lay.cut, lay.px_per_mm, 0.15, smooth=False)
    curve = geo.trace_cut(lay.cut, lay.px_per_mm, 0.15, smooth=True)
    poly_c = poly.points.astype(np.float32).reshape(-1, 1, 2)
    dev = [abs(cv2.pointPolygonTest(poly_c, (float(x), float(y)), True))
           for x, y in curve.flatten(16)]
    assert max(dev) / lay.px_per_mm < 0.3


@pytest.mark.parametrize("back", ["mirror", "blank", "text"])
def test_double_sided_back_modes(back):
    clean = geo.clean_mask(ghost(), close_px=9)
    rgb = rgb_like(clean)
    lay = geo.build_layout(clean, rgb, geo.Params(double_sided=True, back=back))
    h = lay.cut.shape[0] // 2
    assert np.array_equal(lay.cut, lay.cut[::-1])          # shape always mirrored
    back_half = lay.rgb[:h][lay.cut[:h] > 0]
    if back == "mirror":
        assert np.array_equal(lay.rgb[:h], lay.rgb[h:][::-1]) and back_half.min() < 255
        assert lay.back_box is None
    else:
        assert back_half.min() == 255                       # plain paper on the back
        assert lay.rgb[h:][lay.figure[h:] > 0].min() < 255  # front keeps the drawing
    if back == "text":
        cx, cy, w, hh = lay.back_box
        assert cy < h and lay.figure[int(cy), int(cx)] > 0   # inside the back silhouette
        assert 0 < w < lay.cut.shape[1] and 0 < hh < h
    else:
        assert lay.back_box is None


def test_bad_back_mode():
    clean = geo.clean_mask(ghost(), close_px=9)
    with pytest.raises(ValueError, match="back must be"):
        geo.build_layout(clean, rgb_like(clean), geo.Params(double_sided=True, back="nope"))


def test_tab_overlap_only_matters_for_narrow_bottoms():
    # wide bottom (a ~30 mm robe, wider than the 22 mm tab): overlap changes nothing
    wide = np.zeros((1400, 1100), np.uint8)
    cv2.ellipse(wide, (550, 450), (300, 260), 0, 0, 360, 255, -1)
    cv2.rectangle(wide, (190, 450), (910, 1200), 255, -1)
    clean = geo.clean_mask(wide, close_px=9)
    areas = [int((geo.build_layout(clean, rgb_like(clean), geo.Params(tab_overlap_mm=ov)).cut > 0).sum())
             for ov in (0, 3, 10)]
    assert len(set(areas)) == 1
    assert not geo.build_layout(clean, rgb_like(clean), geo.Params()).tab_overlap_used

    # narrow 'leg': more overlap = more paper joining tab and figure
    m = np.zeros((1400, 1000), np.uint8)
    cv2.ellipse(m, (500, 500), (250, 350), 0, 0, 360, 255, -1)
    cv2.rectangle(m, (470, 800), (530, 1250), 255, -1)
    lays = [geo.build_layout(m, rgb_like(m), geo.Params(tab_overlap_mm=ov)) for ov in (1, 3, 10)]
    areas = [int((lay.cut > 0).sum()) for lay in lays]
    assert areas[0] < areas[1] < areas[2]
    assert all(lay.tab_overlap_used for lay in lays)
    # the drawing is never cut, whatever the overlap
    for lay in lays:
        assert not np.any((lay.figure > 0) & (lay.cut == 0))



def test_round_tab_is_a_half_disc():
    clean = geo.clean_mask(ghost(), close_px=9)
    lay = geo.build_layout(clean, rgb_like(clean), geo.Params(tab_shape="round", tab_radius_mm=12.5))
    pxmm = lay.px_per_mm
    (fx0, fx1, fy), = lay.folds
    r = 12.5 * pxmm
    _, _, _, cut_y1 = geo.bbox(lay.cut)
    assert (cut_y1 - fy) / pxmm == pytest.approx(12.5, abs=0.2)   # depth = radius
    cx = (fx0 + fx1) / 2
    for frac in (0.3, 0.6, 0.9):                                   # chord widths of a circle
        y = int(round(fy + frac * r))
        cols = np.flatnonzero(lay.cut[y])
        width = (cols[-1] - cols[0] + 1) / pxmm
        assert width == pytest.approx(2 * 12.5 * np.sqrt(1 - frac ** 2), abs=0.6)
    assert not np.any((lay.figure > 0) & (lay.cut == 0))


def test_tab_and_margin_colours():
    clean = geo.clean_mask(ghost(), close_px=9)
    rgb = rgb_like(clean)
    lay = geo.build_layout(clean, rgb, geo.Params(tab_color="#3b6e2a",
                                                  margin_color="#f3e6c8"))
    (fx0, fx1, fy), = lay.folds
    below = lay.rgb[int(fy) + 3:][lay.cut[int(fy) + 3:] > 0]
    assert (below == (0x3b, 0x6e, 0x2a)).all()                     # tab in the tab colour
    margin = (lay.cut > 0) & (geo.dilate(lay.figure, 0.6 * lay.px_per_mm) == 0)
    margin[int(fy):] = False
    assert (lay.rgb[margin] == (0xf3, 0xe6, 0xc8)).all()          # margin in the margin colour
    # with the original image in the margin, the tab background is plain white
    lay = geo.build_layout(clean, rgb, geo.Params(margin_fill="image", margin_color="#000000"))
    (fx0, fx1, fy), = lay.folds
    assert (lay.rgb[int(fy) + 3:][lay.cut[int(fy) + 3:] > 0] == 255).all()


def test_double_sided_blank_back_keeps_tab_colour():
    clean = geo.clean_mask(ghost(), close_px=9)
    lay = geo.build_layout(clean, rgb_like(clean), geo.Params(
        double_sided=True, back="blank", tab_shape="round", tab_color="#3b6e2a"))
    assert np.array_equal(lay.cut, lay.cut[::-1])
    green = (lay.rgb == (0x3b, 0x6e, 0x2a)).all(-1)
    h = lay.cut.shape[0] // 2
    assert green[:h].sum() == pytest.approx(green[h:].sum(), rel=0.02)  # both tabs coloured


def test_margin_colour_does_not_colour_the_label_tab():
    """Regression: the margin colour used to show behind the tab label."""
    clean = geo.clean_mask(ghost(), close_px=9)
    rgb = rgb_like(clean)
    for tab_color, expected in ((None, (255, 255, 255)), ("#ddeeff", (0xdd, 0xee, 0xff))):
        kw = {"tab_color": tab_color} if tab_color else {}
        lay = geo.build_layout(clean, rgb, geo.Params(margin_color="#f3e6c8", **kw))
        (fx0, fx1, fy), = lay.folds
        assert lay.labels  # the label is still printed on the tab
        tab = lay.rgb[int(fy) + 3:][lay.cut[int(fy) + 3:] > 0]
        assert (tab == expected).all()
        margin = (lay.cut > 0) & (geo.dilate(lay.figure, 0.6 * lay.px_per_mm) == 0)
        margin[int(fy):] = False
        assert (lay.rgb[margin] == (0xf3, 0xe6, 0xc8)).all()  # margin keeps its own colour



def test_tab_joint_width_and_overlap():
    """With fold and overlap at 0 a pointed bottom is joined to the tab by a sliver;
    the overlap widens that joint to the full tab."""
    m = np.zeros((1400, 1000), np.uint8)
    cv2.fillPoly(m, [np.array([[250, 300], [750, 300], [500, 1250]])], 255)
    rgb = rgb_like(m)
    thin = geo.build_layout(m, rgb, geo.Params())
    wide = geo.build_layout(m, rgb, geo.Params(tab_overlap_mm=3))
    assert thin.tab_joint_px / thin.px_per_mm < 8
    assert wide.tab_joint_px / wide.px_per_mm == pytest.approx(22, abs=0.5)


def test_blank_back_has_its_own_colour():
    clean = geo.clean_mask(ghost(), close_px=9)
    lay = geo.build_layout(clean, rgb_like(clean), geo.Params(
        double_sided=True, back="blank", back_color="#202040", margin_color="#f3e6c8",
        tab_color="#3b6e2a"))
    h = lay.cut.shape[0] // 2
    back = lay.rgb[:h][lay.cut[:h] > 0]
    colours = {tuple(c) for c in back}
    assert (0x20, 0x20, 0x40) in colours and (0x3b, 0x6e, 0x2a) in colours  # back + its tab
    assert (0xf3, 0xe6, 0xc8) not in colours                                # no margin colour


def _ring_drawing():
    """A grey pencil ring on white paper, its mask, and the same as a soft cut-out."""
    img = np.full((400, 400, 3), 255, np.uint8)
    cv2.circle(img, (200, 200), 120, (150, 150, 150), 6, cv2.LINE_AA)
    fig = np.zeros((400, 400), np.uint8)
    cv2.circle(fig, (200, 200), 126, 255, -1)
    return img, fig


def test_no_white_halo_on_a_dark_margin():
    """Regression: the white paper around the drawing showed as a halo on dark margins."""
    img, fig = _ring_drawing()
    pxmm = 20.0
    art = geo.compose_art(img, fig, fig, (0, 0, 0), pxmm, False)
    outside = geo.dilate(fig, 0.6 * pxmm) & ~fig          # just beyond the outline
    assert art[outside > 0].max() < 40                       # no light halo there
    assert art[200, 200].min() == 255                        # the drawing's inside stays white
    # with a white margin the result is the plain picture, as before
    plain = geo.compose_art(img, fig, fig, (255, 255, 255), pxmm, False)
    assert np.abs(plain[fig > 0].astype(int) - img[fig > 0]).max() <= 1


def test_alpha_cutout_blends_into_the_margin():
    """A cut-out's soft edge blends into the margin colour (no white fringe), while
    see-through parts inside the figure look as they do on white paper."""
    img, fig = _ring_drawing()
    alpha = cv2.GaussianBlur(fig, (0, 0), 3)                 # soft edge
    alpha[150:250, 150:250] = 120                            # a translucent patch inside
    rgba = np.dstack([img, alpha]).astype(np.float32)
    rgba[..., :3] *= rgba[..., 3:4] / 255.0                  # premultiplied, as loaded
    rgba = np.clip(rgba + 0.5, 0, 255).astype(np.uint8)
    art = geo.compose_art(rgba, fig, fig, (0, 0, 0), 20.0, False)
    edge = (alpha > 5) & (alpha < 250) & (fig == 0)
    assert art[edge].max() < 40                              # soft edge: dark, not white
    assert art[200, 200].min() > 240                         # translucent inside: light



@pytest.mark.parametrize("simplify_mm", [0.01, 0.15])
@pytest.mark.parametrize("double", [False, True])
def test_round_tab_cut_line_is_a_true_circle(simplify_mm, double):
    """Regression: at a fine simplify setting the round tab traced the pixel staircase
    and came out lumpy (up to 0.2 mm off)."""
    clean = geo.clean_mask(ghost(), close_px=9)
    lay = geo.build_layout(clean, rgb_like(clean), geo.Params(
        tab_shape="round", tab_radius_mm=12.5, double_sided=double))
    path = geo.trace_cut(lay.cut, lay.px_per_mm, simplify_mm, True, lay.tab_circles)
    pts = path.flatten(24)
    assert len(lay.tab_circles) == (2 if double else 1)
    for ccx, ccy, r, side in lay.tab_circles:
        arc = pts[(side * (pts[:, 1] - ccy) > 0.2 * r)]       # well inside the half disc
        err = np.abs(np.hypot(arc[:, 0] - ccx, arc[:, 1] - ccy) - r) / lay.px_per_mm
        assert len(arc) > 20 and err.max() < 0.02             # mm
