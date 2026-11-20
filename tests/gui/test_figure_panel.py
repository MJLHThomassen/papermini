"""Tests of the figure settings panel."""

from dataclasses import replace

import pytest
from PIL import Image

pytest.importorskip("PySide6")

from papermini.project.figure_settings import FigureSettings

pytestmark = pytest.mark.usefixtures("fake_default_model")


def test_choices_show_names_and_store_setting_values(app, prefs, size_calculator):
    """Combo boxes show readable names but store the setting values."""
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel(prefs, size_calculator)
    s = FigureSettings(
        tab_shape="round",
        label="",
        tab_color="#3b6e2a",
        margin_fill="image",
        double_sided=True,
        back="text",
    )
    p.set_settings(s, "x", "x")
    assert p.field("tab_shape").currentText().startswith("Round")
    assert p.settings() == s
    assert not p.is_shown("tab_height_mm")  # a half disc has no separate height
    assert not p.is_shown("margin_color")  # the image fills the margin
    assert p.is_shown("tab_color") and not p.is_shown("label_size_mm")
    assert p.is_shown("back_text") and p.is_shown("back_color")
    assert not p.label_switch.isChecked()  # no label = a plain colored tab
    assert not p.is_shown("label") and p.is_shown("no_label")
    assert p.is_shown("tab_radius_mm") and not p.is_shown("tab_width_mm")
    got = []
    p.changed.connect(got.append)
    p.field("tab_shape").setCurrentIndex(p.field("tab_shape").findData("square"))
    assert got[-1].tab_shape == "square" and p.is_shown("tab_height_mm")
    # a blank back has a color but no text fields
    p.field("back").setCurrentIndex(p.field("back").findData("blank"))
    assert p.is_shown("back_color") and not p.is_shown("back_text")
    assert not p.is_shown("back_text_color")
    # no back side at all: none of the back options
    p.field("double_sided").setChecked(False)
    assert not any(p.is_shown(n) for n in ("back", "back_color", "back_text"))
    # no tab: none of the tab options, and the label group cannot be turned on
    p.field("no_tab").setChecked(False)
    assert p.settings().no_tab
    assert not any(
        p.is_shown(n)
        for n in (
            "tab_shape",
            "tab_width_mm",
            "tab_color",
            "no_label",
            "label",
            "label_color",
        )
    )


def test_groups_are_switched_on_and_off_in_their_header(app, prefs, size_calculator):
    """Back side, Tab and Label each have a checkbox at the right of their header:
    ticked = the group is on (for the tab and label too, whose settings are "no_tab"
    and an empty label); unticked, the group shows only its header."""
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel(prefs, size_calculator)
    p.set_settings(FigureSettings(), "x", "x")
    heads = {s.header.text(): s for s in p.sections}
    for title, name in (
        ("Back side", "double_sided"),
        ("Tab", "no_tab"),
        ("Label", "no_label"),
    ):
        box = heads[title]
        assert box.switch is not None and box.switch.isChecked()  # all on by default
        assert box.switch.accessibleName().startswith("Print a ")
        assert box.switch.parent() is box  # in the header row
        assert box.switch.toolTip().startswith("Print a ")
    # a mini always has its outline and cut line: their switches are a token's only
    for title in ("Image outline", "Cut line"):
        assert heads[title].active() and not heads[title].switch.isVisibleTo(p)
    tab, label = heads["Tab"].switch, heads["Label"].switch
    label.setChecked(False)
    assert p.settings().label == "" and not p.is_shown("label_size_mm")
    label.setChecked(True)
    assert p.settings().label is None and p.is_shown("label_size_mm")
    # Label is a sub-group at the end of Tab: no tab, no label group either
    assert heads["Label"].parent_section is heads["Tab"]
    assert heads["Tab"].body.isAncestorOf(heads["Label"])
    tab.setChecked(False)
    assert p.settings().no_tab and not p.is_shown("no_label")
    assert not p.is_shown("label") and not p.is_shown("tab_shape")
    # a group that is off has nothing to show: its header cannot open it
    t = heads["Tab"]
    assert not t.body.isVisibleTo(t) and not t.header.isEnabled()
    t.header.click()
    assert not t.body.isVisibleTo(t)
    tab.setChecked(True)  # on: open as it was
    assert not p.settings().no_tab and t.body.isVisibleTo(t) and p.is_shown("label")
    p.set_settings(FigureSettings(no_tab=True, double_sided=False, label=""), "x", "x")
    assert not any(heads[t].switch.isChecked() for t in ("Back side", "Tab", "Label"))


