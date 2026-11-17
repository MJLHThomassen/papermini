"""The fields of the figure panel: its groups, steps, choices, visibility rules and tooltips."""

from __future__ import annotations

from ... import sizes

# value -> what the (editable) model box shows, where they differ
MODEL_NAMES = {"mask": "mask image file"}


MODEL_VALUES = {v: k for k, v in MODEL_NAMES.items()}


MODELS = ["auto", "rmbg-1.4", "birefnet", "birefnet-lite", "alpha", "mask"]


# The steps of the workflow, one view each: the settings panel shows the active
# step's groups. (step, group title, fields); fields are (field, label, kind, extra) -
# kind: f=float, i=int, b=bool, c=choice, s=str, col=color, size=height and width
# with a link toggle, slider=int slider (lo, hi, slider_hi, suffix, auto checkbox),
# heading=sub-heading inside a group (not a setting), switch=a checkbox in the group's
# header that turns the whole group on or off (extra "invert": the setting is the
# opposite, e.g. no_tab), nolabel=the Label group's switch (off = label ""),
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
    "size": ("size",) + sizes.FILLS,
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
        if kind not in ("heading", "reset")
        for k in FIELD_SETTINGS.get(name, (name,))
    } | ({"kind"} if step == MINIATURE else set())


TIPS = {
    "kind": "Standing mini: a paper figure that stands up, on a tab or a base.\n"
    "Token: a flat round token, the figure in a circle, for the table or a virtual\n"
    "tabletop.",
    "token_diameter_mm": "The token's diameter, ring included. The creature size fills it in\n"
    "(the size's base); changing it by hand makes it Custom.",
    "token_area": "The square of the picture that fills the circle (x0,y0,x1,y1, fractions).\n"
    "Empty: the whole figure, fitted with room around it. In the view, drag the\n"
    "figure to move it and drag a corner of its box to make it bigger or smaller.\n"
    "Clear fits it again.",
    "token_fill": "What fills the circle behind the figure:\n"
    "Color: one solid color (Background color).\n"
    "Original image: the picture around the figure, as it is in the image.",
    "token_fill_color": "The color behind the figure.",
    "token_border_mm": "Width of the ring around the token (0 = no ring). With curved text the\n"
    "ring is at least as wide as the text needs.",
    "token_border_color": "Color of the ring, and of the nameplate and the number badge.",
    "token_outline": "Print an outline around the figure on the token, made like a standing\n"
    "mini's margin.",
    "token_text_on": "Print text on the token: its label, its copy number or both.",
    "token_cut_line": "Print the cut line around the token. Off: the ring's edge shows where to\n"
    "cut. A sheet cut by machine never prints cut lines.",
    "token_text": "What the token shows: the label, the copy's number, or both. Each\n"
    "copy on the sheet gets its own number, 1, 2, 3…; this preview shows # where\n"
    "it goes.",
    "token_text_style": "Nameplate and badge: the label on a band across the bottom, the number\n"
    "in a round badge on the ring.\n"
    "Curved along the ring: the label along the bottom of the ring, the\n"
    "number at its top. The ring is then at least as wide as the text needs.",
    "token_text_mm": "Size of the token's text. It decides how much of the token the text\n"
    "covers: the nameplate is a little taller than the text, and curved text\n"
    "needs a ring about 1.4 times as wide. A label too long for the nameplate\n"
    "shrinks to fit.",
    "token_label": "The label on the token (empty = the file name).",
    "token_text_color": "Color of the token's text, on the ring, the nameplate and the badge.",
    "size": "The D&D creature size: fills in the figure height and the tabs (round base\n"
    "and stand tab) from the project's size table (☰ menu > Preferences… >\n"
    "Creature sizes).\n"
    "Changing the height or a tab size by hand makes it Custom.",
    "height_mm": "Height of the drawn figure on paper, without margin and tab.",
    "width_mm": "Width of the drawn figure on paper, without margin.",
    "size_link": "Linked: the figure keeps its proportions, so setting the height sets the\n"
    "width and the other way round.\n"
    "Unlinked: set height and width separately; the figure is stretched.",
    "copies": "How many of this figure go on the print sheet.",
    "dpi": "Resolution of the embedded artwork. 300 dpi suits most printers.",
    "model": "How the figure is separated from the background.\n"
    "auto: the PNG's transparency if it has any, else rmbg-1.4.\n"
    "rmbg-1.4: BRIA's background removal model, non-commercial use only\n"
    "(downloads 176 MB once).\n"
    "birefnet: sharper edges and fine detail, slower, free for any use\n"
    "(downloads 930 MB once).\n"
    "birefnet-lite: a smaller, faster BiRefNet (downloads 215 MB once).\n"
    "alpha: the PNG's own transparency (no file needed).\n"
    "mask image file: your own black-and-white mask (white = figure).\n"
    "You can also type the path of your own .onnx model.",
    "mask": "Your own mask image: white = figure, black = background, same picture size.",
    "crop": "Background removal only looks inside this box (x0,y0,x1,y1, fractions or px),\n"
    "which helps a lot with busy backgrounds. Drag a box on the image to set it.",
    "strength": "How sure the model must be that a pixel belongs to the figure (0-254).\n"
    "Lower keeps faint pencil lines; higher removes more background.",
    "fill_gaps": "Fills gaps and notches in the outline up to this size (0 = off).\n"
    "Auto scales with the image: 9 px at 1400 px.",
    "keep_all": "Keep separate parts (a floating prop) and join them with bridges,\n"
    "instead of keeping only the largest part.",
    "min_area": "With 'keep detached parts': smaller parts than this are dropped as specks.",
    "margin_mm": "Distance between the drawing and the cut line. The margin is filled\n"
    "with a color or the original image (see Margin fill type).",
    "margin_fill": "What fills the margin, the strip between the cut-out drawing and its\n"
    "cut line:\n"
    "Color: one solid color (Margin fill color).\n"
    "Original image: the picture around the figure, as it is in the image.",
    "margin_color": "The color of the margin between the drawing and the cut line.",
    "smooth_mm": "Rounds the outline; higher values give a calmer cut line.",
    "no_smooth": "Cut line made of straight segments instead of smooth curves.",
    "simplify_mm": "How far the cut line may deviate to use fewer points.",
    "cut_color": "Color of the cut line, for cutting by hand. A sheet cut by machine has no\n"
    "cut lines (see Cut by in the Print sheet step).",
    "cut_width_mm": "Width of the printed cut line, for cutting by hand.",
    "no_tab": "Print a tab: a fold-over stand tab under the feet.\n"
    "Off for slotted or magnetic bases.",
    "tab_shape": "Square: a tab to slot into a (3D printed) stand.\n"
    "Round: a half disc that folds out into a round base. On a double-sided\n"
    "mini the two halves fold out to opposite sides and form a full circle.",
    "tab_width_mm": "Width of the square tab.",
    "tab_radius_mm": "Radius of the round tab (a half disc). 12.5 mm makes a 25 mm base.",
    "tab_height_mm": "How far the square tab reaches below the fold line.",
    "tab_overlap_mm": "How far the tab reaches up past the fold line. It only adds paper where "
    "the figure's bottom is narrower than the tab (feet, a tail), to "
    "strengthen the joint.",
    "fold_mm": "Where the tab folds, measured up from the figure's lowest point.",
    "no_label": "Print a label: text on the tab.\n"
    "Off for a plain tab in its fill color.",
    "label": "Text printed on the tab (empty = the file name). Also the default back text.",
    "label_size_mm": "Largest text size; long labels shrink to fit the tab.",
    "label_color": "Color of the tab label.",
    "tab_color": "Color of the tab (everything below the fold), behind the label.\n"
    "Independent of the margin color; e.g. grass green for a plain tab.",
    "greyscale": "Print the figure in black and white (saves color ink).\n"
    "Color adjustments change only what is printed: background removal\n"
    "always looks at the original picture, so they never run the model again.",
    "brightness": "Lighter (towards white) or darker (towards black). White paper stays\n"
    "white when lightening, black lines stay black when darkening.",
    "contrast": "More contrast makes lights lighter and darks darker; less makes it flatter.",
    "saturation": "How colorful the picture is: -100 is grey, 100 twice as colorful.",
    "hue": "Turns every color around the color wheel (red -> yellow -> green ...).",
    "_reset_adjust": "Back to the original colors.\n"
    "(One slider: double-click it to put it back to 0.)",
    "double_sided": "Print a back side: front and back joined at a fold above the head,\n"
    "glued back to back. Off for the front only.",
    "back": "mirror: the drawing seen from behind; blank: plain paper; "
    "text: plain paper with text (a name or stats); number: the copy's number,\n"
    "large; text and number: the number above the text.",
    "back_text": "Text for the back (empty = the tab label). It is sized to fit the body.",
    "back_color": "Color of a back that is not the mirrored drawing (the back tab keeps the\n"
    "tab's fill color).",
    "font": "The font of all the piece's text: the label, the numbers and the back text.\n"
    "Times and the fonts that come with papermini work on every computer; a font\n"
    "installed only on this computer prints in Times elsewhere.",
    "tab_front": "What the front tab shows: the label, the copy's number, or both (the\n"
    "number above the label). Each copy on the sheet gets its own number,\n"
    "1, 2, 3…; this preview shows # where it goes.",
    "tab_back": "What the back tab of a double-sided mini shows: the label, the copy's\n"
    "number, or both (the number above the label).",
    "back_text_color": "Color of the text and the number on the back.",
}
