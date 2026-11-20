"""Builds a figure's miniature from its settings."""

from __future__ import annotations

from pathlib import Path

from ..pipeline import token as tok
from ..pipeline.mini import Mini, make_mini
from .figure_settings import FigureSettings


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
    mask_options = s.mask_options()
    if s.kind == "token":
        return tok.make_token(
            Path(image),
            s.token_options(),
            mask_options,
            label=s.label,
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
        mask_options,
        label=s.label,
        back_text=s.back_text,
        tab_front=s.tab_front,
        tab_back=s.tab_back,
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
