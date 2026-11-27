from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ...project.figure_settings import STYLE_KEYS, FigureSettings
from ...support.font_library import FontLibrary
from ..fields.field import Field
from ..fields.field_factory import FieldFactory
from ..fields.font_field import FontField
from ..panels.field_visibility import FieldVisibility
from ..panels.figure_fields import FIELD_SETTINGS, OPTIONS, SECTIONS, SPECIAL_FIELDS
from ..step import Step
from ..theme_service import ThemeService
from ..views.qt_fonts import QtFonts


class StyleEditor(QWidget):
    """Edits the style of a FigureSettings with the fields of the settings panel, shown
    and hidden by the same rules. Emits ``changed`` with a new copy on every edit."""

    changed = Signal(object)

    def __init__(
        self,
        fonts: FontLibrary,
        qt_fonts: QtFonts,
        themes: ThemeService,
        parent=None,
    ):
        super().__init__(parent)
        self._factory = FieldFactory(
            {
                **SPECIAL_FIELDS,
                "font": partial(FontField, fonts=fonts, qt_fonts=qt_fonts),
            },
            themes,
        )
        self._visibility = FieldVisibility()
        self._s = FigureSettings()
        self._fields: dict[str, Field] = {}
        self._shown: dict[str, Any] = {}  # field values as last shown or emitted
        self._rows: dict[str, tuple[QFormLayout, QWidget]] = {}
        # each section: its title, its whole widget, its body and its switch
        self._sections: list[tuple[str, QWidget, QWidget, QCheckBox | None]] = []
        self._labels: list[QLabel] = []
        self._loading = True
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addLayout(self._build_kind())
        for step, title, names in SECTIONS:
            styled = [n for n in names if self._styled(n)]
            if step == Step.MINIATURE and styled:
                v.addWidget(self._build_section(title, styled))
        v.addStretch(1)
        self._line_up_labels()
        self._loading = False

    # region building
    @staticmethod
    def _styled(name: str) -> bool:
        """Tell whether every setting the field ``name`` sets is part of a style."""
        return all(k in STYLE_KEYS for k in FIELD_SETTINGS.get(name, (name,)))

    def _build_kind(self) -> QHBoxLayout:
        kind = self._factory.build("kind", OPTIONS["kind"], self._emit)
        self._fields["kind"] = kind
        row = QHBoxLayout()
        row.setSpacing(12)
        label = QLabel(kind.label)
        label.setObjectName("FormLabel")
        label.setToolTip(kind.tooltip)
        row.addWidget(label)
        row.addWidget(kind.widget, 1)
        self._labels.append(label)
        return row

    def _build_section(self, title: str, names: list[str]) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        head = QHBoxLayout()
        heading = QLabel(title)
        heading.setObjectName("SubHeading")
        head.addWidget(heading, 1)
        v.addLayout(head)
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        v.addWidget(body)
        switch = None
        for name in names:
            field = self._factory.build(name, OPTIONS[name], self._emit)
            self._fields[name] = field
            if field.switch is not None:
                switch = field.switch
                switch.setObjectName("SectionSwitch")
                switch.setCursor(Qt.CursorShape.PointingHandCursor)
                head.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
            if field.row is None:
                continue
            self._rows[name] = (form, field.row)
            self._labels += field.labels
            if not field.label:
                form.addRow(field.row)
                continue
            label = QLabel(field.label)
            label.setObjectName("FormLabel")
            label.setToolTip(field.tooltip)
            form.addRow(label, field.row)
            self._labels.append(label)
        self._sections.append((title, box, body, switch))
        return box

    def _line_up_labels(self) -> None:
        """Give the labels one width, so the fields form one column."""
        widest = max((label.sizeHint().width() for label in self._labels), default=0)
        for label in self._labels:
            label.setMinimumWidth(widest)

    # endregion

    # region values
    def set_settings(self, s: FigureSettings) -> None:
        """Show the style of ``s``."""
        self._loading = True
        try:
            self._s = s
            for field in self._fields.values():
                field.show(s)
            self._sync_visible()
            self._shown = self._read()
        finally:
            self._loading = False

    def settings(self) -> FigureSettings:
        """Return the settings shown, with the values of fields not edited as they
        were given (a widget may round them)."""
        read = self._read()
        changed = {k: v for k, v in read.items() if v != self._shown.get(k)}
        return replace(self._s, **changed)

    def field(self, name: str) -> Any:
        """Return the input widget of the setting ``name``."""
        for field in self._fields.values():
            if name in field.inputs:
                return field.inputs[name]
        raise KeyError(name)

    def set_installed_fonts(self, names) -> None:
        """List the fonts installed on this computer after the bundled ones."""
        font = self._fields["font"]
        assert isinstance(font, FontField)
        self._loading, loading = True, self._loading
        try:
            font.set_installed(names)
        finally:
            self._loading = loading

    def _read(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field in self._fields.values():
            values.update(field.read())
        return values

    def _value(self, name: str) -> Any:
        """Return the value the field ``name`` shows, or the setting's value when no
        field shows it."""
        field = self._fields.get(name)
        return field.value() if field is not None else getattr(self._s, name, None)

    def _sync_visible(self) -> None:
        for name, visible in self._visibility.shown(self._value).items():
            if name in self._rows:
                form, row = self._rows[name]
                form.setRowVisible(row, visible)
        token = self._value("kind") == "token"
        tab = not self._value("no_tab")
        for title, box, body, switch in self._sections:
            box.setVisible(self._visibility.section_applies(title, token, tab))
            body.setVisible(switch is None or switch.isChecked())

    def _emit(self, *_) -> None:
        if self._loading:
            return
        self._sync_visible()
        new = self.settings()
        self._shown = self._read()
        if new != self._s:
            self._s = new
            self.changed.emit(new)

    # endregion
