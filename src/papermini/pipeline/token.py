"""Flat round tokens: the cut-out figure in a circle, with a ring, for the table or a
virtual tabletop.

A token is a ``Mini`` like any other piece (its art, a circular cut line, its text), so
the print sheet, the SVG and the PNG output treat both alike. Its diameter comes from the
figure's creature size (the size table's base). The figure is fitted in the circle with
``FIT_FREE`` of the inner diameter free on each side, or framed by ``area``: the square of
the picture that fills the circle. The ring can carry the label and the copy number, on a
nameplate and a badge, or curved along the ring (which is then never narrower than the
text needs).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..support import cache, fonts
from . import adjust as adj_mod
from . import geometry as geo
from .mask_options import MaskOptions
from .mini import (
    NUMBER_PLACEHOLDER,
    Mini,
    check_font,
    figure_mask,
    fit_label_size,
    fit_number_size,
)
from .style import Style
from .text_item import TextItem
from .token_info import TokenInfo
from .token_options import TokenOptions

TOKEN_FILLS = ("color", "image")  # behind the figure: a color, or the picture
TOKEN_TEXTS = ("none", "label", "number", "label_number")
TOKEN_TEXT_STYLES = ("nameplate", "curved")

FIT_FREE = (
    0.08  # a fitted figure leaves this share of the inner diameter free on each side
)

PX_PER_MM = (
    16.0  # working resolution of a token (about 400 dpi; the art is resized to dpi)
)

PLATE = 1.35  # the nameplate's height, as a multiple of the text size
BADGE = 1.35  # the number badge's radius, as a multiple of the text size


def parse_area(v) -> list[float]:
    """A token area from a project or the command line: x0, y0, x1, y1 as fractions of the
    picture (a list, or a string "x0,y0,x1,y1"). It may reach past the picture's edges."""
    try:
        vals = [
            float(x)
            for x in (v.replace(" ", "").split(",") if isinstance(v, str) else v)
        ]
    except (TypeError, ValueError):
        vals = []
    if len(vals) != 4 or not (vals[2] > vals[0] and vals[3] > vals[1]):
        raise ValueError(
            f"token_area must be x0, y0, x1, y1 (fractions of the picture, "
            f"x1 > x0 and y1 > y0), not {v!r}"
        )
    return vals


@lru_cache(maxsize=256)
def _middle(text: str, font: str, bold: bool = False) -> float:
    """Where the middle of ``text``'s letters is (ascenders to descenders), below a text
    item's centre, as a share of the text size. A text item is drawn with its baseline
    0.35 x the size below its centre; letters with descenders sit lower."""
    from ..output.sheet import _font

    try:
        _, top, _, bottom = _font(
            100, serif=True, path=fonts.file_for(font, bold)
        ).getbbox(text, anchor="ls")
    except (
        OSError,
        TypeError,
        ValueError,
    ):  # (a font without metrics: caps-like letters)
        top, bottom = -66, 0
    return 0.35 + (top + bottom) / 200.0


def _arc(
    text: str,
    cx: float,
    cy: float,
    r: float,
    size: float,
    font: str,
    color: str,
    bottom: bool,
    bold: bool = False,
) -> list[TextItem]:
    """``text`` curved along a circle of radius ``r``, one item per character: along the
    bottom read left to right with the tops towards the centre, along the top with the
    tops outwards. The letters (descenders included) are centred on the circle. Shrinks
    to fit in 150 degrees."""
    widths = [fonts.text_width(ch, font, size, bold) for ch in text]
    track = 0.05 * size
    total = sum(widths) + track * max(0, len(text) - 1)
    most = math.radians(150) * r
    if total > most:
        k = most / total
        size, widths, track, total = size * k, [w * k for w in widths], track * k, most
    # the items' centres, so the letters' middle lies on the circle ("down" in the text is
    # outwards along the bottom and inwards along the top)
    shift = _middle(text, font, bold) * size
    r = r - shift if bottom else r + shift
    items, s = [], -total / 2
    for ch, w in zip(text, widths):
        a = (s + w / 2) / r  # angle from the middle of the text
        theta = math.pi / 2 - a if bottom else -math.pi / 2 + a
        rot = -math.degrees(a) if bottom else math.degrees(a)
        if ch.strip():
            items.append(
                TextItem(
                    "tokentext",
                    ch,
                    cx + r * math.cos(theta),
                    cy + r * math.sin(theta),
                    rot,
                    size,
                    color,
                    bold,
                )
            )
        s += w + track
    return items


