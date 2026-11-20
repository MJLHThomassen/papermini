"""The fields of the figure panel: its groups, steps, choices, visibility rules and tooltips."""

from __future__ import annotations

from ...project import sizes
from ...project.figure_settings import FigureSettings

# value -> what the (editable) model box shows, where they differ
MODEL_NAMES = {"mask": "mask image file"}
MODEL_VALUES = {v: k for k, v in MODEL_NAMES.items()}
MODELS = ["auto", "rmbg-1.4", "birefnet", "birefnet-lite", "alpha", "mask"]

# The steps of the workflow, one view each: the settings panel shows the active
# step's groups. (step, group title, fields); fields are (field, label, kind, extra) -
# kind: f=float, i=int, b=bool, c=choice, s=str, col=color, size=height and width
# with a link toggle, slider=int slider (lo, hi, slider_hi, suffix, auto checkbox),
# switch=a checkbox in the group's header that turns the whole group on or off (extra
# "invert": the setting is the opposite, e.g. no_tab), nolabel=the Label group's
# switch (off = label ""),
# reset=a button that puts the listed fields back to their defaults (not a setting)
STEPS = ["Source", "Miniature", "Print sheet"]
SOURCE, MINIATURE, PRINT = range(3)

TAB_CHOICES = [
    ("label", "Label"),
    ("number", "Number"),
    ("label_number", "Label and number"),
]

TOKEN_TEXT_CHOICES = [
    ("label", "Label"),
    ("number", "Number"),
    ("label_number", "Label and number"),
]  # (off: the group's switch)

STEP_HINTS = [
    "Crop the picture first: background removal only looks inside the box.",
    (
        "How big the figure prints, and the paper piece around it: back side, margin, cut "
        "line and stand tab."
    ),
    "The paper, the layout and how the pieces are cut.",
]

TOKEN_STEP_HINT = (
    "How big the token prints, how the figure sits in it, and its ring and text."
)

SECTIONS = [
    (
        SOURCE,
        "Crop",
        [
            ("crop", "Area", "crop", None),
        ],
    ),
    (
        SOURCE,
        "Background removal",
        [
            ("model", "Model", "model", None),
            ("mask", "Mask image file", "file", None),
            ("strength", "Strength", "slider", (0, 254, 254, "", False)),
            ("fill_gaps", "Gap filling", "slider", (0, 1000, 40, " px", True)),
            ("keep_all", "Keep detached parts", "b", None),
            ("min_area", "Min. part area", "i", (0, 10_000_000, 100, " px")),
        ],
    ),
    (
        SOURCE,
        "Image adjustments",
        [  # what is printed; the model never sees them
            ("greyscale", "Greyscale (black and white)", "b", None),
            ("brightness", "Brightness", "slider", (-100, 100, 100, "", False)),
            ("contrast", "Contrast", "slider", (-100, 100, 100, "", False)),
            ("saturation", "Saturation", "slider", (-100, 100, 100, "", False)),
            ("hue", "Hue", "slider", (-180, 180, 180, "\u00b0", False)),
            (
                "_reset_adjust",
                "Reset adjustments",
                "reset",
                ("greyscale", "brightness", "contrast", "saturation", "hue"),
            ),
        ],
    ),
    (
        MINIATURE,
        "Size",
        [  # first (after the Kind): how big the figure prints
            (
                "size",
                "Creature size",
                "c",
                [(s, sizes.label(s)) for s in sizes.SIZE_CHOICES],
            ),
            ("dimensions", "Size", "size", None),
            ("token_diameter_mm", "Diameter", "f", (5, 300, 0.5, 1, " mm")),
            ("dpi", "Image resolution", "i", (72, 2400, 50, " dpi")),
        ],
    ),
    (
        MINIATURE,
        "Token",
        [  # a token: the figure in a circle, inside a ring
            ("token_area", "Area", "tokenarea", None),
            (
                "token_fill",
                "Background",
                "c",
                [("color", "Color"), ("image", "Original image")],
            ),
            ("token_fill_color", "Background color", "col", None),
            ("token_border_mm", "Ring width", "f", (0, 30, 0.5, 1, " mm")),
            ("token_border_color", "Ring color", "col", None),
        ],
    ),
    (
        MINIATURE,
        "Token text",
        [
            ("token_text_on", "Print text", "tokentext", None),
            ("token_text", "Shows", "c", TOKEN_TEXT_CHOICES),
            (
                "token_text_style",
                "Style",
                "c",
                [
                    ("nameplate", "Nameplate and badge"),
                    ("curved", "Curved along the ring"),
                ],
            ),
            ("token_text_mm", "Size", "f", (0.5, 20, 0.1, 1, " mm")),
            ("token_label", "Label", "tlabel", None),
            ("token_text_color", "Color", "col", None),
        ],
    ),
    (
        MINIATURE,
        "Back side",
        [  # it decides what the rest of the piece is
            ("double_sided", "Print a back side", "switch", None),
            (
                "back",
                "Shows",
                "c",
                [
                    ("mirror", "Mirrored drawing"),
                    ("blank", "Blank"),
                    ("text", "Text"),
                    ("number", "Number"),
                    ("text_number", "Text and number"),
                ],
            ),
            ("back_color", "Color", "col", None),
            ("back_text", "Text", "s", None),
            ("back_text_color", "Text color", "col", None),
        ],
    ),
    (
        MINIATURE,
        "Image outline",
        [  # around the drawing: a mini's margin, a token's outline
            (
                "token_outline",
                "Print an outline",
                "switch",
                None,
            ),  # (a token's; a mini has one)
            ("margin_mm", "Margin", "f", (0, 15, 0.1, 2, " mm")),
            (
                "margin_fill",
                "Margin fill type",
                "c",
                [("color", "Color"), ("image", "Original image")],
            ),
            ("margin_color", "Margin fill color", "col", None),
            ("smooth_mm", "Outline smoothing", "f", (0, 5, 0.1, 2, " mm")),
        ],
    ),
    (
        MINIATURE,
        "Cut line",
        [
            (
                "token_cut_line",
                "Print a cut line",
                "switch",
                None,
            ),  # (a token's; a mini has one)
            ("no_smooth", "Straight segments only (no curves)", "b", None),
            ("simplify_mm", "Simplify", "f", (0.01, 2, 0.05, 3, " mm")),
            ("cut_color", "Color", "col", None),
            ("cut_width_mm", "Width", "f", (0.01, 2, 0.05, 2, " mm")),
        ],
    ),
    (
        MINIATURE,
        "Tab",
        [
            ("no_tab", "Print a tab", "switch", "invert"),
            (
                "tab_shape",
                "Shape",
                "c",
                [("square", "Square (stand)"), ("round", "Round (base)")],
            ),
            ("tab_width_mm", "Width", "f", (2, 200, 1, 1, " mm")),
            ("tab_radius_mm", "Radius", "f", (1, 100, 0.5, 1, " mm")),
            ("tab_height_mm", "Height", "f", (1, 100, 0.5, 1, " mm")),
            ("tab_overlap_mm", "Overlap into figure", "f", (0, 30, 0.5, 1, " mm")),
            ("fold_mm", "Fold above lowest point", "f", (0, 20, 0.1, 1, " mm")),
            ("tab_color", "Fill color", "col", None),
        ],
    ),
    (
        MINIATURE,
        "Label",
        [  # on the tab: a sub-group of Tab (SUBSECTIONS)
            ("no_label", "Print a label", "nolabel", None),
            ("label", "Text", "label", None),
            ("label_size_mm", "Size", "f", (0.5, 20, 0.1, 1, " mm")),
            ("label_color", "Color", "col", None),
        ],
    ),
    (
        MINIATURE,
        "Text",
        [  # one font for all of the piece's text
            ("font", "Font", "font", None),
        ],
    ),
    (
        MINIATURE,
        "Number",
        [  # the copy numbers on the tabs: a sub-group of Tab
            ("tab_front", "Front tab", "c", TAB_CHOICES),
            ("tab_back", "Back tab", "c", TAB_CHOICES),
        ],
    ),
]

