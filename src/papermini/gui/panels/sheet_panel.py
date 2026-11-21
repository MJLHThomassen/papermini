from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import Any, ClassVar, cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...output.paper_sizes import PaperSizes
from ...project.sheet_settings import SheetSettings
from ..fields.choice_field import ChoiceField
from ..fields.field import Field
from ..fields.field_factory import FieldFactory, FieldMaker
from ..preferences import Preferences
from .section import Section


class SheetPanel(QScrollArea):
    """The Print sheet step's side panel: edits a SheetSettings (paper, layout and how
    the pieces are cut), says what is on the sheet, and prints or exports it. The
    copies of each figure are set on its card in the figure list."""

    changed = Signal(object)
    printClicked = Signal()
    exportClicked = Signal()

    # its sections, each with its settings in order
    SECTIONS: ClassVar[tuple[tuple[str, tuple[str, ...]], ...]] = (
        (
            "Paper and layout",
            (
                "paper",
                "orientation",
                "paper_width_mm",
                "paper_height_mm",
                "title",
                "margin_mm",
                "gap_mm",
            ),
        ),
        ("Cutting", ("cut", "bleed_mm", "marks", "cut_folds", "mat")),
    )
    # the fields not built from their option alone
    SPECIAL_FIELDS: ClassVar[dict[str, FieldMaker]] = {
        "mat": partial(ChoiceField, none="Any size"),
    }

    def __init__(self, prefs: Preferences, parent=None):
        super().__init__(parent)
        self._prefs = prefs
        self.setObjectName("SheetPanel")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._factory = FieldFactory(self.SPECIAL_FIELDS)
        self._fields: dict[str, Field] = {}
        self._rows: dict[QWidget, QFormLayout] = {}  # widget -> its form, to hide rows
        self._s = SheetSettings()
        self._loading = True
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(18, 16, 14, 16)
        lay.setSpacing(0)
        self._build_header(lay)
        self._build_sections(lay)
        self._build_warnings()
        self._build_buttons(lay)
        self.setWidget(body)
        self.paper = self._field("paper")
        self.orientation = self._field("orientation")
        self.paper_w = self._field("paper_width_mm")
        self.paper_h = self._field("paper_height_mm")
        self.title = self._field("title")
        self.margin = self._field("margin_mm")
        self.gap = self._field("gap_mm")
        self.cut = self._field("cut")
        self.bleed = self._field("bleed_mm")
        self.marks = self._field("marks")
        self.cut_folds = self._field("cut_folds")
        self.mat = self._field("mat")
        self._loading = False
        self._sync_visible(self._s)
        self.set_fit_warning("")

    # region building
    def _build_header(self, lay: QVBoxLayout) -> None:
        title = QLabel("Print sheet")
        title.setObjectName("PanelTitle")
        lay.addWidget(title)
        sub = QLabel("Settings for the whole sheet")
        sub.setObjectName("PanelSub")
        lay.addWidget(sub)
        lay.addSpacing(10)
        hint = QLabel(
            "Paper, layout and how the pieces are cut. Set how many of each "
            "figure go on the sheet on its card in the list on the left."
        )
        hint.setObjectName("StepHint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addSpacing(8)

    def _build_sections(self, lay: QVBoxLayout) -> None:
        options = SheetSettings.options()
        labels = []
        for heading, names in self.SECTIONS:
            box = Section(self._prefs, heading)
            for name in names:
                field = self._factory.build(name, options[name], self._emit)
                self._fields[name] = field
                row = field.widget
                if field.label:
                    box.form.addRow(field.label, row)
                    label = box.form.labelForField(row)
                    assert isinstance(label, QLabel)
                    label.setObjectName("FormLabel")
                    label.setToolTip(field.option.tooltip)
                    labels.append(label)
                else:
                    box.form.addRow(row)
                self._rows[row] = box.form
            lay.addWidget(box)
        widest = max(label.sizeHint().width() for label in labels)
        for label in labels:  # one column of fields across both sections
            label.setMinimumWidth(widest)

    def _build_warnings(self) -> None:
        self.fit_warning = self._warning_under("paper_height_mm")  # a figure too big
        self.fit_warning.setTextFormat(Qt.RichText)
        self.mat_warning = self._warning_under("mat")  # the paper is bigger than it

    def _warning_under(self, name: str) -> QLabel:
        """Add a warning in the row under the field ``name``."""
        row = self._field(name)
        form = self._rows[row]
        index = cast(tuple[int, Any], form.getWidgetPosition(row))[0]
        warning = QLabel()
        warning.setObjectName("WarnBox")
        warning.setWordWrap(True)
        form.insertRow(index + 1, warning)
        self._rows[warning] = form
        return warning

    def _build_buttons(self, lay: QVBoxLayout) -> None:
        lay.addSpacing(12)
        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        lay.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.print_btn = QPushButton("Print…")
        self.print_btn.setToolTip("Print the sheet at its real size  (Ctrl+Shift+P)")
        self.print_btn.clicked.connect(self.printClicked)
        self.export_btn = QPushButton("Export…")
        self.export_btn.setProperty("primary", True)
        self.export_btn.setToolTip(
            "Save the sheet to print (PDF) and, cut by machine, the cut "
            "file (SVG): pick the folder and what to save  (Ctrl+P)"
        )
        self.export_btn.clicked.connect(self.exportClicked)
        for b in (self.print_btn, self.export_btn):
            b.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(b, 1)
        lay.addLayout(buttons)
        lay.addStretch()

    # endregion

    def _field(self, name: str) -> Any:
        """Return the input widget of the setting ``name``."""
        return self._fields[name].widget

    def set_fit_warning(self, text: str) -> None:
        """Say which figures are too big for the paper, under Paper (rich text; "": they
        all fit)."""
        self.fit_warning.setText(text)
        self._rows[self.fit_warning].setRowVisible(self.fit_warning, bool(text))

    def is_shown(self, w: QWidget) -> bool:
        return self._rows[w].isRowVisible(w)

    def set_settings(self, s: SheetSettings):
        self._loading = True
        self._s = s
        for name, field in self._fields.items():
            if name not in ("paper_width_mm", "paper_height_mm"):
                field.show(s)
        self._show_size(s)
        self._loading = False
        self._sync_visible(s)

    def _show_size(self, s: SheetSettings):
        """The custom size fields: the custom size, or the size of the paper chosen (in
        its orientation), where a switch to Custom starts."""
        w, h = PaperSizes.size(s.page, s.orientation)
        self._loading, loading = True, self._loading
        try:
            self._fields["paper_width_mm"].set_value(w)
            self._fields["paper_height_mm"].set_value(h)
        finally:
            self._loading = loading

    def _sync_visible(self, s: SheetSettings):
        """Orientation for a named paper, the size fields for a custom one; bleed, marks,
        the cut file and the mat only when cut by machine, with the mat's warning."""
        custom = s.paper == "custom"
        machine = s.machine
        for w, shown in (
            (self.orientation, not custom),
            (self.paper_w, custom),
            (self.paper_h, custom),
            (self.bleed, machine),
            (self.marks, machine),
            (self.cut_folds, machine),
            (self.mat, machine),
        ):
            self._rows[w].setRowVisible(w, shown)
        warning = s.mat_warning()
        self.mat_warning.setText(
            f"{warning} Use a bigger mat or smaller paper." if warning else ""
        )
        self._rows[self.mat_warning].setRowVisible(self.mat_warning, bool(warning))

    def _emit(self, *_):
        if self._loading:
            return
        custom = self._fields["paper"].value() == "custom"
        if custom and self._s.paper != "custom":
            self._show_size(self._s)  # (Custom starts at the paper chosen before)
        values = {}
        for field in self._fields.values():
            values.update(field.read())
        if not custom:
            values["paper_width_mm"] = values["paper_height_mm"] = None
        new = replace(self._s, **values)
        if not custom:
            self._show_size(new)  # (where a later switch to Custom starts)
        self._sync_visible(new)
        if new != self._s:
            self._s = new
            self.changed.emit(new)
