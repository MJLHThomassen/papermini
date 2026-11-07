"""Settings panels: per-figure options and sheet options."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict

from PySide6.QtCore import QLocale, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QSlider, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from .. import remote
from ..settings import FigureSettings, SheetSettings
from . import prefs, theme

# value -> what the (editable) model box shows, where they differ
MODEL_NAMES = {"mask": "mask image file"}
MODEL_VALUES = {v: k for k, v in MODEL_NAMES.items()}
MODELS = ["auto", "rmbg-1.4", "birefnet", "birefnet-lite", "alpha", "mask"]

# Groups follow the workflow: how big and how many, how the figure is found,
# the outline/cut line around it, the stand tab, its label, and the back.
# (field, label, kind, extra) - kind: f=float, i=int, b=bool, c=choice, s=str,
# col=colour, slider=int slider (lo, hi, slider_hi, suffix, auto checkbox),
# heading=sub-heading inside a group (not a setting)
SECTIONS = [
    ("Print", [
        ("height_mm", "Figure height", "f", (5, 400, 1, 2, " mm")),
        ("copies", "Copies on sheet", "i", (0, 999, 1, "")),
        ("dpi", "Image resolution", "i", (72, 2400, 50, " dpi")),
    ]),
    ("Background removal", [
        ("model", "Model", "model", None),
        ("mask", "Mask image file", "file", None),
        ("crop", "Crop", "crop", None),
        ("strength", "Strength", "slider", (0, 254, 254, "", False)),
        ("fill_gaps", "Gap filling", "slider", (0, 1000, 40, " px", True)),
        ("keep_all", "Keep detached parts", "b", None),
        ("min_area", "Min. part area", "i", (0, 10_000_000, 100, " px")),
    ]),
    ("Outline and cut line", [
        ("margin_mm", "Margin", "f", (0, 15, 0.1, 2, " mm")),
        ("margin_fill", "Margin fill type", "c", [("color", "Colour"), ("image", "Original image")]),
        ("margin_color", "Margin fill colour", "col", None),
        ("smooth_mm", "Outline smoothing", "f", (0, 5, 0.1, 2, " mm")),
        ("_cut_line", "Cut line", "heading", None),
        ("no_smooth", "Straight segments only (no curves)", "b", None),
        ("simplify_mm", "Simplify", "f", (0.01, 2, 0.05, 3, " mm")),
        ("cutter", "Cutting-machine style (red hairline)", "b", None),
        ("bleed_mm", "Bleed", "f", (0, 5, 0.1, 1, " mm")),
        ("cut_color", "Colour", "col", None),
        ("cut_width_mm", "Width", "f", (0.01, 2, 0.05, 2, " mm")),
    ]),
    ("Tab", [
        ("no_tab", "No tab", "b", None),
        ("tab_shape", "Shape", "c", [("square", "Square (stand)"),
                                     ("round", "Round (base)")]),
        ("tab_width_mm", "Width", "f", (2, 200, 1, 1, " mm")),
        ("tab_radius_mm", "Radius", "f", (1, 100, 0.5, 1, " mm")),
        ("tab_height_mm", "Height", "f", (1, 100, 0.5, 1, " mm")),
        ("tab_overlap_mm", "Overlap into figure", "f", (0, 30, 0.5, 1, " mm")),
        ("fold_mm", "Fold above lowest point", "f", (0, 20, 0.1, 1, " mm")),
        ("tab_color", "Fill colour", "col", None),
        ("_tab_label", "Label", "heading", None),
        ("no_label", "No label", "nolabel", None),
        ("label", "Text", "label", None),
        ("label_size_mm", "Size", "f", (0.5, 20, 0.1, 1, " mm")),
        ("label_color", "Colour", "col", None),
    ]),
    ("Double-sided", [
        ("double_sided", "Print a back side (fold over the top)", "b", None),
        ("back", "Back side", "c", [("mirror", "Mirrored drawing"), ("blank", "Blank"),
                                    ("text", "Text")]),
        ("back_color", "Back colour", "col", None),
        ("back_text", "Back text", "s", None),
        ("back_text_color", "Back text colour", "col", None),
    ]),
]

TIPS = {
    "height_mm": "Height of the drawn figure on paper, without margin and tab.",
    "copies": "How many of this figure go on the print sheet.",
    "dpi": "Resolution of the embedded artwork. 300 dpi suits most printers.",
    "model": "How the figure is separated from the background.\n"
             "auto: the PNG's transparency if it has any, else rmbg-1.4.\n"
             "rmbg-1.4: BRIA's background removal model, non-commercial use only\n"
             "(downloads 176 MB once).\n"
             "birefnet: sharper edges and fine detail, slower, free for any use\n"
             "(downloads 930 MB once).\n"
             "birefnet-lite: a smaller, faster BiRefNet (downloads 215 MB once).\n"
             "alpha: the PNG's own transparency (no file needed).\n"
             "mask image file: your own black-and-white mask (white = figure).\n"
             "You can also type the path of your own .onnx model.",
    "mask": "Your own mask image: white = figure, black = background, same picture size.",
    "crop": "Only this region is searched for the figure (x0,y0,x1,y1, fractions or px).\n"
            "Drag a box on the Source / crop tab to set it.",
    "strength": "How sure the model must be that a pixel belongs to the figure (0-254).\n"
                "Lower keeps faint pencil lines; higher removes more background.",
    "fill_gaps": "Fills gaps and notches in the outline up to this size (0 = off).\n"
                 "Auto scales with the image: 9 px at 1400 px.",
    "keep_all": "Keep separate parts (a floating prop) and join them with bridges,\n"
                "instead of keeping only the largest part.",
    "min_area": "With 'keep detached parts': smaller parts than this are dropped as specks.",
    "margin_mm": "Distance between the drawing and the cut line. The margin is filled\n"
                 "with a colour or the original image (see Margin fill type).",
    "margin_fill": "What fills the margin, the strip between the cut-out drawing and its\n"
                   "cut line:\n"
                   "Colour: one solid colour (Margin fill colour).\n"
                   "Original image: the picture around the figure, as it is in the image.",
    "margin_color": "The colour of the margin between the drawing and the cut line.",
    "smooth_mm": "Rounds the outline; higher values give a calmer cut line.",
    "no_smooth": "Cut line made of straight segments instead of smooth curves.",
    "simplify_mm": "How far the cut line may deviate to use fewer points.",
    "cutter": "Red 0.1 mm cut line, which many cutting machines treat as the cut layer.",
    "bleed_mm": "Prints the background this far beyond the cut line, so a slightly misaligned\n"
                "machine cut never shows a white edge. The colour at the edge (margin, tab or\n"
                "back colour) is extended.",
    "cut_color": "Colour of the cut line.",
    "cut_width_mm": "Width of the printed cut line.",
    "no_tab": "No fold-over stand tab (e.g. for slotted or magnetic bases).",
    "tab_shape": "Square: a tab to slot into a (3D printed) stand.\n"
                 "Round: a half disc that folds out into a round base. On a double-sided\n"
                 "mini the two halves fold out to opposite sides and form a full circle.",
    "tab_width_mm": "Width of the square tab.",
    "tab_radius_mm": "Radius of the round tab (a half disc). 12.5 mm makes a 25 mm base.",
    "tab_height_mm": "How far the square tab reaches below the fold line.",
    "tab_overlap_mm": "How far the tab reaches up past the fold line. It only adds paper where "
                      "the figure's bottom is narrower than the tab (feet, a tail), to "
                      "strengthen the joint.",
    "fold_mm": "Where the tab folds, measured up from the figure's lowest point.",
    "no_label": "A plain tab in the fill colour, without text.",
    "label": "Text printed on the tab (empty = the file name). Also the default back text.",
    "label_size_mm": "Largest text size; long labels shrink to fit the tab.",
    "label_color": "Colour of the tab label.",
    "tab_color": "Colour of the tab (everything below the fold), behind the label.\n"
                 "Independent of the margin colour; e.g. grass green for a plain tab.",
    "double_sided": "Print front and back joined at a fold above the head; glue them back to back.",
    "back": "mirror: the drawing seen from behind; blank: plain paper; "
            "text: plain paper with text (a name or stats).",
    "back_text": "Text for the back (empty = the tab label). It is sized to fit the body.",
    "back_color": "Colour of a blank or text back (the back tab keeps the tab's fill colour).",
    "back_text_color": "Colour of the back text.",
}


class _WheelGuard:
    """Only react to the mouse wheel when focused, so scrolling the settings
    panel never changes a value by accident (and the panel scrolls instead)."""

    def _init_guard(self):
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class SpinBox(_WheelGuard, QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_guard()
        self.setKeyboardTracking(False)
        self.lineEdit().setTextMargins(5, 0, 0, 0)  # line up with combo box text


class Slider(_WheelGuard, QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._init_guard()


class SliderField(QWidget):
    """A slider with a number box beside it for exact values. With ``auto`` an "Auto"
    checkbox goes underneath (so all sliders line up): while it is ticked the slider shows
    the automatic value greyed out and ``value()`` is None."""

    valueChanged = Signal()

    def __init__(self, lo: int, hi: int, slider_hi: int, suffix: str = "", auto: bool = False,
                 auto_value: int = 9, parent=None):
        super().__init__(parent)
        self._auto_value = auto_value
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        h = QHBoxLayout()
        h.setSpacing(10)
        v.addLayout(h)
        self.auto = QCheckBox("Auto (scales with the image)") if auto else None
        self.slider = Slider()
        self.slider.setRange(lo, min(hi, slider_hi))  # larger values: type them in the box
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


def _point_locale() -> QLocale:
    """Numbers with a "." decimal point and no thousands separators, whatever the
    system locale: the same as the command line, project files and crop field."""
    loc = QLocale.c()
    loc.setNumberOptions(QLocale.OmitGroupSeparator | QLocale.RejectGroupSeparator)
    return loc


class DoubleSpinBox(_WheelGuard, QDoubleSpinBox):
    """Shows and accepts "." as the decimal point; a typed "," becomes "." too."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_guard()
        self.setLocale(_point_locale())
        self.setKeyboardTracking(False)
        self.lineEdit().setTextMargins(5, 0, 0, 0)  # line up with combo box text

    def validate(self, text, pos):
        return super().validate(text.replace(",", "."), pos)

    def fixup(self, text):
        return super().fixup(text.replace(",", "."))

    def valueFromText(self, text):
        return super().valueFromText(text.replace(",", "."))


