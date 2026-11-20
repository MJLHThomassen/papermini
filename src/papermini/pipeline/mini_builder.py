from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image

from ..support import cache
from .adjustments import Adjustments
from .bleed_painter import MAX_BLEED_MM, BleedPainter
from .cut_path import CutPath
from .cut_path_tracer import CutPathTracer
from .debug_writer import DebugWriter
from .figure_mask import FigureMask
from .figure_masker import FigureMasker
from .figure_scaler import FigureScaler
from .font_checker import FontChecker
from .image_adjuster import ImageAdjuster
from .layout import Layout
from .layout_builder import LayoutBuilder
from .mask_options import MaskOptions
from .mini import Mini
from .morphology import Morphology
from .params import Params
from .read_only import ReadOnly
from .segmentation.cancellation import Cancellation
from .segmentation.download_hooks import DownloadHooks
from .style import Style
from .text_fitter import TextFitter
from .text_item import TextItem


@dataclass(frozen=True)
class _Piece:
    """The printed piece: its artwork, where it lies on the layout's canvas (px) and its
    size (mm)."""

    art: Image.Image
    x0: int
    y0: int
    width_mm: float
    height_mm: float


class MiniBuilder:
    """Builds a paper miniature from an image: image, then mask, layout, cut path and
    the result in millimetres."""

    def __init__(
        self,
        morphology: Morphology,
        fonts: FontChecker,
        masker: FigureMasker,
        scaler: FigureScaler,
        adjuster: ImageAdjuster,
        layouts: LayoutBuilder,
        tracer: CutPathTracer,
        bleed: BleedPainter,
        debug: DebugWriter,
        cancellation: Cancellation,
    ):
        self._morph = morphology
        self._fonts = fonts
        self._masker = masker
        self._scaler = scaler
        self._adjuster = adjuster
        self._layouts = layouts
        self._tracer = tracer
        self._bleed = bleed
        self._debug = debug
        self._cancellation = cancellation

    def make(
        self,
        image_path: Path,
        prm: Params,
        mask_options: MaskOptions,
        *,
        label: str | None,
        back_text: str | None,
        tab_front: str,
        tab_back: str,
        dpi: int,
        simplify_mm: float,
        smooth_path: bool,
        bleed_mm: float,
        adjust: Adjustments,
        style: Style,
        use_cache: bool = True,
        debug_dir: Path | None = None,
        log=print,
        on_stage=None,
        downloads: DownloadHooks | None = None,
    ) -> Mini:
        """Build one miniature. ``on_stage(name, data)``, if given, hears about
        progress: ``("segment", model)`` just before a model runs (it may take a while)
        and ``("outline", (contours, close_px))`` once the figure is found, before the
        layout. ``downloads`` asks before a built-in model downloads, and hears its
        progress."""
        image_path = Path(image_path)
        style = self._fonts.checked(style, image_path.name, log)
        debug = bool(debug_dir)
        fm = self._masker.find(
            image_path,
            mask_options,
            use_cache=use_cache,
            debug=debug,
            log=log,
            on_stage=on_stage,
            downloads=downloads,
        )

        # size (by height, by width, or both: stretched sideways)
        bx0, by0, bx1, by1 = self._morph.bbox(fm.clean)
        bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
        height_mm, stretch = self._scaler.size(bw, bh, prm.height_mm, prm.width_mm)
        prm = replace(prm, height_mm=height_mm, width_mm=None)
        work_key, clean, rgb = self._working(
            fm, height_mm, stretch, prm.max_px_per_mm, debug
        )
        rgb = self._adjusted(rgb, work_key, adjust, debug)
        lay, path_px = self._layout(
            clean, rgb, prm, work_key, adjust, simplify_mm, smooth_path, debug
        )
        self._cancellation.check()

        piece = self._art(lay, path_px, style, bleed_mm, dpi)
        s = 1.0 / lay.px_per_mm
        x0, y0 = piece.x0, piece.y0
        label = image_path.stem if label is None else label
        max_w = lay.label_max_w_px * s if prm.tab else piece.width_mm
        mini = Mini(
            name=image_path.stem,
            width_mm=piece.width_mm,
            height_mm=piece.height_mm,
            art=piece.art,
            cut=path_px.transformed(s, x0, y0),
            folds=[((a - x0) * s, (b - x0) * s, (y - y0) * s) for a, b, y in lay.folds],
            labels=[((x - x0) * s, (y - y0) * s, r) for x, y, r in lay.labels]
            if prm.tab
            else [],
            label=label,
            label_size_mm=TextFitter.label_size(
                label,
                max_w,
                min(style.label_size_mm, lay.label_max_h_px * s or style.label_size_mm),
                style.font,
            ),
            style=style,
            figure_height_mm=lay.figure_height_px * s,
            figure_width_mm=height_mm * bw * stretch / bh,
            aspect=bw / bh,
            source_outline=fm.contours,
            method=fm.method,
            tab_overlap_used=lay.tab_overlap_used
            or not prm.tab
            or prm.tab_overlap_mm == 0,
            tab_joint_mm=lay.tab_joint_px * s if prm.tab else 0.0,
            tab_width_mm=lay.tab_width_px * s if prm.tab else 0.0,
            close_px=fm.close_px,
            # (the front tab's label is upright, the back tab's upside down)
            tab_shows=[tab_front if r == 0 else tab_back for _, _, r in lay.labels]
            if prm.tab
            else [],
            tab_room=(max_w, lay.label_max_h_px * s) if prm.tab else (0.0, 0.0),
        )
        if lay.back_box is not None:
            text = back_text or label or image_path.stem
            self._add_back(mini, lay.back_box, piece, s, prm.back, text, style)

        self._log_result(log, image_path.name, lay, prm, piece, path_px)
        self._place_on_source(mini, lay, path_px, prm, fm.image.size, rgb.shape)
        if debug_dir is not None:
            self._debug.write(Path(debug_dir), image_path.stem, fm.stages, lay, path_px)
        return mini

    def _working(
        self,
        fm: FigureMask,
        height_mm: float,
        stretch: float,
        max_px_per_mm: float,
        debug: bool,
    ):
        """Return the cache key, mask and image at the working resolution for the
        figure's size: stretched sideways if needed, at most ``max_px_per_mm``."""

        def work():
            c, r = (
                (fm.clean, fm.rgb)
                if stretch == 1
                else self._scaler.stretch_x(fm.clean, fm.rgb, stretch)
            )
            return tuple(
                ReadOnly.array(a)
                for a in self._scaler.limit_resolution(c, r, height_mm, max_px_per_mm)
            )

        work_key = (fm.key, height_mm, stretch, max_px_per_mm)
        clean, rgb = work() if debug else cache.working.get_or_make(work_key, work)
        return work_key, clean, rgb

    def _adjusted(
        self, rgb: np.ndarray, work_key: tuple, adjust: Adjustments, debug: bool
    ) -> np.ndarray:
        """Apply the color adjustments to the picture, at the working size (cheap
        there). The mask and outline never see them, so a slider never runs the model
        again."""
        if adjust.is_identity():
            return rgb
        make = lambda: ReadOnly.array(self._adjuster.apply(rgb, adjust))
        return make() if debug else cache.adjusted.get_or_make((work_key, adjust), make)

    def _layout(
        self,
        clean: np.ndarray,
        rgb: np.ndarray,
        prm: Params,
        work_key: tuple,
        adjust: Adjustments,
        simplify_mm: float,
        smooth_path: bool,
        debug: bool,
    ) -> tuple[Layout, CutPath]:
        """Return the margin, tab and vector cut line, cached, so cosmetic changes
        (label, colors, line width, dpi) only redo the cheap finishing."""

        def make():
            lay = self._layouts.build(clean, rgb, prm)
            return lay, self._tracer.trace(
                lay.cut, lay.px_per_mm, simplify_mm, smooth_path, lay.tab_circles
            )

        layout_key = (
            work_key,
            adjust,
            tuple(sorted(asdict(prm).items())),
            simplify_mm,
            smooth_path,
        )
        return make() if debug else cache.layouts.get_or_make(layout_key, make)

    def _art(
        self, lay: Layout, path_px: CutPath, style: Style, bleed_mm: float, dpi: int
    ) -> _Piece:
        """Cut the artwork out of the canvas, with its bleed, at ``dpi``."""
        pxmm = lay.px_per_mm
        # the artwork alpha is the rasterised path, so picture and cut line match
        # exactly
        alpha = self._tracer.rasterize(path_px, lay.cut.shape)

        # room around the cut line: half the stroke, or the bleed (the canvas keeps
        # 6 mm)
        bleed_mm = min(max(0.0, bleed_mm), MAX_BLEED_MM)
        pad = max(style.cut_width_mm / 2 + 0.3, bleed_mm + 0.2 if bleed_mm else 0.0)
        ex0, ey0, ex1, ey1 = path_px.extent()
        x0 = max(0, int(np.floor(ex0 - pad * pxmm)))
        y0 = max(0, int(np.floor(ey0 - pad * pxmm)))
        x1 = int(np.ceil(ex1 + pad * pxmm))
        y1 = int(np.ceil(ey1 + pad * pxmm))
        rgb_c, alpha_c = lay.rgb[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
        if bleed_mm:
            rgb_c, alpha_c = self._bleed.add(rgb_c, alpha_c, bleed_mm * pxmm)
        art = np.dstack([rgb_c, alpha_c])
        w_mm, h_mm = (x1 - x0) / pxmm, (y1 - y0) / pxmm
        size = (max(1, round(w_mm / 25.4 * dpi)), max(1, round(h_mm / 25.4 * dpi)))
        art_im = Image.fromarray(art, "RGBA").resize(size, Image.LANCZOS)
        return _Piece(art_im, x0, y0, w_mm, h_mm)

    @staticmethod
    def _add_back(
        mini: Mini,
        back_box: tuple[float, float, float, float],
        piece: _Piece,
        s: float,
        back: str,
        text: str,
        style: Style,
    ) -> None:
        """Place the back side's number and text in ``back_box`` (canvas px)."""
        bcx, bcy, bw, bh = back_box
        bcx, bcy = (bcx - piece.x0) * s, (bcy - piece.y0) * s
        bw, bh = bw * s, bh * s
        if back in ("number", "text_number"):
            # the number above the text: the back half is upside down on the sheet, so
            # its top is further down the sheet
            nh = bh if back == "number" else 0.45 * bh
            mini.number_box = (bcx, bcy + (bh - nh) / 2, bw, nh)
            bcy, bh = bcy - nh / 2, bh - nh
        if back in ("text", "text_number"):
            size, lines = TextFitter.text_block(
                text, bw, bh, max_size=10.0, font=style.font
            )
            pitch = 1.15 * size
            for i, line in enumerate(lines):
                # the back half is upside down on the sheet: rotate 180 and reverse
                # line order
                off = ((len(lines) - 1) / 2 - i) * pitch
                mini.texts.append(
                    TextItem(
                        "backtext",
                        line,
                        bcx,
                        bcy + off,
                        180.0,
                        size,
                        style.back_text_color,
                    )
                )

    @staticmethod
    def _log_result(
        log, name: str, lay: Layout, prm: Params, piece: _Piece, path_px: CutPath
    ) -> None:
        """Report the piece's size, and a tab overlap that has no effect."""
        if prm.tab and not lay.tab_overlap_used and prm.tab_overlap_mm:
            log(
                f"  {name}: note: the tab overlap has no effect here - the figure's "
                "bottom is wider than the tab (it only matters for narrow feet or "
                "tails)"
            )
        s = 1.0 / lay.px_per_mm
        log(
            f"  {name}: figure {lay.figure_height_px * s:.1f} mm high, "
            f"piece {piece.width_mm:.1f} x {piece.height_mm:.1f} mm, cut line "
            f"{len(path_px.points)} nodes"
        )

    @staticmethod
    def _place_on_source(
        mini: Mini,
        lay: Layout,
        path_px: CutPath,
        prm: Params,
        source_size: tuple[int, int],
        work_shape: tuple[int, ...],
    ) -> None:
        """Map the cut line and folds onto the source image (front side), to show on
        the original artwork what is kept and what is cut away."""
        # canvas -> working image (lay.src) -> source image (the working downscale)
        W, H = source_size
        sx, sy, dx, dy = lay.src
        k = np.array([sx * W / work_shape[1], sy * H / work_shape[0]])
        d = np.array([dx, dy])
        mini.source_cut = CutPath(
            (path_px.points - d) * k,
            None if path_px.controls is None else (path_px.controls - d) * k,
        )
        mini.source_folds = [
            ((a - dx) * k[0], (b - dx) * k[0], (y - dy) * k[1]) for a, b, y in lay.folds
        ]
        if prm.double_sided:
            mini.source_top = max(0.0, (lay.front_top - dy) * k[1])
