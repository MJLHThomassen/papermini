from __future__ import annotations

from collections.abc import Callable

from ...project.option import Option
from .field import Field
from .slider_field import SliderField


class IntSliderField(Field):
    """A whole number on a slider, with a number box beside it for exact values.

    The slider goes up to the option's ``slider``, the box to the top of its range. An
    option that is worked out automatically gets an Auto checkbox.
    """

    def __init__(self, option: Option, changed: Callable[..., None]) -> None:
        low, high = (int(v) for v in option.widget)
        self._slider = SliderField(
            low,
            high,
            option.slider if option.slider is not None else high,
            self.suffix(option.unit),
            option.auto,
        )
        super().__init__(option, self._slider)
        self._slider.valueChanged.connect(changed)

    def value(self) -> int | None:
        return self._slider.value()

    def set_value(self, value: int | None) -> None:
        self._slider.setValue(value)
