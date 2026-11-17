"""Builds a figure's settings from its options and size, and its miniature from them."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from ..pipeline import token as tok
from ..pipeline.mini import Mini, make_mini
from . import sizes
from .figure_settings import FigureSettings


def settings_with_size(
    options: dict[str, Any], table: sizes.SizeTable = sizes.BUILTIN
) -> FigureSettings:
    """Figure settings from ``options`` (a project's figure, or command-line flags): the
    figure's size fills in the values not given, from ``table``; a given value that
    differs from the size's makes the figure custom."""
    o = norm_keys(options)
    size = o.get("size", sizes.DEFAULT_SIZE)
    if size in sizes.SIZES:
        fills = table.row(size).values()
        if o.get("width_mm") is not None and "height_mm" not in o:
            del fills[
                "height_mm"
            ]  # (a width alone scales by width: no height to fill in)
        for k, v in fills.items():
            o.setdefault(k, v)
    s = FigureSettings.from_dict(o)
    return s if sizes.matches(s, table) else replace(s, size=sizes.CUSTOM)


def norm_keys(d: dict[str, Any] | None) -> dict[str, Any]:
    return {str(k).replace("-", "_"): v for k, v in (d or {}).items()}


def build_mini(
    image: Path,
    s: FigureSettings,
    *,
    bleed_mm: float = 0.0,
    use_cache: bool = True,
    debug_dir: Path | None = None,
    log=print,
    on_stage=None,
) -> Mini:
    """Build one figure. ``bleed_mm``: print the edge colors this far beyond the cut
    line (a sheet cut by machine, see ``SheetSettings.figure_bleed``)."""
    # model "mask" = your own mask image; "auto" also uses a mask image if one is given
    use_mask = s.model == "mask" or (s.model == "auto" and bool(s.mask))
    if s.model == "mask" and not s.mask:
        raise ValueError("model 'mask' needs a mask image file - choose one")
    if s.kind == "token":
        return tok.make_token(
            Path(image),
            s.token_options(),
            label=s.label,
            threshold=s.strength,
            close_px=s.fill_gaps,
            keep_all=s.keep_all,
            min_area=s.min_area,
            crop=s.crop,
            model="auto" if s.model == "mask" else s.model,
            mask_path=Path(s.mask) if use_mask else None,
            dpi=s.dpi,
            bleed_mm=bleed_mm,
            adjust=s.adjustments(),
            use_cache=use_cache,
            style=s.style(),
            log=log,
            on_stage=on_stage,
        )
    return make_mini(
        Path(image),
        s.params(),
        label=s.label,
        back_text=s.back_text,
        tab_front=s.tab_front,
        tab_back=s.tab_back,
        threshold=s.strength,
        close_px=s.fill_gaps,
        min_area=s.min_area,
        crop=s.crop,
        model="auto" if s.model == "mask" else s.model,
        mask_path=Path(s.mask) if use_mask else None,
        dpi=s.dpi,
        simplify_mm=s.simplify_mm,
        smooth_path=not s.no_smooth,
        bleed_mm=bleed_mm,
        adjust=s.adjustments(),
        use_cache=use_cache,
        style=s.style(),
        debug_dir=debug_dir,
        log=log,
        on_stage=on_stage,
    )
