from __future__ import annotations

from dataclasses import dataclass, field, replace

import cv2
import numpy as np

from .art_composer import ArtComposer
from .back_mirror import BackMirror
from .figure_scaler import FigureScaler
from .hex_color import HexColor
from .image_extender import ImageExtender
from .layout import Layout
from .morphology import Morphology
from .params import Params

CONTEXT_MM = 6  # the canvas keeps this much room around the cut shape, for previews


@dataclass(frozen=True)
class _Tab:
    """A tab as it is drawn, in canvas pixels: its shape, centre column, fold row, the
    top of its overlap above the fold, and its width and depth below the fold."""

    shape: str
    cx: float
    fold: float
    top: float
    width: float
    height: float


@dataclass
class _TabMarks:
    """What a tab adds to a layout, in canvas pixels: its fold line, where its label
    goes, its exact circle (a round tab) and the room for its label."""

    folds: list[tuple[float, float, float]] = field(default_factory=list)
    labels: list[tuple[float, float, float]] = field(default_factory=list)
    circles: list[tuple[float, float, float, int]] = field(default_factory=list)
    label_w: float = 0.0
    label_h: float = 0.0

    def shifted(self, ox: int, oy: int) -> _TabMarks:
        """Return the marks moved by (-ox, -oy)."""
        return replace(
            self,
            folds=[(a - ox, c - ox, y - oy) for a, c, y in self.folds],
            labels=[(x - ox, y - oy, r) for x, y, r in self.labels],
            circles=[(x - ox, y - oy, r, d) for x, y, r, d in self.circles],
        )


