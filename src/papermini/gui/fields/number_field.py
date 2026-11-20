from __future__ import annotations

from collections.abc import Callable
from typing import get_args

from ...project.option import Option
from .double_spin_box import DoubleSpinBox
from .field import Field
from .spin_box import SpinBox


class NumberField(Field):
    """A number in a spin box, with the option's range, step, decimals and unit. A whole
    number setting gets a whole number box."""

    def __init__(self, option: Option, changed: Callable[..., None]) -> None:
        low, high = option.widget
        if int in (option.type, *get_args(option.type)):
            self._box = SpinBox()
            self._box.setRange(int(low), int(high))
            self._box.setSingleStep(int(option.step))
        else:
            self._box = DoubleSpinBox()
            self._box.setRange(low, high)
            self._box.setSingleStep(option.step)
            self._box.setDecimals(option.decimals)
        self._box.setSuffix(self.suffix(option.unit))
        super().__init__(option, self._box)
        self._box.valueChanged.connect(changed)

    def value(self) -> float:
        return self._box.value()

    def set_value(self, value: float) -> None:
        if isinstance(self._box, SpinBox):
            self._box.setValue(int(value))
        else:
            self._box.setValue(value)
