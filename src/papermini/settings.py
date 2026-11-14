"""Per-figure settings and projects, shared by the CLI, batch YAML and the GUI.

A project file *is* a batch config (saved projects also record the papermini that
saved them and the project format)::

    papermini: 1.0.0
    format: 1
    output: minis
    sheet: {output: minis/sheet.pdf, paper: a4, copies: 1}
    defaults: {height_mm: 42}
    figures:
      - image: dragon.png
        label: Red dragon
      - image: https://example.com/goblin.webp   # a link: downloaded once, then cached
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import geometry as geo
from . import remote, sizes
from .adjust import RANGES as ADJUST_RANGES
from .adjust import Adjustments
from .mini import TAB_SHOWS, Mini, Style, make_mini
from .sheet import (CUSTOM_PAPER_MM, CUT_MODES, MARKS, MATS, ORIENTATIONS, PAPER_CHOICES,
                    Paper, mat_warning, paper_text)

# Saved projects carry this format and the papermini version that saved them. The format
# changes only when a project from an older papermini could no longer be read as it is.
_PROJECT_FORMAT = 1


_MEDIUM = sizes.BUILTIN.row(sizes.DEFAULT_SIZE)
# what a figure's size fills in; saved projects always write these, so a project says
# both the size and its values
SIZE_KEYS = ("size", "height_mm", "tab_radius_mm", "tab_width_mm", "tab_height_mm")


@dataclass
class FigureSettings:
    # size and shape: a creature size fills in the height and the tabs (see sizes.py);
    # height or width keeps the proportions, both stretch the figure
    size: str = sizes.DEFAULT_SIZE   # tiny ... gargantuan, or custom
    height_mm: Optional[float] = _MEDIUM.height_mm
    width_mm: Optional[float] = None
    margin_mm: float = 1.6
    smooth_mm: float = 0.6
    tab_width_mm: float = _MEDIUM.tab_width_mm    # square tab (a stand)
    tab_radius_mm: float = _MEDIUM.base_mm / 2    # round tab (folds out to a base)
    tab_height_mm: float = _MEDIUM.tab_height_mm
    tab_overlap_mm: float = 0.0
    fold_mm: float = 0.0
    no_tab: bool = False
    tab_shape: str = "square"        # "square" (for a stand) or "round" (folds out to a base)
    tab_color: str = "#ffffff"       # tab background, independent of the margin color
    double_sided: bool = True        # front and back, joined at a fold above the head
    back: str = "mirror"             # double-sided back: "mirror", "blank", "text",
    #                                  "number" (large) or "text_number" (number above text)
    back_text: Optional[str] = None  # back with text: None = the label (or file name)
    back_color: str = "#ffffff"      # color of a back that is not the mirrored drawing
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
    tab_front: str = "label"         # what the front tab shows: "label", "number" or
    tab_back: str = "label"          # "label_number" (the copy number above the label)
    dpi: int = 300
    simplify_mm: float = 0.15
    no_smooth: bool = False
    cut_color: str = "#000000"       # the cut line, for cutting by hand
    cut_width_mm: float = 0.3
    label_color: str = "#2f5597"
    label_size_mm: float = 3.4
    font: str = "Times"              # all text: labels, numbers, back text (see fonts.py)
    copies: int = 1

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FigureSettings":
        d = norm_keys(d)
        unknown = set(d) - FIGURE_OPTIONS
        if unknown:
            raise ValueError(f"unknown option(s) {', '.join(sorted(unknown))}")
        if "size" in d and d["size"] not in sizes.SIZE_CHOICES:
            raise ValueError(f"size must be one of {', '.join(sizes.SIZE_CHOICES)}, "
                             f"not {d['size']!r}")
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
                             ("tab_shape", geo.TAB_SHAPES), ("tab_front", TAB_SHOWS),
                             ("tab_back", TAB_SHOWS)):
            if key in d and d[key] not in allowed:
                raise ValueError(f"{key} must be one of {', '.join(allowed)}, not {d[key]!r}")
        for key, (lo, hi) in ADJUST_RANGES.items():
            v = d.get(key)
            if v is not None and (isinstance(v, bool) or not isinstance(v, int)
                                  or not lo <= v <= hi):
                raise ValueError(f"{key} must be a whole number from {lo} to {hi}, not {v!r}")
        if "font" in d and (not isinstance(d["font"], str) or not d["font"].strip()):
            raise ValueError(f"font must be the name of a font, not {d['font']!r}")
        for key in ("margin_color", "tab_color", "back_color", "back_text_color", "cut_color",
                    "label_color"):
            if key in d:
                geo.hex_rgb(str(d[key]))  # raises a clear error for a bad color
        return cls(**d)

    def to_dict(self, base: Optional["FigureSettings"] = None,
                with_size: bool = True) -> Dict[str, Any]:
        """Options that differ from ``base`` (default: the built-in defaults) and, with
        ``with_size`` (as a project saves them), always the size with the values it
        fills in."""
        ref = asdict(base or FigureSettings())
        d = {k: v for k, v in asdict(self).items()
             if v != ref[k] or (with_size and k in SIZE_KEYS)}
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
        return Style(cut_color=self.cut_color, cut_width_mm=self.cut_width_mm,
                     label_color=self.label_color, label_size_mm=self.label_size_mm,
                     back_text_color=self.back_text_color, font=self.font)


FIGURE_OPTIONS = {f.name for f in fields(FigureSettings)}


def settings_with_size(options: Dict[str, Any],
                       table: sizes.SizeTable = sizes.BUILTIN) -> FigureSettings:
    """Figure settings from ``options`` (a project's figure, or command-line flags): the
    figure's size fills in the values not given, from ``table``; a given value that
    differs from the size's makes the figure custom."""
    o = norm_keys(options)
    size = o.get("size", sizes.DEFAULT_SIZE)
    if size in sizes.SIZES:
        fills = table.row(size).values()
        if o.get("width_mm") is not None and "height_mm" not in o:
            del fills["height_mm"]  # (a width alone scales by width: no height to fill in)
        for k, v in fills.items():
            o.setdefault(k, v)
    s = FigureSettings.from_dict(o)
    return s if sizes.matches(s, table) else replace(s, size=sizes.CUSTOM)


def norm_keys(d: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {str(k).replace("-", "_"): v for k, v in (d or {}).items()}


def build_mini(image: Path, s: FigureSettings, *, bleed_mm: float = 0.0, use_cache: bool = True,
               debug_dir: Optional[Path] = None,
               log=print, on_stage=None) -> Mini:
    """Build one figure. ``bleed_mm``: print the edge colors this far beyond the cut
    line (a sheet cut by machine, see ``SheetSettings.figure_bleed``)."""
    # model "mask" = your own mask image; "auto" also uses a mask image if one is given
    use_mask = s.model == "mask" or (s.model == "auto" and bool(s.mask))
    if s.model == "mask" and not s.mask:
        raise ValueError("model 'mask' needs a mask image file - choose one")
    return make_mini(
        Path(image), s.params(),
        label=s.label, back_text=s.back_text, tab_front=s.tab_front, tab_back=s.tab_back,
        threshold=s.strength, close_px=s.fill_gaps, min_area=s.min_area,
        crop=s.crop, model="auto" if s.model == "mask" else s.model,
        mask_path=Path(s.mask) if use_mask else None,
        dpi=s.dpi, simplify_mm=s.simplify_mm, smooth_path=not s.no_smooth,
        bleed_mm=bleed_mm, adjust=s.adjustments(),
        use_cache=use_cache, style=s.style(), debug_dir=debug_dir,
        log=log, on_stage=on_stage,
    )


def safe_name(stem: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_ ." else "_" for ch in stem).strip() or "mini"


# --------------------------------------------------------------------------- projects

@dataclass
class SheetSettings:
    output: Optional[str] = None     # default: <output>/sheet.pdf
    paper: str = "a4"                # a name in sheet.PAPER, or "custom"
    paper_width_mm: Optional[float] = None   # paper "custom": its width and height
    paper_height_mm: Optional[float] = None
    orientation: str = "portrait"    # "portrait" or "landscape" (named paper only)
    copies: int = 1                  # default copies for figures that set none
    preview: bool = False
    title: str = "Paper miniatures"
    margin_mm: float = 12.0
    gap_mm: float = 7.0
    enabled: bool = True
    cut: str = "hand"                # "hand": cut lines on the sheet; "machine": see below
    bleed_mm: float = 1.0            # cut by machine: edge colors printed beyond the cut line
    marks: str = "corners"           # cut by machine: "corners" or "silhouette" alignment marks
    cut_folds: bool = False          # cut by machine: fold lines in the cut file too
    mat: Optional[str] = None        # cut by machine: the cutting mat ("12x12" or "12x24"),
                                     # only to warn when the paper is bigger; None: any size

    @property
    def machine(self) -> bool:
        return self.cut == "machine"

    @property
    def page(self) -> Paper:
        """The paper for ``sheet.pack``: its name, or a custom (width, height) mm."""
        if self.paper == "custom":
            return (self.paper_width_mm, self.paper_height_mm)
        return self.paper

    def paper_text(self) -> str:
        """The paper as messages name it, e.g. "A3 landscape"."""
        return paper_text(self.page, self.orientation)

    def mat_warning(self) -> str:
        """Cut by machine on a mat: why the paper does not fit it ("" when it does)."""
        return mat_warning(self.page, self.orientation, self.mat) if self.machine else ""

    @property
    def figure_bleed(self) -> float:
        """The bleed every figure is built with: only when cut by machine."""
        return self.bleed_mm if self.machine else 0.0

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SheetSettings":
        d = norm_keys(d)
        unknown = set(d) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown sheet option(s) {', '.join(sorted(unknown))}")
        if "paper" not in d and ("paper_width_mm" in d or "paper_height_mm" in d):
            d["paper"] = "custom"  # (a width and height of its own: a custom size)
        for key, allowed in (("cut", CUT_MODES), ("marks", MARKS), ("paper", PAPER_CHOICES),
                             ("orientation", ORIENTATIONS), ("mat", tuple(MATS) + (None,))):
            if key in d and d[key] not in allowed:
                shown = ", ".join(str(a) for a in allowed if a is not None)
                raise ValueError(f"sheet {key} must be one of {shown}, not {d[key]!r}")
        lo, hi = CUSTOM_PAPER_MM
        for key in ("paper_width_mm", "paper_height_mm"):
            v = d.get(key)
            if d.get("paper") == "custom" and not (isinstance(v, (int, float))
                                                   and not isinstance(v, bool)
                                                   and lo <= v <= hi):
                raise ValueError(f"sheet {key} must be from {lo:g} to {hi:g} (mm) for a "
                                 f"custom paper, not {v!r}")
            if d.get("paper") != "custom" and v is not None:
                raise ValueError(f"sheet {key} is only for paper: custom")
        if "bleed_mm" in d and not (isinstance(d["bleed_mm"], (int, float))
                                    and 0 <= d["bleed_mm"] <= 5):
            raise ValueError(f"sheet bleed_mm must be from 0 to 5, not {d['bleed_mm']!r}")
        return cls(**d)


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
    sizes: sizes.SizeTable = sizes.BUILTIN  # the project's creature size table

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
    newer = _check_format(cfg, path.name)
    base = path.parent
    try:
        sheet = SheetSettings.from_dict(cfg.get("sheet") or {})
        table = sizes.SizeTable.from_dict(cfg.get("sizes"))
    except ValueError as e:
        raise ValueError(f"{path.name}: {e}{newer}") from None
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
            s = settings_with_size(o, table)
        except ValueError as e:
            raise ValueError(f"{path.name}: {image.name}: {e}{newer}") from None
        figures.append(FigureEntry(image, s, name, source))
    return Project(path, str(cfg.get("output", "minis")), sheet, figures,
                   bool(cfg.get("debug", False)), table)


def _release(version: Any) -> Optional[Tuple[int, int, int]]:
    """The leading MAJOR.MINOR.PATCH of a papermini version (a development version such
    as 1.2.1.dev3+g1a2b3c4 counts as 1.2.1), or None when it has none."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", str(version).strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _check_format(cfg: Dict[str, Any], name: str) -> str:
    """Refuse a project in a format this papermini cannot read, naming the papermini that
    saved it. Returns the note for errors in a project saved by a newer papermini of the
    same format (which may use options this one does not know), or ""."""
    from . import __version__

    saved = cfg.get("papermini")  # the papermini that saved the project (none when hand-written)
    made_by = f"was made by papermini {saved}" if saved else "uses a newer project format"
    fmt = cfg.get("format", 1)
    if isinstance(fmt, bool) or not isinstance(fmt, int) or fmt < 1:
        raise ValueError(f"{name}: the project format must be a whole number from 1, not {fmt!r}")
    if fmt > _PROJECT_FORMAT:
        raise ValueError(f"{name} {made_by} (project format {fmt}), and papermini {__version__} opens project format {_PROJECT_FORMAT}. Update papermini to open it.")
    made, this = _release(saved or ""), _release(__version__)
    if made and this and made > this:
        return f". The project was made by papermini {saved}, which is newer than papermini {__version__}. Update papermini to open it."
    return ""


class _Flow(dict):
    """A mapping written on one line in a saved project."""


def _dumper():
    import yaml

    class Dumper(yaml.SafeDumper):
        pass

    Dumper.add_representer(_Flow, lambda d, data: d.represent_mapping(
        "tag:yaml.org,2002:map", data, flow_style=True))
    return Dumper


_Dumper = None


def save_project(p: Project, path: Path) -> Path:
    """Write ``p`` as a batch YAML, with the papermini version that saved it and the
    project format. Paths are stored relative to the file."""
    import os

    import yaml

    global _Dumper
    _Dumper = _Dumper or _dumper()
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
    from . import __version__

    cfg: Dict[str, Any] = {"papermini": __version__, "format": _PROJECT_FORMAT,
                           "output": p.output}
    if sheet:
        cfg["sheet"] = sheet
    cfg["sizes"] = {k: _Flow(v) if isinstance(v, dict) else v  # (a size per line)
                    for k, v in p.sizes.to_dict().items()}
    cfg["figures"] = figures
    path.write_text(yaml.dump(cfg, Dumper=_Dumper, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")
    p.path = path
    return path
