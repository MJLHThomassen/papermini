"""Characterisation tests of the fields of the settings panels: the field that edits
each setting, and that a value goes through it both ways. They record today's
behaviour, gaps included, so that a refactor of the options can't drop a field
unnoticed."""

from dataclasses import fields
from typing import Any

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QLineEdit,
)

from papermini.gui.fields.color_button import ColorButton
from papermini.gui.fields.kind_choice import KindChoice
from papermini.project.figure_settings import FIGURE_OPTIONS, FigureSettings
from papermini.project.sheet_settings import SheetSettings

pytestmark = pytest.mark.usefixtures("fake_default_model")

# region editing a widget


def _widget(root, path: str):
    """Find the widget at ``path``: a field of the panel, then attributes of it."""
    first, *rest = path.split(".")
    w = root.field(first) if hasattr(root, "field") else getattr(root, first)
    for name in rest:
        w = getattr(w, name)
    return w


def _shown(w):
    """Return the value a widget shows, as a user would enter it."""
    if isinstance(w, KindChoice):
        return w.value()
    if isinstance(w, QCheckBox):
        return w.isChecked()
    if isinstance(w, QAbstractSpinBox):
        return w.value()
    if isinstance(w, QComboBox):
        return w.currentText() if w.isEditable() else w.currentData()
    if isinstance(w, QLineEdit):
        return w.text()
    if isinstance(w, ColorButton):
        return w.color()
    raise TypeError(w)


def _enter(w, value, monkeypatch) -> None:
    """Enter ``value`` in a widget the way a user does."""
    if isinstance(w, KindChoice):
        w.buttons[value].click()
    elif isinstance(w, QCheckBox):
        w.setChecked(value)
    elif isinstance(w, QAbstractSpinBox):
        w.setValue(value)
    elif isinstance(w, QComboBox) and w.isEditable():
        w.setCurrentText(value)
        w.activated.emit(w.currentIndex())
    elif isinstance(w, QComboBox):
        w.setCurrentIndex(w.findData(value))
    elif isinstance(w, QLineEdit):
        w.setText(value)
        QTest.keyClick(w, Qt.Key.Key_Return)
    elif isinstance(w, ColorButton):
        monkeypatch.setattr(QColorDialog, "getColor", lambda *a: QColor(value))
        w.click()
    else:
        raise TypeError(w)


# endregion

# region figure panel

