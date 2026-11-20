from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ...project.option import Option
from ...support import fonts
from .combo_box import ComboBox
from .field import Field


class FontField(Field):
    """The font of a figure's text: the bundled fonts, each shown in itself, then the
    fonts installed on this computer once they are known.

    A font that is not listed is added. Once the installed fonts are known, it is marked
    as not on this computer.
    """

    MISSING = " (not on this computer)"

    def __init__(self, option: Option, changed: Callable[..., None]) -> None:
        self._box = ComboBox()
        self._box.setMaxVisibleItems(16)
        self._installed: set[str] | None = None  # None until they are known
        for f in fonts.bundled():
            self._add(f.name)
        super().__init__(option, self._box)
        self._box.currentIndexChanged.connect(changed)

    def value(self) -> str:
        return self._box.currentData()

    def set_value(self, value: str) -> None:
        i = self._box.findData(value)
        if i < 0:
            self._add(value, missing=self._installed is not None)
            i = self._box.count() - 1
        self._box.setCurrentIndex(i)

    def missing(self) -> bool:
        """Return whether the font shown is not on this computer."""
        return self._box.currentText().endswith(self.MISSING)

    def set_installed(self, names: Iterable[str]) -> None:
        """List the fonts installed on this computer after the bundled ones."""
        current = self.value()
        bundled = [f.name for f in fonts.bundled()]
        while self._box.count() > len(bundled):
            self._box.removeItem(self._box.count() - 1)
        names = list(names)
        new = [n for n in names if n not in bundled]
        if new:
            self._box.insertSeparator(self._box.count())
            for n in new:
                self._add(n)
        self._installed = set(names)
        self.set_value(current)

    def _add(self, name: str, missing: bool = False) -> None:
        self._box.addItem(name + self.MISSING if missing else name, name)
        if not missing:
            from ..views.drawing import qt_family

            self._box.setItemData(
                self._box.count() - 1, QFont(qt_family(name)), Qt.ItemDataRole.FontRole
            )