class LayoutBuilder:
    """Builds the layout of a mini: the margin, smoothing, tab and cut shape around a
    clean figure mask, and the artwork on its paper."""

    def __init__(
        self,
        morphology: Morphology,
        scaler: FigureScaler,
        composer: ArtComposer,
        mirror: BackMirror,
        extender: ImageExtender,
    ):
        self._morph = morphology
        self._scaler = scaler
        self._composer = composer
        self._mirror = mirror
        self._extender = extender

    def build(self, clean: np.ndarray, rgb: np.ndarray, prm: Params) -> Layout:
        """Build the margin, smoothing and tab around a clean figure mask.

        ``clean`` is the 0/255 figure mask and ``rgb`` the image of the same size.
        ``prm.height_mm`` must be set.
        """
        height_mm = prm.height_mm
        assert height_mm is not None, "the figure's height is set before its layout"
        in_h, in_w = clean.shape
        clean, rgb = self._scaler.limit_resolution(
            clean, rgb, height_mm, prm.max_px_per_mm
        )
        x0, y0, x1, y1 = self._morph.bbox(clean)
        pxmm = (y1 - y0 + 1) / height_mm

        # Work on a canvas around the figure only, padded so neither the margin nor the
        # tab is clipped by the image border. Under the original image as margin fill,
        # the picture goes on past its edges.
        base, side, below = self._padding(prm, pxmm)
        wx0, wy0 = x0 - side, y0 - base
        wx1, wy1 = x1 + side + 1, y1 + below + 1
        fig, img = self._window(clean, rgb, wx0, wy0, wx1, wy1)
        if prm.margin_fill == "image" and img.shape[2] == 3:
            inside = (
                max(0, -wx0),
                max(0, -wy0),
                min(in_w, wx1) - wx0,
                min(in_h, wy1) - wy0,
            )
            img = self._extender.extend(img, fig, inside, pxmm)
        sil = self._silhouette(fig, prm, pxmm)
        _, sy0, _, sy1 = self._morph.bbox(sil)

        cut = sil.copy()
        tab = self._tab(sil, sy1, prm, pxmm) if prm.tab else None
        if tab is not None:
            self._draw_tab(cut, tab)
        if prm.double_sided:
            self._add_top_bridge(cut, sil, sy0, prm, pxmm)
        cut = self._round_cut(cut, sil, prm, pxmm)
        marks = _TabMarks() if tab is None else self._tab_marks(tab, pxmm)
        overlap_used, joint = (
            (True, 0.0)
            if tab is None
            else self._tab_fit(cut, sil, tab, prm.fillet_mm * pxmm)
        )

        ox, oy, win = self._crop_window(cut, pxmm)
        fig, img, sil, cut = fig[win], img[win], sil[win], cut[win]
        marks = marks.shifted(ox, oy)
        paper, art, tabfill = self._paint(img, fig, sil, cut, marks, prm, pxmm)

        tab_w_mm, tab_depth_mm = self._tab_size_mm(prm)
        lay = Layout(
            rgb=art,
            cut=cut,
            figure=fig,
            px_per_mm=pxmm,
            folds=marks.folds,
            labels=marks.labels,
            tab_width_px=tab_w_mm * pxmm,
            tab_height_px=tab_depth_mm * pxmm,
            figure_height_px=y1 - y0 + 1,
            tab_overlap_used=overlap_used,
            tab_joint_px=joint,
            tab_circles=marks.circles,
            label_max_w_px=marks.label_w,
            label_max_h_px=marks.label_h,
            paper=paper,
            tabfill=tabfill,
            # canvas pixel -> input pixel: undo the padded window, the crop and the
            # downscale
            src=(
                in_w / clean.shape[1],
                in_h / clean.shape[0],
                -(x0 - side + ox),
                -(y0 - base + oy),
            ),
        )
        if prm.double_sided:
            lay = self._mirror.mirror(
                lay, sy0 - oy, prm.back, HexColor.to_rgb(prm.back_color)
            )
        return lay

    # region canvas

    @staticmethod
    def _tab_size_mm(prm: Params) -> tuple[float, float]:
        """Return the tab's width and its depth below the fold, in mm."""
        if prm.tab_shape == "round":
            return 2 * prm.tab_radius_mm, prm.tab_radius_mm
        return prm.tab_width_mm, prm.tab_height_mm

    def _padding(self, prm: Params, pxmm: float) -> tuple[int, int, int]:
        """Return the canvas padding around the figure in px: above it, beside it and
        below it (the tab only needs room below and sideways)."""
        base = (
            int(
                np.ceil(
                    (
                        prm.margin_mm
                        + 4 * prm.smooth_mm
                        + prm.bridge_mm
                        + prm.top_bridge_depth_mm
                        + 5
                    )
                    * pxmm
                )
            )
            + 4
        )
        tab_w_mm, tab_depth_mm = self._tab_size_mm(prm)
        side = base + (int(np.ceil(tab_w_mm / 2 * pxmm)) if prm.tab else 0)
        below = base + (
            int(np.ceil((tab_depth_mm + prm.fold_mm) * pxmm)) if prm.tab else 0
        )
        return base, side, below

    @staticmethod
    def _window(mask: np.ndarray, rgb: np.ndarray, x0: int, y0: int, x1: int, y1: int):
        """Cut [x0:x1, y0:y1] out of mask/image. Outside the image: empty mask and white
        paper (RGB) or fully transparent (premultiplied RGBA)."""
        h, w = mask.shape
        m = np.zeros((y1 - y0, x1 - x0), np.uint8)
        c = rgb.shape[2]
        im = np.full((y1 - y0, x1 - x0, c), 255 if c == 3 else 0, np.uint8)
        sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        m[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = mask[sy0:sy1, sx0:sx1]
        im[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = rgb[sy0:sy1, sx0:sx1]
        return m, im

    def _silhouette(self, fig: np.ndarray, prm: Params, pxmm: float) -> np.ndarray:
        """Dilate the figure by the margin, then blur and re-threshold it for a smooth
        outline."""
        sil = self._morph.dilate(fig, prm.margin_mm * pxmm)
        sil = self._morph.smooth_outline(sil, prm.smooth_mm * pxmm)
        sil = self._morph.fill_holes(sil | fig)
        if prm.keep_all:
            sil = self._morph.connect_components(sil, round(prm.bridge_mm * pxmm))
            return self._morph.fill_holes(sil)
        return self._morph.largest_component(sil)

    def _round_cut(
        self, cut: np.ndarray, sil: np.ndarray, prm: Params, pxmm: float
    ) -> np.ndarray:
        """Round the cut shape's inner corners, and keep it one solid piece."""
        if prm.fillet_mm > 0:
            cut = self._morph.close(cut, prm.fillet_mm * pxmm)
        return self._morph.largest_component(self._morph.fill_holes(cut | sil))

    def _crop_window(self, cut: np.ndarray, pxmm: float):
        """Return the offset (ox, oy) and the slices that crop the generous padding
        away, keeping CONTEXT_MM around the cut shape."""
        cx0, cy0, cx1, cy1 = self._morph.bbox(cut)
        b = int(np.ceil(CONTEXT_MM * pxmm))
        ox, oy = max(0, cx0 - b), max(0, cy0 - b)
        return ox, oy, (slice(oy, cy1 + b + 1), slice(ox, cx1 + b + 1))

    def _paint(
        self,
        img: np.ndarray,
        fig: np.ndarray,
        sil: np.ndarray,
        cut: np.ndarray,
        marks: _TabMarks,
        prm: Params,
        pxmm: float,
    ):
        """Return the paper color, the artwork and the tab's area.

        The artwork is the drawing where the figure is, and ``margin_color`` around
        it, or the original image everywhere. The tab below the fold, outside the
        drawing, is painted in ``tab_color``. With the original image, the paper color
        is white.
        """
        paper = (
            HexColor.to_rgb(prm.margin_color)
            if prm.margin_fill == "color"
            else (255, 255, 255)
        )
        art = self._composer.compose(img, fig, paper, pxmm, prm.margin_fill == "image")
        tabfill = None
        if prm.tab:
            # the tab has its own color (with or without the label on it): everything
            # that folds under - the cut shape below the fold, minus the drawing
            fold_row = int(np.ceil(marks.folds[0][2]))
            tabfill = np.zeros(cut.shape, bool)
            tabfill[fold_row:] = (cut[fold_row:] > 0) & (fig[fold_row:] == 0)
            art[tabfill] = HexColor.to_rgb(prm.tab_color)
        return paper, art, tabfill

    # endregion

    # region tab and top bridge

    def _tab(self, sil: np.ndarray, sy1: int, prm: Params, pxmm: float) -> _Tab:
        """Place the tab: centred on the silhouette's bottom band, its fold just above
        the silhouette's lowest point."""
        tab_w_mm, tab_depth_mm = self._tab_size_mm(prm)
        cx = self._band_centre(sil, int(sy1 - prm.tab_band_mm * pxmm), sy1)
        fold = sy1 - prm.fold_mm * pxmm
        return _Tab(
            shape=prm.tab_shape,
            cx=cx,
            fold=fold,
            top=fold - prm.tab_overlap_mm * pxmm,
            width=tab_w_mm * pxmm,
            height=tab_depth_mm * pxmm,
        )

    @staticmethod
    def _band_centre(m: np.ndarray, y0: int, y1: int) -> int:
        """Return the middle column of what ``m`` covers between rows y0 and y1."""
        cols = np.flatnonzero(m[max(0, y0) : y1 + 1].any(axis=0))
        return round((cols.min() + cols.max()) / 2)

    @staticmethod
    def _draw_tab(m: np.ndarray, tab: _Tab, dx: int = 0, dy: int = 0) -> None:
        """Paint a tab into ``m``, shifted by (-dx, -dy): the overlap above the fold
        (top..fold) plus, below the fold, a rectangle (square) or a half disc of the
        tab's width (round)."""
        x0 = round(tab.cx - tab.width / 2) - dx
        x1 = round(tab.cx + tab.width / 2) - dx
        f = round(tab.fold) - dy
        if tab.top < tab.fold:
            cv2.rectangle(m, (x0, round(tab.top) - dy), (x1, f), 255, -1)
        if tab.shape == "round":
            r = round(tab.width / 2)
            cv2.ellipse(m, (round(tab.cx) - dx, f), (r, r), 0, 0, 180, 255, -1)
        else:
            cv2.rectangle(m, (x0, f), (x1, round(tab.fold + tab.height) - dy), 255, -1)

    @staticmethod
    def _tab_marks(tab: _Tab, pxmm: float) -> _TabMarks:
        """Return the tab's fold line, its label's place and room, and its circle."""
        marks = _TabMarks(
            folds=[(tab.cx - tab.width / 2, tab.cx + tab.width / 2, tab.fold)]
        )
        if tab.shape == "round":
            # as _draw_tab draws it, in pixel-edge coordinates
            marks.circles.append(
                (
                    round(tab.cx) + 0.5,
                    round(tab.fold) + 0.5,
                    float(round(tab.width / 2)),
                    1,
                )
            )
            # the label near the straight edge, where the half disc is widest
            r = tab.width / 2
            marks.label_h = 0.42 * r
            ly = tab.fold + 0.08 * r + marks.label_h / 2
            marks.label_w = (
                2 * np.sqrt(max(0.0, r * r - (ly - tab.fold + marks.label_h / 2) ** 2))
                - 1.5 * pxmm
            )
        else:
            ly = tab.fold + tab.height / 2
            marks.label_w, marks.label_h = tab.width - 2 * pxmm, tab.height * 0.8
        marks.labels.append((tab.cx, ly, 0.0))
        return marks

    def _tab_fit(
        self, cut: np.ndarray, sil: np.ndarray, tab: _Tab, fillet_px: float
    ) -> tuple[bool, float]:
        """Return whether the tab's overlap changes the cut shape, and how much paper
        holds the tab, right above the fold (px)."""
        overlap_used = self._overlap_matters(cut, sil, tab, fillet_px)
        joint = 0.0
        row = round(tab.fold) - 1
        if 0 <= row < cut.shape[0]:
            jx0 = max(0, round(tab.cx - tab.width / 2))
            jx1 = round(tab.cx + tab.width / 2) + 1
            joint = float(np.count_nonzero(cut[row, jx0:jx1]))
        return overlap_used, joint

    def _overlap_matters(
        self, cut: np.ndarray, sil: np.ndarray, tab: _Tab, fillet_px: float
    ) -> bool:
        """Tell whether the part of the tab above the fold changes the final cut shape.

        It only adds paper where the figure is narrower than the tab; on a wide
        bottom it lies inside the outline (or in notches the fillet fills anyway).
        Re-does the tab without the overlap in a window around it and compares.
        """
        top, fold = round(tab.top), round(tab.fold)
        if top >= fold:
            return False
        x0, x1 = round(tab.cx - tab.width / 2), round(tab.cx + tab.width / 2)
        m = int(np.ceil(4 * max(fillet_px, 1.0))) + 2
        h, w = cut.shape
        wy0, wy1 = max(0, top - m), min(h, fold + m)
        wx0, wx1 = max(0, x0 - m), min(w, x1 + m + 1)
        alt = sil[wy0:wy1, wx0:wx1].copy()
        self._draw_tab(alt, replace(tab, top=tab.fold), wx0, wy0)  # no overlap
        if fillet_px > 0:
            alt = self._morph.close(alt, fillet_px)
        k = m // 2  # skip the window rim, where closing sees a cut-off neighbourhood
        inner = (slice(k, alt.shape[0] - k), slice(k, alt.shape[1] - k))
        return bool(np.any((cut[wy0:wy1, wx0:wx1] > 0)[inner] != (alt > 0)[inner]))

    def _add_top_bridge(
        self, cut: np.ndarray, sil: np.ndarray, sy0: int, prm: Params, pxmm: float
    ) -> None:
        """Paint the bridge that joins the halves of a double-sided mini at the fold."""
        bw = prm.top_bridge_width_mm * pxmm
        depth = round(prm.top_bridge_depth_mm * pxmm)
        bcx = self._bridge_centre(sil, sy0, depth, round(bw))
        cv2.rectangle(
            cut,
            (round(bcx - bw / 2), sy0),
            (round(bcx + bw / 2) - 1, sy0 + depth),
            255,
            -1,
        )

    @staticmethod
    def _bridge_centre(sil: np.ndarray, y_top: int, depth: int, width: int) -> float:
        """Return the column for the top bridge of a double-sided mini.

        The bridge is a ``width`` x ``depth`` rectangle hanging from the fold row. It
        goes where it overlaps the silhouette most, so it holds the halves together
        where the figure really reaches the fold (a raised wing, not the gap beside
        it). Among equally good places it takes the middle one, so it is centred on a
        head.
        """
        cover = np.count_nonzero(sil[y_top : y_top + max(1, depth)], axis=0).astype(
            np.float64
        )
        w = int(np.clip(width, 1, len(cover)))
        c = np.concatenate([[0.0], np.cumsum(cover)])
        score = c[w:] - c[:-w]  # score[i]: overlap of a bridge over columns i .. i+w-1
        best = int(np.argmax(score))
        good = score >= 0.99 * score[best]
        lo, hi = best, best
        while lo > 0 and good[lo - 1]:
            lo -= 1
        while hi < len(good) - 1 and good[hi + 1]:
            hi += 1
        return (lo + hi) / 2 + w / 2

    # endregion
