"""Tests of token figures in the app."""

import pytest
from PIL import Image

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QToolButton

from papermini.gui.exporting.export_dialogs import ExportDialogs
from papermini.gui.step import Step
from papermini.pipeline.token_options import TokenOptions
from papermini.project.figure_settings import FigureSettings


def test_the_kind_switches_the_settings_groups(
    fonts, app, prefs, size_calculator, qt_fonts, themes
):
    from papermini.gui.panels.figure_panel import FigurePanel

    p = FigurePanel(prefs, size_calculator, fonts, qt_fonts, themes)
    got = []
    p.changed.connect(got.append)
    p.set_settings(FigureSettings(label="Boss"), "x", "x")
    p.set_step(Step.MINIATURE)
    shown = lambda: [s.header.text() for s in p.sections if s.isVisibleTo(p)]
    assert "Back side" in shown() and "Token" not in shown()
    assert p.kind_row.isVisibleTo(p) and p.is_shown("dimensions")
    p.field("kind").buttons["token"].click()
    assert got[-1].kind == "token" and got[-1].label == "Boss"  # (the label is kept)
    assert shown() == [
        "Size",
        "Token",
        "Token text",
        "Image outline",
        "Cut line",
        "Text",
    ]
    assert p.is_shown("token_diameter_mm") and not p.is_shown("dimensions")
    assert "token" in p.step_hint.text()
    # token text: off is "none"; on, it shows the label first
    assert not p.token_text_switch.isChecked() and got[-1].token_text == "none"
    p.token_text_switch.setChecked(True)
    assert got[-1].token_text == "label" and p.is_shown("token_text_mm")
    # curved text: the ring is at least as wide as the text needs, and says so
    style = p.field("token_text_style")
    style.setCurrentIndex(style.findData("curved"))
    ring = p.field("token_border_mm")
    assert ring.minimum() == TokenOptions.min_ring_mm(
        2.5
    ) and ring.value() == TokenOptions.min_ring_mm(2.5)
    assert p.ring_hint.isVisibleTo(p) and "3.5 mm" in p.ring_hint.text()
    # a token can switch its outline and cut line off; both off by default
    for name in ("token_outline", "token_cut_line"):
        switch = p.field(name)
        box = next(b for b in p.sections if b.switch is switch)
        assert switch.isVisibleTo(p) and not box.active()
    p.field("kind").buttons["mini"].click()
    assert got[-1].kind == "mini" and "Back side" in shown()


def _built(wait, w):
    f = w.figures[0]
    assert wait(lambda: f.mini is not None and f.up_to_date)
    return f.mini


@pytest.fixture
def window(window, wait, tmp_path, transparent_figure, size_calculator):
    """The shared main window with one token figure, built, in the Miniature step."""
    w = window
    w.resize(1300, 820)
    w.add_images(
        [transparent_figure(tmp_path / "goblin.png")],
        size_calculator.settings_with_size({"kind": "token", "model": "alpha"}),
    )
    w.list.setCurrentRow(0)
    w.tabs.setCurrentIndex(Step.MINIATURE)
    assert wait(lambda: w.figures[0].mini is not None and w.figures[0].up_to_date)
    return w


def test_a_token_figure_can_be_dragged(app, window, wait):
    from papermini.gui.views.mini_view import MiniView

    w = window
    m = w.figures[0].mini
    v = w.mini_view
    items = lambda: len(v.scene().items())
    b0 = m.token.figure_box
    cx, cy = (b0[0] + b0[2]) / 2, (b0[1] + b0[3]) / 2
    pa, pb = v.mapFromScene(QPointF(cx, cy)), v.mapFromScene(QPointF(cx + 3, cy + 2))
    hover = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(pa),
        QPointF(v.viewport().mapToGlobal(pa)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    app.sendEvent(v.viewport(), hover)
    assert isinstance(v, MiniView)
    cursor = v.viewport().cursor().shape()
    assert cursor == Qt.CursorShape.SizeAllCursor  # a drag moves the figure
    n = items()
    QTest.mousePress(v.viewport(), Qt.MouseButton.LeftButton, pos=pa)
    for k in range(1, 5):
        QTest.mouseMove(v.viewport(), pa + (pb - pa) * (k / 4))
    assert items() > n  # the figure moves with the mouse
    QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton, pos=pb)
    assert w.figures[0].entry.settings.token_area is not None
    m = _built(wait, w)
    b = m.token.figure_box
    assert (b[0] - b0[0], b[1] - b0[1]) == pytest.approx((3, 2), abs=0.15)
    # a corner makes it bigger around the box's centre
    pa = v.mapFromScene(QPointF(b[2], b[3]))
    pb = v.mapFromScene(QPointF(b[2] + 2, b[3] + 2))
    QTest.mousePress(v.viewport(), Qt.MouseButton.LeftButton, pos=pa)
    QTest.mouseMove(v.viewport(), pb)
    QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton, pos=pb)
    b1 = _built(wait, w).token.figure_box
    assert b1[2] - b1[0] > b[2] - b[0]
    assert ((b1[0] + b1[2]) / 2, (b1[1] + b1[3]) / 2) == pytest.approx(
        ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), abs=0.15
    )
    # Esc cancels a drag, a click changes nothing
    area = w.figures[0].entry.settings.token_area
    n = items()
    QTest.mousePress(v.viewport(), Qt.MouseButton.LeftButton, pos=pa)
    QTest.mouseMove(v.viewport(), pb)
    QTest.keyClick(v, Qt.Key.Key_Escape)
    assert items() == n
    QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton, pos=pb)
    QTest.mouseClick(
        v.viewport(), Qt.MouseButton.LeftButton, pos=v.mapFromScene(QPointF(cx, cy))
    )
    assert w.figures[0].entry.settings.token_area == area
    # Clear fits it again
    w.panel.field("token_area").findChild(QToolButton).click()
    assert w.figures[0].entry.settings.token_area is None


def test_a_figure_exports_as_svg_or_png(app, window, tmp_path, monkeypatch, prefs):
    w = window
    item = w.list.item(0)
    from papermini.gui.widgets.figure_delegate import SUBTITLE_ROLE

    assert item.data(SUBTITLE_ROLE) == "⌀ 25 mm"
    for name, filt in (
        ("a.png", ExportDialogs.PNG_FILTER),
        ("b", ExportDialogs.PNG_FILTER),
        ("c.svg", ExportDialogs.SVG_FILTER),
    ):
        monkeypatch.setattr(
            QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, n=name, f=filt: (str(tmp_path / n), f)),
        )
        w.export_current()
    assert {"a.png", "b.png", "c.svg"} <= {p.name for p in tmp_path.iterdir()}
    assert Image.open(tmp_path / "a.png").width == pytest.approx(26 * 256 / 25.4, abs=3)
    prefs.set_png_size_mode("dpi")
    prefs.set_png_dpi(127)  # 5 pixels per mm
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a: (str(tmp_path / "d.png"), ExportDialogs.PNG_FILTER)),
    )
    w.export_current()
    assert Image.open(tmp_path / "d.png").width == pytest.approx(26 * 5, abs=3)
    # Export all asks which files to write
    out = tmp_path / "all"
    out.mkdir()
    monkeypatch.setattr(ExportDialogs, "ask_format", lambda self, parent: "both")
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a: str(out))
    )
    w.export_all()
    assert sorted(p.suffix for p in out.iterdir()) == [".png", ".svg"]
    monkeypatch.setattr(ExportDialogs, "ask_format", lambda self, parent: None)
    w.export_all()
    assert len(list(out.iterdir())) == 2
