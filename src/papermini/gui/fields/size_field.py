from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QToolButton, QWidget

from ...project.option import Option
from .. import theme
from .double_spin_box import DoubleSpinBox
from .field import Field


class SizeField(QWidget):
    """Figure height and width with a link toggle beside them, like an image editor's
    resize dialog. Linked, the figure keeps its proportions: the field you type in sets
    the size and the other one follows (shown once the figure's proportions are known,
    "—" before). Unlinked, both are set and the figure is stretched to them.

    Each field takes its label, tooltip, range, decimals and unit from the option of its
    setting, ``height`` or ``width``."""

    valueChanged = Signal()
    LINK_TIP = (
        "Linked: the figure keeps its proportions, so setting the height sets the\n"
        "width and the other way round.\n"
        "Unlinked: set height and width separately; the figure is stretched."
    )

    def __init__(self, height: Option, width: Option, parent=None):
        super().__init__(parent)
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        self.labels = [QLabel(height.label), QLabel(width.label)]
        self.h, self.w = DoubleSpinBox(), DoubleSpinBox()
        for row, (lab, spin, option) in enumerate(
            zip(self.labels, (self.h, self.w), (height, width))
        ):
            lab.setObjectName("FormLabel")
            lab.setToolTip(option.tooltip)
            spin.setToolTip(option.tooltip)
            spin.setRange(*option.widget)
            spin.setDecimals(option.decimals)
            spin.setSuffix(Field.suffix(option.unit))
            spin.setSpecialValueText("—")  # 0: follows the other one, not known yet
            g.addWidget(lab, row, 0)
            g.addWidget(spin, row, 1)
        self.link = QToolButton()
        self.link.setObjectName("SizeLink")
        self.link.setCheckable(True)
        self.link.setChecked(True)
        self.link.setToolTip(self.LINK_TIP)
        self.link.setAccessibleName("Keep proportions")
        self.link.setCursor(Qt.PointingHandCursor)
        self.link.setIconSize(QSize(18, 18))
        g.addWidget(self.link, 0, 2, 2, 1, Qt.AlignVCenter)
        g.setColumnStretch(1, 1)
        self._lead = "h"  # linked: the field that sets the size
        self._aspect = None  # width / height of the drawing, once built
        self.h.valueChanged.connect(lambda v: self._edited("h", v))
        self.w.valueChanged.connect(lambda v: self._edited("w", v))
        self.link.toggled.connect(self._link_toggled)
        self.refresh_icons()

    def refresh_icons(self):
        on = self.link.isChecked()
        self.link.setIcon(
            theme.icon(
                "link" if on else "unlink",
                theme.current.accent if on else theme.current.muted,
                18,
            )
        )

    def linked(self) -> bool:
        return self.link.isChecked()

    def value(self):
        """(height_mm, width_mm) as in FigureSettings: one of them None when linked."""
        if self.linked():
            return (
                (self.h.value(), None) if self._lead == "h" else (None, self.w.value())
            )
        return self.h.value(), self.w.value()

    def set_value(self, height, width):
        self._lead = "h" if height else "w"
        self._quiet(
            lambda: (
                self.link.setChecked(not (height and width)),
                self.h.setValue(height or 0),
                self.w.setValue(width or 0),
            )
        )
        self.refresh_icons()
        self._follow()

    def set_aspect(self, aspect):
        """The drawing's own width / height (from the last build)."""
        self._aspect = aspect
        self._follow()

    def _quiet(self, fn):
        for w in (self.h, self.w, self.link):
            w.blockSignals(True)
        try:
            fn()
        finally:
            for w in (self.h, self.w, self.link):
                w.blockSignals(False)

    def _follow(self):
        """Linked: show the size the other field follows to (or "—")."""
        if not self.linked():
            return
        a = self._aspect
        if self._lead == "h":
            self._quiet(lambda: self.w.setValue(self.h.value() * a if a else 0))
        else:
            self._quiet(lambda: self.h.setValue(self.w.value() / a if a else 0))

    def _edited(self, which: str, v: float):
        if v <= 0:  # "—" is not a size: put back what it was
            self._follow() if self.linked() else self._quiet(
                lambda: (self.h if which == "h" else self.w).setValue(1)
            )
            return
        if self.linked():
            self._lead = which
            self._follow()
        self.valueChanged.emit()

    def _link_toggled(self, on: bool):
        self.refresh_icons()
        if on:  # back to the drawing's own proportions, keeping the height
            self._lead = "h" if self.h.value() > 0 else "w"
            self._follow()
        else:  # both fields set from what they show now
            h, w = self.h.value(), self.w.value()
            self._quiet(lambda: (self.h.setValue(h or w), self.w.setValue(w or h)))
        self.valueChanged.emit()
