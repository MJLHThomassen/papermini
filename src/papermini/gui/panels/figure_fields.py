"""The layout of the figure panel: the sections of each step and the fields in each
section, the fields not built from their option alone, and which fields are shown
when."""

from __future__ import annotations

from dataclasses import replace
from functools import partial

from ...project.figure_settings import FigureSettings
from ...project.option import Option
from ..fields.area_field import AreaField
from ..fields.choice_field import ChoiceField
from ..fields.field_factory import FieldMaker
from ..fields.kind_field import KindField
from ..fields.mask_file_field import MaskFileField
from ..fields.switch_field import SwitchField
from ..fields.switched_field import SwitchedField
from ..fields.text_field import TextField
from ..step import Step

_SETTINGS = FigureSettings.options()

# The sections of each step, in order: (step, title, fields). A field has the name of
# the setting it edits, or another name in OPTIONS; a name in RESETS is a button.
SECTIONS = [
    (Step.SOURCE, "Crop", ("crop",)),
    (
        Step.SOURCE,
        "Background removal",
        ("model", "mask", "strength", "fill_gaps", "keep_all", "min_area"),
    ),
    (
        Step.SOURCE,
        "Image adjustments",  # what is printed; the model never sees them
        ("greyscale", "brightness", "contrast", "saturation", "hue", "_reset_adjust"),
    ),
    (
        Step.MINIATURE,
        "Size",  # first, after the kind of figure: how big the figure prints
        ("size", "dimensions", "token_diameter_mm", "dpi"),
    ),
    (
        Step.MINIATURE,
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
        Step.MINIATURE,
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
        Step.MINIATURE,
        "Back side",  # it decides what the rest of the piece is
        ("double_sided", "back", "back_color", "back_text", "back_text_color"),
    ),
    (
        Step.MINIATURE,
        "Image outline",  # around the drawing: a mini's margin, a token's outline
        ("token_outline", "margin_mm", "margin_fill", "margin_color", "smooth_mm"),
    ),
    (
        Step.MINIATURE,
        "Cut line",
        ("token_cut_line", "no_smooth", "simplify_mm", "cut_color", "cut_width_mm"),
    ),
    (
        Step.MINIATURE,
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
    (Step.MINIATURE, "Label", ("label", "label_size_mm", "label_color")),  # on the tab
    (Step.MINIATURE, "Text", ("font",)),  # one font for all of the piece's text
    (
        Step.MINIATURE,
        "Number",
        ("tab_front", "tab_back"),
    ),  # the copy numbers on the tabs
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

# kept per figure when a step's settings are copied to every figure
PER_IMAGE = {"label", "crop", "mask", "copies", "token_area"}


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

# the fields not built from their option alone (FigurePanel adds the fields that need
# a service: the font, the dimensions and the model)
SPECIAL_FIELDS: dict[str, FieldMaker] = {
    "kind": KindField,
    "crop": partial(AreaField, placeholder="whole image - drag a box on it"),
    "token_area": partial(
        AreaField, placeholder="whole figure, fitted - drag it in the view"
    ),
    "mask": MaskFileField,
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
