from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .. import theme
from ..preferences import Preferences

SUB_INDENT = 14


class Section(QWidget):
    """A settings group with a clickable header that folds it open/closed
    (remembered between sessions). A group with a switch that is off shows only its
    header and cannot be opened. ``sub``: a group inside another one (indented)."""

    def __init__(self, prefs: Preferences, title: str, parent=None, sub: bool = False):
        super().__init__(parent)
        self._prefs = prefs
        self._title = title
        self.setObjectName("SubSection" if sub else "Section")
        self.setAttribute(Qt.WA_StyledBackground)
        self._active = True
        self.parent_section = None  # the group a sub-group is inside
        v = QVBoxLayout(self)
        v.setContentsMargins(SUB_INDENT if sub else 0, 0, 0, 0 if sub else 10)
        v.setSpacing(2)
        self.header = QPushButton(title)
        self.header.setObjectName("SectionHeader")
        self.header.setCheckable(True)
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setFocusPolicy(Qt.NoFocus)
        self.body = QWidget()
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
        self.switch = box
        self._head.addWidget(box, 0, Qt.AlignVCenter)

    def set_active(self, on: bool):
        """Switched off: only the header, which cannot be opened (there is nothing in
        it); switched on: open or folded as the user left it."""
        if on == self._active:
            return
        self._active = on
        self.header.setEnabled(on)
        self.header.setCursor(Qt.PointingHandCursor if on else Qt.ArrowCursor)
        self._toggle(self.header.isChecked(), remember=False)

    def active(self) -> bool:
        return self._active

    def _toggle(self, open_: bool, remember: bool = True):
        shown = open_ and self._active
        self.body.setVisible(shown)
        self.header.setIcon(
            theme.icon(
                "chevron_down" if shown else "chevron_right", theme.current.muted, 14
            )
        )
        if remember:
            self._prefs.set_section_open(self._title, open_)
