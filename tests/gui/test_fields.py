"""Tests of the input widgets of the settings panels."""

import pytest

pytest.importorskip("PySide6")

from papermini.project.figure_settings import FigureSettings

pytestmark = pytest.mark.usefixtures("fake_default_model")


def test_color_dialog_does_not_inherit_button_color(app):
    """Regression: the button's style sheet colored the whole color dialog."""
    from PySide6.QtWidgets import QWidget

    from papermini.gui.fields.color_button import ColorButton

    b = ColorButton()
    b.set_color("#3b6e2a")
    child = QWidget(b)
    assert "QPushButton" in b.styleSheet()  # scoped to the button itself
    assert child.palette().window().color().name() != "#3b6e2a"


def test_decimal_fields_take_a_point_in_any_locale(app, prefs, size_calculator):
    """Regression: on a system with a decimal comma (e.g. Dutch) the fields showed
    "42,00 mm" and a typed "12.5" was not read as 12.5."""
    from PySide6.QtCore import QLocale, Qt
    from PySide6.QtTest import QTest

    from papermini.gui.fields.double_spin_box import DoubleSpinBox
    from papermini.gui.panels.figure_panel import FigurePanel

    old = QLocale()
    QLocale.setDefault(QLocale(QLocale.Dutch, QLocale.Netherlands))
    try:
        p = FigurePanel(prefs, size_calculator)
        p.set_settings(FigureSettings(height_mm=42), "x", "x")
        box = p.size_field.h
        assert isinstance(box, DoubleSpinBox) and box.text() == "42.00 mm"
        for typed in ("12.5", "12,5"):
            box.lineEdit().selectAll()
            QTest.keyClicks(box.lineEdit(), typed)
            QTest.keyClick(box.lineEdit(), Qt.Key_Return)
            assert box.value() == 12.5 and box.text() == "12.50 mm", typed
        assert p.settings().height_mm == 12.5
    finally:
        QLocale.setDefault(old)


