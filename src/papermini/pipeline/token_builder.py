from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..support.stage_caches import StageCaches
from .adjustments import Adjustments
from .bleed_painter import MAX_BLEED_MM
from .cut_path import CutPath
from .figure_masker import FigureMasker
from .font_checker import FontChecker
from .mask_options import MaskOptions
from .mini import Mini
from .morphology import Morphology
from .segmentation.download_hooks import DownloadHooks
from .style import Style
from .token_framer import PX_PER_MM
from .token_info import TokenInfo
from .token_options import TokenOptions
from .token_renderer import TokenRenderer


class TokenBuilder:
    """Builds a flat round token from an image: the cut-out figure in a circle, with a
    ring, for the table or a virtual tabletop.

    A token is a ``Mini`` like any other piece (its art, a circular cut line, its text),
    so the print sheet, the SVG and the PNG output treat both alike. Its diameter comes
    from the figure's creature size (the size table's base). The figure is fitted in the
    circle with ``FIT_FREE`` of the inner diameter free on each side, or framed by its
    area: the square of the picture that fills the circle. The ring can carry the label
    and the copy number, on a nameplate and a badge, or curved along the ring (which is
    then never narrower than the text needs).
    """

    def __init__(
        self,
        morphology: Morphology,
        fonts: FontChecker,
        masker: FigureMasker,
        renderer: TokenRenderer,
        caches: StageCaches,
    ):
        self._morph = morphology
        self._fonts = fonts
        self._masker = masker
        self._renderer = renderer
        self._caches = caches

    def make(
        self,
        image_path: Path,
        o: TokenOptions,
        mask_options: MaskOptions,
        *,
        label: str | None,
        dpi: int,
        bleed_mm: float,
        adjust: Adjustments,
        style: Style,
        use_cache: bool = True,
        log=print,
        on_stage=None,
        downloads: DownloadHooks | None = None,
    ) -> Mini:
        """Build one token: background removal as for a mini, then the figure framed in
        a circle on its background, inside a ring, with a circular cut line.
        ``downloads`` asks before a built-in model downloads, and hears its progress."""
        image_path = Path(image_path)
        style = self._fonts.checked(style, image_path.name, log)
        fm = self._masker.find(
            image_path,
            mask_options,
            use_cache=use_cache,
            log=log,
            on_stage=on_stage,
            downloads=downloads,
        )
        label = image_path.stem if label is None else label
        bleed_mm = min(max(0.0, bleed_mm), MAX_BLEED_MM)
        pad_mm = max(style.cut_width_mm + 0.3, bleed_mm + 0.2 if bleed_mm else 0.0)
        # a cut line printed for cutting by hand lies just outside the ring, so it never
        # covers its edge (cut by machine, the cut follows the ring and the bleed is
        # beyond)
        cut_out = style.cut_width_mm / 2 if style.cut_line and not bleed_mm else 0.0
        key = ("token", fm.key, o, adjust, bleed_mm, pad_mm, bool(label))
        make = lambda: self._renderer.render(
            fm, o, adjust, bleed_mm, pad_mm, bool(label)
        )
        token = self._caches.layouts.get_or_make(key, make) if use_cache else make()
        if o.curved and o.border_mm < token.ring_mm:
            log(
                f"  {image_path.name}: note: the ring is {token.ring_mm:g} mm wide, the "
                "least that holds curved text"
            )

        side_mm = token.side_px / PX_PER_MM
        px = max(1, round(side_mm / 25.4 * dpi))
        art = Image.fromarray(token.rgba, "RGBA").resize((px, px), Image.LANCZOS)
        c = side_mm / 2
        R = o.diameter_mm / 2
        bx0, by0, bx1, by1 = self._morph.bbox(fm.clean)
        info = TokenInfo(
            cx=c,
            cy=c,
            radius_mm=R,
            inner_mm=token.inner_mm,
            text=o.text,
            text_style=o.text_style,
            color=o.text_color,
            size_mm=token.text_mm,
            plate=token.plate,
            badge=token.badge,
            area=token.area,
            figure_box=token.figure_box,
        )
        mini = Mini(
            name=image_path.stem,
            width_mm=side_mm,
            height_mm=side_mm,
            art=art,
            cut=CutPath.circle(c, c, R + cut_out),
            label=label,
            label_size_mm=token.text_mm,
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
        fx, fy, f = token.frame
        mini.source_cut = CutPath.circle(fx, fy, token.inner_mm * PX_PER_MM / f)
        log(
            f"  {image_path.name}: token {o.diameter_mm:g} mm, ring {token.ring_mm:g} mm"
        )
        return mini
