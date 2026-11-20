from __future__ import annotations

from collections.abc import Callable

from ...project.option import Option
from .color_button import ColorButton
from .field import Field


class ColorField(Field):
    """A #rrggbb color: a button that shows it and opens a color picker."""

    def __init__(self, option: Option, changed: Callable[..., None]) -> None:
        self._button = ColorButton()
        super().__init__(option, self._button)
        self._button.colorChanged.connect(changed)

    def value(self) -> str:
        return self._button.color()

    def set_value(self, value: str) -> None:
        self._button.set_color(value)
