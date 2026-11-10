"""Settings panels: per-figure options and sheet options."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict

from PySide6.QtCore import QLocale, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit,
                               QPushButton, QScrollArea, QSlider, QSpinBox, QStyle,
                               QStyleOptionSlider, QToolButton, QVBoxLayout, QWidget)

from .. import remote
from ..settings import FigureSettings, SheetSettings
from . import prefs, theme
from .widgets import ElidedLabel

# value -> what the (editable) model box shows, where they differ
MODEL_NAMES = {"mask": "mask image file"}
MODEL_VALUES = {v: k for k, v in MODEL_NAMES.items()}
MODELS = ["auto", "rmbg-1.4", "birefnet", "birefnet-lite", "alpha", "mask"]

# The steps of the workflow, one view each: the settings panel shows the active
# step's groups. (step, group title, fields); fields are (field, label, kind, extra) -
# kind: f=float, i=int, b=bool, c=choice, s=str, col=color, size=height and width
# with a link toggle, slider=int slider (lo, hi, slider_hi, suffix, auto checkbox),
# heading=sub-heading inside a group (not a setting), switch=a checkbox in the group's
# header that turns the whole group on or off (extra "invert": the setting is the
# opposite, e.g. no_tab), nolabel=the Label group's switch (off = label ""),
# reset=a button that puts the listed fields back to their defaults (not a setting)
STEPS = ["Source", "Miniature", "Print sheet"]
SOURCE, MINIATURE, PRINT = range(3)
STEP_HINTS = [
    "Crop the picture first: background removal only looks inside the box.",
    "The paper piece around the figure: back side, margin, cut line and stand tab.",
    "How big this figure prints and how many go on the sheet.",
]
SECTIONS = [
    (SOURCE, "Crop", [
        ("crop", "Area", "crop", None),
    ]),
    (SOURCE, "Background removal", [
        ("model", "Model", "model", None),
        ("mask", "Mask image file", "file", None),
        ("strength", "Strength", "slider", (0, 254, 254, "", False)),
        ("fill_gaps", "Gap filling", "slider", (0, 1000, 40, " px", True)),
        ("keep_all", "Keep detached parts", "b", None),
        ("min_area", "Min. part area", "i", (0, 10_000_000, 100, " px")),
    ]),
    (SOURCE, "Image adjustments", [  # what is printed; the model never sees them
        ("greyscale", "Greyscale (black and white)", "b", None),
        ("brightness", "Brightness", "slider", (-100, 100, 100, "", False)),
        ("contrast", "Contrast", "slider", (-100, 100, 100, "", False)),
        ("saturation", "Saturation", "slider", (-100, 100, 100, "", False)),
        ("hue", "Hue", "slider", (-180, 180, 180, "\u00b0", False)),
        ("_reset_adjust", "Reset adjustments", "reset",
         ("greyscale", "brightness", "contrast", "saturation", "hue")),
    ]),
    (MINIATURE, "Back side", [  # first: it decides what the rest of the piece is
        ("double_sided", "Print a back side", "switch", None),
        ("back", "Shows", "c", [("mirror", "Mirrored drawing"), ("blank", "Blank"),
                                ("text", "Text")]),
        ("back_color", "Color", "col", None),
        ("back_text", "Text", "s", None),
        ("back_text_color", "Text color", "col", None),
    ]),
    (MINIATURE, "Outline and cut line", [
        ("margin_mm", "Margin", "f", (0, 15, 0.1, 2, " mm")),
        ("margin_fill", "Margin fill type", "c", [("color", "Color"), ("image", "Original image")]),
        ("margin_color", "Margin fill color", "col", None),
        ("smooth_mm", "Outline smoothing", "f", (0, 5, 0.1, 2, " mm")),
        ("_cut_line", "Cut line", "heading", None),
        ("no_smooth", "Straight segments only (no curves)", "b", None),
        ("simplify_mm", "Simplify", "f", (0.01, 2, 0.05, 3, " mm")),
        ("cutter", "Cutting-machine style (red hairline)", "b", None),
        ("bleed_mm", "Bleed", "f", (0, 5, 0.1, 1, " mm")),
        ("cut_color", "Color", "col", None),
        ("cut_width_mm", "Width", "f", (0.01, 2, 0.05, 2, " mm")),
    ]),
    (MINIATURE, "Tab", [
        ("no_tab", "Print a tab", "switch", "invert"),
        ("tab_shape", "Shape", "c", [("square", "Square (stand)"),
                                     ("round", "Round (base)")]),
        ("tab_width_mm", "Width", "f", (2, 200, 1, 1, " mm")),
        ("tab_radius_mm", "Radius", "f", (1, 100, 0.5, 1, " mm")),
        ("tab_height_mm", "Height", "f", (1, 100, 0.5, 1, " mm")),
        ("tab_overlap_mm", "Overlap into figure", "f", (0, 30, 0.5, 1, " mm")),
        ("fold_mm", "Fold above lowest point", "f", (0, 20, 0.1, 1, " mm")),
        ("tab_color", "Fill color", "col", None),
    ]),
    (MINIATURE, "Label", [  # on the tab: a sub-group of Tab (SUBSECTIONS)
        ("no_label", "Print a label", "nolabel", None),
        ("label", "Text", "label", None),
        ("label_size_mm", "Size", "f", (0.5, 20, 0.1, 1, " mm")),
        ("label_color", "Color", "col", None),
    ]),
    (PRINT, "Size and copies", [
        ("size", "Size", "size", None),
        ("copies", "Copies on sheet", "i", (0, 999, 1, "")),
        ("dpi", "Image resolution", "i", (72, 2400, 50, " dpi")),
    ]),
]

# groups shown inside another group (indented, at its end): sub-group -> group
SUBSECTIONS = {"Label": "Tab"}
SUB_INDENT = 14

# the settings each field sets ("size" sets two, "no_label" is the label "")
FIELD_SETTINGS = {"size": ("height_mm", "width_mm"), "no_label": ("label",)}


# kept per figure by "Apply to all"
PER_IMAGE = {"label", "crop", "mask", "copies"}


def step_settings(step: int) -> set:
    """The FigureSettings fields edited in ``step``."""
    return {k for st, _, items in SECTIONS if st == step
            for name, _, kind, _ in items if kind not in ("heading", "reset")
            for k in FIELD_SETTINGS.get(name, (name,))}


TIPS = {
    "height_mm": "Height of the drawn figure on paper, without margin and tab.",
    "width_mm": "Width of the drawn figure on paper, without margin.",
    "size_link": "Linked: the figure keeps its proportions, so setting the height sets the\n"
                 "width and the other way round.\n"
                 "Unlinked: set height and width separately; the figure is stretched.",
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
    "crop": "Background removal only looks inside this box (x0,y0,x1,y1, fractions or px),\n"
            "which helps a lot with busy backgrounds. Drag a box on the image to set it.",
    "strength": "How sure the model must be that a pixel belongs to the figure (0-254).\n"
                "Lower keeps faint pencil lines; higher removes more background.",
    "fill_gaps": "Fills gaps and notches in the outline up to this size (0 = off).\n"
                 "Auto scales with the image: 9 px at 1400 px.",
    "keep_all": "Keep separate parts (a floating prop) and join them with bridges,\n"
                "instead of keeping only the largest part.",
    "min_area": "With 'keep detached parts': smaller parts than this are dropped as specks.",
    "margin_mm": "Distance between the drawing and the cut line. The margin is filled\n"
                 "with a color or the original image (see Margin fill type).",
    "margin_fill": "What fills the margin, the strip between the cut-out drawing and its\n"
                   "cut line:\n"
                   "Color: one solid color (Margin fill color).\n"
                   "Original image: the picture around the figure, as it is in the image.",
    "margin_color": "The color of the margin between the drawing and the cut line.",
    "smooth_mm": "Rounds the outline; higher values give a calmer cut line.",
    "no_smooth": "Cut line made of straight segments instead of smooth curves.",
    "simplify_mm": "How far the cut line may deviate to use fewer points.",
    "cutter": "Red 0.1 mm cut line, which many cutting machines treat as the cut layer.",
    "bleed_mm": "Prints the background this far beyond the cut line, so a slightly misaligned\n"
                "machine cut never shows a white edge. The color at the edge (margin, tab or\n"
                "back color) is extended.",
    "cut_color": "Color of the cut line.",
    "cut_width_mm": "Width of the printed cut line.",
    "no_tab": "Print a tab: a fold-over stand tab under the feet.\n"
              "Off for slotted or magnetic bases.",
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
    "no_label": "Print a label: text on the tab.\n"
                "Off for a plain tab in its fill color.",
    "label": "Text printed on the tab (empty = the file name). Also the default back text.",
    "label_size_mm": "Largest text size; long labels shrink to fit the tab.",
    "label_color": "Color of the tab label.",
    "tab_color": "Color of the tab (everything below the fold), behind the label.\n"
                 "Independent of the margin color; e.g. grass green for a plain tab.",
    "greyscale": "Print the figure in black and white (saves color ink).\n"
                 "Color adjustments change only what is printed: background removal\n"
                 "always looks at the original picture, so they never run the model again.",
    "brightness": "Lighter (towards white) or darker (towards black). White paper stays\n"
                  "white when lightening, black lines stay black when darkening.",
    "contrast": "More contrast makes lights lighter and darks darker; less makes it flatter.",
    "saturation": "How colorful the picture is: -100 is grey, 100 twice as colorful.",
    "hue": "Turns every color around the color wheel (red -> yellow -> green ...).",
    "_reset_adjust": "Back to the original colors.\n"
                     "(One slider: double-click it to put it back to 0.)",
    "double_sided": "Print a back side: front and back joined at a fold above the head,\n"
                    "glued back to back. Off for the front only.",
    "back": "mirror: the drawing seen from behind; blank: plain paper; "
            "text: plain paper with text (a name or stats).",
    "back_text": "Text for the back (empty = the tab label). It is sized to fit the body.",
    "back_color": "Color of a blank or text back (the back tab keeps the tab's fill color).",
    "back_text_color": "Color of the back text.",
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


SNAP_PX = 6  # a dragged centred slider snaps to its centre within this many pixels


class Slider(_WheelGuard, QSlider):
    """A horizontal slider. With a ``centre`` (a range from below to above it, like
    -100..100 around 0) it fills from that centre instead of from the left, marks it with
    a short vertical line, snaps to it while dragged close by, and goes back to it on a
    double-click."""

    def __init__(self, parent=None, centre=None):
        super().__init__(Qt.Horizontal, parent)
        self._init_guard()
        self.centre = centre
        if centre is not None:
            self.setProperty("centred", True)  # the style sheet leaves the fill to paintEvent
            self.actionTriggered.connect(self._snap)

    def _snap(self, action: int) -> None:
        if action != QSlider.SliderMove.value or not self.isSliderDown():  # (an int)
            return  # keys, clicks on the track and typed values are taken as they are
        span = max(1, self.width() - self._handle_rect(self.minimum()).width())
        reach = SNAP_PX * (self.maximum() - self.minimum()) / span
        if abs(self.sliderPosition() - self.centre) <= reach:
            self.setSliderPosition(self.centre)

    def mouseDoubleClickEvent(self, e):
        if self.centre is not None and e.button() == Qt.LeftButton:
            self.setValue(self.centre)
            e.accept()
        else:
            super().mouseDoubleClickEvent(e)

    def _option(self, position=None) -> QStyleOptionSlider:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        if position is not None:
            opt.sliderPosition = opt.sliderValue = position
        return opt

    def _handle_rect(self, position):
        return self.style().subControlRect(QStyle.CC_Slider, self._option(position),
                                           QStyle.SC_SliderHandle, self)

    def centre_x(self) -> float:
        return self._handle_rect(self.centre).center().x() + 0.5

    def paintEvent(self, e):
        if self.centre is None:
            return super().paintEvent(e)
        st, p = self.style(), QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        opt = self._option()
        opt.subControls = QStyle.SC_SliderGroove
        st.drawComplexControl(QStyle.CC_Slider, opt, p, self)
        t = theme.current
        cy = self.rect().center().y() + 0.5
        cx = self.centre_x()
        vx = self._handle_rect(self.sliderPosition()).center().x() + 0.5
        fill = QColor(t.accent if self.isEnabled() else t.muted)
        p.fillRect(QRectF(min(cx, vx), cy - 2, abs(vx - cx), 4), fill)
        p.setPen(QPen(QColor(t.muted), 1.5))
        p.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))  # the centre mark
        opt.subControls = QStyle.SC_SliderHandle
        st.drawComplexControl(QStyle.CC_Slider, opt, p, self)
        p.end()


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
        self.slider = Slider(centre=0 if lo < 0 < hi else None)
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
    (remembered between sessions). A group with a switch that is off shows only its
    header and cannot be opened. ``sub``: a group inside another one (indented)."""

    def __init__(self, title: str, parent=None, sub: bool = False):
        super().__init__(parent)
        self.setObjectName("SubSection" if sub else "Section")
        self.setAttribute(Qt.WA_StyledBackground)
        self._key = f"sections/{title}"
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
        open_ = prefs.store().value(self._key, True, type=bool)
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
        self.header.setIcon(theme.icon("chevron_down" if shown else "chevron_right",
                                       theme.current.muted, 14))
        if remember:
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
        # which painted the whole color dialog in the selected color
        self.setStyleSheet(f"QPushButton {{ background: {c}; color: {fg}; border-radius: 6px; "
                           f"border: 1px solid rgba(128, 128, 128, 0.45); padding: 3px 8px; "
                           f"font-family: Consolas, monospace; }}")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self.window(), "Color")
        if c.isValid():
            self.set_color(c.name())
            self.colorChanged.emit(c.name())


