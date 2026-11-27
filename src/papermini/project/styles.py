"""The style presets that come with papermini. They cannot be changed or deleted,
only copied."""

from __future__ import annotations

from .style_preset import StylePreset

BLACK = "#000000"
WHITE = "#ffffff"

BUILTIN_STYLES = (
    StylePreset("Standing mini"),  # the defaults
    StylePreset(
        "Standing mini - dark mode",
        {
            "margin_color": BLACK,
            "tab_color": BLACK,
            "back_color": BLACK,
            "label_color": WHITE,
            "back_label_color": WHITE,
            "back_text_color": WHITE,
        },
    ),
    StylePreset("Token", {"kind": "token", "token_text": "label"}),
)

# the preset new figures get, until the user picks another in the preferences
DEFAULT_STYLE = BUILTIN_STYLES[0].name
