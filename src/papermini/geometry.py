"""Mask clean-up, margin, tab and cut-line geometry.

Everything here works on plain numpy arrays (uint8 masks with values 0/255),
so it can be tested with synthetic masks and no model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


# --------------------------------------------------------------------------- helpers

def disk(r: int) -> np.ndarray:
    r = max(1, int(round(r)))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def dilate(m: np.ndarray, r: float) -> np.ndarray:
    """Grow a 0/255 mask by a disk of radius ``r`` px.

    Large radii use a distance transform, whose cost does not depend on ``r``
    (a big structuring element makes cv2.dilate very slow).
    """
    if r <= 0:
        return m.copy()
    if r <= 6:
        return cv2.dilate(m, disk(r))
    d = cv2.distanceTransform(cv2.bitwise_not(m), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return ((d <= r) * 255).astype(np.uint8)


def erode(m: np.ndarray, r: float) -> np.ndarray:
    """Shrink a 0/255 mask by a disk of radius ``r`` px (see :func:`dilate`)."""
    if r <= 0:
        return m.copy()
    if r <= 6:
        return cv2.erode(m, disk(r))
    d = cv2.distanceTransform(m, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return ((d > r) * 255).astype(np.uint8)


def close(m: np.ndarray, r: float) -> np.ndarray:
    """Morphological closing with a disk of radius ``r`` px."""
    return erode(dilate(m, r), r)


def fill_holes(m: np.ndarray) -> np.ndarray:
    """Fill every background region that is not connected to the outside."""
    p = np.pad(m, 1)
    ff = p.copy()
    cv2.floodFill(ff, np.zeros((p.shape[0] + 2, p.shape[1] + 2), np.uint8), (0, 0), 255)
    return (p | cv2.bitwise_not(ff))[1:-1, 1:-1]


def largest_component(m: np.ndarray) -> np.ndarray:
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return m
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return ((lab == i) * 255).astype(np.uint8)


def filter_components(m: np.ndarray, min_area: int) -> np.ndarray:
    """Keep every component of at least ``min_area`` px (always keeps the largest)."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return m
    areas = st[1:, cv2.CC_STAT_AREA]
    keep = np.flatnonzero(areas >= min(min_area, areas.max())) + 1
    return (np.isin(lab, keep) * 255).astype(np.uint8)


def bbox(m: np.ndarray) -> Tuple[int, int, int, int]:
    """(x0, y0, x1, y1) inclusive bounding box of the non-zero pixels."""
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        raise ValueError("empty mask: nothing was detected as foreground "
                         "(try a lower --strength, a --crop, or another --model)")
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


MAX_PARTS = 60


def connect_components(m: np.ndarray, width_px: int) -> np.ndarray:
    """Join all components into one shape with straight bridges of ``width_px``.

    Bridges follow a minimum spanning tree over the parts (closest outline
    points), computed once - not one full-canvas pass per bridge.
    """
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    k = len(cs)
    if k <= 1:
        return m
    if k > MAX_PARTS:
        raise ValueError(f"{k} separate parts is too many to bridge (max {MAX_PARTS}); "
                         "raise the min. part area or the strength, or turn off keep-all")
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
            cv2.line(m, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), 255,
                     thickness=max(2, width_px), lineType=cv2.LINE_8)
    return m


def smooth_outline(m: np.ndarray, sigma: float) -> np.ndarray:
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
    small = cv2.resize(m, (max(1, round(w * f)), max(1, round(h * f))), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 8.0)
    big = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    return ((big > 127) * 255).astype(np.uint8)


# --------------------------------------------------------------------------- clean-up

def default_close_px(width: int, height: int) -> int:
    """Closing radius that scales with the image: ~9 px at 1400 px long side."""
    return max(1, int(round(9 * max(width, height) / 1400)))