def test_settings_side_never_cuts_off_controls(app, tmp_path, new_window):
    """The settings side cannot be made narrower than its widest step needs, so the
    header checkboxes and fields stay visible; a long figure name does not widen it."""
    from PySide6.QtCore import Qt

    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "a.png")
    w = new_window()
    w.setAttribute(Qt.WA_DontShowOnScreen)
    w.resize(1300, 900)
    w.show()
    w.add_images([tmp_path / "a.png"])
    w.figures[0].entry.name = "a-very-long-figure-name-" * 4
    w.list.setCurrentRow(-1)
    w.list.setCurrentRow(0)  # (shows the name again)
    p = w.panel
    for step in range(3):
        w.tabs.setCurrentIndex(step)
        sizes = w.splitter.sizes()
        w.splitter.setSizes([sizes[0], sizes[1] + sizes[2] - 1, 1])  # narrowest
        for _ in range(3):  # (the scroll bar may appear, then the body follows)
            app.processEvents()
        assert w.splitter.sizes()[2] >= p.minimumSizeHint().width()
        assert p.widget().width() <= p.viewport().width(), step  # nothing clipped
        for box in p.sections:
            if box.switch is not None and box.switch.isVisibleTo(p):
                right = box.switch.mapTo(p.widget(), box.switch.rect().topRight()).x()
                assert right <= p.viewport().width(), box.header.text()


def test_a_mask_file_is_a_model_choice(app, prefs, size_calculator):
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel(prefs, size_calculator)
    p.set_settings(FigureSettings(), "x", "x")
    assert not p.is_shown("mask")  # auto: no file field
    combo = p.field("model")
    combo.setCurrentText("alpha")
    combo.activated.emit(0)
    assert not p.is_shown("mask")  # alpha uses the image itself
    combo.setCurrentText("mask image file")
    combo.activated.emit(0)
    assert p.is_shown("mask") and p.settings().model == "mask"
    # no label: the Label group's switch
    p.label_switch.setChecked(False)
    assert p.settings().label == "" and not p.is_shown("label")
    p.label_switch.setChecked(True)
    assert p.settings().label is None and p.is_shown("label")


def test_the_settings_are_hidden_without_a_figure(app, tmp_path, new_window):
    """Regression: with no figure selected the whole form stayed visible, greyed out,
    under a small heading (the sections were looked up before they had a parent)."""
    from papermini.gui.panels.figure_fields import SECTIONS

    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "a.png")
    w = new_window()
    p = w.panel
    shown = lambda x: x.isVisibleTo(p)
    assert len(p.sections) > 3
    assert shown(p.empty_box) and p.empty_title.text() == "No figure selected"
    assert "Add images" in p.empty_text.text()
    assert not any(shown(s) for s in p.sections + [p.apply_all, p.title, p.subtitle])
    assert p.isEnabled()  # a disabled panel would grey out the message too

    w.add_images([tmp_path / "a.png"])
    assert not shown(p.empty_box) and any(shown(s) for s in p.sections)
    assert all(
        shown(s) == (st == p.step())
        for s, (st, _, _) in zip(p.sections, SECTIONS, strict=True)
    )
    assert shown(p.title) and shown(p.apply_all)

    w.list.setCurrentRow(-1)  # figures, but none selected
    assert shown(p.empty_box) and "Select a figure" in p.empty_text.text()
    assert not any(shown(s) for s in p.sections)

    w.list.setCurrentRow(0)
    w.remove_current()
    assert shown(p.empty_box) and "Add images" in p.empty_text.text()


def test_the_image_adjustments_follow_greyscale_and_reset_together(
    app, prefs, size_calculator
):
    """Step 1 has color sliders; greyscale hides saturation and hue (nothing to turn);
    Reset puts all of them back in one change, and is off while there is nothing to reset."""
    from PySide6.QtWidgets import QPushButton

    from papermini.gui.panels.figure_fields import SOURCE
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel(prefs, size_calculator)
    p.set_settings(FigureSettings(), "x", "x")
    p.set_step(SOURCE)
    box = next(b for b in p.sections if b.header.text() == "Image adjustments")
    assert box.isVisibleTo(p)
    reset = box.findChild(QPushButton, "ResetButton")
    assert reset is not None
    assert not reset.isEnabled()  # nothing to reset yet
    got = []
    p.changed.connect(got.append)
    p.field("brightness").spin.setValue(30)
    p.field("hue").slider.setValue(-90)
    assert (got[-1].brightness, got[-1].hue) == (30, -90) and reset.isEnabled()
    p.field("greyscale").setChecked(True)
    assert got[-1].greyscale and not p.is_shown("saturation") and not p.is_shown("hue")
    assert p.is_shown("brightness") and p.is_shown("contrast")
    n = len(got)
    reset.click()
    assert len(got) == n + 1  # one change, not five
    assert got[-1].adjustments().is_identity() and not reset.isEnabled()
    assert p.is_shown("saturation")
    assert "_reset_adjust" not in p.step_settings()  # (a button, not a setting)
    assert {"greyscale", "brightness", "hue"} <= p.step_settings()


