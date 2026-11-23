from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..pipeline.adjustments import Adjustments
from ..pipeline.mask_options import MaskOptions
from ..pipeline.mini import TAB_SHOWS
from ..pipeline.params import BACK_MODES, MARGIN_FILLS, TAB_SHAPES, Params
from ..pipeline.segmentation.segment import DEFAULT_MODEL, ONNX_MODELS
from ..pipeline.style import Style
from ..pipeline.token_options import (
    TOKEN_FILLS,
    TOKEN_TEXT_STYLES,
    TOKEN_TEXTS,
    TokenOptions,
)
from . import sizes
from .option import Option

_MEDIUM = sizes.BUILTIN.row(sizes.DEFAULT_SIZE)

KINDS = ("mini", "token")  # a standing miniature or a flat round token

_SIZE = "size and shape"
_TOKEN = "token (--kind token)"
_PICTURE = "picture (colors of what is printed; the mask is unaffected)"
_MASK = "mask"
_OUTPUT = "output"

# the built-in models, two lines each: what it is good at, then its licence and size
_MODEL_LINES = "".join(
    f"{name}: {spec['about']}\n"
    f"{'Free for any use' if spec['commercial'] else 'Non-commercial use only'}. "
    f"Downloads {spec['mb']} MB once.\n"
    for name, spec in ONNX_MODELS.items()
)


