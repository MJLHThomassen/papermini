"""Tests that the settings panels build each field from the option of its setting."""

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractSpinBox, QCheckBox, QComboBox, QFormLayout

from papermini.project.figure_settings import FigureSettings
from papermini.project.sheet_settings import SheetSettings

pytestmark = pytest.mark.usefixtures("fake_default_model")

# the sheet panel's widget of each setting
SHEET_WIDGETS = {
    "paper": "paper",
    "orientation": "orientation",
    "paper_width_mm": "paper_w",
    "paper_height_mm": "paper_h",
    "title": "title",
    "margin_mm": "margin",
    "gap_mm": "gap",
    "cut": "cut",
    "bleed_mm": "bleed",
    "marks": "marks",
    "cut_folds": "cut_folds",
    "mat": "mat",
}


@pytest.fixture
def figure_widgets(app, prefs, size_calculator):
    """Returns each setting's widget in a figure panel, by setting."""
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel(prefs, size_calculator)
    p.set_settings(FigureSettings(), "x", "x")
    widgets = {}
    for name in FigureSettings.options():
        try:
            widgets[name] = p.field(name)
        except KeyError:
            continue
    yield widgets  # (the panel stays alive until the test ends)


@pytest.fixture
def sheet_widgets(app, prefs):
    """Returns each setting's widget in a sheet panel, by setting."""
    from papermini.gui.panels.sheet_panel import SheetPanel

    p = SheetPanel(prefs)
    yield {name: getattr(p, attr) for name, attr in SHEET_WIDGETS.items()}


def _suffix(unit: str) -> str:
    return f" {unit}" if unit.isalpha() else unit


def _label(w) -> str:
    """Return the text of the form label beside ``w``, or its own text."""
    form = w.parentWidget().layout()
    label = form.labelForField(w) if isinstance(form, QFormLayout) else None
    return label.text() if label is not None else w.text()


@pytest.mark.parametrize("settings", [FigureSettings, SheetSettings])
def test_each_number_field_has_its_options_range_step_and_unit(
    settings, figure_widgets, sheet_widgets
):
    widgets = figure_widgets if settings is FigureSettings else sheet_widgets
    wrong = {}
    for name, option in settings.options().items():
        w = widgets.get(name)
        if not isinstance(w, QAbstractSpinBox) or option.slider is not None:
            continue
        shown = (w.minimum(), w.maximum(), w.singleStep(), w.suffix())
        expected = (*option.widget, option.step, _suffix(option.unit))
        if shown != expected:
            wrong[name] = (shown, expected)
    assert wrong == {}
    assert {n for n, w in widgets.items() if isinstance(w, QAbstractSpinBox)}


def test_each_slider_has_its_options_range_and_auto(figure_widgets):
    sliders = {n: o for n, o in FigureSettings.options().items() if o.slider}
    assert sliders
    for name, option in sliders.items():
        w = figure_widgets[name]
        assert (w.spin.minimum(), w.spin.maximum()) == option.widget
        assert w.slider.maximum() == option.slider
        assert w.spin.suffix() == _suffix(option.unit)
        assert (w.auto is not None) == option.auto


@pytest.mark.parametrize("settings", [FigureSettings, SheetSettings])
def test_each_choice_field_names_its_options_choices(
    settings, figure_widgets, sheet_widgets
):
    widgets = figure_widgets if settings is FigureSettings else sheet_widgets
    for name, option in settings.options().items():
        w = widgets.get(name)
        if not isinstance(w, QComboBox) or not option.choices:
            continue
        items = [(w.itemText(i), w.itemData(i)) for i in range(w.count())]
        expected = list(zip(option.choice_labels, option.choices, strict=True))
        if name == "token_text":  # (the section's switch turns it off)
            expected = [item for item in expected if item[1] != "none"]
        if name == "mat":
            expected = [("Any size", ""), *expected]
        assert items == expected, name


@pytest.mark.parametrize("settings", [FigureSettings, SheetSettings])
def test_each_field_has_its_options_label(settings, figure_widgets, sheet_widgets):
    widgets = figure_widgets if settings is FigureSettings else sheet_widgets
    wrong = {}
    for name, option in settings.options().items():
        w = widgets.get(name)
        if w is None or name == "kind":
            continue
        if isinstance(w, QCheckBox) and not w.text():  # a switch in a header
            shown = w.accessibleName()
        else:
            shown = _label(w)
        if shown != option.label:
            wrong[name] = (shown, option.label)
    assert wrong == {}


def test_a_crop_that_cannot_be_read_keeps_the_crop(app, prefs, size_calculator):
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel(prefs, size_calculator)
    p.set_settings(FigureSettings(crop=[0.1, 0.0, 0.9, 1.0]), "x", "x")
    edit = p.field("crop").edit
    for text in ("not a crop", "1, 2, 3"):
        edit.setText(text)
        QTest.keyClick(edit, Qt.Key.Key_Return)
        assert p.settings().crop == [0.1, 0.0, 0.9, 1.0]
    edit.setText("0.2, 0, 0.8, 1")
    QTest.keyClick(edit, Qt.Key.Key_Return)
    edit.setText("still not a crop")
    QTest.keyClick(edit, Qt.Key.Key_Return)
    assert p.settings().crop == [0.2, 0.0, 0.8, 1.0]