def clean_mask(
    raw: np.ndarray,
    threshold: int = 40,
    close_px: Optional[int] = None,
    keep_all: bool = False,
    min_area: int = 1000,
    stages: Optional[Dict[str, np.ndarray]] = None,
) -> np.ndarray:
    """Threshold, close, fill holes and drop specks. Returns a 0/255 mask."""
    h, w = raw.shape
    if close_px is None:
        close_px = default_close_px(w, h)
    p = close_px + 2  # pad so closing/flood fill behave at the image border
    m = np.pad(((raw > threshold) * 255).astype(np.uint8), p)
    if stages is not None:
        stages["1_threshold"] = m[p:-p, p:-p]
    if close_px > 0:
        m = close(m, close_px)
    if stages is not None:
        stages["2_closed"] = m[p:-p, p:-p]
    m = fill_holes(m)
    if stages is not None:
        stages["3_filled"] = m[p:-p, p:-p]
    m = filter_components(m, min_area) if keep_all else largest_component(m)
    m = m[p:-p, p:-p]
    if stages is not None:
        stages["4_clean"] = m
    return m


# --------------------------------------------------------------------------- layout

@dataclass
class Params:
    height_mm: Optional[float] = 42.0  # figure height, excluding margin and tab
    width_mm: Optional[float] = None   # figure width; see figure_size()
    margin_mm: float = 1.6        # distance between drawing and cut line
    smooth_mm: float = 0.6        # Gaussian sigma that rounds the outline
    tab: bool = True
    tab_width_mm: float = 22.0    # square tab
    tab_radius_mm: float = 12.5   # round tab (a half disc; 12.5 = a 25 mm base)
    tab_height_mm: float = 12.0   # below the fold line
    tab_overlap_mm: float = 0.0   # how far the tab reaches up into the figure
    fold_mm: float = 0.0          # fold line above the silhouette's lowest point
    tab_band_mm: float = 6.0      # bottom band used to centre the tab
    fillet_mm: float = 1.0        # rounds inner corners (closing) - never removes paper
    keep_all: bool = False
    bridge_mm: float = 2.5        # width of bridges joining separate parts (--keep-all)
    margin_fill: str = "color"    # "color" (margin_color) or "image": what shows in the margin
    margin_color: str = "#ffffff" # colour of the margin around the drawing
    tab_shape: str = "square"     # "square" (slots into a stand) or "round" (folds out to a base)
    tab_color: str = "#ffffff"    # tab background, independent of the margin colour
    double_sided: bool = False
    back: str = "mirror"          # double-sided back: "mirror" (image), "blank" or "text"
    back_color: str = "#ffffff"   # colour of a blank/text back
    max_px_per_mm: float = 24.0   # working resolution cap (~600 dpi; output is 300 dpi)
    top_bridge_width_mm: float = 12.0  # double-sided: joint at the top fold
    top_bridge_depth_mm: float = 3.0


@dataclass
class Layout:
    """Result of :func:`build_layout`, all in pixels of one canvas."""

    rgb: np.ndarray               # HxWx3 artwork (white outside the figure)
    cut: np.ndarray               # HxW 0/255 cut shape
    figure: np.ndarray            # HxW 0/255 clean figure mask (drawing that must not be cut)
    px_per_mm: float
    folds: List[Tuple[float, float, float]] = field(default_factory=list)   # (x0, x1, y)
    labels: List[Tuple[float, float, float]] = field(default_factory=list)  # (cx, cy, rot)
    tab_width_px: float = 0.0
    tab_height_px: float = 0.0
    figure_height_px: int = 0     # one side, also for double-sided layouts
    # double-sided with back="text": where the text may go (cx, cy, max_w, max_h), px
    back_box: Optional[Tuple[float, float, float, float]] = None
    # False when the tab's overlap lies entirely inside the silhouette (a figure whose
    # bottom is wider than the tab), i.e. tab_overlap_mm has no visible effect
    tab_overlap_used: bool = True
    tab_joint_px: float = 0.0     # width of paper joining tab and figure, just above the fold
    label_max_w_px: float = 0.0   # room for the tab label (depends on the tab shape)
    # round tabs: exact circles (cx, cy, r, side) in pixel-edge coordinates; side +1 =
    # the half below cy, -1 = above (the mirrored back). The traced cut line is snapped
    # onto them so a round tab is a true circle, not a traced pixel staircase.
    tab_circles: List[Tuple[float, float, float, int]] = field(default_factory=list)
    label_max_h_px: float = 0.0
    paper: Tuple[int, int, int] = (255, 255, 255)  # margin colour, RGB
    tabfill: Optional[np.ndarray] = None  # HxW bool: tab area (painted in the tab colour)
    # where this canvas lies in the image given to build_layout, for the front side:
    # (sx, sy, dx, dy) with image pixel = ((x - dx) * sx, (y - dy) * sy)
    src: Tuple[float, float, float, float] = (1.0, 1.0, 0.0, 0.0)
    front_top: float = 0.0        # canvas row where the front starts (double-sided: the fold)