# groups shown inside another group (indented, at its end): sub-group -> group
SUBSECTIONS = {"Label": "Tab", "Number": "Tab"}

# the settings each field sets ("dimensions" sets two, "no_label" is the label "", the
# Token text switch off is token_text "none"), and the creature size also fills in the
# height, the tabs and a token's diameter
FIELD_SETTINGS = {
    "dimensions": ("height_mm", "width_mm"),
    "no_label": ("label",),
    "size": ("size",)
    + tuple(k for k, o in FigureSettings.options().items() if o.sized),
    "token_label": ("label",),
    "token_text_on": ("token_text",),
}

# a token's field that sets the same setting as a mini's (shown for the kind in use)
TWINS = {"token_label": "label"}

# the switches of groups a token can turn off but a mini always has (hidden for a mini)
TOKEN_SWITCHES = ("token_outline", "token_cut_line")

# groups that only one kind of figure has (the others belong to both)
KIND_SECTIONS = {
    "Back side": "mini",
    "Tab": "mini",
    "Token": "token",
    "Token text": "token",
}

# kept per figure by "Apply to all"
PER_IMAGE = {"label", "crop", "mask", "copies", "token_area"}


def step_settings(step: int) -> set:
    """The FigureSettings fields edited in ``step`` (the Kind is at the top of Miniature)."""
    return {
        k
        for st, _, items in SECTIONS
        if st == step
        for name, _, kind, _ in items
        if kind != "reset"
        for k in FIELD_SETTINGS.get(name, (name,))
    } | ({"kind"} if step == MINIATURE else set())


# each setting's tooltip comes from its option; the others belong to fields that are
# not a setting of their own
TIPS = {
    **{name: o.tooltip for name, o in FigureSettings.options().items()},
    "token_text_on": "Print text on the token: its label, its copy number or both.",
    "token_label": "The label on the token (empty = the file name).",
    "size_link": "Linked: the figure keeps its proportions, so setting the height sets the\n"
    "width and the other way round.\n"
    "Unlinked: set height and width separately; the figure is stretched.",
    "no_label": "Print a label: text on the tab.\n"
    "Off for a plain tab in its fill color.",
    "_reset_adjust": "Back to the original colors.\n"
    "(One slider: double-click it to put it back to 0.)",
}