class ComboBox(_WheelGuard, QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_guard()
        # long item names must not widen the settings panel (the list still shows them)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)


class Section(QWidget):
    """A settings group with a clickable header that folds it open/closed
    (remembered between sessions)."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Section")
        self.setAttribute(Qt.WA_StyledBackground)
        self._key = f"sections/{title}"
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 10)
        v.setSpacing(2)
        self.header = QPushButton(title)
        self.header.setObjectName("SectionHeader")
        self.header.setCheckable(True)
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setFocusPolicy(Qt.NoFocus)
        self.body = QWidget()
        v.addWidget(self.header)
        v.addWidget(self.body)
        self.header.toggled.connect(self._toggle)
        open_ = prefs.store().value(self._key, True, type=bool)
        self.header.setChecked(open_)
        self._toggle(open_)

    def _toggle(self, open_: bool):
        self.body.setVisible(open_)
        self.header.setIcon(theme.icon("chevron_down" if open_ else "chevron_right",
                                       theme.current.muted, 14))
        prefs.store().setValue(self._key, open_)


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = "#000000"
        self.clicked.connect(self._pick)
        self.setFixedWidth(90)

    def color(self) -> str:
        return self._color

    def set_color(self, c: str):
        self._color = c
        fg = "#fff" if QColor(c).lightness() < 128 else "#000"
        self.setText(c)
        # scoped to this button: an unscoped style sheet is inherited by child widgets,
        # which painted the whole colour dialog in the selected colour
        self.setStyleSheet(f"QPushButton {{ background: {c}; color: {fg}; border-radius: 6px; "
                           f"border: 1px solid rgba(128, 128, 128, 0.45); padding: 3px 8px; "
                           f"font-family: Consolas, monospace; }}")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self.window(), "Colour")
        if c.isValid():
            self.set_color(c.name())
            self.colorChanged.emit(c.name())


class FigurePanel(QScrollArea):
    """Edits a FigureSettings; emits ``changed`` with a new copy on every edit."""

    changed = Signal(object)
    applyToAll = Signal()
    clearCrop = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._s = FigureSettings()
        self._w: Dict[str, Any] = {}
        self._shown: Dict[str, Any] = {}  # widget values as last shown/emitted
        self._rows: Dict[str, Any] = {}   # name -> (form layout, row widget), to hide rows
        self._loading = False
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(18, 16, 14, 16)
        lay.setSpacing(0)
        self.title = QLabel("No figure selected")
        self.title.setObjectName("PanelTitle")
        lay.addWidget(self.title)
        self.subtitle = QLabel("Settings for the selected figure")
        self.subtitle.setObjectName("PanelSub")
        lay.addWidget(self.subtitle)
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

        for title, items in SECTIONS:
            box = Section(title)
            sections.append(box)
            form = QFormLayout(box.body)
            form.setContentsMargins(2, 0, 0, 0)
            form.setHorizontalSpacing(12)
            form.setVerticalSpacing(8)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for name, label, kind, extra in items:
                if kind == "heading":
                    h = QLabel(label.upper())
                    h.setObjectName("SubHeading")
                    form.addRow(h)
                    self._rows[name] = (form, h)
                    continue
                w = self._make(name, kind, extra)
                self._rows[name] = (form, w)
                if kind == "nolabel":
                    w.setToolTip(TIPS[name])
                    form.addRow(w)
                    continue
                if name in TIPS:
                    w.setToolTip(TIPS[name])
                if kind == "b":
                    form.addRow(w)
                else:
                    form.addRow(label, w)
                    form.labelForField(w).setToolTip(TIPS.get(name, ""))
                    form.labelForField(w).setObjectName("FormLabel")
                if name == "tab_overlap_mm":
                    self.overlap_hint = QLabel()
                    self.overlap_hint.setWordWrap(True)
                    self.overlap_hint.setObjectName("Hint")
                    self.overlap_hint.setVisible(False)
                    form.addRow(self.overlap_hint)
            lay.addWidget(box)

        labels = [lab for form, _ in self._rows.values()
                  for lab in [form.labelForField(_)] if isinstance(lab, QLabel)]
        widest = max((lab.sizeHint().width() for lab in labels), default=0)
        for lab in labels:
            lab.setMinimumWidth(widest)
        self.sections = sections
        self.copies = self._w["copies"][1]
        lay.addSpacing(12)
        self.apply_all = QPushButton("Apply to all figures")
        self.apply_all.setToolTip("Copies these settings to every figure, except label, crop, "
                                  "mask and copies")
        self.apply_all.clicked.connect(self.applyToAll)
        lay.addWidget(self.apply_all)
        lay.addStretch()
        self.setWidget(body)
        self.set_empty(True)

    def set_empty(self, empty: bool, message: str = "Add images to see their settings here."):
        """No figure selected: a clear message instead of a wall of disabled fields."""
        for w in [self.title, self.subtitle, self.apply_all] + self.sections:
            w.setVisible(not empty)
        self.empty_box.setVisible(empty)
        self.empty_text.setText(message)

    def refresh_icons(self):
        self.empty_icon.setPixmap(theme.pixmap("sliders", theme.current.muted, 40))

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
            w = QCheckBox(dict((n, l) for _, its in SECTIONS for n, l, *_ in its)[name])
            w.toggled.connect(self._emit)
        elif kind == "c":
            w = ComboBox()
            for item in extra:
                value, text = item if isinstance(item, tuple) else (item, item)
                w.addItem(text, value)
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
            edit.setPlaceholderText("none - drag on the Source tab")
            edit.editingFinished.connect(self._emit)
            b = QToolButton()
            b.setText("Clear")
            b.clicked.connect(lambda: (edit.clear(), self._emit()))
            h.addWidget(edit)
            h.addWidget(b)
            w.edit = edit
        elif kind == "label":
            w = QLineEdit()
            w.editingFinished.connect(self._emit)
        elif kind == "nolabel":
            # not a setting of its own: ticked means label "" (see _read)
            w = QCheckBox("No label")
            w.toggled.connect(self._emit)
            self.no_label = w
            return w
        else:  # pragma: no cover
            raise ValueError(kind)
        self._w[name] = (kind, w)
        return w

    def _browse_mask(self, edit: QLineEdit):
        f, _ = QFileDialog.getOpenFileName(self, "Mask image (white = figure)", "",
                                           remote.IMAGE_FILTER)
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
                v = getattr(s, name)
                if kind in ("f", "i"):
                    w.setValue(v)
                elif kind == "slider":
                    w.setValue(v)
                elif kind == "b":
                    w.setChecked(bool(v))
                elif kind == "c":
                    w.setCurrentIndex(max(0, w.findData(v)))
                elif kind == "s":
                    w.setText(v or "")
                elif kind == "col":
                    w.set_color(v)
                elif kind == "model":
                    w.setCurrentText(MODEL_NAMES.get(v, v))
                elif kind == "file":
                    w.edit.setText(v or "")
                elif kind == "crop":
                    w.edit.setText(_crop_text(v))
                elif kind == "label":
                    w.setPlaceholderText(stem or "file name")
                    self.no_label.setChecked(v == "")
                    w.setText(v or "")
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

    def _read(self) -> Dict[str, Any]:
        vals: Dict[str, Any] = {}
        for name, (kind, w) in self._w.items():
            if kind in ("f", "i"):
                vals[name] = w.value()
            elif kind == "slider":
                vals[name] = w.value()
            elif kind == "b":
                vals[name] = w.isChecked()
            elif kind == "c":
                vals[name] = w.currentData()
            elif kind == "s":
                vals[name] = w.text().strip() or None
            elif kind == "col":
                vals[name] = w.color()
            elif kind == "model":
                text = w.currentText().strip() or "auto"
                vals[name] = MODEL_VALUES.get(text, text)
            elif kind == "file":
                vals[name] = w.edit.text().strip() or None
            elif kind == "crop":
                vals[name] = _parse_crop_text(w.edit.text(), self._s.crop)
            elif kind == "label":
                vals[name] = "" if self.no_label.isChecked() else (w.text().strip() or None)
        return vals

    OVERLAP_HINTS = {
        "unused": "No effect on this figure: its bottom is wider than the tab, so the overlap "
                  "is already inside the outline. It only matters for narrow feet or tails.",
        "narrow": "Only {joint:.1f} mm of paper joins the tab to the figure (its bottom is "
                  "narrow), which may tear when folded. Raise the overlap to strengthen it.",
    }

    def set_overlap_hint(self, kind=None, joint: float = 0.0):
        """Note under 'Overlap into figure': None, "unused" or "narrow" (with the joint width)."""
        show = kind in self.OVERLAP_HINTS and not self._w["no_tab"][1].isChecked()
        if show:
            self.overlap_hint.setText(self.OVERLAP_HINTS[kind].format(joint=joint))
        self.overlap_hint.setVisible(show)

    def set_auto_fill_gaps(self, px: int):
        """The gap filling the last build picked automatically, shown while Auto is on."""
        self._w["fill_gaps"][1].set_auto_value(px)

    def set_crop(self, crop):
        """Crop set from the Source tab."""
        self._w["crop"][1].edit.setText(_crop_text(crop))
        self._emit()

    def is_shown(self, name: str) -> bool:
        form, w = self._rows[name]
        return form.isRowVisible(w)

    def _sync_visible(self):
        """Only show the fields that do something in the current state."""
        val = lambda n: self._w[n][1].currentData()  # noqa: E731
        tab = not self._w["no_tab"][1].isChecked()
        label = tab and not self.no_label.isChecked()
        square = val("tab_shape") == "square"
        double = self._w["double_sided"][1].isChecked()
        model = self._w["model"][1].currentText().strip()
        show = {
            "mask": MODEL_VALUES.get(model, model) == "mask",
            "min_area": self._w["keep_all"][1].isChecked(),
            "margin_color": val("margin_fill") == "color",
            "cut_color": not self._w["cutter"][1].isChecked(),
            "cut_width_mm": not self._w["cutter"][1].isChecked(),
            "bleed_mm": self._w["cutter"][1].isChecked(),
            "tab_shape": tab,
            "tab_width_mm": tab and square,
            "tab_height_mm": tab and square,
            "tab_radius_mm": tab and not square,
            "tab_overlap_mm": tab,
            "fold_mm": tab,
            "tab_color": tab,
            "_tab_label": tab,
            "no_label": tab,
            "label": label,
            "label_size_mm": label,
            "label_color": label,
            "back": double,
            "back_color": double and val("back") in ("blank", "text"),
            "back_text": double and val("back") == "text",
            "back_text_color": double and val("back") == "text",
        }
        for name, visible in show.items():
            form, w = self._rows[name]
            form.setRowVisible(w, visible)
        if not tab:
            self.overlap_hint.setVisible(False)

    def _emit(self, *_):
        if self._loading:
            return
        self._sync_visible()
        new = self.settings()
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


def _parse_crop_text(text: str, old):
    text = text.strip()
    if not text:
        return None
    try:
        vals = [float(v) for v in text.replace(" ", "").split(",")]
    except ValueError:
        return old
    return vals if len(vals) == 4 else old


class SheetPanel(QWidget):
    """Paper, title, margins - edits a SheetSettings."""

    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        from .widgets import FlowLayout

        self.setObjectName("SheetBar")
        self.setAttribute(Qt.WA_StyledBackground)
        # wraps onto a second line when the canvas is narrow (a single row would hold
        # the canvas - and so the side panels - at ~760 px)
        h = FlowLayout(self, spacing=14)
        h.setContentsMargins(14, 8, 14, 8)
        self.paper = ComboBox()
        self.paper.addItems(["a4", "letter"])
        self.title = QLineEdit()
        self.title.setFixedWidth(180)
        self.margin = DoubleSpinBox()
        self.margin.setRange(0, 50)
        self.margin.setSuffix(" mm")
        self.gap = DoubleSpinBox()
        self.gap.setRange(0, 50)
        self.gap.setSuffix(" mm")
        for lbl, w in (("Paper", self.paper), ("Title", self.title),
                       ("Margin", self.margin), ("Gap", self.gap)):
            pair = QWidget()  # a label and its field wrap together
            ph = QHBoxLayout(pair)
            ph.setContentsMargins(0, 0, 0, 0)
            ph.setSpacing(6)
            lab = QLabel(lbl)
            lab.setObjectName("FormLabel")
            ph.addWidget(lab)
            ph.addWidget(w)
            h.addWidget(pair)
        self.info = QLabel()
        self.info.setObjectName("Muted")
        h.addWidget(self.info)
        self.paper.currentTextChanged.connect(self._emit)
        self.title.editingFinished.connect(self._emit)
        self.margin.valueChanged.connect(self._emit)
        self.gap.valueChanged.connect(self._emit)
        self._s = SheetSettings()
        self._loading = False

    def set_settings(self, s: SheetSettings):
        self._loading = True
        self._s = s
        self.paper.setCurrentText(s.paper)
        self.title.setText(s.title)
        self.margin.setValue(s.margin_mm)
        self.gap.setValue(s.gap_mm)
        self._loading = False

    def _emit(self, *_):
        if self._loading:
            return
        new = replace(self._s, paper=self.paper.currentText(), title=self.title.text(),
                      margin_mm=self.margin.value(), gap_mm=self.gap.value())
        if new != self._s:
            self._s = new
            self.changed.emit(new)
