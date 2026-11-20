from __future__ import annotations

from collections.abc import Callable

from ...project.option import Option
from .field import Field
from .kind_choice import KindChoice


class KindField(Field):
    """The kind of figure: a radio button for each of the option's choices."""

    def __init__(self, option: Option, changed: Callable[..., None]) -> None:
        kinds = zip(option.choices, option.choice_labels, strict=True)
        self._choice = KindChoice(kinds)
        super().__init__(option, self._choice)
        self._choice.valueChanged.connect(changed)

    def value(self) -> str:
        return self._choice.value()

    def set_value(self, value: str) -> None:
        self._choice.setValue(value)
