from __future__ import annotations

import math

import cv2
import numpy as np

from .adjustments import Adjustments
from .art_composer import ArtComposer
from .bleed_painter import BleedPainter
from .figure_mask import FigureMask
from .hex_color import HexColor
from .image_adjuster import ImageAdjuster
from .morphology import Morphology
from .rendered_token import RenderedToken
from .token_framer import PX_PER_MM, TokenFramer
from .token_options import TokenOptions

PLATE = 1.35  # the nameplate's height, as a multiple of the text size
BADGE = 1.35  # the number badge's radius, as a multiple of the text size


class TokenRenderer:
    """Paints a token: the framed picture or figure on its background, inside a ring,
    with a nameplate and a number badge."""

    def __init__(
        self,
        morphology: Morphology,
        framer: TokenFramer,
        adjuster: ImageAdjuster,
        composer: ArtComposer,
        bleed: BleedPainter,
    ):
        self._morph = morphology
        self._framer = framer
        self._adjuster = adjuster
        self._composer = composer
        self._bleed = bleed

    def render(
        self,
        fm: FigureMask,
        o: TokenOptions,
        adj: Adjustments,
        bleed_mm: float,
        pad_mm: float,
        has_label: bool,
    ) -> RenderedToken:
        """Return the token's pixels (RGBA, PX_PER_MM) and where its parts are."""
        W, H = fm.image.size
        R = o.diameter_mm / 2
        ring = min(o.ring_mm(), R - 0.5)
        ri = R - ring
        p = PX_PER_MM
        n = math.ceil(2 * (R + pad_mm) * p)
        c = n / 2
        show_label = o.text in ("label", "label_number") and has_label
        show_number = o.text in ("number", "label_number")
        plate_mm = min(ri, PLATE * o.text_mm) if not o.curved and show_label else 0.0
        fx, fy, f = self._frame(fm, o, ri, plate_mm)
        art = self._picture(fm, o, adj, (fx, fy, f), n)

        # the ring, the nameplate and the badge
        ring_rgb = np.array(HexColor.to_rgb(o.border_color), np.float32)
        inner = self._disk(n, c, ri * p)[..., None]
        art = inner * art + (1.0 - inner) * ring_rgb
        # the nameplate and the badge, in the ring color
        shape = np.zeros((n, n), np.float32)
        plate = badge = None
        if not o.curved and show_number:
            disk, badge = self._badge(o, n, R, ri, plate_mm, show_label)
            shape = np.maximum(shape, disk)
        if not o.curved and show_label:
            band, plate = self._plate(o, n, R, ri, plate_mm, badge)
            # (below the circle it is the ring's color anyway)
            shape = np.maximum(shape, band)
        art = shape[..., None] * ring_rgb + (1.0 - shape[..., None]) * art

        alpha = (self._disk(n, c, R * p) * 255.0).astype(np.uint8)
        out = np.clip(art + 0.5, 0, 255).astype(np.uint8)
        if bleed_mm:
            out, alpha = self._bleed.add(out, alpha, bleed_mm * p)
        bx0, by0, bx1, by1 = self._morph.bbox(fm.clean)
        box = (np.array([bx0 - fx, by0 - fy, bx1 + 1 - fx, by1 + 1 - fy]) * f + c) / p
        fbox = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
        return RenderedToken(
            rgba=np.dstack([out, alpha]),
            side_px=n,
            ring_mm=ring,
            inner_mm=ri,
            text_mm=o.text_mm,
            plate=plate,
            badge=badge,
            area=self._framer.to_area(fx, fy, f, (W, H), ri),
            figure_box=fbox,
            frame=(fx, fy, f),
        )

    def _frame(
        self, fm: FigureMask, o: TokenOptions, ri: float, plate_mm: float
    ) -> tuple[float, float, float]:
        """Frame the picture: by the token's area, or fitted around the figure."""
        if o.area is not None:
            return self._framer.from_area(o.area, fm.image.size, ri)
        # fitted in the part of the circle above the nameplate: the largest circle
        # there lies plate_mm / 2 higher; (fx, fy) is then the picture's point at the
        # centre
        outline_mm = o.margin_mm if o.outline else 0.0
        fx, fy, f = self._framer.fit(fm.contours, ri - plate_mm / 2, outline_mm)
        return fx, fy + plate_mm / 2 * PX_PER_MM / f, f

    def _picture(
        self,
        fm: FigureMask,
        o: TokenOptions,
        adj: Adjustments,
        frame: tuple[float, float, float],
        n: int,
    ) -> np.ndarray:
        """Return the picture and the figure on the token's background (float RGB)."""
        fx, fy, f = frame
        p = PX_PER_MM
        rgb = fm.rgb
        blank = (255, 255, 255) if rgb.shape[2] == 3 else (0, 0, 0, 0)
        img = self._place(rgb, f, fx, fy, n, cv2.INTER_LINEAR, blank)
        fig = (
            (self._place(fm.clean, f, fx, fy, n, cv2.INTER_LINEAR, 0) > 127) * 255
        ).astype(np.uint8)
        if not adj.is_identity():
            img = self._adjuster.apply(img, adj)
        a = img[..., 3:4].astype(np.float32) / 255.0 if img.shape[2] == 4 else 1.0
        over_white = np.clip(
            img[..., :3].astype(np.float32) + (1.0 - a) * 255.0, 0, 255
        )
        fill = HexColor.to_rgb(o.fill_color)
        if o.fill == "image":
            bg = over_white
        else:
            bg = np.empty((n, n, 3), np.float32)
            bg[:] = fill
        if o.outline:
            sil = self._morph.dilate(fig, o.margin_mm * p)
            sil = self._morph.fill_holes(
                self._morph.smooth_outline(sil, o.smooth_mm * p) | fig
            )
            paper = (
                HexColor.to_rgb(o.margin_color)
                if o.margin_fill == "color"
                else (255, 255, 255)
            )
            figart = self._composer.compose(
                img, fig, paper, p, o.margin_fill == "image"
            )
            soft = cv2.GaussianBlur(sil.astype(np.float32) / 255.0, (0, 0), 0.6)[
                ..., None
            ]
            return soft * figart + (1.0 - soft) * bg
        if o.fill == "image":
            return bg
        return self._composer.compose(img, fig, fill, p, False).astype(np.float32)

    def _badge(
        self,
        o: TokenOptions,
        n: int,
        R: float,
        ri: float,
        plate_mm: float,
        show_label: bool,
    ) -> tuple[np.ndarray, tuple[float, float, float]]:
        """Return the number badge's disk (0..1) and its place (cx, cy, r) in mm: at
        the bottom right of the ring, or higher up, clear of the nameplate."""
        p = PX_PER_MM
        c = n / 2
        rb = min(0.4 * R, BADGE * o.text_mm)
        ang = math.radians(40)  # (bottom right)
        if show_label:  # higher up the ring, clear of the nameplate
            room = (ri - plate_mm - 0.3 - rb) / (R - rb)
            ang = min(ang, max(math.radians(-30), math.asin(max(-1.0, min(1.0, room)))))
        bx, by = c + (R - rb) * math.cos(ang) * p, c + (R - rb) * math.sin(ang) * p
        disk = np.clip(
            rb * p
            + 0.5
            - np.hypot(*np.meshgrid(np.arange(n) + 0.5 - bx, np.arange(n) + 0.5 - by)),
            0,
            1,
        )
        return disk, (bx / p, by / p, rb)

    def _plate(
        self,
        o: TokenOptions,
        n: int,
        R: float,
        ri: float,
        plate_mm: float,
        badge: tuple[float, float, float] | None,
    ) -> tuple[np.ndarray, tuple[float, float, float, float]]:
        """Return the nameplate's band (0..1) across the bottom of the circle, and the
        label's box (cx, cy, w, h) in mm."""
        p = PX_PER_MM
        c = n / 2
        text_mm = o.text_mm
        h = plate_mm
        top = c + (ri - h) * p
        band = np.zeros((n, n), np.float32)
        band[int(top) :] = 1.0
        if int(top) < n:
            band[int(top)] = 1.0 - (top - int(top))
        y = ri - h / 2  # (the text's middle, mm from the centre)
        # the ring beside the band has its color too: as wide as the token is along the
        # bottom of the letters, keeping clear of the cut line
        edge = R - max(0.4, 0.15 * text_mm)
        half = math.sqrt(max(0.0, edge * edge - (y + 0.3 * text_mm) ** 2))
        if badge is not None and badge[1] - c / p + badge[2] > y - 0.6 * text_mm:
            # (centred, clear of the badge)
            half = min(half, badge[0] - c / p - badge[2] - 0.3)
        return band, (c / p, c / p + y, max(1.0, 2 * half), h)

    @staticmethod
    def _place(
        a: np.ndarray, f: float, cx: float, cy: float, n: int, interp: int, fill
    ) -> np.ndarray:
        """Return the part of image ``a`` around (cx, cy) on an ``n`` x ``n`` canvas,
        scaled by ``f`` (shrunk first with area averaging, so a big picture never
        aliases)."""
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
        M = np.array(
            [[f / gx, 0, c - cx * f], [0, f / gy, c - cy * f]], dtype=np.float32
        )
        return cv2.warpAffine(
            a, M, (n, n), flags=interp, borderMode=cv2.BORDER_CONSTANT, borderValue=fill
        )

    @staticmethod
    def _disk(n: int, c: float, r: float) -> np.ndarray:
        """Return an anti-aliased disk of radius ``r`` px around (c, c) on an n x n
        canvas (0..1)."""
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
        return np.clip(r + 0.5 - np.hypot(xx - c, yy - c), 0.0, 1.0)
