from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...pipeline.tab_label import LABEL_SHOWS
from .figure_fields import KIND_SECTIONS, TAB_SECTIONS, TOKEN_PARTS


class FieldVisibility:
    """Decides which fields and sections of the figure settings do something for a
    figure, from the values its fields show."""

    def shown(self, value: Callable[[str], Any]) -> dict[str, bool]:
        """Return, for each field that is only shown at times, whether it is shown when
        ``value`` returns the value of each field by name."""
        tab = not value("no_tab")
        token = value("kind") == "token"
        square = value("tab_shape") == "square"
        double = value("double_sided")
        own_back_tab = double and tab and value("tab_back") != "same"
        show = {
            "mask": value("model") == "mask",
            "min_area": value("keep_all"),
            "tab_shape": tab,
            "tab_width_mm": tab and square,
            "tab_height_mm": tab and square,
            "tab_radius_mm": tab and not square,
            "tab_overlap_mm": tab,
            "fold_mm": tab,
            "tab_color": tab,
            "label_color": value("tab_front") != "none",
            "label": value("tab_front") in LABEL_SHOWS,
            "label_size_mm": value("tab_front") in LABEL_SHOWS,
            "back": double,
            "back_color": double and value("back") != "mirror",
            "back_text": double and value("back") in ("text", "text_number"),
            "back_text_color": double
            and value("back") in ("text", "number", "text_number"),
            "tab_back": double and tab,
            "back_label_color": own_back_tab and value("tab_back") != "none",
            "back_label": own_back_tab and value("tab_back") in LABEL_SHOWS,
            "back_label_size_mm": own_back_tab and value("tab_back") in LABEL_SHOWS,
        }
        show["saturation"] = show["hue"] = not value("greyscale")
        # a token: its own fields instead of the mini's; the margin makes its outline
        text = value("token_text")
        show.update(
            {
                "dimensions": not token,
                "token_diameter_mm": token,
                "token_fill_color": value("token_fill") == "color",
                "token_text_style": text != "none",
                "token_text_mm": text != "none",
                "token_label": text in ("label", "label_number"),
                "token_text_color": text != "none",
                "cut_detail": not token,
            }
        )
        # (a mini always has its outline and its cut line: only a token's can be left
        # out)
        for check, names in TOKEN_PARTS.items():
            show[check] = token
            for name in names:
                show[name] = not token or value(check)
        return show

    def section_applies(self, title: str, token: bool, tab: bool) -> bool:
        """Tell whether the section ``title`` does something for a token or a mini
        (``token``), with or without a ``tab``."""
        kind = "token" if token else "mini"
        if KIND_SECTIONS.get(title, kind) != kind:
            return False
        return not (title in TAB_SECTIONS and not tab)
