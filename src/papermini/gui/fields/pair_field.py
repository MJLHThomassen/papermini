from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QWidget

from ...project.option import Option
from .field import Field
from .field_factory import FieldMaker


class PairField(Field):
    """Two settings in one row: the field of its own option, built by ``first``, and
    the field of ``second``, built by ``second_maker``, beside it.

    With ``only_for``, the second field shows only while the first has that value.
    """

    def __init__(
        self,
        option: Option,
        changed: Callable[..., None],
        first: FieldMaker,
        second: Option,
        second_maker: FieldMaker,
        only_for: Any = None,
    ) -> None:
        self._only_for = only_for
        self._changed = changed
        self._first = first(option, self._first_changed)
        self._second = second_maker(second, changed)
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        h.addWidget(self._first.widget, 1)
        h.addWidget(self._second.widget)
        super().__init__(option, box)
        self.inputs = self._first.inputs | self._second.inputs
        self._first.widget.setToolTip(self.tooltip)
        self._second.widget.setToolTip(self._second.tooltip)

    def value(self) -> Any:
        return self._first.value()

    def set_value(self, value: Any) -> None:
        self._first.set_value(value)
        self._sync_second()

    def show(self, settings: Any) -> None:
        self._first.show(settings)
        self._second.show(settings)
        self._sync_second()

    def read(self) -> dict[str, Any]:
        return self._first.read() | self._second.read()

    def _first_changed(self, *args: Any) -> None:
        self._sync_second()
        self._changed(*args)

    def _sync_second(self) -> None:
        shown = self._only_for is None or self._first.value() == self._only_for
        self._second.widget.setVisible(shown)
