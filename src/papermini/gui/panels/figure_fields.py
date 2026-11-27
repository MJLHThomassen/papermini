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
from ..fields.color_field import ColorField
from ..fields.field_factory import FieldMaker
from ..fields.kind_field import KindField
from ..fields.mask_file_field import MaskFileField
from ..fields.number_field import NumberField
from ..fields.pair_field import PairField
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
        "Border",  # the paper around the drawing, and the cut along its edge
        (
            "token_cut_line",
            "cut_width_mm",
            "token_outline",
            "margin_mm",
            "margin_fill",
            "smooth_mm",
            "cut_detail",
        ),
    ),
    (Step.MINIATURE, "Text", ("font",)),  # one font for all of the piece's text
    (
        Step.MINIATURE,
        "Tab",  # what both tabs share
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
    (
        Step.MINIATURE,
        "Front",  # the front tab
        ("tab_front", "label_color", "label", "label_size_mm"),
    ),
    (
        Step.MINIATURE,
        "Back side",  # its own Shows, then the same tab fields as the front
        (
            "double_sided",
            "back",
            "back_color",
            "back_text",
            "back_text_color",
            "tab_back",
            "back_label_color",
            "back_label",
            "back_label_size_mm",
        ),
    ),
]

# sections about the tabs, hidden when a mini has no tab
TAB_SECTIONS = ("Front",)

# buttons that put settings back to their defaults: button -> the settings
RESETS = {"_reset_adjust": ("greyscale", "brightness", "contrast", "saturation", "hue")}

# the settings each field sets ("dimensions" sets two), and the creature size also fills
# in the height, the tabs and a token's diameter
FIELD_SETTINGS = {
    "dimensions": ("height_mm", "width_mm"),
    "size": ("size",) + tuple(k for k, o in _SETTINGS.items() if o.sized),
    "token_label": ("label",),
    "margin_fill": ("margin_fill", "margin_color"),
    "cut_detail": ("simplify_mm", "no_smooth"),
    "cut_width_mm": ("cut_width_mm", "cut_color"),
}

# a token's field that sets the same setting as a mini's (shown for the kind in use)
TWINS = {"token_label": "label"}

# the label fields, which print the file name when they are empty
NAME_FIELDS = ("label", "token_label", "back_label")

# the parts of the border a token can leave out but a mini always has: the checkbox
# of each, and the fields it hides
TOKEN_PARTS = {
    "token_outline": ("margin_mm", "margin_fill", "smooth_mm"),
    "token_cut_line": ("cut_width_mm",),
}

# sections that only one kind of figure has (the others belong to both)
KIND_SECTIONS = {
    "Back side": "mini",
    "Tab": "mini",
    "Front": "mini",
    "Token": "token",
    "Token text": "token",
}

# kept per figure when a step's settings are copied to every figure
PER_IMAGE = {"label", "back_label", "crop", "mask", "copies", "token_area"}


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
    "cut_detail": Option(
        name="cut_detail",
        label="Detail",
        tooltip="How closely the cut line follows the outline. A coarser line has fewer "
        "corners, so it is easier to cut by hand. Straight is made of straight lines "
        "only: every corner is one cut, so it is the quickest to cut with scissors.",
        stops=(
            {"simplify_mm": 0.05, "no_smooth": False},
            {"simplify_mm": 0.15, "no_smooth": False},
            {"simplify_mm": 0.6, "no_smooth": False},
            {"simplify_mm": 0.6, "no_smooth": True},
        ),
        choice_labels=("Exact", "Fine", "Coarse", "Straight"),
        choice_details=(
            "Follows every bump of the outline. The most corners.",
            "Close to the outline, with small bumps smoothed over.",
            "Smooths over larger bumps, with few corners.",
            "As coarse, in straight lines. The easiest to cut.",
        ),
    ),
    "_reset_adjust": Option(
        name="_reset_adjust",
        label="Reset adjustments",
        tooltip="Back to the original colors.\n"
        "(One slider: double-click it to put it back to 0.)",
    ),
}

# the switches of the fields that are off at one of their values
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
    "margin_fill": partial(
        PairField,
        first=ChoiceField,
        second=_SETTINGS["margin_color"],
        second_maker=ColorField,
        only_for="color",
    ),
    "cut_width_mm": partial(
        PairField,
        first=NumberField,
        second=_SETTINGS["cut_color"],
        second_maker=ColorField,
    ),
    "no_tab": partial(SwitchField, invert=True),
    "token_text": partial(
        SwitchedField,
        inner=partial(ChoiceField, hidden=("none",)),
        switch=_TOKEN_TEXT_SWITCH,
        off="none",
    ),
}