def token_text_items(
    t: TokenInfo, label: str, number: int | None, font: str
) -> list[TextItem]:
    """A token's label and copy number, as ``t.text`` says and where ``t.text_style``
    puts them (the preview shows the number as #)."""
    num = NUMBER_PLACEHOLDER if number is None else str(number)
    show_label = t.text in ("label", "label_number") and bool(label)
    show_number = t.text in ("number", "label_number")
    items: list[TextItem] = []
    if t.text_style == "curved":
        r = (t.radius_mm + t.inner_mm) / 2
        if show_label:
            items += _arc(label, t.cx, t.cy, r, t.size_mm, font, t.color, bottom=True)
        if show_number:
            items += _arc(
                num, t.cx, t.cy, r, t.size_mm, font, t.color, bottom=False, bold=True
            )
        return items
    if (
        show_label and t.plate is not None
    ):  # (centred: the letters' middle on the band's)
        cx, cy, w, _h = t.plate
        size = fit_label_size(label, w, t.size_mm, font)
        items.append(
            TextItem(
                "tokentext",
                label,
                cx,
                cy - _middle(label, font) * size,
                0.0,
                size,
                t.color,
            )
        )
    if show_number and t.badge is not None:
        cx, cy, r = t.badge
        size = fit_number_size(num, 1.25 * r, 1.1 * r, font)
        items.append(
            TextItem(
                "tokentext",
                num,
                cx,
                cy - _middle(num, font, True) * size,
                0.0,
                size,
                t.color,
                True,
            )
        )
    return items


def fit_frame(
    contours: Sequence[np.ndarray], inner_mm: float, outline_mm: float = 0.0
) -> tuple[float, float, float]:
    """The fitted framing: (cx, cy) in image pixels and the scale in token pixels per
    image pixel, so the whole figure (with its outline) sits in the circle with
    ``FIT_FREE`` of the inner diameter free on each side."""
    pts = [c for c in contours if len(c)]
    if not pts:
        raise ValueError(
            "background removal found no figure in this image: try a lower "
            "strength, a crop or another model"
        )
    (x, y), r = cv2.minEnclosingCircle(np.vstack(pts).astype(np.float32))
    room = max(0.3 * inner_mm, inner_mm * (1 - 2 * FIT_FREE) - outline_mm)
    return float(x), float(y), room * PX_PER_MM / max(float(r), 1.0)


def area_frame(
    area: Sequence[float], size: tuple[int, int], inner_mm: float
) -> tuple[float, float, float]:
    """The framing of a token ``area`` (fractions of a ``size`` = (w, h) picture): its
    centre and the scale that makes it fill the circle inside the ring."""
    W, H = size
    x0, y0, x1, y1 = area
    side = max((x1 - x0) * W, (y1 - y0) * H, 1.0)
    return (x0 + x1) / 2 * W, (y0 + y1) / 2 * H, 2 * inner_mm * PX_PER_MM / side


def frame_area(
    cx: float, cy: float, f: float, size: tuple[int, int], inner_mm: float
) -> tuple[float, float, float, float]:
    """The token area (fractions) of a framing: the square around (cx, cy) that fills the
    circle at scale ``f``."""
    W, H = size
    half = inner_mm * PX_PER_MM / f
    return (
        round((cx - half) / W, 4),
        round((cy - half) / H, 4),
        round((cx + half) / W, 4),
        round((cy + half) / H, 4),
    )


def _place(
    a: np.ndarray, f: float, cx: float, cy: float, n: int, interp: int, fill
) -> np.ndarray:
    """The part of image ``a`` around (cx, cy) on an ``n`` x ``n`` canvas, scaled by
    ``f`` (shrunk first with area averaging, so a big picture never aliases)."""
    h, w = a.shape[:2]
    gx = gy = 1.0
    if f < 1:
        a = cv2.resize(
            a,
            (max(1, round(w * f)), max(1, round(h * f))),
            interpolation=cv2.INTER_AREA,
        )
        gx, gy = a.shape[1] / w, a.shape[0] / h
    c = n / 2
    M = np.float32([[f / gx, 0, c - cx * f], [0, f / gy, c - cy * f]])
    return cv2.warpAffine(
        a, M, (n, n), flags=interp, borderMode=cv2.BORDER_CONSTANT, borderValue=fill
    )


def _disk(n: int, c: float, r: float) -> np.ndarray:
    """An anti-aliased disk of radius ``r`` px around (c, c) on an n x n canvas (0..1)."""
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    return np.clip(r + 0.5 - np.hypot(xx - c, yy - c), 0.0, 1.0)


def circle_path(cx: float, cy: float, r: float, n: int = 8) -> geo.CutPath:
    """A circle as a closed path of ``n`` cubic arcs."""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    pts = np.stack([cx + r * np.cos(a), cy + r * np.sin(a)], axis=1)
    h = 4.0 / 3.0 * math.tan(math.pi / (2 * n)) * r  # handle length of one arc
    tang = np.stack([-np.sin(a), np.cos(a)], axis=1)
    nxt = np.roll(np.arange(n), -1)
    ctrl = np.stack([pts + h * tang, pts[nxt] - h * tang[nxt]], axis=1)
    return geo.CutPath(pts, ctrl)


