from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...project.option import Option
from .field import Field
from .size_field import SizeField


class DimensionsField(Field):
    """A figure's height and width, with a toggle that keeps its proportions. It brings
    its own labels, from the options of its settings, ``height`` and ``width``."""

    def __init__(
        self,
        option: Option,
        changed: Callable[..., None],
        height: Option,
        width: Option,
    ) -> None:
        self._size = SizeField(height, width)
        super().__init__(option, self._size)
        self.label = ""
        self.labels = list(self._size.labels)
        self._size.valueChanged.connect(changed)

    def value(self) -> tuple[float | None, float | None]:
        return self._size.value()

    def set_value(self, value: tuple[float | None, float | None]) -> None:
        self._size.set_value(*value)

    def show(self, settings: Any) -> None:
        self.set_value((settings.height_mm, settings.width_mm))

    def read(self) -> dict[str, Any]:
        height, width = self.value()
        return {"height_mm": height, "width_mm": width}
