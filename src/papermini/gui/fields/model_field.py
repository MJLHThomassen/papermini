from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from ...project.option import Option
from .combo_box import ComboBox
from .field import Field


class ModelField(Field):
    """The background removal model: one of the models in a list, or the path of a
    model typed in. Empty is auto."""

    MODELS: ClassVar = (
        "auto",
        "rmbg-1.4",
        "birefnet",
        "birefnet-lite",
        "alpha",
        "mask",
    )
    # a model's name in the list, where it is not the model itself
    NAMES: ClassVar = {"mask": "mask image file"}
    VALUES: ClassVar = {name: model for model, name in NAMES.items()}

    def __init__(self, option: Option, changed: Callable[..., None]) -> None:
        self._box = ComboBox()
        self._box.setEditable(True)
        self._box.addItems([self.NAMES.get(m, m) for m in self.MODELS])
        super().__init__(option, self._box)
        self._box.activated.connect(changed)
        line = self._box.lineEdit()
        assert line is not None
        line.editingFinished.connect(changed)

    def value(self) -> str:
        text = self._box.currentText().strip() or "auto"
        return self.VALUES.get(text, text)

    def set_value(self, value: str) -> None:
        self._box.setCurrentText(self.NAMES.get(value, value))