def _overlap_matters(cut: np.ndarray, sil: np.ndarray, tab, fillet_px: float) -> bool:
    """Does the part of the tab above the fold change the final cut shape?

    It only adds paper where the figure is narrower than the tab; on a wide
    bottom it lies inside the outline (or in notches the fillet fills anyway).
    Re-does the tab without the overlap in a window around it and compares.
    """
    shape, cx, fold_f, top_f, tw, th = tab
    top, fold = int(round(top_f)), int(round(fold_f))
    if top >= fold:
        return False
    x0, x1 = int(round(cx - tw / 2)), int(round(cx + tw / 2))
    m = int(np.ceil(4 * max(fillet_px, 1.0))) + 2
    h, w = cut.shape
    wy0, wy1 = max(0, top - m), min(h, fold + m)
    wx0, wx1 = max(0, x0 - m), min(w, x1 + m + 1)
    alt = sil[wy0:wy1, wx0:wx1].copy()
    draw_tab(alt, shape, cx, fold_f, fold_f, tw, th, wx0, wy0)  # same tab, no overlap
    if fillet_px > 0:
        alt = close(alt, fillet_px)
    k = m // 2  # skip the window rim, where closing sees a cut-off neighbourhood
    inner = (slice(k, alt.shape[0] - k), slice(k, alt.shape[1] - k))
    return bool(np.any((cut[wy0:wy1, wx0:wx1] > 0)[inner] != (alt > 0)[inner]))


MARGIN_FILLS = ("color", "image")
TAB_SHAPES = ("square", "round")


def hex_rgb(c: str) -> Tuple[int, int, int]:
    """'#rrggbb' (or 'rgb') -> (r, g, b)."""
    h = c.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        raise ValueError(f"not a colour: {c!r} (use #rrggbb)")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def draw_tab(m: np.ndarray, shape: str, cx: float, fold: float, top: float, tw: float,
             th: float, dx: int = 0, dy: int = 0) -> None:
    """Paint a tab into ``m``: the overlap above the fold (top..fold) plus, below the
    fold, a rectangle tw x th (square) or a half disc of diameter tw (round)."""
    x0, x1 = int(round(cx - tw / 2)) - dx, int(round(cx + tw / 2)) - dx
    f = int(round(fold)) - dy
    if top < fold:
        cv2.rectangle(m, (x0, int(round(top)) - dy), (x1, f), 255, -1)
    if shape == "round":
        r = int(round(tw / 2))
        cv2.ellipse(m, (int(round(cx)) - dx, f), (r, r), 0, 0, 180, 255, -1)
    else:
        cv2.rectangle(m, (x0, f), (x1, int(round(fold + th)) - dy), 255, -1)


def _band_centre(m: np.ndarray, y0: int, y1: int) -> int:
    cols = np.flatnonzero(m[max(0, y0):y1 + 1].any(axis=0))
    return int(round((cols.min() + cols.max()) / 2))


def _bridge_centre(sil: np.ndarray, y_top: int, depth: int, width: int) -> float:
    """Column for the top bridge of a double-sided mini.

    The bridge is a ``width`` x ``depth`` rectangle hanging from the fold row. It goes
    where it overlaps the silhouette most, so it holds the halves together where the
    figure really reaches the fold (a raised wing, not the gap beside it). Among
    equally good places it takes the middle one, so it is centred on a head.
    """
    cover = np.count_nonzero(sil[y_top:y_top + max(1, depth)], axis=0).astype(np.float64)
    w = int(np.clip(width, 1, len(cover)))
    c = np.concatenate([[0.0], np.cumsum(cover)])
    score = c[w:] - c[:-w]  # score[i]: overlap of a bridge over columns i .. i + w - 1
    best = int(np.argmax(score))
    good = score >= 0.99 * score[best]
    lo, hi = best, best
    while lo > 0 and good[lo - 1]:
        lo -= 1
    while hi < len(good) - 1 and good[hi + 1]:
        hi += 1
    return (lo + hi) / 2 + w / 2


