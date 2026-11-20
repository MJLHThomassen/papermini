from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...project.option import Option
from .edit_with_button import EditWithButton
from .field import Field


class AreaField(Field):
    """An area of the picture, x0, y0, x1, y1, typed in or dragged in a view, with a
    button that clears it. Empty is None.

    The option's ``parse`` reads the typed text, or else four numbers are read. Text it
    cannot read keeps the area as it was.
    """

    def __init__(
        self, option: Option, changed: Callable[..., None], placeholder: str
    ) -> None:
        self._box = EditWithButton("Clear", placeholder)
        self._parse = option.parse or self._four_numbers
        self._last: Any = None  # the area last shown or read
        super().__init__(option, self._box)
        self._box.edit.editingFinished.connect(changed)
        self._box.button.clicked.connect(lambda: (self._box.edit.clear(), changed()))

    def value(self) -> Any:
        text = self._box.edit.text().strip()
        if not text:
            return None
        try:
            self._last = self._parse(text)
        except ValueError:
            pass
        return self._last

    def set_value(self, value: Any) -> None:
        self._last = value
        if value is None or value == "":
            text = ""
        elif isinstance(value, str):
            text = value
        else:
            text = ", ".join(f"{v:g}" for v in value)
        self._box.edit.setText(text)

    @staticmethod
    def _four_numbers(text: str) -> list[float]:
        vals = [float(v) for v in text.replace(" ", "").split(",")]
        if len(vals) != 4:
            raise ValueError(text)
        return vals
