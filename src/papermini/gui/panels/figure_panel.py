from __future__ import annotations

import html
from dataclasses import replace
from functools import partial
from typing import Any, ClassVar, cast

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...pipeline.segmentation import segment
from ...pipeline.segmentation.segmenter_registry import SegmenterRegistry
from ...pipeline.token_options import TokenOptions
from ...project import sizes
from ...project.figure_settings import FigureSettings
from ...project.size_calculator import SizeCalculator
from ...support.font_library import FontLibrary
from ..fields.dimensions_field import DimensionsField
from ..fields.field import Field
from ..fields.field_factory import FieldFactory
from ..fields.font_field import FontField
from ..fields.model_field import ModelField
from ..fields.size_field import SizeField
from ..preferences import Preferences
from ..step import Step
from ..theme_service import ThemeService
from ..views.qt_fonts import QtFonts
from ..widgets.elided_label import ElidedLabel
from .figure_fields import (
    FIELD_SETTINGS,
    KIND_SECTIONS,
    OPTIONS,
    PER_IMAGE,
    RESETS,
    SECTIONS,
    SPECIAL_FIELDS,
    SUBSECTIONS,
    TOKEN_SWITCHES,
    TWINS,
)
from .section import SUB_INDENT, Section


class FigurePanel(QScrollArea):
    """Edits a FigureSettings; emits ``changed`` with a new copy on every edit.
    Shows the groups of one workflow step at a time (``set_step``)."""

    changed = Signal(object)
    applyToAll = Signal(object)  # the settings to copy (those of the shown step)
    exportPiece = Signal()  # the Miniature step's Export button (SVG or PNG)

    def __init__(
        self,
        prefs: Preferences,
        size_calculator: SizeCalculator,
        fonts: FontLibrary,
        qt_fonts: QtFonts,
        themes: ThemeService,
        parent=None,
    ):
        super().__init__(parent)
        self._prefs = prefs
        self._size_calculator = size_calculator
        self._themes = themes
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._s = FigureSettings()
        options = FigureSettings.options()
        self._factory = FieldFactory(
            {
                **SPECIAL_FIELDS,
                "font": partial(FontField, fonts=fonts, qt_fonts=qt_fonts),
                "dimensions": partial(
                    DimensionsField,
                    height=options["height_mm"],
                    width=options["width_mm"],
                    themes=themes,
                ),
                "model": partial(ModelField, themes=themes),
            },
            themes,
        )
        self._fields: dict[str, Field] = {}
        self._shown: dict[str, Any] = {}  # field values as last shown or emitted
        self._rows: dict[str, tuple[QFormLayout, QWidget]] = {}  # to hide rows
        # each switch, with the section whose header it is in
        self._switches: dict[str, tuple[QCheckBox, Section]] = {}
        self._resets: dict[str, QPushButton] = {}
        self._labels: list[tuple[QLabel, int]] = []  # form labels and their indent
        self._step = Step.SOURCE
        self._empty = True
        self._measuring = False  # (all sections shown, of both kinds of figure)
        self._auto_method: str | None = None
        self._size_table = sizes.BUILTIN
        self._size_label = ""
        self._figure_width: float | None = None
        self._loading = True
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(18, 16, 14, 16)
        lay.setSpacing(0)
        self._build_header(lay)
        self._build_empty_state(lay)
        self._build_kind_row(lay)
        self._build_sections(lay)
        self._build_hints()
        self._line_up_labels()
        self._build_buttons(lay)
        self.setWidget(body)
        self.size_field: SizeField = self.field("dimensions")
        self.label_switch = self._switch("label")
        self.token_text_switch = self._switch("token_text")
        self._loading = False
        self.refresh_icons()
        self._min_width = self._widest_step()
        self.set_step(Step.SOURCE)
        self.set_empty(True)

    # region building
    def _build_header(self, lay: QVBoxLayout) -> None:
        self.title = ElidedLabel("No figure selected")  # a long name never widens it
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

    def _build_empty_state(self, lay: QVBoxLayout) -> None:
        """Build what is shown instead of the settings when no figure is selected."""
        self.empty_box = QWidget()
        self.empty_box.setObjectName("PanelEmpty")
        ev = QVBoxLayout(self.empty_box)
        ev.setContentsMargins(12, 0, 12, 0)
        ev.setSpacing(10)
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = QLabel("No figure selected")
        self.empty_title.setObjectName("EmptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text = QLabel()
        self.empty_text.setObjectName("Muted")
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text.setWordWrap(True)
        ev.addStretch(2)
        for w in (self.empty_icon, self.empty_title, self.empty_text):
            ev.addWidget(w)
        ev.addStretch(3)  # a little above the middle looks centred
        lay.addWidget(self.empty_box, 1)

    def _build_kind_row(self, lay: QVBoxLayout) -> None:
        """Build the Kind, above the sections of the Miniature step."""
        kind = self._factory.build("kind", OPTIONS["kind"], self._emit)
        self._fields["kind"] = kind
        self.kind_row = QWidget()
        kh = QHBoxLayout(self.kind_row)
        kh.setContentsMargins(2, 0, 0, 12)
        kh.setSpacing(12)
        label = QLabel(kind.label)
        label.setObjectName("FormLabel")
        label.setToolTip(kind.tooltip)
        kh.addWidget(label)
        kh.addWidget(kind.widget, 1)
        lay.addWidget(self.kind_row)
        self._labels.append((label, 0))

    def _build_sections(self, lay: QVBoxLayout) -> None:
        self.sections: list[Section] = []
        boxes: dict[str, Section] = {}
        for _, title, names in SECTIONS:
            box = Section(self._prefs, self._themes, title, sub=title in SUBSECTIONS)
            indent = SUB_INDENT if title in SUBSECTIONS else 0
            for name in names:
                if name in RESETS:
                    self._add_reset(box.form, name)
                else:
                    self._add_field(box, name, indent)
            if title in SUBSECTIONS:  # at the end of its section, folded away with it
                parent = boxes[SUBSECTIONS[title]]
                box.parent_section = parent
                parent.form.addRow(box)
            else:
                lay.addWidget(box)
            boxes[title] = box
            self.sections.append(box)

    def _add_field(self, box: Section, name: str, indent: int) -> None:
        field = self._factory.build(name, OPTIONS[name], self._emit)
        form = box.form
        self._fields[name] = field
        if field.switch is not None:
            box.set_switch(field.switch)
            self._switches[field.switch_name] = (field.switch, box)
        if field.row is None:
            return
        self._rows[name] = (form, field.row)
        self._labels += [(label, 0) for label in field.labels]
        if not field.label:
            form.addRow(field.row)
            return
        form.addRow(field.label, field.row)
        label = form.labelForField(field.row)
        assert isinstance(label, QLabel)
        label.setObjectName("FormLabel")
        label.setToolTip(field.tooltip)
        self._labels.append((label, indent))

    def _add_reset(self, form: QFormLayout, name: str) -> None:
        """Add a button that puts the settings of ``name`` in RESETS back to their
        defaults."""
        b = QPushButton(OPTIONS[name].label)
        b.setObjectName("ResetButton")
        b.setToolTip(OPTIONS[name].tooltip)
        b.clicked.connect(lambda: self._reset(RESETS[name]))
        form.addRow(b)
        self._rows[name] = (form, b)
        self._resets[name] = b

    def _build_hints(self) -> None:
        """Build the notes under some fields, hidden until there is something to say."""
        (self.font_warning,) = self._hints_under("font", "WarnBox")
        # the size's squares and base, and a warning for a wide figure
        self.size_hint, self.size_warning = self._hints_under("size", "Hint", "WarnBox")
        self.size_hint.setVisible(True)
        # how auto found the figure, and the licence of a non-commercial model while it
        # is the one used
        self.auto_hint, self.licence_hint = self._hints_under(
            "model", "MethodBox", "LicenceBox"
        )
        for hint in (self.auto_hint, self.licence_hint):
            hint.setTextFormat(Qt.TextFormat.RichText)
        (self.ring_hint,) = self._hints_under("token_border_mm", "Hint")  # curved text
        (self.overlap_hint,) = self._hints_under("tab_overlap_mm", "Hint")

    def _hints_under(self, name: str, *object_names: str) -> list[QLabel]:
        """Add hidden notes under the field ``name``, one per object name."""
        form, row = self._rows[name]
        index = cast(tuple[int, Any], form.getWidgetPosition(row))[0]
        hints = []
        for offset, object_name in enumerate(object_names, 1):
            hint = QLabel()
            hint.setObjectName(object_name)
            hint.setWordWrap(True)
            hint.setVisible(False)
            form.insertRow(index + offset, hint)
            hints.append(hint)
        return hints

    def _line_up_labels(self) -> None:
        """Give the labels one width, so the fields form one column, also inside the
        indented sub-sections."""
        widest = max((label.sizeHint().width() for label, _ in self._labels), default=0)
        for label, indent in self._labels:
            label.setMinimumWidth(widest - indent)

    def _build_buttons(self, lay: QVBoxLayout) -> None:
        lay.addSpacing(12)
        self.apply_all = QPushButton("Apply to all figures")
        self.apply_all.clicked.connect(
            lambda: self.applyToAll.emit(self.step_settings())
        )
        lay.addWidget(self.apply_all)
        lay.addSpacing(8)
        self.export_piece = QPushButton("Export…")  # (Miniature step: this figure's)
        self.export_piece.setToolTip(
            "Save this figure as an SVG (the piece with its cut line, for Inkscape or a "
            "cutting machine) or a PNG (a picture of the piece, for a virtual tabletop)  "
            "(Ctrl+E)"
        )
        self.export_piece.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_piece.clicked.connect(self.exportPiece)
        lay.addWidget(self.export_piece)
        lay.addStretch()

    def _switch(self, name: str) -> Any:
        """Return the switch of the field ``name``."""
        return self._fields[name].switch

    def _font(self) -> FontField:
        font = self._fields["font"]
        assert isinstance(font, FontField)
        return font

    def _widest_step(self) -> int:
        """The width that shows every control of every step, measured with each step's
        groups shown (hidden widgets do not count in a minimum size)."""
        body = self.widget()
        widths = []
        self._empty = False
        self._measuring = True
        for box in self.sections:  # (a folded group still needs its room when opened)
            box.body.setVisible(True)
        for step in Step:
            self._step = step
            self._sync_sections()
            body.layout().activate()
            widths.append(body.minimumSizeHint().width())
        self._measuring = False
        for box in self.sections:
            box._toggle(box.header.isChecked(), remember=False)
        frame = 2 * self.frameWidth() + self.verticalScrollBar().sizeHint().width()
        return max(widths) + frame

    # endregion

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
        self.export_piece.setVisible(not empty and self._step == Step.MINIATURE)
        self.empty_box.setVisible(empty)
        self.empty_text.setText(message)
        self._sync_sections()

    def set_step(self, step: Step):
        """Show the settings of one workflow step."""
        self._step = step
        self.export_piece.setVisible(not self._empty and step == Step.MINIATURE)
        self._sync_sections()
        self.verticalScrollBar().setValue(0)

    def step(self) -> Step:
        return self._step

    def step_settings(self) -> set:
        """Return the settings shown now, minus the per-image ones that applying
        settings to all figures never copies."""
        return self._step_fields(self._step) - PER_IMAGE

    @staticmethod
    def _step_fields(step: Step) -> set:
        """Return the FigureSettings fields edited in ``step``, with the kind of figure
        in the miniature step."""
        return {
            k
            for st, _, names in SECTIONS
            if st == step
            for name in names
            if name not in RESETS
            for k in FIELD_SETTINGS.get(name, (name,))
        } | ({"kind"} if step == Step.MINIATURE else set())

    def is_token(self) -> bool:
        """Whether the figure shown is a token (its Kind field)."""
        return self._fields["kind"].value() == "token"

    def _sync_sections(self):
        kind = "token" if self.is_token() else "mini"
        self.kind_row.setVisible(not self._empty and self._step == Step.MINIATURE)
        for box, (step, title, _) in zip(self.sections, SECTIONS, strict=True):
            box.setVisible(
                not self._empty
                and step == self._step
                and (KIND_SECTIONS.get(title, kind) == kind or self._measuring)
            )
        self.step_hint.setText(
            self._step.token_hint if kind == "token" else self._step.hint
        )
        if self._step == Step.SHEET:
            return  # the window shows the sheet panel in this step
        title = self._step.title.lower()
        self.apply_all.setText(f"Apply {title} settings to all figures")
        self.apply_all.setToolTip(
            "Copies the settings shown here to every figure"
            + {
                Step.SOURCE: ", except the crop and mask file",
                Step.MINIATURE: ", except the label and a token's Area",
            }[self._step]
        )

    def refresh_icons(self):
        self.empty_icon.setPixmap(
            self._themes.pixmap("sliders", self._themes.current.muted, 40)
        )
        self.size_field.refresh_icons()

    # region values
    def set_settings(self, s: FigureSettings, title: str = "", stem: str = ""):
        self._loading = True
        try:
            self._s = s
            self.title.setText(title)
            for field in self._fields.values():
                field.show(s)
            for name in (*TWINS, *TWINS.values()):  # the label's fields
                self.field(name).setPlaceholderText(stem or "file name")
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
        for name, field in self._fields.items():
            # a setting with a field for each kind of figure: read the one in use
            if (name in TWINS.values() and token) or (name in TWINS and not token):
                continue
            vals.update(field.read())
        return vals

    OVERLAP_HINTS: ClassVar = {
        "unused": "No effect on this figure: its bottom is wider than the tab, so the overlap "
        "is already inside the outline. It only matters for narrow feet or tails.",
        "narrow": "Only {joint:.1f} mm of paper joins the tab to the figure (its bottom is "
        "narrow), which may tear when folded. Raise the overlap to strengthen it.",
    }

    def set_overlap_hint(self, kind=None, joint: float = 0.0):
        """Note under 'Overlap into figure': None, "unused" or "narrow" (with the joint width)."""
        show = kind in self.OVERLAP_HINTS and not self._value("no_tab")
        if show:
            self.overlap_hint.setText(self.OVERLAP_HINTS[kind].format(joint=joint))
        self.overlap_hint.setVisible(show)

    @staticmethod
    def auto_method_text(method: str) -> str:
        """Describe in words which model "auto" picked for a figure (the Mini's ``method``)."""
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

    # endregion

    # region fonts
    def set_installed_fonts(self, names) -> None:
        """List the fonts installed on this computer (found in the background) after the
        bundled ones."""
        self._loading, loading = True, self._loading
        try:
            self._font().set_installed(names)
        finally:
            self._loading = loading
        self._sync_font_warning()

    def _sync_font_warning(self) -> None:
        font = self._font()
        missing = font.missing()
        self.font_warning.setText(
            f"{font.value()} is not on this computer: this figure prints in "
            f"{FontLibrary.DEFAULT}."
            if missing
            else ""
        )
        self.font_warning.setVisible(missing)

    # endregion

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
            self._fields["size"].show(s)
            if s.size != sizes.CUSTOM:  # (Custom: leave the field being edited alone)
                self._fields["dimensions"].show(s)
                for name, option in OPTIONS.items():
                    if option.sized and name in self._fields:
                        self._fields[name].show(s)
            self._sync_visible()
            self._shown = self._read()
        finally:
            self._loading = False

    def _sync_size_hint(self):
        size = self._value("size") or sizes.CUSTOM
        text = self._size_calculator.footprint_text(size, self._size_table)
        label = self._size_label
        self.size_hint.setText(f"{text} · {label}" if text and label else text)
        self.size_hint.setVisible(bool(text))
        warning = (
            ""
            if self.is_token()
            else self._size_calculator.width_warning(
                size, self._figure_width or 0, self._size_table
            )
        )
        self.size_warning.setText(warning)
        self.size_warning.setVisible(bool(warning))

    def _sync_auto_hint(self):
        model = self._value("model")
        method = self._auto_method
        self.auto_hint.setVisible(bool(method) and model == "auto")
        used = (
            method if model == "auto" else model
        )  # (auto: what it picked, once known)
        if used and SegmenterRegistry.non_commercial(used):
            self.licence_hint.setText(
                f"<b>Non-commercial use only.</b> You are responsible for not using "
                f"{html.escape(segment.ONNX_MODELS[used].title)} commercially, for "
                f"example to make minis you sell. For commercial use, pick "
                f"{' or '.join(SegmenterRegistry.free_models())}."
            )
            self.licence_hint.setToolTip(SegmenterRegistry.licence_notice(used))
        self.licence_hint.setVisible(
            bool(used) and SegmenterRegistry.non_commercial(used)
        )

    def set_auto_fill_gaps(self, px: int):
        """The gap filling the last build picked automatically, shown while Auto is on."""
        self.field("fill_gaps").set_auto_value(px)

    def set_aspect(self, aspect):
        """The selected figure's own width / height, for the linked size fields."""
        self.size_field.set_aspect(aspect)

    def set_crop(self, crop):
        """Crop set by dragging a box on the Source view."""
        self._fields["crop"].set_value(crop)
        self._emit()

    def set_token_area(self, area):
        """A token's framing set by dragging the figure in the Miniature view."""
        self._fields["token_area"].set_value(area)
        self._emit()

    def field(self, name: str) -> Any:
        """Return the input widget of the setting ``name``."""
        return self._fields[name].widget

    def _value(self, name: str) -> Any:
        """Return the value the field ``name`` shows."""
        return self._fields[name].value()

    def is_shown(self, name: str) -> bool:
        """Whether a field is shown; for a group's switch, whether it can be used."""
        if name in self._switches:  # usable unless the group it is inside is off
            box = self._switches[name][1].parent_section
            return box is None or box.active()
        form, w = self._rows[name]
        return form.isRowVisible(w)

    def _sync_visible(self):
        """Only show the fields that do something in the current state; a group that
        is switched off shows only its header."""
        val = self._value
        tab = not val("no_tab")
        label = tab and self.label_switch.isChecked()
        # (a mini always has its outline, the margin, and its cut line: only a token's can
        # be switched off)
        token = self.is_token()
        for name in TOKEN_SWITCHES:
            self._switches[name][0].setVisible(token)
        always = set() if token else set(TOKEN_SWITCHES)
        for name, (switch, box) in self._switches.items():  # off: only the header
            box.set_active(switch.isChecked() or name in always)
        square = val("tab_shape") == "square"
        double = val("double_sided")
        show = {
            "mask": val("model") == "mask",
            "min_area": val("keep_all"),
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
        grey = val("greyscale")
        show["saturation"] = show["hue"] = not grey
        # a token: its own fields instead of the mini's; the margin makes its outline
        text = val("token_text")
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
        for name, b in self._resets.items():  # only when there is something to reset
            b.setEnabled(any(read[n] != getattr(d, n) for n in RESETS[name]))
        if not tab:
            self.overlap_hint.setVisible(False)
        self._sync_sections()
        self._sync_auto_hint()
        self._sync_size_hint()
        self._sync_font_warning()

    def _sync_ring(self, curved: bool) -> None:
        """Curved text needs a ring at least this wide: the field stops there, and says so."""
        w = self.field("token_border_mm")
        least = (
            TokenOptions.min_ring_mm(self._value("token_text_mm")) if curved else 0.0
        )
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
        for token_field, mini_field in TWINS.items():
            self._fields[mini_field if self.is_token() else token_field].show(s)

    def _reset(self, names):
        """Put ``names`` back to their defaults, as one change."""
        d = FigureSettings()
        self._loading = True
        try:
            for name in names:
                self._fields[name].set_value(getattr(d, name))
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

    # endregion
