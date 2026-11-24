from __future__ import annotations

from PySide6.QtGui import QFontDatabase

from ...support.font_library import FontLibrary


class QtFonts:
    """Finds the font family Qt draws a miniature's font with, so that the app shows
    what the PDF prints."""

    def __init__(self, fonts: FontLibrary) -> None:
        self._fonts = fonts
        self._families: dict[str, str] = {}

    def family(self, name: str) -> str:
        """Return the family of the font ``name``: Times New Roman for Times, else the
        font's own files, registered with Qt once."""
        if name not in self._families:
            font, _ = self._fonts.resolve(name)
            family = "Times New Roman"
            if font.regular is not None:
                found = []
                for path in (font.regular, font.bold):
                    if path is not None:
                        fid = QFontDatabase.addApplicationFont(str(path))
                        found += (
                            QFontDatabase.applicationFontFamilies(fid)
                            if fid >= 0
                            else []
                        )
                family = found[0] if found else font.name
            self._families[name] = family
        return self._families[name]