class SizeField(QWidget):
    """Figure height and width with a link toggle beside them, like an image editor's
    resize dialog. Linked, the figure keeps its proportions: the field you type in sets
    the size and the other one follows (shown once the figure's proportions are known,
    "—" before). Unlinked, both are set and the figure is stretched to them."""

    valueChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        self.labels = [QLabel("Figure height"), QLabel("Figure width")]
        self.h, self.w = DoubleSpinBox(), DoubleSpinBox()
        for row, (lab, spin, tip) in enumerate(zip(self.labels, (self.h, self.w),
                                                    (TIPS["height_mm"], TIPS["width_mm"]))):
            lab.setObjectName("FormLabel")
            lab.setToolTip(tip)
            spin.setToolTip(tip)
            spin.setRange(0, 1000)
            spin.setDecimals(2)
            spin.setSuffix(" mm")
            spin.setSpecialValueText("—")  # 0: follows the other one, not known yet
            g.addWidget(lab, row, 0)
            g.addWidget(spin, row, 1)
        self.link = QToolButton()
        self.link.setObjectName("SizeLink")
        self.link.setCheckable(True)
        self.link.setChecked(True)
        self.link.setToolTip(TIPS["size_link"])
        self.link.setAccessibleName("Keep proportions")
        self.link.setCursor(Qt.PointingHandCursor)
        self.link.setIconSize(QSize(18, 18))
        g.addWidget(self.link, 0, 2, 2, 1, Qt.AlignVCenter)
        g.setColumnStretch(1, 1)
        self._lead = "h"     # linked: the field that sets the size
        self._aspect = None  # width / height of the drawing, once built
        self.h.valueChanged.connect(lambda v: self._edited("h", v))
        self.w.valueChanged.connect(lambda v: self._edited("w", v))
        self.link.toggled.connect(self._link_toggled)
        self.refresh_icons()

    def refresh_icons(self):
        on = self.link.isChecked()
        self.link.setIcon(theme.icon("link" if on else "unlink",
                                     theme.current.accent if on else theme.current.muted, 18))

    def linked(self) -> bool:
        return self.link.isChecked()

    def value(self):
        """(height_mm, width_mm) as in FigureSettings: one of them None when linked."""
        if self.linked():
            return (self.h.value(), None) if self._lead == "h" else (None, self.w.value())
        return self.h.value(), self.w.value()

    def set_value(self, height, width):
        self._lead = "h" if height else "w"
        self._quiet(lambda: (self.link.setChecked(not (height and width)),
                             self.h.setValue(height or 0), self.w.setValue(width or 0)))
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
                lambda: (self.h if which == "h" else self.w).setValue(1))
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
        else:   # both fields set from what they show now
            h, w = self.h.value(), self.w.value()
            self._quiet(lambda: (self.h.setValue(h or w), self.w.setValue(w or h)))
        self.valueChanged.emit()


