from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Params:
    height_mm: float | None = 42.0  # figure height, excluding margin and tab
    width_mm: float | None = None  # figure width; see figure_size()
    margin_mm: float = 1.6  # distance between drawing and cut line
    smooth_mm: float = 0.6  # Gaussian sigma that rounds the outline
    tab: bool = True
    tab_width_mm: float = 22.0  # square tab
    tab_radius_mm: float = 12.5  # round tab (a half disc; 12.5 = a 25 mm base)
    tab_height_mm: float = 12.0  # below the fold line
    tab_overlap_mm: float = 0.0  # how far the tab reaches up into the figure
    fold_mm: float = 0.0  # fold line above the silhouette's lowest point
    tab_band_mm: float = 6.0  # bottom band used to centre the tab
    fillet_mm: float = 1.0  # rounds inner corners (closing) - never removes paper
    keep_all: bool = False
    bridge_mm: float = 2.5  # width of bridges joining separate parts (--keep-all)
    margin_fill: str = (
        "color"  # "color" (margin_color) or "image": what shows in the margin
    )
    margin_color: str = "#ffffff"  # color of the margin around the drawing
    tab_shape: str = (
        "square"  # "square" (slots into a stand) or "round" (folds out to a base)
    )
    tab_color: str = "#ffffff"  # tab background, independent of the margin color
    double_sided: bool = False
    back: str = "mirror"  # double-sided back: "mirror" (image), "blank", "text",
    #                               "number" or "text_number"
    back_color: str = "#ffffff"  # color of a blank/text back
    max_px_per_mm: float = 24.0  # working resolution cap (~600 dpi; output is 300 dpi)
    top_bridge_width_mm: float = 12.0  # double-sided: joint at the top fold
    top_bridge_depth_mm: float = 3.0