# Each setting of the figure panel: (its widget, a value entered there, the setting it
# gives, the settings it starts from).
FIGURE_FIELDS: dict[str, tuple[str, Any, Any, dict[str, Any]]] = {
    "kind": ("kind", "token", "token", {}),
    "size": ("size", "large", "large", {}),
    "height_mm": ("dimensions.h", 40.0, 40.0, {}),
    "width_mm": ("dimensions.w", 20.0, 20.0, {}),
    "margin_mm": ("margin_mm", 2.5, 2.5, {}),
    "smooth_mm": ("smooth_mm", 1.2, 1.2, {}),
    "tab_width_mm": ("tab_width_mm", 30.0, 30.0, {}),
    "tab_radius_mm": ("tab_radius_mm", 20.0, 20.0, {}),
    "tab_height_mm": ("tab_height_mm", 15.0, 15.0, {}),
    "tab_overlap_mm": ("tab_overlap_mm", 3.0, 3.0, {}),
    "fold_mm": ("fold_mm", 2.0, 2.0, {}),
    "no_tab": ("no_tab", False, True, {}),  # (the switch prints a tab)
    "tab_shape": ("tab_shape", "round", "round", {}),
    "tab_color": ("tab_color", "#3b6e2a", "#3b6e2a", {}),
    "double_sided": ("double_sided", False, False, {}),
    "back": ("back", "text", "text", {}),
    "back_text": ("back_text", "Stats", "Stats", {}),
    "back_color": ("back_color", "#eeeeee", "#eeeeee", {}),
    "back_text_color": ("back_text_color", "#111111", "#111111", {}),
    "model": ("model", "birefnet", "birefnet", {}),
    "mask": ("mask.edit", "m.png", "m.png", {}),
    "crop": ("crop.edit", "0.1, 0, 0.9, 1", [0.1, 0.0, 0.9, 1.0], {}),
    "strength": ("strength.spin", 60, 60, {}),
    # (turning automatic gap filling off keeps the value it had)
    "fill_gaps": ("fill_gaps.auto", False, 9, {}),
    "keep_all": ("keep_all", True, True, {}),
    "min_area": ("min_area", 500, 500, {}),
    "margin_fill": ("margin_fill", "image", "image", {}),
    "margin_color": ("margin_color", "#123456", "#123456", {}),
    "greyscale": ("greyscale", True, True, {}),
    "brightness": ("brightness.spin", 10, 10, {}),
    "contrast": ("contrast.spin", 20, 20, {}),
    "saturation": ("saturation.spin", -30, -30, {}),
    "hue": ("hue.spin", 90, 90, {}),
    "label": ("label", "Hero", "Hero", {}),
    "tab_front": ("tab_front", "number", "number", {}),
    "tab_back": ("tab_back", "label_number", "label_number", {}),
    "dpi": ("dpi", 150, 150, {}),
    "simplify_mm": ("simplify_mm", 0.3, 0.3, {}),
    "no_smooth": ("no_smooth", True, True, {}),
    "cut_color": ("cut_color", "#ff0000", "#ff0000", {}),
    "cut_width_mm": ("cut_width_mm", 0.5, 0.5, {}),
    "label_color": ("label_color", "#555555", "#555555", {}),
    "label_size_mm": ("label_size_mm", 4.0, 4.0, {}),
    "font": ("font", "Kalam", "Kalam", {}),
    "token_diameter_mm": ("token_diameter_mm", 40.0, 40.0, {}),
    "token_area": ("token_area.edit", "0.1, 0.2, 0.9, 1", [0.1, 0.2, 0.9, 1.0], {}),
    "token_fill": ("token_fill", "image", "image", {}),
    "token_fill_color": ("token_fill_color", "#222222", "#222222", {}),
    "token_border_mm": ("token_border_mm", 3.0, 3.0, {}),
    "token_border_color": ("token_border_color", "#333333", "#333333", {}),
    "token_outline": ("token_outline", True, True, {}),
    "token_cut_line": ("token_cut_line", True, True, {}),
    # (the token text switch has to be on)
    "token_text": ("token_text", "number", "number", {"token_text": "label"}),
    "token_text_style": ("token_text_style", "curved", "curved", {}),
    "token_text_mm": ("token_text_mm", 4.0, 4.0, {}),
    "token_text_color": ("token_text_color", "#444444", "#444444", {}),
}

# FigureSettings fields that the figure panel has no field for.
FIGURE_SETTINGS_WITHOUT_A_FIELD = {"copies"}  # (set on the figure's card)

# the panel field of a setting, where it has another name
FIGURE_FIELD_NAMES = {"height_mm": "dimensions", "width_mm": "dimensions"}

# Settings whose field has no tooltip.
FIGURE_FIELDS_WITHOUT_A_TOOLTIP: set[str] = set()


@pytest.fixture
def figure_panel(app):
    from papermini.gui.panels.figure_panel import FigurePanel

    return FigurePanel()


def test_every_figure_setting_has_a_field_or_is_listed():
    assert FIGURE_OPTIONS - set(FIGURE_FIELDS) == FIGURE_SETTINGS_WITHOUT_A_FIELD


# (These tests check every setting on one panel: building a FigurePanel takes about
# half a second.)


def test_each_figure_setting_has_its_panel_field(figure_panel):
    missing = set()
    for name in FIGURE_OPTIONS:
        try:
            figure_panel.field(FIGURE_FIELD_NAMES.get(name, name))
        except KeyError:
            missing.add(name)
    assert missing == FIGURE_SETTINGS_WITHOUT_A_FIELD


def test_each_figure_field_shows_its_setting(figure_panel):
    wrong = {}  # setting: (what its field shows, what it should show)
    for name, (path, entered, setting, start) in FIGURE_FIELDS.items():
        figure_panel.set_settings(FigureSettings(**{**start, name: setting}), "x", "x")
        shown = _shown(_widget(figure_panel, path))
        if shown != entered:
            wrong[name] = (shown, entered)
    assert wrong == {}