class FigurePanel(QScrollArea):
    """Edits a FigureSettings; emits ``changed`` with a new copy on every edit.
    Shows the groups of one workflow step at a time (``set_step``)."""

    changed = Signal(object)
    applyToAll = Signal(object)  # the settings to copy (those of the shown step)
    clearCrop = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._s = FigureSettings()
        self._w: Dict[str, Any] = {}
        self._shown: Dict[str, Any] = {}  # widget values as last shown/emitted
        self._rows: Dict[str, Any] = {}   # name -> (form layout, row widget), to hide rows
        self._switches: Dict[str, Any] = {}  # name -> Section whose header holds it
        self._invert: set = set()          # switches whose setting is the opposite
        self._resets: Dict[str, Any] = {}  # name -> (button, fields it resets)
        self._loading = False
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(18, 16, 14, 16)
        lay.setSpacing(0)
        self.title = ElidedLabel("No figure selected")  # a long name never widens the panel
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
        extra_labels = []  # labels inside compound fields, lined up with the form labels

        forms, boxes, sub_labels = {}, {}, []
        for step, title, items in SECTIONS:
            box = Section(title, sub=title in SUBSECTIONS)
            boxes[title] = box
            sections.append(box)
            self._section_steps.append(step)
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
                if kind in ("switch", "nolabel"):  # in the header, for the whole group
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

        labels = [lab for form, _ in self._rows.values()
                  for lab in [form.labelForField(_)] if isinstance(lab, QLabel)] + extra_labels
        widest = max((lab.sizeHint().width() for lab in labels), default=0)
        for lab in labels:  # one column of fields, also inside the indented sub-groups
            lab.setMinimumWidth(widest - (SUB_INDENT if lab in sub_labels else 0))
        self.sections = sections
        self.copies = self._w["copies"][1]
        self.size_field = self._w["size"][1]
        lay.addSpacing(12)
        self.apply_all = QPushButton("Apply to all figures")
        self.apply_all.clicked.connect(lambda: self.applyToAll.emit(self.step_settings()))
        lay.addWidget(self.apply_all)
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
        for box in self.sections:  # (a folded group still needs its room when opened)
            box.body.setVisible(True)
        for step in range(len(STEPS)):
            self._step = step
            self._sync_sections()
            body.layout().activate()
            widths.append(body.minimumSizeHint().width())
        for box in self.sections:
            box._toggle(box.header.isChecked(), remember=False)
        frame = 2 * self.frameWidth() + self.verticalScrollBar().sizeHint().width()
        return max(widths) + frame

    def minimumSizeHint(self) -> QSize:
        """Never narrower than its widest step, so no control is cut off at the right
        (the header checkboxes are the first to go); the window keeps to this."""
        return QSize(self._min_width, super().minimumSizeHint().height())

    def set_empty(self, empty: bool, message: str = "Add images to see their settings here."):
        """No figure selected: a clear message instead of a wall of disabled fields."""
        self._empty = empty
        for w in (self.title, self.subtitle, self.step_hint, self.apply_all):
            w.setVisible(not empty)
        self.empty_box.setVisible(empty)
        self.empty_text.setText(message)
        self._sync_sections()

    def set_step(self, step: int):
        """Show the settings of one workflow step (SOURCE, MINIATURE or PRINT)."""
        self._step = step
        self.step_hint.setText(STEP_HINTS[step])
        self._sync_sections()
        self.verticalScrollBar().setValue(0)

    def step(self) -> int:
        return self._step

    def step_settings(self) -> set:
        """The settings shown now, minus the per-image ones "Apply to all" never copies."""
        return step_settings(self._step) - PER_IMAGE

    def _sync_sections(self):
        for box, step in zip(self.sections, self._section_steps):
            box.setVisible(not self._empty and step == self._step)
        names = {SOURCE: "source", MINIATURE: "miniature", PRINT: "size"}
        self.apply_all.setText(f"Apply {names[self._step]} settings to all figures")
        self.apply_all.setToolTip("Copies the settings shown here to every figure"
                                  + {SOURCE: ", except the crop and mask file",
                                     MINIATURE: ", except the label",
                                     PRINT: ", except the copies"}[self._step])

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
            w = QCheckBox(dict((n, l) for _, _, its in SECTIONS for n, l, *_ in its)[name])
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
        elif kind == "label":
            w = QLineEdit()
            w.editingFinished.connect(self._emit)
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
                if kind == "size":
                    w.set_value(s.height_mm, s.width_mm)
                    continue
                v = getattr(s, name)
                if kind in ("f", "i"):
                    w.setValue(v)
                elif kind == "slider":
                    w.setValue(v)
                elif kind == "b":
                    w.setChecked(bool(v))
                elif kind == "switch":
                    w.setChecked(bool(v) != (name in self._invert))
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
                    self.label_switch.setChecked(v != "")
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
            elif kind == "size":
                vals["height_mm"], vals["width_mm"] = w.value()
            elif kind == "slider":
                vals[name] = w.value()
            elif kind == "b":
                vals[name] = w.isChecked()
            elif kind == "switch":
                vals[name] = w.isChecked() != (name in self._invert)
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
                vals[name] = "" if not self.label_switch.isChecked() else (w.text().strip() or None)
        return vals

    OVERLAP_HINTS = {
        "unused": "No effect on this figure: its bottom is wider than the tab, so the overlap "
                  "is already inside the outline. It only matters for narrow feet or tails.",
        "narrow": "Only {joint:.1f} mm of paper joins the tab to the figure (its bottom is "
                  "narrow), which may tear when folded. Raise the overlap to strengthen it.",
    }

    def set_overlap_hint(self, kind=None, joint: float = 0.0):
        """Note under 'Overlap into figure': None, "unused" or "narrow" (with the joint width)."""
        show = kind in self.OVERLAP_HINTS and self._w["no_tab"][1].isChecked()  # (tab on)
        if show:
            self.overlap_hint.setText(self.OVERLAP_HINTS[kind].format(joint=joint))
        self.overlap_hint.setVisible(show)

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
        val = lambda n: self._w[n][1].currentData()  # noqa: E731
        tab = self._w["no_tab"][1].isChecked()  # (the switch is "print a tab")
        label = tab and self.label_switch.isChecked()
        for box in set(self._switches.values()):  # off: only the header, not openable
            box.set_active(box.switch.isChecked())
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
            "label": label,
            "label_size_mm": label,
            "label_color": label,
            "back": double,
            "back_color": double and val("back") in ("blank", "text"),
            "back_text": double and val("back") == "text",
            "back_text_color": double and val("back") == "text",
        }
        grey = self._w["greyscale"][1].isChecked()
        show["saturation"] = show["hue"] = not grey
        for name, visible in show.items():
            form, w = self._rows[name]
            form.setRowVisible(w, visible)
        read, d = self._read(), FigureSettings()
        for b, names in self._resets.values():  # only when there is something to reset
            b.setEnabled(any(read[n] != getattr(d, n) for n in names))
        if not tab:
            self.overlap_hint.setVisible(False)

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
    """Paper, title, margins - edits a SheetSettings - and a Print button."""

    changed = Signal(object)
    printClicked = Signal()

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
        self.print_btn = QPushButton("Print…")
        self.print_btn.setToolTip("Print the sheet at its real size  (Ctrl+Shift+P)")
        self.print_btn.setCursor(Qt.PointingHandCursor)
        self.print_btn.clicked.connect(self.printClicked)
        h.addWidget(self.print_btn)
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
