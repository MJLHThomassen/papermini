from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from ..pipeline import geometry as geo
from ..pipeline import token as tok
from ..pipeline.adjust import RANGES as ADJUST_RANGES
from ..pipeline.adjustments import Adjustments
from ..pipeline.mini import TAB_SHOWS
from ..pipeline.style import Style
from . import sizes

_MEDIUM = sizes.BUILTIN.row(sizes.DEFAULT_SIZE)


# what a figure's size fills in; saved projects always write these, so a project says
# both the size and its values (a token also its diameter)
SIZE_KEYS = ("size", "height_mm", "tab_radius_mm", "tab_width_mm", "tab_height_mm")


KINDS = ("mini", "token")  # a standing miniature or a flat round token


@dataclass
class FigureSettings:
    kind: str = "mini"  # "mini" (standing) or "token" (flat and round)
    # size and shape: a creature size fills in the height and the tabs (see sizes.py);
    # height or width keeps the proportions, both stretch the figure
    size: str = sizes.DEFAULT_SIZE  # tiny ... gargantuan, or custom
    height_mm: float | None = _MEDIUM.height_mm
    width_mm: float | None = None
    margin_mm: float = 1.6
    smooth_mm: float = 0.6
    tab_width_mm: float = _MEDIUM.tab_width_mm  # square tab (a stand)
    tab_radius_mm: float = _MEDIUM.base_mm / 2  # round tab (folds out to a base)
    tab_height_mm: float = _MEDIUM.tab_height_mm
    tab_overlap_mm: float = 0.0
    fold_mm: float = 0.0
    no_tab: bool = False
    tab_shape: str = "square"  # "square" (for a stand) or "round" (folds out to a base)
    tab_color: str = "#ffffff"  # tab background, independent of the margin color
    double_sided: bool = True  # front and back, joined at a fold above the head
    back: str = "mirror"  # double-sided back: "mirror", "blank", "text",
    #                                  "number" (large) or "text_number" (number above text)
    back_text: str | None = None  # back with text: None = the label (or file name)
    back_color: str = "#ffffff"  # color of a back that is not the mirrored drawing
    back_text_color: str = "#2f5597"
    # mask
    model: str = "auto"
    mask: str | None = None
    crop: Any = None  # "x0,y0,x1,y1" or [x0, y0, x1, y1], fractions or px
    strength: int = 40  # mask threshold 0-254: higher removes more background
    fill_gaps: int | None = None  # closing radius in px; None = scales with the image
    keep_all: bool = False
    min_area: int = 1000
    margin_fill: str = "color"  # "color" (margin_color) or "image"
    margin_color: str = "#ffffff"
    # picture: color adjustments of what is printed (never of what the model sees)
    greyscale: bool = False
    brightness: int = 0  # -100..100
    contrast: int = 0  # -100..100
    saturation: int = 0  # -100..100
    hue: int = 0  # -180..180 degrees
    # output
    label: str | None = None  # None = file name, "" = no label
    tab_front: str = "label"  # what the front tab shows: "label", "number" or
    tab_back: str = "label"  # "label_number" (the copy number above the label)
    dpi: int = 300
    simplify_mm: float = 0.15
    no_smooth: bool = False
    cut_color: str = "#000000"  # the cut line, for cutting by hand
    cut_width_mm: float = 0.3
    label_color: str = "#2f5597"
    label_size_mm: float = 3.4
    font: str = "Times"  # all text: labels, numbers, back text (see fonts.py)
    copies: int = 1
    # a token (kind "token"): its diameter comes from the creature size's base
    token_diameter_mm: float = _MEDIUM.base_mm
    token_area: Any = None  # [x0, y0, x1, y1] fractions of the picture: the square
    #                                  that fills the circle; None = the figure fitted in it
    token_fill: str = "color"  # behind the figure: "color" or "image" (the picture)
    token_fill_color: str = "#ffffff"
    token_border_mm: float = 2.0  # the ring around the token (0 = none)
    token_border_color: str = "#000000"
    token_outline: bool = False  # an outline around the figure, as the mini's margin
    token_cut_line: bool = (
        False  # print the cut line (the ring's edge shows where to cut)
    )
    token_text: str = "none"  # "none", "label", "number" or "label_number"
    token_text_style: str = "nameplate"  # "nameplate" (a band and a badge) or "curved"
    token_text_mm: float = 2.5  # its size: the nameplate's height and a curved ring's
    #                                  least width follow from it
    token_text_color: str = "#ffffff"  # (on the ring, the nameplate and the badge)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FigureSettings:
        from .settings import norm_keys

        d = norm_keys(d)
        unknown = set(d) - FIGURE_OPTIONS
        if unknown:
            raise ValueError(f"unknown option(s) {', '.join(sorted(unknown))}")
        if "size" in d and d["size"] not in sizes.SIZE_CHOICES:
            raise ValueError(
                f"size must be one of {', '.join(sizes.SIZE_CHOICES)}, "
                f"not {d['size']!r}"
            )
        if d.get("width_mm") is not None and "height_mm" not in d:
            d["height_mm"] = None  # a width alone: scale by width, keep the proportions
        for key in ("height_mm", "width_mm"):
            v = d.get(key)
            if v is not None and (
                isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0
            ):
                raise ValueError(f"{key} must be a number above 0, not {v!r}")
        if d.get("height_mm", 1) is None and d.get("width_mm") is None:
            raise ValueError("give height_mm, width_mm or both")
        for key, allowed in (
            ("back", geo.BACK_MODES),
            ("margin_fill", geo.MARGIN_FILLS),
            ("tab_shape", geo.TAB_SHAPES),
            ("tab_front", TAB_SHOWS),
            ("tab_back", TAB_SHOWS),
            ("kind", KINDS),
            ("token_fill", tok.TOKEN_FILLS),
            ("token_text", tok.TOKEN_TEXTS),
            ("token_text_style", tok.TOKEN_TEXT_STYLES),
        ):
            if key in d and d[key] not in allowed:
                raise ValueError(
                    f"{key} must be one of {', '.join(allowed)}, not {d[key]!r}"
                )
        for key, (lo, hi) in ADJUST_RANGES.items():
            v = d.get(key)
            if v is not None and (
                isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi
            ):
                raise ValueError(
                    f"{key} must be a whole number from {lo} to {hi}, not {v!r}"
                )
        if "font" in d and (not isinstance(d["font"], str) or not d["font"].strip()):
            raise ValueError(f"font must be the name of a font, not {d['font']!r}")
        for key in (
            "margin_color",
            "tab_color",
            "back_color",
            "back_text_color",
            "cut_color",
            "label_color",
            "token_fill_color",
            "token_border_color",
            "token_text_color",
        ):
            if key in d:
                geo.hex_rgb(str(d[key]))  # raises a clear error for a bad color
        for key, lo in (
            ("token_diameter_mm", 0.0),
            ("token_border_mm", None),
            ("token_text_mm", 0.0),
        ):
            v = d.get(key)
            if v is not None and (
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or (v <= 0 if lo is not None else v < 0)
            ):
                raise ValueError(
                    f"{key} must be a number {'above' if lo is not None else 'from'}"
                    f" 0, not {v!r}"
                )
        if d.get("token_area") is not None:
            d["token_area"] = tok.parse_area(d["token_area"])
        return cls(**d)

    def to_dict(
        self, base: FigureSettings | None = None, with_size: bool = True
    ) -> dict[str, Any]:
        """Options that differ from ``base`` (default: the built-in defaults) and, with
        ``with_size`` (as a project saves them), always the size with the values it
        fills in."""
        ref = asdict(base or FigureSettings())
        size_keys = SIZE_KEYS + (("token_diameter_mm",) if self.kind == "token" else ())
        d = {
            k: v
            for k, v in asdict(self).items()
            if v != ref[k] or (with_size and k in size_keys)
        }
        if self.kind != "token" and self.size != sizes.CUSTOM:
            d.pop("token_diameter_mm", None)  # (a mini's: what its size fills in)
        if self.width_mm is not None:  # a width alone would mean "scale by width"
            d.setdefault("height_mm", self.height_mm)
        if isinstance(d.get("token_area"), tuple):
            d["token_area"] = list(d["token_area"])
        return d

    def params(self) -> geo.Params:
        return geo.Params(
            height_mm=self.height_mm,
            width_mm=self.width_mm,
            margin_mm=self.margin_mm,
            smooth_mm=self.smooth_mm,
            tab=not self.no_tab,
            tab_width_mm=self.tab_width_mm,
            tab_radius_mm=self.tab_radius_mm,
            tab_height_mm=self.tab_height_mm,
            tab_overlap_mm=self.tab_overlap_mm,
            fold_mm=self.fold_mm,
            keep_all=self.keep_all,
            margin_fill=self.margin_fill,
            double_sided=self.double_sided,
            back=self.back,
            back_color=self.back_color,
            margin_color=self.margin_color,
            tab_shape=self.tab_shape,
            tab_color=self.tab_color,
        )

    def adjustments(self) -> Adjustments:
        return Adjustments(
            brightness=self.brightness,
            contrast=self.contrast,
            saturation=self.saturation,
            hue=self.hue,
            greyscale=self.greyscale,
        )

    def token_options(self) -> tok.TokenOptions:
        """What a token is made of (kind "token"); the outline uses the margin."""
        return tok.TokenOptions(
            diameter_mm=self.token_diameter_mm,
            border_mm=self.token_border_mm,
            border_color=self.token_border_color,
            fill=self.token_fill,
            fill_color=self.token_fill_color,
            outline=self.token_outline,
            margin_mm=self.margin_mm,
            margin_fill=self.margin_fill,
            margin_color=self.margin_color,
            smooth_mm=self.smooth_mm,
            area=None if self.token_area is None else tuple(self.token_area),
            text=self.token_text,
            text_style=self.token_text_style,
            text_mm=self.token_text_mm,
            text_color=self.token_text_color,
        )

    def style(self) -> Style:
        return Style(
            cut_color=self.cut_color,
            cut_width_mm=self.cut_width_mm,
            label_color=self.label_color,
            label_size_mm=self.label_size_mm,
            back_text_color=self.back_text_color,
            font=self.font,
            cut_line=self.kind != "token" or self.token_cut_line,
        )


FIGURE_OPTIONS = {f.name for f in fields(FigureSettings)}
