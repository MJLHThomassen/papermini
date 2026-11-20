from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QCheckBox

from ...project.option import Option
from .field import Field


class SwitchField(Field):
    """A setting that turns a whole section on or off: a switch in the section's header.

    Ticked always means the section is on. With ``invert`` the setting is the opposite
    of the switch, for a setting that leaves something out.
    """

    def __init__(
        self, option: Option, changed: Callable[..., None], invert: bool = False
    ) -> None:
        self._box = QCheckBox()
        self._box.setAccessibleName(option.label)
        self._invert = invert
        super().__init__(option, self._box)
        self.row = None
        self.switch = self._box
        self.switch_name = option.name
        self._box.toggled.connect(changed)

    def value(self) -> bool:
        return self._box.isChecked() != self._invert

    def set_value(self, value: bool) -> None:
        self._box.setChecked(bool(value) != self._invert)