@dataclass
class FigureSettings:
    """A figure's settings, each field with its option."""

    kind: str = Option(
        label="Kind",
        help="mini: a standing paper miniature; token: a flat round "
        "token, set up with the token options",
        tooltip="Standing mini: a paper figure that stands up, on a tab or a base.\n"
        "Token: a flat round token, the figure in a circle, for the table or a virtual\n"
        "tabletop.",
        group="kind",
        choices=KINDS,
        choice_labels=("Standing mini", "Token"),
    ).field("mini")
    size: str = Option(
        label="Creature size",
        help="creature size: fills in the height and the tabs from the size "
        "table; --height-mm or a tab size given as well wins "
        "and makes it custom",
        tooltip="The D&D creature size: fills in the figure height and the tabs (round "
        "base\n"
        "and stand tab) from the project's size table (☰ menu > Preferences… >\n"
        "Creature sizes).\n"
        "Changing the height or a tab size by hand makes it Custom.",
        group=_SIZE,
        choices=sizes.SIZE_CHOICES,
        choice_labels=tuple(sizes.LABELS[s] for s in sizes.SIZE_CHOICES),
    ).field(sizes.DEFAULT_SIZE)
    height_mm: float | None = Option(
        label="Figure height",
        help="height of the drawn figure, without margin and tab",
        tooltip="Height of the drawn figure on paper, without margin and tab.",
        group=_SIZE,
        low=0,
        above=True,
        widget=(0, 1000),
        unit="mm",
        sized=True,
        kinds=("mini",),
    ).field(_MEDIUM.height_mm)
    width_mm: float | None = Option(
        label="Figure width",
        help="width of the drawn figure; alone it scales by width, with "
        "--height-mm the figure is stretched to both",
        none_means="set by the height",
        tooltip="Width of the drawn figure on paper, without margin.",
        group=_SIZE,
        low=0,
        above=True,
        widget=(0, 1000),
        unit="mm",
        kinds=("mini",),
    ).field(None)
    margin_mm: float = Option(
        label="Margin",
        help="distance between the drawing and the cut line",
        tooltip="Distance between the drawing and the cut line. The margin is filled\n"
        "with a color or the original image (see Margin fill type).",
        group=_SIZE,
        widget=(0, 15),
        unit="mm",
        step=0.1,
    ).field(1.6)
    smooth_mm: float = Option(
        label="Outline smoothing",
        help="outline rounding, Gaussian sigma",
        tooltip="Rounds the outline; higher values give a calmer cut line.",
        group=_SIZE,
        widget=(0, 5),
        unit="mm",
        step=0.1,
    ).field(0.6)
    tab_width_mm: float = Option(
        label="Width",
        help="square tab width",
        tooltip="Width of the square tab.",
        group=_SIZE,
        widget=(2, 200),
        unit="mm",
        sized=True,
        kinds=("mini",),
        decimals=1,
    ).field(_MEDIUM.tab_width_mm)
    tab_radius_mm: float = Option(
        label="Radius",
        help="round tab radius; 12.5 makes a 25 mm base",
        tooltip="Radius of the round tab (a half disc). 12.5 mm makes a 25 mm base.",
        group=_SIZE,
        widget=(1, 100),
        unit="mm",
        sized=True,
        kinds=("mini",),
        step=0.5,
        decimals=1,
    ).field(_MEDIUM.base_mm / 2)
    tab_height_mm: float = Option(
        label="Height",
        help="square tab height below the fold",
        tooltip="How far the square tab reaches below the fold line.",
        group=_SIZE,
        widget=(1, 100),
        unit="mm",
        sized=True,
        kinds=("mini",),
        step=0.5,
        decimals=1,
    ).field(_MEDIUM.tab_height_mm)
    tab_overlap_mm: float = Option(
        label="Overlap into figure",
        help="tab reach above the fold, adds paper beside narrow feet",
        tooltip="How far the tab reaches up past the fold line. It only adds paper "
        "where the figure's bottom is narrower than the tab (feet, a tail), to "
        "strengthen the joint.",
        group=_SIZE,
        widget=(0, 30),
        unit="mm",
        kinds=("mini",),
        step=0.5,
        decimals=1,
    ).field(0.0)
    fold_mm: float = Option(
        label="Fold above lowest point",
        help="fold line above the lowest point of the outline",
        tooltip="Where the tab folds, measured up from the figure's lowest point.",
        group=_SIZE,
        widget=(0, 20),
        unit="mm",
        kinds=("mini",),
        step=0.1,
        decimals=1,
    ).field(0.0)
    no_tab: bool = Option(
        label="Print a tab",
        help="no fold tab",
        tooltip="Print a tab: a fold-over stand tab under the feet.\n"
        "Off for slotted or magnetic bases.",
        group=_SIZE,
        kinds=("mini",),
    ).field(False)
    tab_shape: str = Option(
        label="Shape",
        help="square: slots into a stand; round: a half disc (--tab-radius-mm) "
        "that folds out into a round base",
        tooltip="Square: a tab to slot into a (3D printed) stand.\n"
        "Round: a half disc that folds out into a round base. On a double-sided\n"
        "mini the two halves fold out to opposite sides and form a full circle.",
        group=_SIZE,
        choices=TAB_SHAPES,
        kinds=("mini",),
        choice_labels=("Square (stand)", "Round (base)"),
    ).field("square")
    tab_color: str = Option(
        label="Fill color",
        help="tab color behind the label, independent of the margin; "
        "use --label '' for a plain tab",
        tooltip="Color of the tab (everything below the fold), behind the label.\n"
        "Independent of the margin color; e.g. grass green for a plain tab.",
        group=_SIZE,
        kinds=("mini",),
        color=True,
    ).field("#ffffff")
    double_sided: bool = Option(
        label="Print a back side",
        help="front + back joined at a top fold, tabs at both ends; "
        "--no-double-sided prints the front only",
        tooltip="Print a back side: front and back joined at a fold above the head,\n"
        "glued back to back. Off for the front only.",
        group=_SIZE,
        kinds=("mini",),
    ).field(True)
    back: str = Option(
        label="Shows",
        help="double-sided back: mirrored image, blank, text, the copy "
        "number (large), or text_number (the number above the text)",
        tooltip="mirror: the drawing seen from behind; blank: plain paper; "
        "text: plain paper with text (a name or stats); number: the copy's number,\n"
        "large; text and number: the number above the text.",
        group=_SIZE,
        choices=BACK_MODES,
        kinds=("mini",),
        choice_labels=(
            "Mirrored drawing",
            "Blank",
            "Text",
            "Number",
            "Text and number",
        ),
    ).field("mirror")
    back_text: str | None = Option(
        label="Text",
        help="text on the back with --back text or text_number",
        none_means="the label",
        tooltip="Text for the back (empty = the tab label). It is sized to fit the "
        "body.",
        group=_SIZE,
        kinds=("mini",),
    ).field(None)
    back_color: str = Option(
        label="Color",
        help="color of a back that is not the mirrored image",
        tooltip="Color of a back that is not the mirrored drawing (the back tab keeps "
        "the\n"
        "tab's fill color).",
        group=_SIZE,
        kinds=("mini",),
        color=True,
    ).field("#ffffff")
    back_text_color: str = Option(
        label="Text color",
        help="color of the back text",
        tooltip="Color of the text and the number on the back.",
        group=_SIZE,
        kinds=("mini",),
        color=True,
    ).field("#2f5597")
    model: str = Option(
        label="Model",
        help=f"{', '.join(ONNX_MODELS)}, alpha, mask (with --mask) or a .onnx file; "
        f"'auto' uses --mask if given, else the image's transparency if it has any, "
        f"else {DEFAULT_MODEL}",
        tooltip="How the figure is separated from the background.\n"
        f"auto: The image's transparency if it has any, else {DEFAULT_MODEL}.\n"
        f"{_MODEL_LINES}"
        "alpha: The image's own transparency (no download).\n"
        "mask image file: Your own black-and-white mask (white = figure).\n"
        "You can also type the path of your own .onnx model.",
        group=_MASK,
    ).field("auto")
    mask: str | None = Option(
        label="Mask image file",
        help="your own mask image (white = figure) instead of a model",
        tooltip="Your own mask image: white = figure, black = background, same picture "
        "size.",
        group=_MASK,
    ).field(None)
    crop: Any = Option(  # noqa: RUF009 (a dataclass field)
        label="Area",
        help="x0,y0,x1,y1 region (fractions or px) the model looks at",
        none_means="the whole image",
        tooltip="Background removal only looks inside this box (x0,y0,x1,y1, fractions "
        "or px),\n"
        "which helps a lot with busy backgrounds. Drag a box on the image to set it.",
        group=_MASK,
    ).field(None)
    strength: int = Option(
        label="Strength",
        help="background removal strength 0-254: lower keeps faint lines, "
        "higher removes more background",
        tooltip="How sure the model must be that a pixel belongs to the figure "
        "(0-254).\n"
        "Lower keeps faint pencil lines; higher removes more background.",
        group=_MASK,
        widget=(0, 254),
        slider=254,
    ).field(40)
    fill_gaps: int | None = Option(
        label="Gap filling",
        help="fill gaps and notches in the outline up to this many px; 0 = off",
        none_means="scales with the image, 9 px at 1400 px",
        tooltip="Fills gaps and notches in the outline up to this size (0 = off).\n"
        "Auto scales with the image: 9 px at 1400 px.",
        group=_MASK,
        widget=(0, 1000),
        unit="px",
        auto=True,
        slider=40,
    ).field(None)
    keep_all: bool = Option(
        label="Keep detached parts",
        help="keep detached parts (>= --min-area) and bridge them to the figure",
        tooltip="Keep separate parts (a floating prop) and join them with bridges,\n"
        "instead of keeping only the largest part.",
        group=_MASK,
    ).field(False)
    min_area: int = Option(
        label="Min. part area",
        help="smallest part kept with --keep-all",
        tooltip="With 'keep detached parts': smaller parts than this are dropped as "
        "specks.",
        group=_MASK,
        widget=(0, 10_000_000),
        unit="px",
        step=100,
    ).field(1000)
    margin_fill: str = Option(
        label="Margin fill type",
        help="what shows between drawing and cut line: --margin-color "
        "or the original image",
        tooltip="What fills the margin, the strip between the cut-out drawing and its\n"
        "cut line:\n"
        "Color: one solid color (Margin fill color).\n"
        "Original image: the picture around the figure, as it is in the image.",
        group=_SIZE,
        choices=MARGIN_FILLS,
        choice_labels=("Color", "Original image"),
    ).field("color")
    margin_color: str = Option(
        label="Margin fill color",
        help="color of the margin around the drawing",
        tooltip="The color of the margin between the drawing and the cut line.",
        group=_SIZE,
        color=True,
    ).field("#ffffff")
    greyscale: bool = Option(
        label="Greyscale (black and white)",
        help="print in black and white",
        tooltip="Print the figure in black and white (saves color ink).\n"
        "Color adjustments change only what is printed: background removal\n"
        "always looks at the original picture, so they never run the model again.",
        group=_PICTURE,
    ).field(False)
    brightness: int = Option(
        label="Brightness",
        help="-100 (black) to 100 (white); white paper stays white",
        tooltip="Lighter (towards white) or darker (towards black). White paper stays\n"
        "white when lightening, black lines stay black when darkening.",
        group=_PICTURE,
        low=-100,
        high=100,
        widget=(-100, 100),
        slider=100,
    ).field(0)
    contrast: int = Option(
        label="Contrast",
        help="-100 to 100",
        tooltip="More contrast makes lights lighter and darks darker; less makes it "
        "flatter.",
        group=_PICTURE,
        low=-100,
        high=100,
        widget=(-100, 100),
        slider=100,
    ).field(0)
    saturation: int = Option(
        label="Saturation",
        help="-100 (grey) to 100 (twice as colorful)",
        tooltip="How colorful the picture is: -100 is grey, 100 twice as colorful.",
        group=_PICTURE,
        low=-100,
        high=100,
        widget=(-100, 100),
        slider=100,
    ).field(0)
    hue: int = Option(
        label="Hue",
        help="turn the colors around the color wheel, -180 to 180 degrees",
        tooltip="Turns every color around the color wheel (red -> yellow -> green ...).",
        group=_PICTURE,
        low=-180,
        high=180,
        widget=(-180, 180),
        unit="°",
        slider=180,
    ).field(0)
    label: str | None = Option(
        label="Text",
        help="text on the tab; '' for none",
        none_means="the file name",
        tooltip="Text printed on the tab (empty = the file name). Also the default back "
        "text.",
        group=_OUTPUT,
    ).field(None)
    tab_front: str = Option(
        label="Front tab",
        help="what the front tab shows: the label, the copy number, or "
        "label_number (the number above the label)",
        tooltip="What the front tab shows: the label, the copy's number, or both (the\n"
        "number above the label). Each copy on the sheet gets its own number,\n"
        "1, 2, 3…; this preview shows # where it goes.",
        group=_OUTPUT,
        choices=TAB_SHOWS,
        kinds=("mini",),
        choice_labels=("Label", "Number", "Label and number"),
    ).field("label")
    tab_back: str = Option(
        label="Back tab",
        help="what the back tab of a double-sided mini shows (as --tab-front)",
        tooltip="What the back tab of a double-sided mini shows: the label, the copy's\n"
        "number, or both (the number above the label).",
        group=_OUTPUT,
        choices=TAB_SHOWS,
        kinds=("mini",),
        choice_labels=("Label", "Number", "Label and number"),
    ).field("label")
    dpi: int = Option(
        label="Image resolution",
        help="embedded image resolution",
        tooltip="Resolution of the embedded artwork. 300 dpi suits most printers.",
        group=_OUTPUT,
        widget=(72, 2400),
        unit="dpi",
        step=50,
    ).field(300)
    simplify_mm: float = Option(
        label="Simplify",
        help="cut line simplification",
        tooltip="How far the cut line may deviate to use fewer points.",
        group=_OUTPUT,
        widget=(0.01, 2),
        unit="mm",
        kinds=("mini",),
        step=0.05,
        decimals=3,
    ).field(0.15)
    no_smooth: bool = Option(
        label="Straight segments only (no curves)",
        help="straight-segment cut line, no Béziers",
        tooltip="Cut line made of straight segments instead of smooth curves.",
        group=_OUTPUT,
        kinds=("mini",),
    ).field(False)
    cut_color: str = Option(
        label="Color",
        help="cut line color, for cutting by hand",
        tooltip="Color of the cut line, for cutting by hand. A sheet cut by machine has "
        "no\n"
        "cut lines (see Cut by in the Print sheet step).",
        group=_OUTPUT,
        color=True,
    ).field("#000000")
    cut_width_mm: float = Option(
        label="Width",
        help="cut line width, for cutting by hand",
        tooltip="Width of the printed cut line, for cutting by hand.",
        group=_OUTPUT,
        widget=(0.01, 2),
        unit="mm",
        step=0.05,
    ).field(0.3)
    label_color: str = Option(
        label="Color",
        help="color of the tab label",
        tooltip="Color of the tab label.",
        group=_OUTPUT,
        kinds=("mini",),
        color=True,
    ).field("#2f5597")
    label_size_mm: float = Option(
        label="Size",
        help="largest size of the tab label; long labels shrink to fit the tab",
        tooltip="Largest text size; long labels shrink to fit the tab.",
        group=_OUTPUT,
        widget=(0.5, 20),
        unit="mm",
        kinds=("mini",),
        step=0.1,
        decimals=1,
    ).field(3.4)
    font: str = Option(
        label="Font",
        help="font of all the text: labels, numbers, back text",
        tooltip="The font of all the piece's text: the label, the numbers and the back "
        "text.\n"
        "Times and the fonts that come with papermini work on every computer; a font\n"
        "installed only on this computer prints in Times elsewhere.",
        group=_OUTPUT,
    ).field("Times")
    copies: int = Option(
        label="Copies",
        help="a figure with numbers (--tab-front, --tab-back, --back or "
        "--token-text): write one file per copy, each with its number",
        tooltip="How many of this figure go on the print sheet.",
    ).field(1)
    token_diameter_mm: float = Option(
        label="Diameter",
        help="the token's diameter, ring included",
        tooltip="The token's diameter, ring included. The creature size fills it in\n"
        "(the size's base); changing it by hand makes it Custom.",
        group=_TOKEN,
        low=0,
        above=True,
        widget=(5, 300),
        unit="mm",
        sized=True,
        kinds=("token",),
        step=0.5,
        decimals=1,
    ).field(_MEDIUM.base_mm)
    token_area: Any = Option(  # noqa: RUF009 (a dataclass field)
        label="Area",
        help="x0,y0,x1,y1: the square of the picture that fills the circle, as "
        "fractions of the picture",
        none_means="the whole figure, fitted",
        tooltip="The square of the picture that fills the circle (x0,y0,x1,y1, "
        "fractions).\n"
        "Empty: the whole figure, fitted with room around it. In the view, drag the\n"
        "figure to move it and drag a corner of its box to make it bigger or smaller.\n"
        "Clear fits it again.",
        group=_TOKEN,
        kinds=("token",),
        parse=TokenOptions.parse_area,
    ).field(None)
    token_fill: str = Option(
        label="Background",
        help="behind the figure: --token-fill-color or the original image",
        tooltip="What fills the circle behind the figure:\n"
        "Color: one solid color (Background color).\n"
        "Original image: the picture around the figure, as it is in the image.",
        group=_TOKEN,
        choices=TOKEN_FILLS,
        kinds=("token",),
        choice_labels=("Color", "Original image"),
    ).field("color")
    token_fill_color: str = Option(
        label="Background color",
        help="color behind the figure",
        tooltip="The color behind the figure.",
        group=_TOKEN,
        kinds=("token",),
        color=True,
    ).field("#ffffff")
    token_border_mm: float = Option(
        label="Ring width",
        help="width of the ring; 0 = none",
        tooltip="Width of the ring around the token (0 = no ring). With curved text "
        "the\n"
        "ring is at least as wide as the text needs.",
        group=_TOKEN,
        low=0,
        widget=(0, 30),
        unit="mm",
        kinds=("token",),
        step=0.5,
        decimals=1,
    ).field(2.0)
    token_border_color: str = Option(
        label="Ring color",
        help="color of the ring",
        tooltip="Color of the ring, and of the nameplate and the number badge.",
        group=_TOKEN,
        kinds=("token",),
        color=True,
    ).field("#000000")
    token_outline: bool = Option(
        label="Print an outline",
        help="an outline around the figure, made like a mini's margin "
        "(--margin-mm, --margin-fill, --margin-color)",
        tooltip="Print an outline around the figure on the token, made like a "
        "standing\n"
        "mini's margin.",
        group=_TOKEN,
        kinds=("token",),
    ).field(False)
    token_cut_line: bool = Option(
        label="Print a cut line",
        help="print the cut line around the token; without it, the ring's edge "
        "shows where to cut",
        tooltip="Print the cut line around the token. Off: the ring's edge shows where "
        "to\n"
        "cut. A sheet cut by machine never prints cut lines.",
        group=_TOKEN,
        kinds=("token",),
    ).field(False)
    token_text: str = Option(
        label="Shows",
        help="what the token shows: none, the label, the copy number, or label_number",
        tooltip="What the token shows: the label, the copy's number, or both. Each\n"
        "copy on the sheet gets its own number, 1, 2, 3…; this preview shows # "
        "where\n"
        "it goes.",
        group=_TOKEN,
        choices=TOKEN_TEXTS,
        kinds=("token",),
        choice_labels=("None", "Label", "Number", "Label and number"),
    ).field("none")
    token_text_style: str = Option(
        label="Style",
        help="nameplate: the label on a band across the bottom, the number on a "
        "badge; curved: along the ring, which is then at least as "
        "wide as the text needs",
        tooltip="Nameplate and badge: the label on a band across the bottom, the "
        "number\n"
        "in a round badge on the ring.\n"
        "Curved along the ring: the label along the bottom of the ring, the\n"
        "number at its top. The ring is then at least as wide as the text needs.",
        group=_TOKEN,
        choices=TOKEN_TEXT_STYLES,
        kinds=("token",),
        choice_labels=("Nameplate and badge", "Curved along the ring"),
    ).field("nameplate")
    token_text_mm: float = Option(
        label="Size",
        help="size of the token's text: the nameplate is a little taller, and "
        "curved text needs a ring 1.4 times as wide",
        tooltip="Size of the token's text. It decides how much of the token the text\n"
        "covers: the nameplate is a little taller than the text, and curved text\n"
        "needs a ring about 1.4 times as wide. A label too long for the nameplate\n"
        "shrinks to fit.",
        group=_TOKEN,
        low=0,
        above=True,
        widget=(0.5, 20),
        unit="mm",
        kinds=("token",),
        step=0.1,
        decimals=1,
    ).field(2.5)
    token_text_color: str = Option(
        label="Color",
        help="color of the token's text",
        tooltip="Color of the token's text, on the ring, the nameplate and the badge.",
        group=_TOKEN,
        kinds=("token",),
        color=True,
    ).field("#ffffff")

    @classmethod
    def options(cls) -> dict[str, Option]:
        """Return each field's option, by field name."""
        return _OPTIONS

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FigureSettings:
        d = Option.norm_keys(d)
        unknown = set(d) - FIGURE_OPTIONS
        if unknown:
            raise ValueError(f"unknown option(s) {', '.join(sorted(unknown))}")
        d = {key: _OPTIONS[key].check(value) for key, value in d.items()}
        if d.get("width_mm") is not None and "height_mm" not in d:
            d["height_mm"] = None  # a width alone: scale by width, keep the proportions
        if d.get("height_mm", 1) is None and d.get("width_mm") is None:
            raise ValueError("give height_mm, width_mm or both")
        if "font" in d and (not isinstance(d["font"], str) or not d["font"].strip()):
            raise ValueError(f"font must be the name of a font, not {d['font']!r}")
        return cls(**d)

    def to_dict(
        self, base: FigureSettings | None = None, with_size: bool = True
    ) -> dict[str, Any]:
        """Options that differ from ``base`` (default: the built-in defaults) and, with
        ``with_size`` (as a project saves them), always the size with the values it
        fills in."""
        ref = asdict(base or FigureSettings())
        size_keys = SIZE_KEYS + (TOKEN_SIZE_KEYS if self.kind == "token" else ())
        d = {
            k: v
            for k, v in asdict(self).items()
            if v != ref[k] or (with_size and k in size_keys)
        }
        if self.kind != "token" and self.size != sizes.CUSTOM:
            for k in TOKEN_SIZE_KEYS:  # (a mini's: what its size fills in)
                d.pop(k, None)
        if self.width_mm is not None:  # a width alone would mean "scale by width"
            d.setdefault("height_mm", self.height_mm)
        if isinstance(d.get("token_area"), tuple):
            d["token_area"] = list(d["token_area"])
        return d

    def params(self) -> Params:
        return Params(
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

    def mask_options(self) -> MaskOptions:
        """Return the background-removal options. Model "mask" uses the mask image
        file, and model "auto" uses it too when one is given."""
        if self.model == "mask" and not self.mask:
            raise ValueError("model 'mask' needs a mask image file - choose one")
        use_mask = self.mask and self.model in ("mask", "auto")
        return MaskOptions(
            model="auto" if self.model == "mask" else self.model,
            mask_path=Path(self.mask) if use_mask else None,
            crop=self.crop,
            threshold=self.strength,
            close_px=self.fill_gaps,
            keep_all=self.keep_all,
            min_area=self.min_area,
        )

    def mask_inputs(self) -> tuple:
        """Return the settings the background removal depends on: the model, the mask
        image file and the crop. A change to any other setting never runs the model
        again."""
        return (self.model, self.mask, self.crop)

    def adjustments(self) -> Adjustments:
        return Adjustments(
            brightness=self.brightness,
            contrast=self.contrast,
            saturation=self.saturation,
            hue=self.hue,
            greyscale=self.greyscale,
        )

    def token_options(self) -> TokenOptions:
        """The token's options (kind "token"); the outline uses the margin."""
        return TokenOptions(
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


_OPTIONS = Option.of(FigureSettings)
FIGURE_OPTIONS = set(_OPTIONS)

# what a figure's size fills in; saved projects always write these, so a project says
# both the size and its values (a token also the values only a token has: its diameter)
SIZE_KEYS = ("size",) + tuple(
    k for k, o in _OPTIONS.items() if o.sized and "mini" in (o.kinds or KINDS)
)
TOKEN_SIZE_KEYS = tuple(
    k for k, o in _OPTIONS.items() if o.sized and "mini" not in (o.kinds or KINDS)
)
