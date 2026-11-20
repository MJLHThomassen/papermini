from __future__ import annotations

from dataclasses import dataclass

MARGIN_FILLS = ("color", "image")
TAB_SHAPES = ("square", "round")
BACK_MODES = ("mirror", "blank", "text", "number", "text_number")


@dataclass
class Params:
    """The layout parameters of a mini: its size, margin, tab and back (see
    ``FigureSettings`` for each option's meaning and default)."""

    height_mm: float | None  # figure height, excluding margin and tab
    width_mm: float | None  # figure width; see FigureScaler.size()
    margin_mm: float  # distance between drawing and cut line
    smooth_mm: float  # Gaussian sigma that rounds the outline
    tab: bool
    tab_width_mm: float  # square tab
    tab_radius_mm: float  # round tab (a half disc; 12.5 = a 25 mm base)
    tab_height_mm: float  # below the fold line
    tab_overlap_mm: float  # how far the tab reaches up into the figure
    fold_mm: float  # fold line above the silhouette's lowest point
    keep_all: bool  # bridge detached parts to the figure
    margin_fill: str  # "color" (margin_color) or "image": what shows in the margin
    margin_color: str  # color of the margin around the drawing
    tab_shape: str  # "square" (slots into a stand) or "round" (folds out to a base)
    tab_color: str  # tab background, independent of the margin color
    double_sided: bool
    back: str  # double-sided back: "mirror" (image), "blank", "text",
    #            "number" or "text_number"
    back_color: str  # color of a blank/text back
    tab_band_mm: float = 6.0  # bottom band used to centre the tab
    fillet_mm: float = 1.0  # rounds inner corners (closing) - never removes paper
    bridge_mm: float = 2.5  # width of bridges joining separate parts (--keep-all)
    max_px_per_mm: float = 24.0  # working resolution cap (~600 dpi; output is 300 dpi)
    top_bridge_width_mm: float = 12.0  # double-sided: joint at the top fold
    top_bridge_depth_mm: float = 3.0
