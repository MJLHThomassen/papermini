"""The layout of the figure panel: its steps, the sections of each step and the fields in
each section, the fields not built from their option alone, and which fields are shown
when."""

from __future__ import annotations

from dataclasses import replace
from functools import partial

from ...project.figure_settings import FigureSettings
from ...project.option import Option
from ..fields.area_field import AreaField
from ..fields.choice_field import ChoiceField
from ..fields.dimensions_field import DimensionsField
from ..fields.field_factory import FieldMaker
from ..fields.font_field import FontField
from ..fields.kind_field import KindField
from ..fields.mask_file_field import MaskFileField
from ..fields.model_field import ModelField
from ..fields.switch_field import SwitchField
from ..fields.switched_field import SwitchedField
from ..fields.text_field import TextField

_SETTINGS = FigureSettings.options()

# The steps of the workflow, one view each: the settings panel shows the active step's
# sections.
STEPS = ["Source", "Miniature", "Print sheet"]
SOURCE, MINIATURE, PRINT = range(3)

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

# The sections of each step, in order: (step, title, fields). A field has the name of
# the setting it edits, or another name in OPTIONS; a name in RESETS is a button.
SECTIONS = [
    (SOURCE, "Crop", ("crop",)),
    (
        SOURCE,
        "Background removal",
        ("model", "mask", "strength", "fill_gaps", "keep_all", "min_area"),
    ),
    (
        SOURCE,
        "Image adjustments",  # what is printed; the model never sees them
        ("greyscale", "brightness", "contrast", "saturation", "hue", "_reset_adjust"),
    ),
    (
        MINIATURE,
        "Size",  # first (after the Kind): how big the figure prints
        ("size", "dimensions", "token_diameter_mm", "dpi"),
    ),
    (
        MINIATURE,
        "Token",  # a token: the figure in a circle, inside a ring
        (
            "token_area",
            "token_fill",
            "token_fill_color",
            "token_border_mm",
            "token_border_color",
        ),
    ),
    (
        MINIATURE,
        "Token text",
        (
            "token_text",
            "token_text_style",
            "token_text_mm",
            "token_label",
            "token_text_color",
        ),
    ),
    (
        MINIATURE,
        "Back side",  # it decides what the rest of the piece is
        ("double_sided", "back", "back_color", "back_text", "back_text_color"),
    ),
    (
        MINIATURE,
        "Image outline",  # around the drawing: a mini's margin, a token's outline
        ("token_outline", "margin_mm", "margin_fill", "margin_color", "smooth_mm"),
    ),
    (
        MINIATURE,
        "Cut line",
        ("token_cut_line", "no_smooth", "simplify_mm", "cut_color", "cut_width_mm"),
    ),
    (
        MINIATURE,
        "Tab",
        (
            "no_tab",
            "tab_shape",
            "tab_width_mm",
            "tab_radius_mm",
            "tab_height_mm",
            "tab_overlap_mm",
            "fold_mm",
            "tab_color",
        ),
    ),
    (MINIATURE, "Label", ("label", "label_size_mm", "label_color")),  # on the tab
    (MINIATURE, "Text", ("font",)),  # one font for all of the piece's text
    (MINIATURE, "Number", ("tab_front", "tab_back")),  # the copy numbers on the tabs
]

# sections shown inside another section (indented, at its end): sub-section -> section
SUBSECTIONS = {"Label": "Tab", "Number": "Tab"}

# buttons that put settings back to their defaults: button -> the settings
RESETS = {"_reset_adjust": ("greyscale", "brightness", "contrast", "saturation", "hue")}

# the settings each field sets ("dimensions" sets two), and the creature size also fills
# in the height, the tabs and a token's diameter
FIELD_SETTINGS = {
    "dimensions": ("height_mm", "width_mm"),
    "size": ("size",) + tuple(k for k, o in _SETTINGS.items() if o.sized),
    "token_label": ("label",),
}

# a token's field that sets the same setting as a mini's (shown for the kind in use)
TWINS = {"token_label": "label"}

# the switches of sections a token can turn off but a mini always has (hidden for a mini)
TOKEN_SWITCHES = ("token_outline", "token_cut_line")

# sections that only one kind of figure has (the others belong to both)
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
        for st, _, names in SECTIONS
        if st == step
        for name in names
        if name not in RESETS
        for k in FIELD_SETTINGS.get(name, (name,))
    } | ({"kind"} if step == MINIATURE else set())


# the option of each field: a setting's own, or the label and tooltip of a field that is
# not a setting of its own
OPTIONS = {
    **_SETTINGS,
    "dimensions": Option(name="dimensions"),
    "token_label": replace(
        _SETTINGS["label"],
        label="Label",
        tooltip="The label on the token (empty = the file name).",
    ),
    "_reset_adjust": Option(
        name="_reset_adjust",
        label="Reset adjustments",
        tooltip="Back to the original colors.\n"
        "(One slider: double-click it to put it back to 0.)",
    ),
}

# the switches of the fields that are off at one of their values
_LABEL_SWITCH = Option(
    name="no_label",
    label="Print a label",
    tooltip="Print a label: text on the tab.\nOff for a plain tab in its fill color.",
)
_TOKEN_TEXT_SWITCH = Option(
    name="token_text_on",
    label="Print text",
    tooltip="Print text on the token: its label, its copy number or both.",
)

# the fields not built from their option alone
SPECIAL_FIELDS: dict[str, FieldMaker] = {
    "kind": KindField,
    "dimensions": partial(
        DimensionsField, height=_SETTINGS["height_mm"], width=_SETTINGS["width_mm"]
    ),
    "crop": partial(AreaField, placeholder="whole image - drag a box on it"),
    "token_area": partial(
        AreaField, placeholder="whole figure, fitted - drag it in the view"
    ),
    "mask": MaskFileField,
    "model": ModelField,
    "font": FontField,
    "back_text": partial(TextField, placeholder="the label (or file name)"),
    "double_sided": SwitchField,
    "token_outline": SwitchField,
    "token_cut_line": SwitchField,
    "no_tab": partial(SwitchField, invert=True),
    "label": partial(
        SwitchedField,
        inner=TextField,
        switch=_LABEL_SWITCH,
        off="",
    ),
    "token_text": partial(
        SwitchedField,
        inner=partial(ChoiceField, hidden=("none",)),
        switch=_TOKEN_TEXT_SWITCH,
        off="none",
    ),
}