def test_each_figure_field_edits_its_setting(figure_panel, monkeypatch):
    got = []
    figure_panel.changed.connect(got.append)
    wrong = {}  # setting: (the value the panel emitted, the value it should emit)
    for name, (path, entered, setting, start) in FIGURE_FIELDS.items():
        figure_panel.set_settings(FigureSettings(**start), "x", "x")
        got.clear()
        _enter(_widget(figure_panel, path), entered, monkeypatch)
        result = getattr(got[-1], name) if got else "no change emitted"
        if result != setting:
            wrong[name] = (result, setting)
    assert wrong == {}


def test_each_figure_field_has_a_tooltip(figure_panel):
    without = set()
    for name, (path, *_) in FIGURE_FIELDS.items():
        w = _widget(
            figure_panel, path if name in FIGURE_FIELD_NAMES else path.split(".")[0]
        )
        if not w.toolTip():
            without.add(name)
    assert without == FIGURE_FIELDS_WITHOUT_A_TOOLTIP


def test_a_tokens_label_field_edits_the_label(figure_panel):
    figure_panel.set_settings(FigureSettings(kind="token", label="Hero"), "x", "x")
    w = figure_panel.field("token_label")
    assert w.text() == "Hero"
    w.setText("Goblin")
    QTest.keyClick(w, Qt.Key.Key_Return)
    assert figure_panel.settings().label == "Goblin"


# endregion

# region sheet panel

# Each setting of the sheet panel: (its widget, a value entered there, the setting it
# gives, the settings it starts from).
CUSTOM_A4: dict[str, Any] = {
    "paper": "custom",
    "paper_width_mm": 210.0,
    "paper_height_mm": 297.0,
}
SHEET_FIELDS: dict[str, tuple[str, Any, Any, dict[str, Any]]] = {
    "paper": ("paper", "a3", "a3", {}),
    "orientation": ("orientation", "landscape", "landscape", {}),
    "paper_width_mm": ("paper_w", 200.0, 200.0, CUSTOM_A4),
    "paper_height_mm": ("paper_h", 300.0, 300.0, CUSTOM_A4),
    "title": ("title", "Goblins", "Goblins", {}),
    "margin_mm": ("margin", 8.0, 8.0, {}),
    "gap_mm": ("gap", 5.0, 5.0, {}),
    "cut": ("cut", "machine", "machine", {}),
    "bleed_mm": ("bleed", 2.0, 2.0, {}),
    "marks": ("marks", "silhouette", "silhouette", {}),
    "cut_folds": ("cut_folds", True, True, {}),
    "mat": ("mat", "12x12", "12x12", {}),
}

# SheetSettings fields that the sheet panel has no field for.
SHEET_SETTINGS_WITHOUT_A_FIELD = {"copies", "enabled", "output", "preview"}


@pytest.fixture
def sheet_panel(app):
    from papermini.gui.panels.sheet_panel import SheetPanel

    return SheetPanel()


def test_every_sheet_setting_has_a_field_or_is_listed():
    names = {f.name for f in fields(SheetSettings)}
    assert names - set(SHEET_FIELDS) == SHEET_SETTINGS_WITHOUT_A_FIELD


@pytest.mark.parametrize("name", sorted(SHEET_FIELDS))
def test_each_sheet_field_shows_its_setting(sheet_panel, name):
    path, entered, setting, start = SHEET_FIELDS[name]
    sheet_panel.set_settings(SheetSettings(**{**start, name: setting}))
    assert _shown(_widget(sheet_panel, path)) == entered


@pytest.mark.parametrize("name", sorted(SHEET_FIELDS))
def test_each_sheet_field_edits_its_setting(sheet_panel, monkeypatch, name):
    path, entered, setting, start = SHEET_FIELDS[name]
    sheet_panel.set_settings(SheetSettings(**start))
    got = []
    sheet_panel.changed.connect(got.append)
    _enter(_widget(sheet_panel, path), entered, monkeypatch)
    assert got and getattr(got[-1], name) == setting


@pytest.mark.parametrize("name", sorted(SHEET_FIELDS))
def test_each_sheet_field_has_a_tooltip(sheet_panel, name):
    assert _widget(sheet_panel, SHEET_FIELDS[name][0]).toolTip()


# endregion
