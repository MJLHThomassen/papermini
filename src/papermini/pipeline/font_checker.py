from __future__ import annotations

from dataclasses import replace

from ..support import fonts
from .style import Style


class FontChecker:
    """Makes sure a piece is printed in a font this computer has."""

    def checked(self, style: Style, name: str, log=print) -> Style:
        """Return ``style``, printing in the default font when its font is not on this
        computer."""
        if fonts.resolve(style.font)[1]:
            return style
        log(
            f"  {name}: note: the font {style.font} is not on this computer: "
            f"printing in {fonts.DEFAULT}"
        )
        return replace(style, font=fonts.DEFAULT)
