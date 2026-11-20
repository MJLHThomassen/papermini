from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QFileDialog

from ...project.option import Option
from ...support import remote
from .edit_with_button import EditWithButton
from .field import Field


class MaskFileField(Field):
    """The path of a mask image file, typed in or picked with a button. Empty is None."""

    def __init__(self, option: Option, changed: Callable[..., None]) -> None:
        self._box = EditWithButton("…", "choose a mask image (white = figure)")
        self._changed = changed
        super().__init__(option, self._box)
        self._box.edit.editingFinished.connect(changed)
        self._box.button.clicked.connect(self._browse)

    def value(self) -> str | None:
        return self._box.edit.text().strip() or None

    def set_value(self, value: str | None) -> None:
        self._box.edit.setText(value or "")

    def _browse(self) -> None:
        f, _ = QFileDialog.getOpenFileName(
            self._box, "Mask image (white = figure)", "", remote.IMAGE_FILTER
        )
        if f:
            self._box.edit.setText(f)
            self._changed()