def test_the_settings_follow_the_step(app, tmp_path, new_window):
    """Each step shows its own settings; "Apply to all" copies only those."""
    from papermini.gui.panels.figure_fields import MINIATURE, PRINT, SOURCE

    for n in "ab":
        Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / f"{n}.png")
    w = new_window()
    w.add_images([tmp_path / "a.png", tmp_path / "b.png"])
    p = w.panel
    titles = lambda: [s.header.text() for s in p.sections if s.isVisibleTo(p)]
    expected = [
        ["Crop", "Background removal", "Image adjustments"],
        [
            "Size",
            "Back side",
            "Image outline",
            "Cut line",
            "Tab",
            "Label",
            "Text",
            "Number",
        ],
        [],
    ]
    for i, want in enumerate(expected):
        w.views.group.button(i).click()  # the step buttons in the header
        assert w.tabs.currentIndex() == i and p.step() == i and titles() == want
        # the Print sheet step shows the sheet's own settings instead
        assert w.side.currentWidget() is (w.sheet_panel if i == PRINT else p)
        assert p.export_piece.isVisibleTo(p) == (i == MINIATURE)  # (this figure's file)
        assert p.kind_row.isVisibleTo(p) == (i == MINIATURE)
    w.tabs.setCurrentIndex(w.SOURCE)
    assert "Crop" in p.step_hint.text() and p.step() == SOURCE

    a, b = w.figures
    w.list.setCurrentRow(0)
    w.panel.changed.emit(
        replace(a.entry.settings, height_mm=30, margin_mm=3, strength=90)
    )
    w.list.itemDelegate().copiesChanged.emit(a.uid, 4)  # (set on its card)
    w.tabs.setCurrentIndex(w.MINI)
    assert "miniature" in p.apply_all.text()
    p.apply_all.click()
    assert b.entry.settings.height_mm == 30  # the Miniature step's settings...
    assert b.entry.settings.size == a.entry.settings.size == "custom"  # (and its size)
    assert b.entry.settings.margin_mm == 3
    assert b.entry.settings.strength == FigureSettings().strength  # ...not the others
    assert b.entry.settings.copies == 1  # copies stay per figure


def test_strength_and_gap_filling_are_sliders(app, prefs, size_calculator):
    """Strength and gap filling are sliders with a number box; gap filling has an
    Auto checkbox (it used to be a spin box where 0 meant auto, so 0 = off was impossible)."""
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel(prefs, size_calculator)
    p.set_settings(FigureSettings(strength=60, fill_gaps=None), "x", "x")
    th, cl = p.field("strength"), p.field("fill_gaps")
    assert th.slider.value() == th.spin.value() == 60 and th.auto is None
    assert cl.auto.isChecked() and not cl.slider.isEnabled() and not cl.spin.isEnabled()
    got = []
    p.changed.connect(got.append)

    th.slider.setValue(80)  # slider and box stay in step
    assert th.spin.value() == 80 and got[-1].strength == 80
    th.spin.setValue(25)
    assert th.slider.value() == 25 and got[-1].strength == 25

    p.set_auto_fill_gaps(14)  # what the last build picked
    assert cl.spin.value() == 14 and p.settings().fill_gaps is None
    cl.auto.setChecked(False)  # carry on from the automatic value
    assert cl.slider.isEnabled() and got[-1].fill_gaps == 14
    cl.slider.setValue(0)  # 0 = no gap filling, now possible
    assert got[-1].fill_gaps == 0
    cl.spin.setValue(300)  # past the slider's end: typed in the box
    assert got[-1].fill_gaps == 300 and cl.slider.value() == cl.slider.maximum()
    cl.auto.setChecked(True)
    assert got[-1].fill_gaps is None and cl.spin.value() == 14

    p.set_settings(FigureSettings(fill_gaps=0), "x", "x")
    assert (
        not cl.auto.isChecked() and cl.spin.value() == 0 and p.settings().fill_gaps == 0
    )


def test_number_fields_follow_the_back_side(app, prefs, size_calculator):
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel(prefs, size_calculator)
    p.set_settings(
        FigureSettings(double_sided=True, back="number", tab_front="number"), "x", "x"
    )
    assert p.field("tab_front").currentData() == "number"
    assert p.is_shown("tab_front") and p.is_shown("tab_back")
    assert p.is_shown("back_text_color") and not p.is_shown("back_text")
    p.field("back").setCurrentIndex(p.field("back").findData("text_number"))
    assert p.is_shown("back_text") and p.is_shown("back_text_color")
    p.field("back").setCurrentIndex(p.field("back").findData("mirror"))
    assert not p.is_shown("back_text_color") and not p.is_shown("back_color")
    p.field("double_sided").setChecked(False)
    assert p.is_shown("tab_front") and not p.is_shown("tab_back")  # (no back tab)
    assert p.settings().tab_front == "number"


def test_editing_a_field_keeps_the_exact_loaded_values_of_the_others(built_window):
    built_window.panel.field("margin_mm").setValue(2.0)
    s = built_window.current().entry.settings
    assert s.margin_mm == 2.0 and s.height_mm == 42.25 and s.dpi == 3000
