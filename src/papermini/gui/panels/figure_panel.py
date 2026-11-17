from __future__ import annotations

import html
from dataclasses import replace
from typing import Any, ClassVar

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ... import fonts, remote, segment, sizes
from ... import token as tok
from ...settings import FigureSettings
from .. import theme
from ..fields.color_button import ColorButton
from ..fields.combo_box import ComboBox
from ..fields.double_spin_box import DoubleSpinBox
from ..fields.kind_choice import KindChoice
from ..fields.size_field import SizeField
from ..fields.slider_field import SliderField
from ..fields.spin_box import SpinBox
from ..widgets.elided_label import ElidedLabel
from .figure_fields import (
    KIND_SECTIONS,
    MINIATURE,
    MODEL_NAMES,
    MODEL_VALUES,
    MODELS,
    PER_IMAGE,
    PRINT,
    SECTIONS,
    SOURCE,
    STEP_HINTS,
    STEPS,
    SUBSECTIONS,
    TIPS,
    TOKEN_STEP_HINT,
    TOKEN_SWITCHES,
    TWINS,
    step_settings,
)
from .section import SUB_INDENT, Section


class FigurePanel(QScrollArea):
    """Edits a FigureSettings; emits ``changed`` with a new copy on every edit.
    Shows the groups of one workflow step at a time (``set_step``)."""

    changed = Signal(object)
    applyToAll = Signal(object)  # the settings to copy (those of the shown step)
    clearCrop = Signal()
    exportPiece = Signal()  # the Miniature step's Export button (SVG or PNG)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._s = FigureSettings()
        self._w: dict[str, Any] = {}
        self._shown: dict[str, Any] = {}  # widget values as last shown/emitted
        self._rows: dict[
            str, Any
        ] = {}  # name -> (form layout, row widget), to hide rows
        self._switches: dict[str, Any] = {}  # name -> Section whose header holds it
        self._invert: set = set()  # switches whose setting is the opposite
        self._resets: dict[str, Any] = {}  # name -> (button, fields it resets)
        self._loading = False
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(18, 16, 14, 16)
        lay.setSpacing(0)
        self.title = ElidedLabel(
            "No figure selected"
        )  # a long name never widens the panel
        self.title.setObjectName("PanelTitle")
        lay.addWidget(self.title)
        self.subtitle = QLabel("Settings for the selected figure")
        self.subtitle.setObjectName("PanelSub")
        lay.addWidget(self.subtitle)
        lay.addSpacing(10)
        self.step_hint = QLabel()
        self.step_hint.setObjectName("StepHint")
        self.step_hint.setWordWrap(True)
        lay.addWidget(self.step_hint)
        lay.addSpacing(8)

        # shown instead of the settings when no figure is selected
        self.empty_box = QWidget()
        self.empty_box.setObjectName("PanelEmpty")
        ev = QVBoxLayout(self.empty_box)
        ev.setContentsMargins(12, 0, 12, 0)
        ev.setSpacing(10)
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignCenter)
        self.empty_title = QLabel("No figure selected")
        self.empty_title.setObjectName("EmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_text = QLabel()
        self.empty_text.setObjectName("Muted")
        self.empty_text.setAlignment(Qt.AlignCenter)
        self.empty_text.setWordWrap(True)
        ev.addStretch(2)
        for w in (self.empty_icon, self.empty_title, self.empty_text):
            ev.addWidget(w)
        ev.addStretch(3)  # a little above the middle looks centred
        lay.addWidget(self.empty_box, 1)
        self.refresh_icons()

        sections = []
        self._section_steps = []
        self._section_titles = []
        extra_labels = []  # labels inside compound fields, lined up with the form labels

        forms, boxes, sub_labels = {}, {}, []
        # the Kind, above the groups of the Miniature step
        self.kind_row = QWidget()
        kh = QHBoxLayout(self.kind_row)
        kh.setContentsMargins(2, 0, 0, 12)
        kh.setSpacing(12)
        kind_label = QLabel("Kind")
        kind_label.setObjectName("FormLabel")
        kind_label.setToolTip(TIPS["kind"])
        kind = KindChoice()
        kind.setToolTip(TIPS["kind"])
        kind.valueChanged.connect(self._emit)
        kh.addWidget(kind_label)
        kh.addWidget(kind, 1)
        lay.addWidget(self.kind_row)
        self._w["kind"] = ("radio", kind)
        extra_labels.append(kind_label)
        for step, title, items in SECTIONS:
            box = Section(title, sub=title in SUBSECTIONS)
            boxes[title] = box
            sections.append(box)
            self._section_steps.append(step)
            self._section_titles.append(title)
            form = QFormLayout(box.body)
            form.setContentsMargins(2, 0, 0, 0)
            form.setHorizontalSpacing(12)
            form.setVerticalSpacing(8)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            forms[title] = form
            for name, label, kind, extra in items:
                if kind == "heading":
                    h = QLabel(label.upper())
                    h.setObjectName("SubHeading")
                    form.addRow(h)
                    self._rows[name] = (form, h)
                    continue
                if kind == "reset":
                    b = QPushButton(label)
                    b.setObjectName("ResetButton")
                    b.setToolTip(TIPS.get(name, ""))
                    b.clicked.connect(lambda _=False, names=extra: self._reset(names))
                    form.addRow(b)
                    self._rows[name] = (form, b)
                    self._resets[name] = (b, extra)
                    continue
                w = self._make(name, kind, extra)
                if kind in (
                    "switch",
                    "nolabel",
                    "tokentext",
                ):  # in the header, for the group
                    w.setObjectName("SectionSwitch")
                    w.setAccessibleName(label)
                    w.setToolTip(TIPS[name])
                    w.setCursor(Qt.PointingHandCursor)
                    box.set_switch(w)
                    self._switches[name] = box
                    continue
                self._rows[name] = (form, w)
                if kind == "size":  # brings its own labels
                    form.addRow(w)
                    extra_labels += w.labels
                    continue
                if name in TIPS:
                    w.setToolTip(TIPS[name])
                if kind == "b":
                    form.addRow(w)
                else:
                    form.addRow(label, w)
                    form.labelForField(w).setToolTip(TIPS.get(name, ""))
                    form.labelForField(w).setObjectName("FormLabel")
                    if title in SUBSECTIONS:
                        sub_labels.append(form.labelForField(w))
                if name == "font":  # a font this computer does not have
                    self.font_warning = QLabel()
                    self.font_warning.setObjectName("WarnBox")
                    self.font_warning.setWordWrap(True)
                    self.font_warning.setVisible(False)
                    form.addRow(self.font_warning)
                if name == "size":
                    # the size's squares and base, and a warning for a wide figure
                    self.size_hint = QLabel()
                    self.size_hint.setObjectName("Hint")
                    self.size_hint.setWordWrap(True)
                    form.addRow(self.size_hint)
                    self.size_warning = QLabel()
                    self.size_warning.setObjectName("WarnBox")
                    self.size_warning.setWordWrap(True)
                    self.size_warning.setVisible(False)
                    form.addRow(self.size_warning)
                if name == "model":
                    self.auto_hint = QLabel()
                    self.auto_hint.setWordWrap(True)
                    self.auto_hint.setObjectName("MethodBox")
                    self.auto_hint.setTextFormat(Qt.RichText)
                    self.auto_hint.setVisible(False)
                    form.addRow(self.auto_hint)
                    # the licence of a non-commercial model, while it is the one used
                    self.licence_hint = QLabel()
                    self.licence_hint.setWordWrap(True)
                    self.licence_hint.setObjectName("LicenceBox")
                    self.licence_hint.setTextFormat(Qt.RichText)
                    self.licence_hint.setVisible(False)
                    form.addRow(self.licence_hint)
                if name == "token_border_mm":  # curved text: the ring's least width
                    self.ring_hint = QLabel()
                    self.ring_hint.setWordWrap(True)
                    self.ring_hint.setObjectName("Hint")
                    self.ring_hint.setVisible(False)
                    form.addRow(self.ring_hint)
                if name == "tab_overlap_mm":
                    self.overlap_hint = QLabel()
                    self.overlap_hint.setWordWrap(True)
                    self.overlap_hint.setObjectName("Hint")
                    self.overlap_hint.setVisible(False)
                    form.addRow(self.overlap_hint)
            if title in SUBSECTIONS:  # at the end of its group, folded away with it
                box.parent_section = boxes[SUBSECTIONS[title]]
                forms[SUBSECTIONS[title]].addRow(box)
            else:
                lay.addWidget(box)

        labels = [
            lab
            for form, _ in self._rows.values()
            for lab in [form.labelForField(_)]
            if isinstance(lab, QLabel)
        ] + extra_labels
        widest = max((lab.sizeHint().width() for lab in labels), default=0)
        for lab in labels:  # one column of fields, also inside the indented sub-groups
            lab.setMinimumWidth(widest - (SUB_INDENT if lab in sub_labels else 0))
        self.sections = sections
        self.size_field = self._w["dimensions"][1]
        lay.addSpacing(12)
        self.apply_all = QPushButton("Apply to all figures")
        self.apply_all.clicked.connect(
            lambda: self.applyToAll.emit(self.step_settings())
        )
        lay.addWidget(self.apply_all)
        lay.addSpacing(8)
        self.export_piece = QPushButton(
            "Export…"
        )  # (Miniature step: this figure's piece)
        self.export_piece.setToolTip(
            "Save this figure as an SVG (the piece with its cut line, for Inkscape or a "
            "cutting machine) or a PNG (a picture of the piece, for a virtual tabletop)  "
            "(Ctrl+E)"
        )
        self.export_piece.setCursor(Qt.PointingHandCursor)
        self.export_piece.clicked.connect(self.exportPiece)
        lay.addWidget(self.export_piece)
        lay.addStretch()
        self.setWidget(body)
        self._empty = True
        self._min_width = self._widest_step()
        self.set_step(SOURCE)
        self.set_empty(True)

    def _widest_step(self) -> int:
        """The width that shows every control of every step, measured with each step's
        groups shown (hidden widgets do not count in a minimum size)."""
        body = self.widget()
        widths = []
        self._empty = False
        self._measuring = True  # (the groups of both kinds of figure)
        for box in self.sections:  # (a folded group still needs its room when opened)
            box.body.setVisible(True)
        for step in range(len(STEPS)):
            self._step = step
            self._sync_sections()
            body.layout().activate()
            widths.append(body.minimumSizeHint().width())
        self._measuring = False
        for box in self.sections:
            box._toggle(box.header.isChecked(), remember=False)
        frame = 2 * self.frameWidth() + self.verticalScrollBar().sizeHint().width()
        return max(widths) + frame

    def minimumSizeHint(self) -> QSize:
        """Never narrower than its widest step, so no control is cut off at the right
        (the header checkboxes are the first to go); the window keeps to this."""
        return QSize(self._min_width, super().minimumSizeHint().height())

    def set_empty(
        self, empty: bool, message: str = "Add images to see their settings here."
    ):
        """No figure selected: a clear message instead of a wall of disabled fields."""
        self._empty = empty
        for w in (self.title, self.subtitle, self.step_hint, self.apply_all):
            w.setVisible(not empty)
        self.export_piece.setVisible(not empty and self._step == MINIATURE)
        self.empty_box.setVisible(empty)
        self.empty_text.setText(message)
        self._sync_sections()

    def set_step(self, step: int):
        """Show the settings of one workflow step (SOURCE, MINIATURE or PRINT)."""
        self._step = step
        self.export_piece.setVisible(not self._empty and step == MINIATURE)
        self._sync_sections()
        self.verticalScrollBar().setValue(0)

    def step(self) -> int:
        return self._step

    def step_settings(self) -> set:
        """The settings shown now, minus the per-image ones "Apply to all" never copies."""
        return step_settings(self._step) - PER_IMAGE

    def is_token(self) -> bool:
        """Whether the figure shown is a token (its Kind field)."""
        return "kind" in self._w and self._w["kind"][1].value() == "token"

    def _sync_sections(self):
        kind = "token" if self.is_token() else "mini"
        if hasattr(self, "kind_row"):
            self.kind_row.setVisible(not self._empty and self._step == MINIATURE)
        for box, step, title in zip(
            self.sections, self._section_steps, self._section_titles
        ):
            box.setVisible(
                not self._empty
                and step == self._step
                and (
                    KIND_SECTIONS.get(title, kind) == kind
                    or getattr(self, "_measuring", False)
                )
            )
        self.step_hint.setText(
            TOKEN_STEP_HINT
            if self._step == MINIATURE and kind == "token"
            else STEP_HINTS[self._step]
        )
        names = {SOURCE: "source", MINIATURE: "miniature", PRINT: "size"}
        self.apply_all.setText(f"Apply {names[self._step]} settings to all figures")
        self.apply_all.setToolTip(
            "Copies the settings shown here to every figure"
            + {
                SOURCE: ", except the crop and mask file",
                MINIATURE: ", except the label",
                PRINT: ", except the copies",
            }[self._step]
        )

    def refresh_icons(self):
        self.empty_icon.setPixmap(theme.pixmap("sliders", theme.current.muted, 40))
        if hasattr(self, "size_field"):
            self.size_field.refresh_icons()

    # ----------------------------------------------------------------- widgets
    def _make(self, name: str, kind: str, extra):
        if kind == "f":
            lo, hi, step, dec, suffix = extra
            w = DoubleSpinBox()
            w.setRange(lo, hi)
            w.setSingleStep(step)
            w.setDecimals(dec)
            w.setSuffix(suffix)
            w.setKeyboardTracking(False)
            w.valueChanged.connect(self._emit)
        elif kind == "i":
            lo, hi, step, suffix = extra
            w = SpinBox()
            w.setRange(lo, hi)
            w.setSingleStep(step)
            w.setSuffix(suffix)
            w.setKeyboardTracking(False)
            w.valueChanged.connect(self._emit)
        elif kind == "slider":
            lo, hi, slider_hi, suffix, auto = extra
            w = SliderField(lo, hi, slider_hi, suffix, auto)
            w.valueChanged.connect(self._emit)
        elif kind == "b":
            w = QCheckBox({n: l for _, _, its in SECTIONS for n, l, *_ in its}[name])
            w.toggled.connect(self._emit)
        elif kind == "switch":
            w = QCheckBox()  # ticked = the group is on, whatever the setting is called
            w.toggled.connect(self._emit)
            if extra == "invert":
                self._invert.add(name)
        elif kind == "size":
            w = SizeField()
            w.valueChanged.connect(self._emit)
        elif kind == "c":
            w = ComboBox()
            for item in extra:
                value, text = item if isinstance(item, tuple) else (item, item)
                w.addItem(text, value)
            w.currentIndexChanged.connect(self._emit)
        elif kind == "font":
            w = ComboBox()
            w.setMaxVisibleItems(16)
            for f in fonts.bundled():
                self._add_font(w, f.name)
            w.currentIndexChanged.connect(self._emit)
        elif kind == "s":
            w = QLineEdit()
            w.setPlaceholderText("the label (or file name)")
            w.editingFinished.connect(self._emit)
        elif kind == "col":
            w = ColorButton()
            w.colorChanged.connect(self._emit)
        elif kind == "model":
            w = ComboBox()
            w.setEditable(True)
            w.addItems([MODEL_NAMES.get(m, m) for m in MODELS])
            w.activated.connect(self._emit)
            w.lineEdit().editingFinished.connect(self._emit)
        elif kind == "file":
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit()
            edit.setPlaceholderText("choose a mask image (white = figure)")
            edit.editingFinished.connect(self._emit)
            b = QToolButton()
            b.setText("…")
            b.clicked.connect(lambda: self._browse_mask(edit))
            h.addWidget(edit)
            h.addWidget(b)
            w.edit = edit
        elif kind == "crop":
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit()
            edit.setPlaceholderText("whole image - drag a box on it")
            edit.editingFinished.connect(self._emit)
            b = QToolButton()
            b.setText("Clear")
            b.clicked.connect(lambda: (edit.clear(), self._emit()))
            h.addWidget(edit)
            h.addWidget(b)
            w.edit = edit
        elif kind == "tokenarea":
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit()
            edit.setPlaceholderText("whole figure, fitted - drag it in the view")
            edit.editingFinished.connect(self._emit)
            b = QToolButton()
            b.setText("Clear")
            b.clicked.connect(lambda: (edit.clear(), self._emit()))
            h.addWidget(edit)
            h.addWidget(b)
            w.edit = edit
        elif kind in ("label", "tlabel"):
            w = QLineEdit()
            w.editingFinished.connect(self._emit)
        elif kind == "tokentext":
            # not a setting of its own: unticked means token_text "none" (see _read)
            w = QCheckBox()
            w.toggled.connect(self._emit)
            self.token_text_switch = w
            return w
        elif kind == "nolabel":
            # not a setting of its own: unticked means label "" (see _read)
            w = QCheckBox()
            w.toggled.connect(self._emit)
            self.label_switch = w
            return w
        else:  # pragma: no cover
            raise ValueError(kind)
        self._w[name] = (kind, w)
        return w

    def _browse_mask(self, edit: QLineEdit):
        f, _ = QFileDialog.getOpenFileName(
            self, "Mask image (white = figure)", "", remote.IMAGE_FILTER
        )
        if f:
            edit.setText(f)
            self._emit()

    # ----------------------------------------------------------------- values
    def set_settings(self, s: FigureSettings, title: str = "", stem: str = ""):
        self._loading = True
        try:
            self._s = s
            self.title.setText(title)
            for name, (kind, w) in self._w.items():
                if kind == "size":
                    w.set_value(s.height_mm, s.width_mm)
                    continue
                v = getattr(s, TWINS.get(name, name))
                if kind in ("f", "i", "radio") or kind == "slider":
                    w.setValue(v)
                elif kind == "b":
                    w.setChecked(bool(v))
                elif kind == "switch":
                    w.setChecked(bool(v) != (name in self._invert))
                elif kind == "c":
                    w.setCurrentIndex(max(0, w.findData(v)))
                elif kind == "font":
                    self._show_font(v)
                elif kind == "s":
                    w.setText(v or "")
                elif kind == "col":
                    w.set_color(v)
                elif kind == "tlabel":
                    w.setPlaceholderText(stem or "file name")
                    w.setText(v or "")
                elif kind == "tokenarea":
                    w.edit.setText(_crop_text(v))
                elif kind == "model":
                    w.setCurrentText(MODEL_NAMES.get(v, v))
                elif kind == "file":
                    w.edit.setText(v or "")
                elif kind == "crop":
                    w.edit.setText(_crop_text(v))
                elif kind == "label":
                    w.setPlaceholderText(stem or "file name")
                    self.label_switch.setChecked(v != "")
                    w.setText(v or "")
            self.token_text_switch.setChecked(s.token_text != "none")
            self._sync_visible()
            self.set_empty(False)
            self._shown = self._read()
        finally:
            self._loading = False

    def settings(self) -> FigureSettings:
        """Current settings: fields whose widget was not touched keep their exact
        value (a loaded 42.25 mm or dpi 3000 is not rounded/clamped by a widget)."""
        read = self._read()
        changed = {k: v for k, v in read.items() if v != self._shown.get(k)}
        return replace(self._s, **changed)

    def _read(self) -> dict[str, Any]:
        vals: dict[str, Any] = {}
        token = self.is_token()
        for name, (kind, w) in self._w.items():
            # a setting with a field for each kind of figure: read the one in use
            if (name in TWINS.values() and token) or (name in TWINS and not token):
                continue
            if kind in ("f", "i"):
                vals[name] = w.value()
            elif kind == "size":
                vals["height_mm"], vals["width_mm"] = w.value()
            elif kind == "slider":
                vals[name] = w.value()
            elif kind == "b":
                vals[name] = w.isChecked()
            elif kind == "switch":
                vals[name] = w.isChecked() != (name in self._invert)
            elif kind in ("c", "font"):
                vals[name] = w.currentData()
            elif kind == "radio":
                vals[name] = w.value()
            elif kind == "s":
                vals[name] = w.text().strip() or None
            elif kind == "col":
                vals[name] = w.color()
            elif kind == "tlabel":
                vals[TWINS[name]] = w.text().strip() or None
            elif kind == "tokenarea":
                vals[name] = _parse_area_text(w.edit.text(), self._s.token_area)
            elif kind == "model":
                text = w.currentText().strip() or "auto"
                vals[name] = MODEL_VALUES.get(text, text)
            elif kind == "file":
                vals[name] = w.edit.text().strip() or None
            elif kind == "crop":
                vals[name] = _parse_crop_text(w.edit.text(), self._s.crop)
            elif kind == "label":
                vals[name] = (
                    ""
                    if not self.label_switch.isChecked()
                    else (w.text().strip() or None)
                )
        if not self.token_text_switch.isChecked():
            vals["token_text"] = "none"
        return vals

    OVERLAP_HINTS: ClassVar = {
        "unused": "No effect on this figure: its bottom is wider than the tab, so the overlap "
        "is already inside the outline. It only matters for narrow feet or tails.",
        "narrow": "Only {joint:.1f} mm of paper joins the tab to the figure (its bottom is "
        "narrow), which may tear when folded. Raise the overlap to strengthen it.",
    }

    def set_overlap_hint(self, kind=None, joint: float = 0.0):
        """Note under 'Overlap into figure': None, "unused" or "narrow" (with the joint width)."""
        show = (
            kind in self.OVERLAP_HINTS and self._w["no_tab"][1].isChecked()
        )  # (tab on)
        if show:
            self.overlap_hint.setText(self.OVERLAP_HINTS[kind].format(joint=joint))
        self.overlap_hint.setVisible(show)

    @staticmethod
    def auto_method_text(method: str) -> str:
        """What model "auto" picked for a figure, in words (the Mini's ``method``)."""
        if method == "alpha":
            chosen = "the image's own transparency"
        elif method == "mask":
            chosen = "your mask image file"
        else:
            chosen = f"{html.escape(method)} (the image has no transparency)"
        return f"<b>Chosen method:</b> {chosen}"

    def set_auto_method(self, method: str | None):
        """Note under 'Model': how "auto" found the selected figure (the method of its
        last build), or None while that is not known yet."""
        self._auto_method = method
        if method:
            self.auto_hint.setText(self.auto_method_text(method))
        self._sync_auto_hint()

    # ----------------------------------------------------------------- fonts
    def _add_font(self, w: QComboBox, name: str, missing: bool = False) -> None:
        w.addItem(f"{name} (not on this computer)" if missing else name, name)
        if not missing:  # (each font shown in itself)
            from ..views.drawing import qt_family

            w.setItemData(w.count() - 1, QFont(qt_family(name)), Qt.FontRole)

    def set_installed_fonts(self, names) -> None:
        """List the fonts installed on this computer (found in the background) after the
        bundled ones."""
        w = self._w["font"][1]
        current = w.currentData()
        self._loading, loading = True, self._loading
        try:
            bundled = [f.name for f in fonts.bundled()]
            while w.count() > len(bundled):  # (anything after them: listed again below)
                w.removeItem(w.count() - 1)
            new = [n for n in names if n not in bundled]
            if new:
                w.insertSeparator(w.count())
                for n in new:
                    self._add_font(w, n)
            self._installed_fonts = set(names)
            self._show_font(current)
        finally:
            self._loading = loading

    def _show_font(self, name: str) -> None:
        w = self._w["font"][1]
        i = w.findData(name)
        known = getattr(self, "_installed_fonts", None)
        if i < 0 and known is not None:  # (only once the installed fonts are known)
            self._add_font(w, name, missing=True)
            i = w.count() - 1
        elif i < 0:
            self._add_font(w, name)  # (shown as is until the scan says otherwise)
            i = w.count() - 1
        w.setCurrentIndex(i)
        missing = w.itemText(i).endswith("(not on this computer)")
        self.font_warning.setText(
            f"{name} is not on this computer: this figure prints in {fonts.DEFAULT}."
            if missing
            else ""
        )
        self.font_warning.setVisible(missing)

    def set_size_table(self, table: sizes.SizeTable, label: str = ""):
        """The project's creature size table and its name (its preset, or that it is the
        project's own), for the hint under Creature size."""
        self._size_table = table
        self._size_label = label
        self._sync_size_hint()

    def set_figure_width(self, width_mm: float | None):
        """The width the selected figure was built at (None while not known), for the
        warning when it is wider than its creature size's squares."""
        self._figure_width = width_mm
        self._sync_size_hint()

    def show_size(self, s: FigureSettings):
        """Show the settings after the window matched them to the creature size: a picked
        size's filled-in values, or Custom after a hand edit. Emits nothing."""
        self._loading = True
        try:
            self._s = s
            w = self._w["size"][1]
            w.setCurrentIndex(max(0, w.findData(s.size)))
            if s.size != sizes.CUSTOM:  # (Custom: leave the field being edited alone)
                self._w["dimensions"][1].set_value(s.height_mm, s.width_mm)
                for name in (
                    "tab_radius_mm",
                    "tab_width_mm",
                    "tab_height_mm",
                    "token_diameter_mm",
                ):
                    if name in self._w:
                        self._w[name][1].setValue(getattr(s, name))
            self._sync_visible()
            self._shown = self._read()
        finally:
            self._loading = False

    def _sync_size_hint(self):
        if not hasattr(self, "size_hint"):
            return
        table = getattr(self, "_size_table", sizes.BUILTIN)
        size = self._w["size"][1].currentData() or sizes.CUSTOM
        text = sizes.footprint_text(size, table)
        label = getattr(self, "_size_label", "")
        self.size_hint.setText(f"{text} · {label}" if text and label else text)
        self.size_hint.setVisible(bool(text))
        warning = (
            ""
            if self.is_token()
            else sizes.width_warning(
                size, getattr(self, "_figure_width", None) or 0, table
            )
        )
        self.size_warning.setText(warning)
        self.size_warning.setVisible(bool(warning))

    def _sync_auto_hint(self):
        model = self._w["model"][1].currentText().strip()
        method = getattr(self, "_auto_method", None)
        self.auto_hint.setVisible(bool(method) and model == "auto")
        used = (
            method if model == "auto" else model
        )  # (auto: what it picked, once known)
        if used and segment.non_commercial(used):
            self.licence_hint.setText(
                f"<b>Non-commercial use only.</b> You are responsible for not using "
                f"{html.escape(segment.ONNX_MODELS[used]['title'])} commercially, for "
                f"example to make minis you sell. For commercial use, pick birefnet or "
                f"birefnet-lite."
            )
            self.licence_hint.setToolTip(segment.licence_notice(used))
        self.licence_hint.setVisible(bool(used) and segment.non_commercial(used))

    def set_auto_fill_gaps(self, px: int):
        """The gap filling the last build picked automatically, shown while Auto is on."""
        self._w["fill_gaps"][1].set_auto_value(px)

    def set_aspect(self, aspect):
        """The selected figure's own width / height, for the linked size fields."""
        self.size_field.set_aspect(aspect)

    def set_crop(self, crop):
        """Crop set by dragging a box on the Source view."""
        self._w["crop"][1].edit.setText(_crop_text(crop))
        self._emit()

    def set_token_area(self, area):
        """A token's framing set by dragging the figure in the Miniature view."""
        self._w["token_area"][1].edit.setText(_crop_text(area))
        self._emit()

    def is_shown(self, name: str) -> bool:
        """Whether a field is shown; for a group's switch, whether it can be used."""
        if name in self._switches:  # usable unless the group it is inside is off
            box = self._switches[name].parent_section
            return box is None or box.active()
        form, w = self._rows[name]
        return form.isRowVisible(w)

    def _sync_visible(self):
        """Only show the fields that do something in the current state; a group that
        is switched off shows only its header."""
        val = lambda n: self._w[n][1].currentData()
        tab = self._w["no_tab"][1].isChecked()  # (the switch is "print a tab")
        label = tab and self.label_switch.isChecked()
        # (a mini always has its outline, the margin, and its cut line: only a token's can
        # be switched off)
        token = self.is_token()
        for name in TOKEN_SWITCHES:
            self._switches[name].switch.setVisible(token)
        always = set() if token else {self._switches[n] for n in TOKEN_SWITCHES}
        for box in set(self._switches.values()):  # off: only the header, not openable
            box.set_active(box.switch.isChecked() or box in always)
        square = val("tab_shape") == "square"
        double = self._w["double_sided"][1].isChecked()
        model = self._w["model"][1].currentText().strip()
        show = {
            "mask": MODEL_VALUES.get(model, model) == "mask",
            "min_area": self._w["keep_all"][1].isChecked(),
            "margin_color": val("margin_fill") == "color",
            "tab_shape": tab,
            "tab_width_mm": tab and square,
            "tab_height_mm": tab and square,
            "tab_radius_mm": tab and not square,
            "tab_overlap_mm": tab,
            "fold_mm": tab,
            "tab_color": tab,
            "label": label,
            "label_size_mm": label,
            "label_color": label,
            "back": double,
            "back_color": double and val("back") != "mirror",
            "back_text": double and val("back") in ("text", "text_number"),
            "back_text_color": double
            and val("back") in ("text", "number", "text_number"),
            "tab_back": double,
        }
        grey = self._w["greyscale"][1].isChecked()
        show["saturation"] = show["hue"] = not grey
        # a token: its own fields instead of the mini's; the margin makes its outline
        text = val("token_text") if self.token_text_switch.isChecked() else "none"
        show.update(
            {
                "dimensions": not token,
                "token_diameter_mm": token,
                "token_fill_color": val("token_fill") == "color",
                "token_text_style": text != "none",
                "token_text_mm": text != "none",
                "token_label": text in ("label", "label_number"),
                "token_text_color": text != "none",
                "no_smooth": not token,
                "simplify_mm": not token,
            }
        )
        self._sync_ring(
            token and text != "none" and val("token_text_style") == "curved"
        )
        for name, visible in show.items():
            form, w = self._rows[name]
            form.setRowVisible(w, visible)
        read, d = self._read(), FigureSettings()
        for b, names in self._resets.values():  # only when there is something to reset
            b.setEnabled(any(read[n] != getattr(d, n) for n in names))
        if not tab:
            self.overlap_hint.setVisible(False)
        self._sync_sections()
        self._sync_auto_hint()
        self._sync_size_hint()

    def _sync_ring(self, curved: bool) -> None:
        """Curved text needs a ring at least this wide: the field stops there, and says so."""
        w = self._w["token_border_mm"][1]
        least = tok.min_ring_mm(self._w["token_text_mm"][1].value()) if curved else 0.0
        w.blockSignals(True)
        w.setMinimum(least)
        w.blockSignals(False)
        self.ring_hint.setText(
            f"Curved text of this size needs a ring of at least {least:g} "
            "mm. A smaller text size allows a narrower ring."
            if curved
            else ""
        )
        self.ring_hint.setVisible(curved)

    def _sync_twins(self, s: FigureSettings) -> None:
        """Show ``s`` in the field of the kind not in use too (the label has a field for
        minis and one for tokens), so switching kind keeps what was typed."""
        if self.is_token():
            self._w["label"][1].setText(s.label or "")
            self.label_switch.setChecked(s.label != "")
        else:
            self._w["token_label"][1].setText(s.label or "")

    def _reset(self, names):
        """Put ``names`` back to their defaults, as one change."""
        d = FigureSettings()
        self._loading = True
        try:
            for name in names:
                kind, w = self._w[name]
                if kind in ("b", "switch"):
                    w.setChecked(bool(getattr(d, name)) != (name in self._invert))
                else:
                    w.setValue(getattr(d, name))
        finally:
            self._loading = False
        self._emit()

    def _emit(self, *_):
        if self._loading:
            return
        self._sync_visible()
        new = self.settings()
        self._loading = True
        try:
            self._sync_twins(new)
        finally:
            self._loading = False
        self._shown = self._read()
        if new != self._s:
            self._s = new
            self.changed.emit(new)


def _crop_text(crop) -> str:
    if crop is None or crop == "":
        return ""
    if isinstance(crop, str):
        return crop
    return ", ".join(f"{v:g}" for v in crop)


def _parse_area_text(text: str, old):
    """A token area typed in its field (None when empty; the old one when it cannot be read)."""
    if not text.strip():
        return None
    try:
        return tok.parse_area(text)
    except ValueError:
        return old


def _parse_crop_text(text: str, old):
    text = text.strip()
    if not text:
        return None
    try:
        vals = [float(v) for v in text.replace(" ", "").split(",")]
    except ValueError:
        return old
    return vals if len(vals) == 4 else old