def test_color_sliders_snap_to_their_centre(app):
    """A slider around 0 (the color adjustments) fills from the middle, marks 0 with a
    short line, snaps to 0 when dragged close by (typed values are kept), and goes back to
    0 on a double-click. Sliders that start at 0 (strength) stay as they were."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QColor, QMouseEvent

    from papermini.gui import theme
    from papermini.gui.fields.slider import SNAP_PX
    from papermini.gui.fields.slider_field import SliderField

    theme.apply(app, "light")  # (as the window does)
    assert SliderField(0, 254, 254).slider.centre is None
    f = SliderField(-100, 100, 100)
    f.setAttribute(Qt.WA_DontShowOnScreen)
    f.resize(300, 40)
    f.show()
    app.processEvents()
    sl = f.slider
    assert sl.centre == 0
    got = []
    f.valueChanged.connect(lambda: got.append(f.value()))

    def x_of(v):
        return sl.handle_rect(v).center().x()

    def send(kind, x, held=Qt.LeftButton):
        t = {
            "press": QEvent.MouseButtonPress,
            "move": QEvent.MouseMove,
            "release": QEvent.MouseButtonRelease,
            "double": QEvent.MouseButtonDblClick,
        }[kind]
        pos = QPointF(x, sl.height() / 2)
        b = Qt.NoButton if kind == "move" else Qt.LeftButton
        app.sendEvent(
            sl,
            QMouseEvent(
                t,
                pos,
                sl.mapToGlobal(pos),
                b,
                Qt.NoButton if kind == "release" else held,
                Qt.NoModifier,
            ),
        )

    def drag(to_x):
        send("press", x_of(sl.value()))
        send("move", to_x)
        send("release", to_x)
        return f.value()

    assert drag(x_of(50)) == 50  # far away: where it is put
    assert drag(x_of(0) + SNAP_PX - 2) == 0  # close by: snapped to 0
    assert drag(x_of(-60)) == -60
    assert drag(x_of(0) - SNAP_PX + 2) == 0
    assert drag(x_of(0) + 3 * SNAP_PX) > 0  # past the snap: free again
    f.spin.setValue(2)
    assert f.value() == 2  # typed values are kept
    send("press", x_of(2))
    send("release", x_of(2))
    send("double", x_of(2))
    send("release", x_of(2))
    assert f.value() == 0 and got[-1] == 0  # double-click: back to 0

    t = theme.current
    f.setValue(60)
    img = f.grab().toImage()
    cy = sl.mapTo(f, sl.rect().center()).y()
    off = sl.mapTo(f, sl.rect().topLeft()).x()
    accent, border = QColor(t.accent), QColor(t.border)

    def near(c, ref):
        return (
            max(
                abs(c.red() - ref.red()),
                abs(c.green() - ref.green()),
                abs(c.blue() - ref.blue()),
            )
            < 40
        )

    cx, vx = off + int(sl.centre_x()), off + x_of(60)
    assert near(img.pixelColor((cx + vx) // 2, cy), accent)  # filled from 0 to 60
    assert near(img.pixelColor(off + x_of(-50), cy), border)  # not left of 0
    mark = QColor(t.muted)
    assert any(
        near(img.pixelColor(cx + dx, cy - 5), mark) for dx in (-1, 0, 1)
    )  # the 0 mark
    f.close()


def test_size_fields_keep_proportions_until_unlinked(app, prefs, size_calculator):
    """Linked, the field typed in sets the size and the other follows the figure's
    proportions; unlinked, both are set (the figure is stretched)."""
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel(prefs, size_calculator)
    p.set_settings(FigureSettings(height_mm=40), "x", "x")
    f = p.size_field
    assert f.linked() and f.w.text() == "—"  # proportions not known yet
    p.set_aspect(0.5)
    assert f.w.value() == 20
    f.w.setValue(30)  # typing the width
    s = p.settings()
    assert (s.height_mm, s.width_mm) == (None, 30) and f.h.value() == 60
    f.link.click()  # unlink: both as shown
    s = p.settings()
    assert (s.height_mm, s.width_mm) == (60, 30) and not f.linked()
    f.h.setValue(50)  # the width stays
    assert (p.settings().height_mm, p.settings().width_mm) == (50, 30)
    f.link.click()  # linked again: by height
    s = p.settings()
    assert (s.height_mm, s.width_mm) == (50, None) and f.w.value() == 25
    p.set_settings(FigureSettings(height_mm=42, width_mm=10), "x", "x")
    assert not f.linked() and (f.h.value(), f.w.value()) == (42, 10)


def test_the_font_field_lists_the_fonts_and_keeps_a_missing_one(
    app, prefs, size_calculator
):
    """The bundled fonts first, the installed ones once found; a font this computer does
    not have is kept, marked and warned about."""
    from papermini.gui.panels.figure_panel import FigurePanel
    from papermini.support import fonts

    p = FigurePanel(prefs, size_calculator)
    w = p.field("font")
    names = lambda: [w.itemData(i) for i in range(w.count()) if w.itemData(i)]
    assert names() == [f.name for f in fonts.bundled()]
    s = FigureSettings(font="Kalam")
    p.set_settings(s, "x", "x")
    assert w.currentText() == "Kalam" and p.settings() == s
    got = []
    p.changed.connect(got.append)
    w.setCurrentIndex(w.findData("Almendra"))
    assert got[-1].font == "Almendra"
    # before the installed fonts are known, an unknown font is shown as it is
    p.set_settings(FigureSettings(font="Georgia"), "x", "x")
    assert w.currentText() == "Georgia" and p.font_warning.isHidden()
    p.set_installed_fonts(["Arial", "Georgia"])
    assert names()[-2:] == ["Arial", "Georgia"] and w.currentText() == "Georgia"
    assert p.font_warning.isHidden() and p.settings().font == "Georgia"
    # once they are known, a missing one is marked, and kept in the settings
    p.set_settings(FigureSettings(font="No Such Font"), "x", "x")
    assert w.currentText() == "No Such Font (not on this computer)"
    assert not p.font_warning.isHidden() and "prints in Times" in p.font_warning.text()
    assert p.settings().font == "No Such Font"
    p.set_settings(FigureSettings(font="Arial"), "x", "x")
    assert p.font_warning.isHidden()


def test_the_wheel_over_an_unfocused_field_changes_nothing(app, built_window):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    field = built_window.panel.field("strength")
    before = field.value()
    for part in (field.slider, field.spin):
        ev = QWheelEvent(
            QPointF(5, 5),
            QPointF(5, 5),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.NoScrollPhase,
            False,
        )
        app.sendEvent(part, ev)
    assert field.value() == before