def _render(
    fm,
    o: TokenOptions,
    adj: adj_mod.Adjustments,
    bleed_mm: float,
    pad_mm: float,
    has_label: bool,
):
    """The token's pixels (RGBA, PX_PER_MM) and where its parts are, in token pixels."""
    W, H = fm.image.size
    R = o.diameter_mm / 2
    ring = min(o.ring_mm(), R - 0.5)
    ri = R - ring
    p = PX_PER_MM
    n = math.ceil(2 * (R + pad_mm) * p)
    c = n / 2
    outline_mm = o.margin_mm if o.outline else 0.0
    plate_mm = (
        min(ri, PLATE * o.text_mm)
        if not o.curved and has_label and o.text in ("label", "label_number")
        else 0.0
    )
    if o.area is not None:
        fx, fy, f = area_frame(o.area, (W, H), ri)
    else:
        # fitted in the part of the circle above the nameplate: the largest circle there
        # lies plate_mm / 2 higher; (fx, fy) is then the picture's point at the centre
        fx, fy, f = fit_frame(fm.contours, ri - plate_mm / 2, outline_mm)
        fy += plate_mm / 2 * p / f

    # the picture and the figure on the token
    rgb = fm.rgb
    blank = (255, 255, 255) if rgb.shape[2] == 3 else (0, 0, 0, 0)
    img = _place(rgb, f, fx, fy, n, cv2.INTER_LINEAR, blank)
    fig = ((_place(fm.clean, f, fx, fy, n, cv2.INTER_LINEAR, 0) > 127) * 255).astype(
        np.uint8
    )
    if not adj.is_identity():
        img = adj_mod.apply(img, adj)
    a = img[..., 3:4].astype(np.float32) / 255.0 if img.shape[2] == 4 else 1.0
    over_white = np.clip(img[..., :3].astype(np.float32) + (1.0 - a) * 255.0, 0, 255)
    fill = geo.hex_rgb(o.fill_color)
    if o.fill == "image":
        bg = over_white
    else:
        bg = np.empty((n, n, 3), np.float32)
        bg[:] = fill
    if o.outline:
        sil = geo.dilate(fig, o.margin_mm * p)
        sil = geo.fill_holes(geo.smooth_outline(sil, o.smooth_mm * p) | fig)
        paper = (
            geo.hex_rgb(o.margin_color) if o.margin_fill == "color" else (255, 255, 255)
        )
        figart = geo.compose_art(img, fig, sil, paper, p, o.margin_fill == "image")
        soft = cv2.GaussianBlur(sil.astype(np.float32) / 255.0, (0, 0), 0.6)[..., None]
        art = soft * figart + (1.0 - soft) * bg
    elif o.fill == "image":
        art = bg
    else:
        art = geo.compose_art(img, fig, fig, fill, p, False).astype(np.float32)

    # the ring, the nameplate and the badge
    ring_rgb = np.array(geo.hex_rgb(o.border_color), np.float32)
    inner = _disk(n, c, ri * p)[..., None]
    art = inner * art + (1.0 - inner) * ring_rgb
    shape = np.zeros(
        (n, n), np.float32
    )  # the nameplate and the badge, in the ring color
    plate = badge = None
    show_label = o.text in ("label", "label_number") and has_label
    show_number = o.text in ("number", "label_number")
    text_mm = o.text_mm
    if not o.curved and show_number:
        rb = min(0.4 * R, BADGE * text_mm)
        ang = math.radians(40)  # (bottom right)
        if show_label:  # higher up the ring, clear of the nameplate
            room = (ri - plate_mm - 0.3 - rb) / (R - rb)
            ang = min(ang, max(math.radians(-30), math.asin(max(-1.0, min(1.0, room)))))
        bx, by = c + (R - rb) * math.cos(ang) * p, c + (R - rb) * math.sin(ang) * p
        shape = np.maximum(
            shape,
            np.clip(
                rb * p
                + 0.5
                - np.hypot(
                    *np.meshgrid(np.arange(n) + 0.5 - bx, np.arange(n) + 0.5 - by)
                ),
                0,
                1,
            ),
        )
        badge = (bx / p, by / p, rb)
    if not o.curved and show_label:
        h = plate_mm
        top = c + (ri - h) * p
        band = np.zeros((n, n), np.float32)
        band[int(top) :] = 1.0
        if int(top) < n:
            band[int(top)] = 1.0 - (top - int(top))
        shape = np.maximum(
            shape, band
        )  # (below the circle it is the ring's color anyway)
        y = ri - h / 2  # (the text's middle, mm from the centre)
        # the ring beside the band has its color too: as wide as the token is along the
        # bottom of the letters, keeping clear of the cut line
        edge = R - max(0.4, 0.15 * text_mm)
        half = math.sqrt(max(0.0, edge * edge - (y + 0.3 * text_mm) ** 2))
        if badge is not None and badge[1] - c / p + badge[2] > y - 0.6 * text_mm:
            half = min(
                half, badge[0] - c / p - badge[2] - 0.3
            )  # (centred, clear of the badge)
        plate = (c / p, c / p + y, max(1.0, 2 * half), h)
    art = shape[..., None] * ring_rgb + (1.0 - shape[..., None]) * art

    alpha = (_disk(n, c, R * p) * 255.0).astype(np.uint8)
    out = np.clip(art + 0.5, 0, 255).astype(np.uint8)
    if bleed_mm:
        out, alpha = geo.add_bleed(out, alpha, bleed_mm * p)
    bx0, by0, bx1, by1 = geo.bbox(fm.clean)
    fbox = tuple(
        float(v)
        for v in (np.array([bx0 - fx, by0 - fy, bx1 + 1 - fx, by1 + 1 - fy]) * f + c)
        / p
    )
    return (
        np.dstack([out, alpha]),
        n,
        ring,
        ri,
        text_mm,
        plate,
        badge,
        frame_area(fx, fy, f, (W, H), ri),
        fbox,
        (fx, fy, f),
    )


