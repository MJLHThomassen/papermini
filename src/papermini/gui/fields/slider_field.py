from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QVBoxLayout, QWidget

from ..theme_service import ThemeService
from .slider import Slider
from .spin_box import SpinBox


class SliderField(QWidget):
    """A slider with a number box beside it for exact values. With ``auto`` an "Auto"
    checkbox goes underneath (so all sliders line up): while it is ticked the slider shows
    the automatic value greyed out and ``value()`` is None."""

    valueChanged = Signal()

    def __init__(
        self,
        themes: ThemeService,
        lo: int,
        hi: int,
        slider_hi: int,
        suffix: str = "",
        auto: bool = False,
        auto_value: int = 9,
        parent=None,
    ):
        super().__init__(parent)
        self._auto_value = auto_value
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        h = QHBoxLayout()
        h.setSpacing(10)
        v.addLayout(h)
        self.auto = QCheckBox("Auto (scales with the image)") if auto else None
        self.slider = Slider(themes, centre=0 if lo < 0 < hi else None)
        self.slider.setRange(
            lo, min(hi, slider_hi)
        )  # larger values: type them in the box
        self.slider.setPageStep(max(1, (slider_hi - lo) // 10))
        self.spin = SpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setSuffix(suffix)
        self.spin.setFixedWidth(64)
        h.addWidget(self.slider, 1)
        h.addWidget(self.spin)
        if self.auto is not None:
            self.auto.toggled.connect(self._auto_toggled)
            v.addWidget(self.auto)
        self.slider.valueChanged.connect(self._changed)
        self.spin.valueChanged.connect(self._changed)

    def is_auto(self) -> bool:
        return self.auto is not None and self.auto.isChecked()

    def value(self):
        return None if self.is_auto() else self.spin.value()

    def setValue(self, v) -> None:
        if self.auto is not None:
            self.auto.blockSignals(True)
            self.auto.setChecked(v is None)
            self.auto.blockSignals(False)
        self._show(self._auto_value if v is None else v)
        self._sync_enabled()

    def set_auto_value(self, v: int) -> None:
        self._auto_value = v
        if self.is_auto():
            self._show(v)

    def _show(self, v: int) -> None:
        for w in (self.slider, self.spin):
            w.blockSignals(True)
            w.setValue(v)  # the slider stops at its end for larger typed values
            w.blockSignals(False)

    def _sync_enabled(self) -> None:
        for w in (self.slider, self.spin):
            w.setEnabled(not self.is_auto())

    def _changed(self, v: int) -> None:
        self._show(v)
        self.valueChanged.emit()

    def _auto_toggled(self, on: bool) -> None:
        if on:
            self._show(self._auto_value)
        self._sync_enabled()  # unticked: carry on from the automatic value
        self.valueChanged.emit()
