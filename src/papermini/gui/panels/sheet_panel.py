from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...output.sheet import (
    MAT_LABELS,
    PAPER_CHOICES,
    PAPER_LABELS,
    paper_size,
)
from ...project.sheet_settings import SheetSettings
from ..fields.combo_box import ComboBox
from ..fields.double_spin_box import DoubleSpinBox
from .section import Section


class SheetPanel(QScrollArea):
    """The Print sheet step's side panel: edits a SheetSettings (paper, layout and how
    the pieces are cut), says what is on the sheet, and prints or exports it. The
    copies of each figure are set on its card in the figure list."""

    changed = Signal(object)
    printClicked = Signal()
    exportClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SheetPanel")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(18, 16, 14, 16)
        lay.setSpacing(0)
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

        self.paper = ComboBox()
        for value in PAPER_CHOICES:
            self.paper.addItem(PAPER_LABELS[value], value)
        self.orientation = ComboBox()
        for text, value in (("Portrait", "portrait"), ("Landscape", "landscape")):
            self.orientation.addItem(text, value)
        self.fit_warning = QLabel()  # a figure too big for the paper
        self.fit_warning.setObjectName("WarnBox")
        self.fit_warning.setWordWrap(True)
        self.fit_warning.setTextFormat(Qt.RichText)
        options = SheetSettings.options()
        self.paper_w, self.paper_h = DoubleSpinBox(), DoubleSpinBox()
        for w in (self.paper_w, self.paper_h):
            w.setRange(*options["paper_width_mm"].widget)
            w.setDecimals(1)
            w.setSuffix(" mm")
        self.title = QLineEdit()
        self.margin = DoubleSpinBox()
        self.margin.setRange(*options["margin_mm"].widget)
        self.margin.setSuffix(" mm")
        self.gap = DoubleSpinBox()
        self.gap.setRange(*options["gap_mm"].widget)
        self.gap.setSuffix(" mm")
        self.cut = ComboBox()
        for text, value in (("By hand", "hand"), ("Machine", "machine")):
            self.cut.addItem(text, value)
        self.bleed = DoubleSpinBox()
        self.bleed.setRange(*options["bleed_mm"].widget)
        self.bleed.setSingleStep(0.1)
        self.bleed.setDecimals(1)
        self.bleed.setSuffix(" mm")
        self.marks = ComboBox()
        for text, value in (
            ("Corners", "corners"),
            ("Silhouette", "silhouette"),
            ("None", "none"),
        ):
            self.marks.addItem(text, value)
        self.cut_folds = QCheckBox(options["cut_folds"].label)
        self.mat = ComboBox()
        self.mat.addItem("Any size", "")
        for value, text in MAT_LABELS.items():
            self.mat.addItem(text, value)
        self.mat_warning = QLabel()  # the paper is bigger than the mat
        self.mat_warning.setObjectName("WarnBox")
        self.mat_warning.setWordWrap(True)

        self._rows = {}  # widget -> its form, to show or hide the row
        labels = []
        for heading, fields in (
            (
                "Paper and layout",
                (
                    ("paper", self.paper),
                    ("orientation", self.orientation),
                    ("paper_width_mm", self.paper_w),
                    ("paper_height_mm", self.paper_h),
                    ("", self.fit_warning),
                    ("title", self.title),
                    ("margin_mm", self.margin),
                    ("gap_mm", self.gap),
                ),
            ),
            (
                "Cutting",
                (
                    ("cut", self.cut),
                    ("bleed_mm", self.bleed),
                    ("marks", self.marks),
                    ("cut_folds", self.cut_folds),
                    ("mat", self.mat),
                    ("", self.mat_warning),
                ),
            ),
        ):
            box = Section(heading)
            form = QFormLayout(box.body)
            form.setContentsMargins(2, 0, 0, 0)
            form.setHorizontalSpacing(12)
            form.setVerticalSpacing(8)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for name, w in fields:
                if name:
                    w.setToolTip(options[name].tooltip)
                if name and w is not self.cut_folds:
                    form.addRow(options[name].label, w)
                    lab = form.labelForField(w)
                    lab.setObjectName("FormLabel")
                    lab.setToolTip(options[name].tooltip)
                    labels.append(lab)
                else:
                    form.addRow(w)
                self._rows[w] = form
            lay.addWidget(box)
        widest = max(lab.sizeHint().width() for lab in labels)
        for lab in labels:  # one column of fields across both groups
            lab.setMinimumWidth(widest)

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
        self.setWidget(body)

        self.paper.currentIndexChanged.connect(self._emit)
        self.orientation.currentIndexChanged.connect(self._emit)
        self.paper_w.valueChanged.connect(self._emit)
        self.paper_h.valueChanged.connect(self._emit)
        self.mat.currentIndexChanged.connect(self._emit)
        self.title.editingFinished.connect(self._emit)
        self.margin.valueChanged.connect(self._emit)
        self.gap.valueChanged.connect(self._emit)
        self.cut.currentIndexChanged.connect(self._emit)
        self.bleed.valueChanged.connect(self._emit)
        self.marks.currentIndexChanged.connect(self._emit)
        self.cut_folds.toggled.connect(self._emit)
        self._s = SheetSettings()
        self._loading = False
        self._sync_visible(self._s)
        self.set_fit_warning("")

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
        self.paper.setCurrentIndex(max(0, self.paper.findData(s.paper)))
        self.orientation.setCurrentIndex(
            max(0, self.orientation.findData(s.orientation))
        )
        self._show_size(s)
        self.mat.setCurrentIndex(max(0, self.mat.findData(s.mat or "")))
        self.title.setText(s.title)
        self.margin.setValue(s.margin_mm)
        self.gap.setValue(s.gap_mm)
        self.cut.setCurrentIndex(self.cut.findData(s.cut))
        self.bleed.setValue(s.bleed_mm)
        self.marks.setCurrentIndex(self.marks.findData(s.marks))
        self.cut_folds.setChecked(s.cut_folds)
        self._loading = False
        self._sync_visible(s)

    def _show_size(self, s: SheetSettings):
        """The custom size fields: the custom size, or the size of the paper chosen (in
        its orientation), where a switch to Custom starts."""
        w, h = paper_size(s.page, s.orientation)
        self._loading, loading = True, self._loading
        try:
            self.paper_w.setValue(w)
            self.paper_h.setValue(h)
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
        paper = self.paper.currentData()
        custom = paper == "custom"
        if custom and self._s.paper != "custom":
            self._show_size(self._s)  # (Custom starts at the paper chosen before)
        new = replace(
            self._s,
            paper=paper,
            orientation=self.orientation.currentData(),
            paper_width_mm=self.paper_w.value() if custom else None,
            paper_height_mm=self.paper_h.value() if custom else None,
            title=self.title.text(),
            margin_mm=self.margin.value(),
            gap_mm=self.gap.value(),
            cut=self.cut.currentData(),
            bleed_mm=self.bleed.value(),
            marks=self.marks.currentData(),
            cut_folds=self.cut_folds.isChecked(),
            mat=self.mat.currentData() or None,
        )
        if not custom:
            self._show_size(new)  # (where a later switch to Custom starts)
        self._sync_visible(new)
        if new != self._s:
            self._s = new
            self.changed.emit(new)