def make_token(
    image_path: Path,
    o: TokenOptions,
    mask_options: MaskOptions,
    *,
    label: str | None,
    dpi: int,
    bleed_mm: float,
    adjust: adj_mod.Adjustments,
    style: Style,
    use_cache: bool = True,
    log=print,
    on_stage=None,
) -> Mini:
    """Build one token: background removal as for a mini, then the figure framed in a
    circle on its background, inside a ring, with a circular cut line."""
    image_path = Path(image_path)
    style = check_font(style, image_path.name, log)
    fm = figure_mask(
        image_path, mask_options, use_cache=use_cache, log=log, on_stage=on_stage
    )
    label = image_path.stem if label is None else label
    bleed_mm = min(max(0.0, bleed_mm), geo.MAX_BLEED_MM)
    pad_mm = max(style.cut_width_mm + 0.3, bleed_mm + 0.2 if bleed_mm else 0.0)
    # a cut line printed for cutting by hand lies just outside the ring, so it never
    # covers its edge (cut by machine, the cut follows the ring and the bleed is beyond)
    cut_out = style.cut_width_mm / 2 if style.cut_line and not bleed_mm else 0.0
    key = ("token", fm.key, o, adjust, bleed_mm, pad_mm, bool(label))
    make = lambda: _render(fm, o, adjust, bleed_mm, pad_mm, bool(label))
    rgba, n, ring, ri, text_mm, plate, badge, area, fbox, (fx, fy, f) = (
        cache.layouts.get_or_make(key, make) if use_cache else make()
    )
    if o.curved and o.border_mm < ring:
        log(
            f"  {image_path.name}: note: the ring is {ring:g} mm wide, the least that holds "
            "curved text"
        )

    side_mm = n / PX_PER_MM
    px = max(1, round(side_mm / 25.4 * dpi))
    art = Image.fromarray(rgba, "RGBA").resize((px, px), Image.LANCZOS)
    c = side_mm / 2
    R = o.diameter_mm / 2
    bx0, by0, bx1, by1 = geo.bbox(fm.clean)
    info = TokenInfo(
        cx=c,
        cy=c,
        radius_mm=R,
        inner_mm=ri,
        text=o.text,
        text_style=o.text_style,
        color=o.text_color,
        size_mm=text_mm,
        plate=plate,
        badge=badge,
        area=area,
        figure_box=fbox,
    )
    mini = Mini(
        name=image_path.stem,
        width_mm=side_mm,
        height_mm=side_mm,
        art=art,
        cut=circle_path(c, c, R + cut_out),
        label=label,
        label_size_mm=text_mm,
        style=style,
        figure_height_mm=o.diameter_mm,
        figure_width_mm=o.diameter_mm,
        aspect=(bx1 - bx0 + 1) / (by1 - by0 + 1),
        source_outline=fm.contours,
        method=fm.method,
        close_px=fm.close_px,
        kind="token",
        token=info,
    )
    # the circle inside the ring, on the source image
    mini.source_cut = circle_path(fx, fy, ri * PX_PER_MM / f)
    log(f"  {image_path.name}: token {o.diameter_mm:g} mm, ring {ring:g} mm")
    return mini
