"""Per-figure settings and projects, shared by the CLI, batch YAML and the GUI.

A project file *is* a batch config::

    output: minis
    sheet: {output: minis/sheet.pdf, paper: a4, copies: 1}
    defaults: {height_mm: 42}
    figures:
      - image: dragon.png
        label: Red dragon
      - image: https://example.com/goblin.webp   # a link: downloaded once, then cached
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import geometry as geo
from . import remote
from .adjust import RANGES as ADJUST_RANGES
from .adjust import Adjustments
from .mini import Mini, Style, make_mini

CUTTER_STYLE = {"cut_color": "#ff0000", "cut_width_mm": 0.1}


@dataclass
class FigureSettings:
    # size and shape: height or width keeps the proportions, both stretch the figure
    height_mm: Optional[float] = 42.0
    width_mm: Optional[float] = None
    margin_mm: float = 1.6
    smooth_mm: float = 0.6
    tab_width_mm: float = 22.0       # square tab
    tab_radius_mm: float = 12.5      # round tab
    tab_height_mm: float = 12.0
    tab_overlap_mm: float = 0.0
    fold_mm: float = 0.0
    no_tab: bool = False
    tab_shape: str = "square"        # "square" (for a stand) or "round" (folds out to a base)
    tab_color: str = "#ffffff"       # tab background, independent of the margin color
    double_sided: bool = True        # front and back, joined at a fold above the head
    back: str = "mirror"             # double-sided back: "mirror", "blank" or "text"
    back_text: Optional[str] = None  # back="text": None = the label (or file name)
    back_color: str = "#ffffff"      # color of a blank/text back
    back_text_color: str = "#2f5597"
    # mask
    model: str = "auto"
    mask: Optional[str] = None
    crop: Any = None                 # "x0,y0,x1,y1" or [x0, y0, x1, y1], fractions or px
    strength: int = 40               # mask threshold 0-254: higher removes more background
    fill_gaps: Optional[int] = None  # closing radius in px; None = scales with the image
    keep_all: bool = False
    min_area: int = 1000
    margin_fill: str = "color"       # "color" (margin_color) or "image"
    margin_color: str = "#ffffff"
    # picture: color adjustments of what is printed (never of what the model sees)
    greyscale: bool = False
    brightness: int = 0              # -100..100
    contrast: int = 0                # -100..100
    saturation: int = 0              # -100..100
    hue: int = 0                     # -180..180 degrees
    # output
    label: Optional[str] = None      # None = file name, "" = no label
    dpi: int = 300
    simplify_mm: float = 0.15
    no_smooth: bool = False
    cut_color: str = "#000000"
    cut_width_mm: float = 0.3
    cutter: bool = False
    bleed_mm: float = 1.0            # with cutter: background printed beyond the cut line
    label_color: str = "#2f5597"
    label_size_mm: float = 3.4
    copies: int = 1

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FigureSettings":
        d = norm_keys(d)
        unknown = set(d) - FIGURE_OPTIONS
        if unknown:
            raise ValueError(f"unknown option(s) {', '.join(sorted(unknown))}")
        if d.get("width_mm") is not None and "height_mm" not in d:
            d["height_mm"] = None  # a width alone: scale by width, keep the proportions
        for key in ("height_mm", "width_mm"):
            v = d.get(key)
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))
                                  or v <= 0):
                raise ValueError(f"{key} must be a number above 0, not {v!r}")
        if d.get("height_mm", 1) is None and d.get("width_mm") is None:
            raise ValueError("give height_mm, width_mm or both")
        for key, allowed in (("back", geo.BACK_MODES), ("margin_fill", geo.MARGIN_FILLS),
                             ("tab_shape", geo.TAB_SHAPES)):
            if key in d and d[key] not in allowed:
                raise ValueError(f"{key} must be one of {', '.join(allowed)}, not {d[key]!r}")
        for key, (lo, hi) in ADJUST_RANGES.items():
            v = d.get(key)
            if v is not None and (isinstance(v, bool) or not isinstance(v, int)
                                  or not lo <= v <= hi):
                raise ValueError(f"{key} must be a whole number from {lo} to {hi}, not {v!r}")
        for key in ("margin_color", "tab_color", "back_color", "back_text_color", "cut_color",
                    "label_color"):
            if key in d:
                geo.hex_rgb(str(d[key]))  # raises a clear error for a bad color
        return cls(**d)

    def to_dict(self, base: Optional["FigureSettings"] = None) -> Dict[str, Any]:
        """Options that differ from ``base`` (default: the built-in defaults)."""
        ref = asdict(base or FigureSettings())
        d = {k: v for k, v in asdict(self).items() if v != ref[k]}
        if self.width_mm is not None:  # a width alone would mean "scale by width"
            d.setdefault("height_mm", self.height_mm)
        return d

    def params(self) -> geo.Params:
        return geo.Params(
            height_mm=self.height_mm, width_mm=self.width_mm,
            margin_mm=self.margin_mm, smooth_mm=self.smooth_mm,
            tab=not self.no_tab, tab_width_mm=self.tab_width_mm,
            tab_radius_mm=self.tab_radius_mm,
            tab_height_mm=self.tab_height_mm, tab_overlap_mm=self.tab_overlap_mm,
            fold_mm=self.fold_mm, keep_all=self.keep_all, margin_fill=self.margin_fill,
            double_sided=self.double_sided, back=self.back, back_color=self.back_color,
            margin_color=self.margin_color, tab_shape=self.tab_shape,
            tab_color=self.tab_color,
        )

    def adjustments(self) -> Adjustments:
        return Adjustments(brightness=self.brightness, contrast=self.contrast,
                           saturation=self.saturation, hue=self.hue,
                           greyscale=self.greyscale)

    def style(self) -> Style:
        st = Style(cut_color=self.cut_color, cut_width_mm=self.cut_width_mm,
                   label_color=self.label_color, label_size_mm=self.label_size_mm,
                   back_text_color=self.back_text_color)
        if self.cutter:
            for k, v in CUTTER_STYLE.items():
                setattr(st, k, v)
        return st


FIGURE_OPTIONS = {f.name for f in fields(FigureSettings)}


def norm_keys(d: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {str(k).replace("-", "_"): v for k, v in (d or {}).items()}


def build_mini(image: Path, s: FigureSettings, *, use_cache: bool = True,
               debug_dir: Optional[Path] = None,
               log=print, on_stage=None) -> Mini:
    # model "mask" = your own mask image; "auto" also uses a mask image if one is given
    use_mask = s.model == "mask" or (s.model == "auto" and bool(s.mask))
    if s.model == "mask" and not s.mask:
        raise ValueError("model 'mask' needs a mask image file - choose one")
    return make_mini(
        Path(image), s.params(),
        label=s.label, back_text=s.back_text, threshold=s.strength, close_px=s.fill_gaps, min_area=s.min_area,
        crop=s.crop, model="auto" if s.model == "mask" else s.model,
        mask_path=Path(s.mask) if use_mask else None,
        dpi=s.dpi, simplify_mm=s.simplify_mm, smooth_path=not s.no_smooth,
        bleed_mm=s.bleed_mm if s.cutter else 0.0, adjust=s.adjustments(),
        use_cache=use_cache, style=s.style(), debug_dir=debug_dir,
        log=log, on_stage=on_stage,
    )


def safe_name(stem: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_ ." else "_" for ch in stem).strip() or "mini"


# --------------------------------------------------------------------------- projects

@dataclass
class SheetSettings:
    output: Optional[str] = None     # default: <output>/sheet.pdf
    paper: str = "a4"
    copies: int = 1                  # default copies for figures that set none
    preview: bool = False
    title: str = "Paper miniatures"
    margin_mm: float = 12.0
    gap_mm: float = 7.0
    enabled: bool = True


@dataclass
class FigureEntry:
    image: Path                      # absolute (for a link: the downloaded copy)
    settings: FigureSettings = field(default_factory=FigureSettings)
    name: Optional[str] = None       # output file name (default: label or image name)
    source: Optional[str] = None     # the link the image came from; saved instead of the path

    def svg_name(self) -> str:
        return safe_name(self.name or self.settings.label or self.image.stem) + ".svg"

    @property
    def display_name(self) -> str:
        return self.name or self.settings.label or self.image.stem


@dataclass
class Project:
    path: Optional[Path] = None      # the YAML file, if saved
    output: str = "minis"
    sheet: SheetSettings = field(default_factory=SheetSettings)
    figures: List[FigureEntry] = field(default_factory=list)
    debug: bool = False

    @property
    def base(self) -> Path:
        return self.path.parent if self.path else Path.cwd()

    @property
    def output_dir(self) -> Path:
        return self.base / self.output

    @property
    def sheet_path(self) -> Path:
        return self.base / self.sheet.output if self.sheet.output else self.output_dir / "sheet.pdf"


def load_project(path: Path) -> Project:
    import yaml

    path = Path(path).resolve()
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base = path.parent
    sheet_d = norm_keys(cfg.get("sheet"))
    unknown = set(sheet_d) - {f.name for f in fields(SheetSettings)}
    if unknown:
        raise ValueError(f"{path.name}: unknown sheet option(s) {', '.join(sorted(unknown))}")
    sheet = SheetSettings(**sheet_d)
    defaults = norm_keys(cfg.get("defaults"))
    figures = []
    for entry in cfg.get("figures") or []:
        if isinstance(entry, str):
            entry = {"image": entry}
        o = {**defaults, **norm_keys(entry)}
        if "image" not in o:
            raise ValueError(f"{path.name}: every figure needs an 'image'")
        src = o.pop("image")
        source = str(src).strip() if remote.is_url(src) else None
        image = remote.fetch_image(source) if source else (base / remote.local_path(src)).resolve()
        name = o.pop("name", None)
        o.setdefault("copies", sheet.copies)
        if o.get("mask"):
            o["mask"] = str((base / o["mask"]).resolve())
        if str(o.get("model", "")).endswith(".onnx"):
            o["model"] = str((base / o["model"]).resolve())
        try:
            s = FigureSettings.from_dict(o)
        except ValueError as e:
            raise ValueError(f"{path.name}: {image.name}: {e}") from None
        figures.append(FigureEntry(image, s, name, source))
    return Project(path, str(cfg.get("output", "minis")), sheet, figures, bool(cfg.get("debug", False)))


def save_project(p: Project, path: Path) -> Path:
    """Write ``p`` as a batch YAML; paths are stored relative to the file."""
    import os

    import yaml

    path = Path(path).resolve()
    base = path.parent

    def rel(f) -> str:
        try:
            return Path(os.path.relpath(Path(f).resolve(), base)).as_posix()
        except ValueError:  # other drive on Windows
            return Path(f).resolve().as_posix()

    sheet = {k: v for k, v in asdict(p.sheet).items() if v != getattr(SheetSettings(), k)}
    figures = []
    for f in p.figures:
        d: Dict[str, Any] = {"image": f.source or rel(f.image)}
        if f.name:
            d["name"] = f.name
        o = f.settings.to_dict()
        if o.get("mask"):
            o["mask"] = rel(o["mask"])
        if str(o.get("model", "")).endswith(".onnx"):
            o["model"] = rel(o["model"])
        if isinstance(o.get("crop"), tuple):
            o["crop"] = list(o["crop"])
        d.update(o)
        figures.append(d)
    cfg: Dict[str, Any] = {"output": p.output}
    if sheet:
        cfg["sheet"] = sheet
    cfg["figures"] = figures
    path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    p.path = path
    return path
