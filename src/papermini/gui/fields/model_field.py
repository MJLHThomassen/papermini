from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from ...pipeline.segmentation import segment
from ...project.option import Option
from ..theme_service import ThemeService
from .combo_box import ComboBox
from .detail_item_delegate import DETAIL_ROLE, DetailItemDelegate
from .edit_with_button import EditWithButton
from .field import Field


class ModelField(Field):
    """The background removal model, picked from a list. The last choice in the list
    is a custom model, whose file is typed in or picked in a box under the list; its
    value is that path, empty until one is given.

    The list and the tooltip describe every choice, the built-in models from
    ``segment.ONNX_MODELS``."""

    CUSTOM = "custom"  # the list's choice for a custom model file
    # a choice's name in the list, where it is not the model itself
    NAMES: ClassVar = {"mask": "mask image file", CUSTOM: "custom model file"}
    # what the choices that are not built-in models do
    DETAILS: ClassVar = {
        "auto": f"The image's transparency if it has any, else {segment.DEFAULT_MODEL}.",
        "alpha": "The image's own transparency. Needs no download.",
        "mask": "Your own black-and-white mask (white = figure).",
        CUSTOM: "Your own .onnx model, with the same input as RMBG-1.4.",
    }
    _LIST_FRAME_PX = 6  # the open list's padding and border on each side
    _GAP_PX = 4  # between the list and the model file box

    def __init__(
        self, option: Option, changed: Callable[..., None], themes: ThemeService
    ) -> None:
        self._changed = changed
        self._box = ComboBox()
        self._box.setItemDelegate(DetailItemDelegate(themes, self._box))
        self._choices: tuple[str, ...] = (
            "auto",
            *segment.ONNX_MODELS,
            "alpha",
            "mask",
            self.CUSTOM,
        )
        for choice in self._choices:
            self._box.addItem(self.NAMES.get(choice, choice), choice)
            self._box.setItemData(
                self._box.count() - 1, self._detail(choice), DETAIL_ROLE
            )
        # the list opens wider than the field, so the detail lines fit
        view = self._box.view()
        view.setMinimumWidth(view.sizeHintForColumn(0) + 2 * self._LIST_FRAME_PX)
        self._file = EditWithButton("…", "path of an .onnx model file")
        self._file.setVisible(False)
        super().__init__(option, self._box)
        self._file.setToolTip(self.DETAILS[self.CUSTOM])
        self.row = QWidget()
        v = QVBoxLayout(self.row)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(self._GAP_PX)
        v.addWidget(self._box)
        v.addWidget(self._file)
        self._box.currentIndexChanged.connect(self._picked)
        self._file.edit.editingFinished.connect(changed)
        self._file.button.clicked.connect(self._browse)

    def value(self) -> str:
        choice = self._box.currentData()
        if choice == self.CUSTOM:
            return self._file.edit.text().strip()
        return choice

    def set_value(self, value: str) -> None:
        index = self._box.findData(value)
        if index < 0:  # the path of a custom model
            index = self._box.findData(self.CUSTOM)
            self._file.edit.setText(value)
        with QSignalBlocker(self._box):
            self._box.setCurrentIndex(index)
        self._file.setVisible(index == self._box.findData(self.CUSTOM))

    def _picked(self) -> None:
        custom = self._box.currentData() == self.CUSTOM
        self._file.setVisible(custom)
        if custom and not self._file.edit.text().strip():
            self._file.edit.setFocus()
        self._changed()

    def _browse(self) -> None:
        f, _ = QFileDialog.getOpenFileName(
            self._file, "ONNX model", "", "ONNX models (*.onnx)"
        )
        if f:
            self._file.edit.setText(f)
            self._changed()

    def _detail(self, choice: str) -> str:
        """Describe ``choice`` in one or two lines."""
        if choice in self.DETAILS:
            return self.DETAILS[choice]
        spec = segment.ONNX_MODELS[choice]
        licence = "Free for any use" if spec.commercial else "Non-commercial use only"
        return f"{spec.about}\n{licence} · {spec.mb} MB download"

    def _tooltip(self, option: Option) -> str:
        """Return the option's tooltip, then a table of every choice."""
        return self._choice_tooltip(
            option.tooltip,
            ((self.NAMES.get(c, c), self._detail(c)) for c in self._choices),
        )
