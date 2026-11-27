from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..preferences import Preferences
from ..theme_service import ThemeService


class Section(QWidget):
    """A settings group with a clickable header that folds it open/closed
    (remembered between sessions). A group with a switch that is off shows only its
    header and cannot be opened. Its fields go in ``form``, labels on the left."""

    def __init__(
        self,
        prefs: Preferences,
        themes: ThemeService,
        title: str,
        parent=None,
    ):
        super().__init__(parent)
        self._themes = themes
        self._prefs = prefs
        self._title = title
        self.setObjectName("Section")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._active = True
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 10)
        v.setSpacing(2)
        self.header = QPushButton(title)
        self.header.setObjectName("SectionHeader")
        self.header.setCheckable(True)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.body = QWidget()
        self.form = QFormLayout(self.body)
        self.form.setContentsMargins(2, 0, 0, 0)
        self.form.setHorizontalSpacing(12)
        self.form.setVerticalSpacing(8)
        self.form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self.switch = None
        self._head = QHBoxLayout()
        self._head.setContentsMargins(0, 0, 4, 0)
        self._head.addWidget(self.header, 1)
        v.addLayout(self._head)
        v.addWidget(self.body)
        self.header.toggled.connect(self._toggle)
        open_ = prefs.section_open(title)
        self.header.setChecked(open_)
        self._toggle(open_)

    def set_switch(self, box: QCheckBox):
        """A checkbox at the right of the header that turns the whole group on or off."""
        box.setObjectName("SectionSwitch")
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch = box
        self._head.addWidget(box, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_active(self, on: bool):
        """Switched off: only the header, which cannot be opened (there is nothing in
        it); switched on: open or folded as the user left it."""
        if on == self._active:
            return
        self._active = on
        self.header.setEnabled(on)
        self.header.setCursor(
            Qt.CursorShape.PointingHandCursor if on else Qt.CursorShape.ArrowCursor
        )
        self._toggle(self.header.isChecked(), remember=False)

    def active(self) -> bool:
        return self._active

    def _toggle(self, open_: bool, remember: bool = True):
        shown = open_ and self._active
        self.body.setVisible(shown)
        self.header.setIcon(
            self._themes.icon(
                "chevron_down" if shown else "chevron_right",
                self._themes.current.muted,
                14,
            )
        )
        if remember:
            self._prefs.set_section_open(self._title, open_)
