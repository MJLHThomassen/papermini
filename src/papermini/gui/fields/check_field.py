from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QCheckBox

from ...project.option import Option
from .field import Field


class CheckField(Field):
    """A setting that is on or off: a checkbox with the option's label beside it."""

    def __init__(self, option: Option, changed: Callable[..., None]) -> None:
        self._box = QCheckBox(option.label)
        super().__init__(option, self._box)
        self.label = ""
        self._box.toggled.connect(changed)

    def value(self) -> bool:
        return self._box.isChecked()

    def set_value(self, value: bool) -> None:
        self._box.setChecked(bool(value))
