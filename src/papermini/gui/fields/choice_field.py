from __future__ import annotations

from collections.abc import Callable, Collection
from typing import Any

from ...project.option import Option
from .combo_box import ComboBox
from .field import Field


class ChoiceField(Field):
    """One of the option's choices, in a drop-down list that names each choice.

    ``hidden`` choices are left out of the list. With ``none``, the list starts with an
    item of that name for None.
    """

    def __init__(
        self,
        option: Option,
        changed: Callable[..., None],
        hidden: Collection[Any] = (),
        none: str = "",
    ) -> None:
        self._box = ComboBox()
        self._none = none
        if none:
            self._box.addItem(none, "")
        labels = option.choice_labels or tuple(str(c) for c in option.choices)
        for choice, label in zip(option.choices, labels, strict=True):
            if choice not in hidden:
                self._box.addItem(label, choice)
        super().__init__(option, self._box)
        self._box.currentIndexChanged.connect(changed)

    def value(self) -> Any:
        data = self._box.currentData()
        return None if self._none and data == "" else data

    def set_value(self, value: Any) -> None:
        self._box.setCurrentIndex(max(0, self._box.findData(value or "")))