def _runs(row: np.ndarray) -> List[Tuple[int, int]]:
    """(start, end) column pairs of the filled runs in a row, end exclusive."""
    d = np.diff(np.concatenate([[0], (row > 0).astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def figure_size(w_px: int, h_px: int, height_mm: Optional[float],
                width_mm: Optional[float]) -> Tuple[float, float]:
    """(height in mm, horizontal stretch) for a ``w_px`` x ``h_px`` drawing.

    Height only or width only keep the drawing's proportions; both stretch it
    sideways to that width (the height sets the scale).
    """
    if not height_mm and not width_mm:
        raise ValueError("give a figure height, a width or both")
    if not width_mm:
        return float(height_mm), 1.0
    if not height_mm:
        return width_mm * h_px / w_px, 1.0
    return float(height_mm), (width_mm / height_mm) / (w_px / h_px)


def stretch_x(clean: np.ndarray, rgb: np.ndarray, f: float) -> Tuple[np.ndarray, np.ndarray]:
    """Mask and image ``f`` times as wide (``figure_size`` with both width and height)."""
    size = (max(1, round(clean.shape[1] * f)), clean.shape[0])
    interp = cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR
    mask = ((cv2.resize(clean, size, interpolation=interp) > 127) * 255).astype(np.uint8)
    return mask, cv2.resize(rgb, size, interpolation=interp)


def outline(clean: np.ndarray) -> List[np.ndarray]:
    """The detected figure's outline (outer edges and holes) as point arrays, in
    pixels of ``clean``: what background removal found, before any margin."""
    cs, _ = cv2.findContours(clean, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS)
    return [c.reshape(-1, 2).astype(np.float64) + 0.5 for c in cs if len(c) >= 3]


def limit_resolution(clean: np.ndarray, rgb: np.ndarray, height_mm: float,
                     max_px_per_mm: float) -> Tuple[np.ndarray, np.ndarray]:
    """Downscale mask and image so the figure has at most ``max_px_per_mm``.

    A small figure from a big image would otherwise make the padded canvas and
    every morphology step grow with (px per mm)^2.
    """
    x0, y0, x1, y1 = bbox(clean)
    pxmm = (y1 - y0 + 1) / height_mm
    if pxmm <= max_px_per_mm:
        return clean, rgb
    f = max_px_per_mm / pxmm
    size = (max(1, round(clean.shape[1] * f)), max(1, round(clean.shape[0] * f)))
    small = ((cv2.resize(clean, size, interpolation=cv2.INTER_AREA) > 127) * 255).astype(np.uint8)
    if not small.any():
        return clean, rgb
    return small, cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)


def _window(mask: np.ndarray, rgb: np.ndarray, x0: int, y0: int, x1: int, y1: int):
    """Cut [x0:x1, y0:y1] out of mask/image. Outside the image: empty mask and white
    paper (RGB) or fully transparent (premultiplied RGBA)."""
    h, w = mask.shape
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    c = rgb.shape[2]
    im = np.full((y1 - y0, x1 - x0, c), 255 if c == 3 else 0, np.uint8)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    m[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = mask[sy0:sy1, sx0:sx1]
    im[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = rgb[sy0:sy1, sx0:sx1]
    return m, im


def compose_art(img: np.ndarray, fig: np.ndarray, sil: np.ndarray,
                paper: Tuple[int, int, int], pxmm: float, image_margin: bool) -> np.ndarray:
    """Artwork on the margin colour ``paper``.

    ``img`` is RGB, or premultiplied RGBA for images with transparency (used as
    real transparency, never flattened onto white).

    The inside of the drawing keeps its own colours (a white ghost stays white).
    Around its edge - a thin rim inside the outline and a 0.25 mm band beyond it,
    kept so stray pencil strokes are not clipped - the picture is printed like ink
    on the margin colour: the source's white paper becomes the margin colour and
    dark strokes stay dark. On a white margin this is exactly the plain picture;
    on a dark one it removes the white halo around the figure.
    """
    P = np.array(paper, np.float32)
    S = img[..., :3].astype(np.float32)            # (premultiplied) colour
    a = img[..., 3:4].astype(np.float32) / 255.0 if img.shape[2] == 4 else 1.0
    if image_margin:
        w = (sil > 0).astype(np.float32)[..., None]
        art = w * S + (1.0 - w) * a * P
    else:
        sigma = max(0.5, 0.12 * pxmm)
        soft = lambda m: cv2.GaussianBlur(m.astype(np.float32) / 255.0, (0, 0), sigma)[..., None]  # noqa: E731
        core = soft(erode(fig, 0.2 * pxmm))                          # the drawing itself
        band = np.maximum(soft(dilate(fig, 0.25 * pxmm)), fig[..., None] / 255.0)
        ink = S * (P / 255.0)                                        # printed on the margin
        # inside the drawing, transparency shows as it does on white paper (a translucent
        # ghost stays light); at the edge and beyond, it lets the margin colour through
        inside = S + (1.0 - a) * 255.0
        edge = band * ink + (1.0 - band) * a * P + (1.0 - a) * P
        art = core * inside + (1.0 - core) * edge
        return np.clip(art + 0.5, 0, 255).astype(np.uint8)
    art = art + (1.0 - a) * P                                        # transparent -> margin
    return np.clip(art + 0.5, 0, 255).astype(np.uint8)


def build_layout(clean: np.ndarray, rgb: np.ndarray, prm: Params) -> Layout:
    """Margin, smoothing and tab around a clean figure mask.

    ``clean`` is the 0/255 figure mask and ``rgb`` the image of the same size.
    """
    in_h, in_w = clean.shape
    clean, rgb = limit_resolution(clean, rgb, prm.height_mm, prm.max_px_per_mm)
    x0, y0, x1, y1 = bbox(clean)
    pxmm = (y1 - y0 + 1) / prm.height_mm

    # Work on a canvas around the figure only, padded so neither the margin nor the
    # tab is clipped by the image border (the tab only needs room below and sideways).
    base = int(np.ceil((prm.margin_mm + 4 * prm.smooth_mm + prm.bridge_mm
                        + prm.top_bridge_depth_mm + 5) * pxmm)) + 4
    round_tab = prm.tab_shape == "round"
    tab_w_mm = 2 * prm.tab_radius_mm if round_tab else prm.tab_width_mm
    side = base + (int(np.ceil(tab_w_mm / 2 * pxmm)) if prm.tab else 0)
    tab_depth_mm = prm.tab_radius_mm if round_tab else prm.tab_height_mm
    below = base + (int(np.ceil((tab_depth_mm + prm.fold_mm) * pxmm)) if prm.tab else 0)
    fig, img = _window(clean, rgb, x0 - side, y0 - base, x1 + side + 1, y1 + below + 1)

    # Silhouette: dilate by the margin, blur and re-threshold for a smooth outline.
    sil = dilate(fig, prm.margin_mm * pxmm)
    sil = smooth_outline(sil, prm.smooth_mm * pxmm)
    sil = fill_holes(sil | fig)
    if prm.keep_all:
        sil = connect_components(sil, int(round(prm.bridge_mm * pxmm)))
        sil = fill_holes(sil)
    else:
        sil = largest_component(sil)

    cut = sil.copy()
    folds: List[Tuple[float, float, float]] = []
    labels: List[Tuple[float, float, float]] = []
    overlap_used = True
    tw = tab_w_mm * pxmm
    th = (prm.tab_radius_mm if round_tab else prm.tab_height_mm) * pxmm
    label_w = label_h = 0.0
    circles: List[Tuple[float, float, float, int]] = []

    _, sy0, _, sy1 = bbox(sil)
    if prm.tab:
        cx = _band_centre(sil, int(sy1 - prm.tab_band_mm * pxmm), sy1)
        fold_y = sy1 - prm.fold_mm * pxmm
        top = fold_y - prm.tab_overlap_mm * pxmm
        draw_tab(cut, prm.tab_shape, cx, fold_y, top, tw, th)
        if round_tab:  # as drawn by draw_tab, in pixel-edge coordinates
            circles.append((round(cx) + 0.5, round(fold_y) + 0.5, float(round(tw / 2)), 1))
        tab_geom = (prm.tab_shape, cx, fold_y, top, tw, th)
        folds.append((cx - tw / 2, cx + tw / 2, fold_y))
        if round_tab:
            # label near the straight edge, where the half disc is widest
            r = tw / 2
            label_h = 0.42 * r
            ly = fold_y + 0.08 * r + label_h / 2
            label_w = 2 * np.sqrt(max(0.0, r * r - (ly - fold_y + label_h / 2) ** 2)) - 1.5 * pxmm
        else:
            ly = fold_y + th / 2
            label_w, label_h = tw - 2 * pxmm, th * 0.8
        labels.append((cx, ly, 0.0))  # where the label goes (if there is one)

    if prm.double_sided:
        bw = prm.top_bridge_width_mm * pxmm
        depth = int(round(prm.top_bridge_depth_mm * pxmm))
        bcx = _bridge_centre(sil, sy0, depth, int(round(bw)))
        cv2.rectangle(cut, (int(round(bcx - bw / 2)), sy0),
                      (int(round(bcx + bw / 2)) - 1, sy0 + depth), 255, -1)

    if prm.fillet_mm > 0:
        cut = close(cut, prm.fillet_mm * pxmm)
    cut = largest_component(fill_holes(cut | sil))
    joint = 0.0
    if prm.tab:
        overlap_used = _overlap_matters(cut, sil, tab_geom, prm.fillet_mm * pxmm)
        row = int(round(fold_y)) - 1  # how much paper holds the tab, right above the fold
        if 0 <= row < cut.shape[0]:
            jx0, jx1 = max(0, int(round(cx - tw / 2))), int(round(cx + tw / 2)) + 1
            joint = float(np.count_nonzero(cut[row, jx0:jx1]))

    # Crop the generous padding away (keep 6 mm of context for previews).
    cx0, cy0, cx1, cy1 = bbox(cut)
    b = int(np.ceil(6 * pxmm))
    ox, oy = max(0, cx0 - b), max(0, cy0 - b)
    win = (slice(oy, cy1 + b + 1), slice(ox, cx1 + b + 1))
    fig, img, sil, cut = fig[win], img[win], sil[win], cut[win]
    folds = [(a - ox, c - ox, y - oy) for a, c, y in folds]
    labels = [(x - ox, y - oy, r) for x, y, r in labels]
    circles = [(x - ox, y - oy, r, d) for x, y, r, d in circles]
    sy0 -= oy

    # Artwork: the drawing where the figure is, the paper colour in margin and tab
    # (or the original image in the margin), and optionally a coloured tab.
    # (with the image in the margin, the tab and a blank back are plain white)
    paper = hex_rgb(prm.margin_color) if prm.margin_fill == "color" else (255, 255, 255)
    art = compose_art(img, fig, sil, paper, pxmm, prm.margin_fill == "image")
    tabfill = None
    if prm.tab:
        # the tab has its own colour (with or without the label on it): everything that
        # folds under - the cut shape below the fold, minus the drawing
        fold_row = int(np.ceil(folds[0][2]))
        tabfill = np.zeros(cut.shape, bool)
        tabfill[fold_row:] = (cut[fold_row:] > 0) & (fig[fold_row:] == 0)
        art[tabfill] = hex_rgb(prm.tab_color)

    # canvas pixel -> input pixel: undo the padded window, this crop and the downscale
    src = (in_w / clean.shape[1], in_h / clean.shape[0],
           -(x0 - side + ox), -(y0 - base + oy))
    lay = Layout(art, cut, fig, pxmm, folds, labels, tw, th, y1 - y0 + 1,
                 tab_overlap_used=overlap_used, tab_joint_px=joint, tab_circles=circles,
                 label_max_w_px=label_w, label_max_h_px=label_h,
                 paper=paper, tabfill=tabfill, src=src)
    if prm.double_sided:
        lay = _mirror_at_top(lay, sy0, prm.back, hex_rgb(prm.back_color))
    return lay


BACK_MODES = ("mirror", "blank", "text")


def _mirror_at_top(lay: Layout, y_top: int, back: str = "mirror",
                   back_rgb: Tuple[int, int, int] = (255, 255, 255)) -> Layout:
    """Front + vertically mirrored back, joined at a fold through ``y_top``.

    The fold line runs across all the paper that joins the halves there (the top
    bridge, and a wing or head that reaches the fold beside it).
    The cut shape is always mirrored (so the halves line up when glued); with
    ``back`` "blank" or "text" the back half shows white paper instead of the
    mirrored drawing, and "text" also reports where text fits (``back_box``).
    """
    if back not in BACK_MODES:
        raise ValueError(f"back must be one of {', '.join(BACK_MODES)}, not {back!r}")

    def stack(a, blank=False):
        front = a[y_top:]
        if not blank:
            top = front[::-1]
        else:
            top = np.empty_like(front)
            top[:] = back_rgb
            if lay.tabfill is not None:  # the back tab keeps its colour
                keep = lay.tabfill[y_top:][::-1]
                top[keep] = front[::-1][keep]
        return np.concatenate([top, front], axis=0)

    h = lay.cut.shape[0] - y_top  # rows of each half; fold is at row h
    folds = [(float(a), float(b), float(h)) for a, b in _runs(lay.cut[y_top])]
    labels = []
    for fx0, fx1, fy in lay.folds:
        fy = fy - y_top
        folds += [(fx0, fx1, h + fy), (fx0, fx1, h - fy)]
    for lx, ly, _ in lay.labels:
        ly = ly - y_top
        labels += [(lx, h + ly, 0.0), (lx, h - ly, 180.0)]
    figure = stack(lay.figure)
    return Layout(stack(lay.rgb, blank=back != "mirror"), stack(lay.cut), figure, lay.px_per_mm,
                  folds, labels, lay.tab_width_px, lay.tab_height_px, lay.figure_height_px,
                  _text_box(figure[:h]) if back == "text" else None,
                  tab_overlap_used=lay.tab_overlap_used, tab_joint_px=lay.tab_joint_px,
                  tab_circles=[c for x, y, r, d in lay.tab_circles
                               for c in ((x, h + (y - y_top), r, d), (x, h - (y - y_top), r, -d))],
                  label_max_w_px=lay.label_max_w_px,
                  label_max_h_px=lay.label_max_h_px, paper=lay.paper,
                  tabfill=None if lay.tabfill is None else stack(lay.tabfill),
                  # the front moved down by h - y_top rows (the mirrored back is above it)
                  src=(*lay.src[:3], lay.src[3] + h - y_top), front_top=float(h))


def _text_box(fig: np.ndarray) -> Tuple[float, float, float, float]:
    """Room for text inside a figure silhouette: (cx, cy, max_w, max_h) in px.

    Centred on the figure; the width is what the silhouette offers through its
    middle (a narrow row there limits it), the height ~60% of the figure.
    """
    x0, y0, x1, y1 = bbox(fig)
    cx, cy = (x0 + x1 + 1) / 2, (y0 + y1 + 1) / 2
    hh = (y1 - y0 + 1) * 0.3
    rows = fig[int(cy - hh / 2):int(cy + hh / 2) + 1] > 0
    # centre on the body, not on the bounding box (an arm or prop would pull it sideways)
    centres = []
    for r in rows:
        xs = np.flatnonzero(r)
        if len(xs):
            runs = np.split(xs, np.flatnonzero(np.diff(xs) > 1) + 1)
            body = max(runs, key=len)
            centres.append((body[0] + body[-1] + 1) / 2)
    if centres:
        cx = float(np.median(centres))
    widths = []
    for r in rows:
        xs = np.flatnonzero(r)
        if len(xs):
            # the run through the centre column (holes/arms beside it do not count)
            c = int(np.clip(round(cx), xs[0], xs[-1]))
            left = c - np.argmin(r[c::-1]) + 1 if not r[c::-1].all() else 0
            right = c + np.argmin(r[c:]) if not r[c:].all() else len(r)
            widths.append(max(0, right - left))
    w = float(np.percentile(widths, 20)) if widths else float(x1 - x0 + 1)
    return cx, cy, w * 0.82, (y1 - y0 + 1) * 0.6


# --------------------------------------------------------------------------- cut path

@dataclass
class CutPath:
    """Closed path: ``points`` (N x 2) and optional cubic ``controls`` (N x 2 x 2).

    Segment i runs from points[i] to points[(i+1) % N], with control points
    controls[i, 0] and controls[i, 1] when ``controls`` is set, else straight.
    """

    points: np.ndarray
    controls: Optional[np.ndarray] = None

    def transformed(self, scale: float, dx: float = 0.0, dy: float = 0.0) -> "CutPath":
        f = lambda a: (a - np.array([dx, dy])) * scale  # noqa: E731
        return CutPath(f(self.points), None if self.controls is None else f(self.controls))

    def flatten(self, steps: int = 12) -> np.ndarray:
        """Polyline approximation (closed, last point not repeated)."""
        if self.controls is None:
            return self.points.copy()
        p0 = self.points
        p3 = np.roll(self.points, -1, axis=0)
        c1, c2 = self.controls[:, 0], self.controls[:, 1]
        t = np.linspace(0, 1, steps, endpoint=False)[None, :, None]
        mt = 1 - t
        pts = (mt ** 3 * p0[:, None] + 3 * mt ** 2 * t * c1[:, None]
               + 3 * mt * t ** 2 * c2[:, None] + t ** 3 * p3[:, None])
        return pts.reshape(-1, 2)

    def extent(self) -> Tuple[float, float, float, float]:
        a = self.flatten()
        return float(a[:, 0].min()), float(a[:, 1].min()), float(a[:, 0].max()), float(a[:, 1].max())


def bezier_controls(P: np.ndarray, corner_deg: float = 55.0,
                    max_handle: float = np.inf) -> np.ndarray:
    """Smooth cubic handles through ``P``; sharp turns stay sharp corners.

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
    return np.stack([np.convolve(ext[:, i], k, mode="valid") for i in range(2)], axis=1)


def trace_cut(cut: np.ndarray, px_per_mm: float, simplify_mm: float = 0.15,
              smooth: bool = True, circles=()) -> CutPath:
    """Outer contour of the cut shape as one closed (optionally Bézier) path.

    ``circles`` (cx, cy, r, side): outline points on the given half circle are
    moved exactly onto it, so round tabs come out perfectly round.
    """
    cs, _ = cv2.findContours(cut, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        raise ValueError("empty cut shape")
    c = max(cs, key=cv2.contourArea)[:, 0, :].astype(np.float64)
    c = _smooth_closed(c, 1.5)
    c = cv2.approxPolyDP(c.astype(np.float32).reshape(-1, 1, 2),
                         max(0.5, simplify_mm * px_per_mm), True)[:, 0, :].astype(np.float64)
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
    ctrl = bezier_controls(c, max_handle=0.8 * px_per_mm) if smooth and len(c) >= 4 else None
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
            h = 4.0 / 3.0 * np.tan(da / 4.0) * r          # signed handle length
            ctrl[i, 0] = c[i] + h * np.array([-np.sin(a0), np.cos(a0)])
            ctrl[i, 1] = c[j] - h * np.array([-np.sin(a1), np.cos(a1)])
    return CutPath(c, ctrl)


def add_bleed(rgb: np.ndarray, alpha: np.ndarray, bleed_px: float):
    """Print beyond the cut line: extend the colours at the cut edge outwards by
    ``bleed_px`` (each new pixel takes the colour of the nearest pixel inside), so a
    slightly misaligned machine cut never shows white paper. Returns (rgb, alpha)."""
    inside = alpha > 127
    if bleed_px <= 0 or not inside.any():
        return rgb, alpha
    # take the colours from just inside the edge: right at the cut line a pixel can
    # still hold a neighbouring colour (raster fill vs. the exact vector cut line)
    e = 2
    core = cv2.erode(inside.astype(np.uint8), disk(e)) > 0
    if not core.any():
        core, e = inside, 0
    dist, lab = cv2.distanceTransformWithLabels(
        np.where(core, 0, 255).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_5,
        labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(core)             # every core pixel has its own label
    n = int(lab.max()) + 1
    near_y = np.zeros(n, np.int32)
    near_x = np.zeros(n, np.int32)
    near_y[lab[ys, xs]], near_x[lab[ys, xs]] = ys, xs
    ext = rgb[near_y[lab], near_x[lab]]
    ring = np.clip(bleed_px + e + 0.5 - dist, 0.0, 1.0) * 255.0   # anti-aliased outer edge
    return ext, np.maximum(alpha, ring.astype(np.uint8))


def rasterize(path: CutPath, shape: Tuple[int, int], antialias: bool = True) -> np.ndarray:
    """Fill ``path`` (pixel coordinates, edge convention) into a uint8 mask."""
    out = np.zeros(shape, np.uint8)
    pts = np.round((path.flatten() - 0.5) * 16).astype(np.int32)
    cv2.fillPoly(out, [pts], 255, lineType=cv2.LINE_AA if antialias else cv2.LINE_8, shift=4)
    return out
