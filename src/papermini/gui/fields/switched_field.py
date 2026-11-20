from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QCheckBox

from ...project.option import Option
from .field import Field


class SwitchedField(Field):
    """A field with a switch in its section's header. Switched off, its setting is
    ``off``, whatever the field shows.

    ``inner`` builds the field, and ``switch`` gives the switch its name, label and
    tooltip.
    """

    def __init__(
        self,
        option: Option,
        changed: Callable[..., None],
        inner: Callable[[Option, Callable[..., None]], Field],
        switch: Option,
        off: Any,
    ) -> None:
        self._inner = inner(option, changed)
        self._off = off
        self._box = QCheckBox()
        self._box.setAccessibleName(switch.label)
        self._box.setToolTip(switch.tooltip)
        super().__init__(option, self._inner.widget)
        self.label = self._inner.label
        self.switch = self._box
        self.switch_name = switch.name
        self._box.toggled.connect(changed)

    def value(self) -> Any:
        return self._inner.value() if self._box.isChecked() else self._off

    def set_value(self, value: Any) -> None:
        self._box.setChecked(value != self._off)
        self._inner.set_value(value)
