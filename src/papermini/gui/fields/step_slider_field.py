from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ...project.option import Option
from ..theme_service import ThemeService
from .field import Field
from .slider import Slider


class StepSliderField(Field):
    """A slider through the option's stops, with a mark at each stop and the stop's name
    beside it. Each stop sets one or more settings.

    Settings that match no stop show at the nearest one: the stop with the fewest
    other values, then the closest numbers.
    """

    def __init__(
        self, option: Option, changed: Callable[..., None], themes: ThemeService
    ) -> None:
        self._stops = option.stops
        self._names = option.choice_labels
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        self._slider = Slider(themes, marks=True)
        self._slider.setRange(0, len(self._stops) - 1)
        self._slider.setPageStep(1)
        self._name = QLabel()
        width = max(self._name.fontMetrics().horizontalAdvance(n) for n in self._names)
        self._name.setFixedWidth(width)
        h.addWidget(self._slider, 1)
        h.addWidget(self._name)
        super().__init__(option, box)
        self.inputs = {name: self._slider for name in self._stops[0]}
        for w in (self._slider, self._name):
            w.setToolTip(self.tooltip)
        self._slider.valueChanged.connect(self._show_name)
        self._slider.valueChanged.connect(changed)

    def value(self) -> Mapping[str, Any]:
        return self._stops[self._slider.value()]

    def set_value(self, value: Mapping[str, Any]) -> None:
        index = min(
            range(len(self._stops)), key=lambda i: self._distance(self._stops[i], value)
        )
        self._slider.blockSignals(True)
        self._slider.setValue(index)
        self._slider.blockSignals(False)
        self._show_name(index)

    def show(self, settings: Any) -> None:
        self.set_value({name: getattr(settings, name) for name in self._stops[0]})

    def read(self) -> dict[str, Any]:
        return dict(self.value())

    @staticmethod
    def _distance(stop: Mapping[str, Any], value: Mapping[str, Any]) -> tuple:
        """Return how far ``value`` is from ``stop``: how many of its values that are not
        numbers differ, then how far apart its numbers are."""
        numbers = [n for n, v in stop.items() if type(v) in (int, float)]
        others = sum(stop[n] != value[n] for n in stop if n not in numbers)
        return others, sum(abs(stop[n] - value[n]) for n in numbers)

    def _show_name(self, index: int) -> None:
        self._name.setText(self._names[index])
