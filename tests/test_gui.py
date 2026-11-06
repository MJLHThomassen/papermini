"""GUI smoke test (offscreen). Skipped when PySide6 is not installed."""

import os
import time

import cv2
import numpy as np
import pytest
from PIL import Image

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from papermini.settings import FigureSettings  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    from PySide6.QtCore import QSettings

    # keep the tests away from the user's real preferences
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                      str(tmp_path_factory.mktemp("settings")))
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def fresh_prefs(app):
    from papermini.gui import prefs

    prefs.store().clear()  # every test starts with default layout, theme and sections
    yield


def wait(app, cond, timeout=180):  # generous: CI runners can be slow; returns as soon as cond()
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_build_edit_and_save(app, tmp_path):
    from papermini.gui.window import MainWindow

    im = np.full((900, 700, 3), 255, np.uint8)
    cv2.ellipse(im, (350, 450), (200, 300), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "hero.png")
    Image.fromarray(np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)).save(tmp_path / "m.png")

    w = MainWindow()
    try:
        w.add_images([tmp_path / "hero.png"], FigureSettings(mask=str(tmp_path / "m.png")))
        fig = w.current()
        assert wait(app, lambda: fig.up_to_date), fig.error
        assert fig.mini.figure_height_mm == pytest.approx(42, abs=0.05)
        assert fig.mini.overlay is not None
        # defaults (fold and overlap 0) on a wide joint: no note under the overlap field
        assert fig.mini.tab_overlap_used and fig.mini.tab_joint_mm > 10
        assert not w.panel.overlap_hint.isVisibleTo(w.panel)

        # edit through the panel -> rebuild with the new height
        w.panel._w["height_mm"][1].setValue(30)
        assert fig.entry.settings.height_mm == 30
        assert wait(app, lambda: fig.up_to_date and fig.mini.figure_height_mm < 31), fig.error
        assert fig.mini.figure_height_mm == pytest.approx(30, abs=0.05)

        # crop from the source view lands in the settings
        w.crop_view.cropChanged.emit([0.1, 0.1, 0.9, 0.9])
        assert fig.entry.settings.crop == [0.1, 0.1, 0.9, 0.9]

        # sheet tab builds a layout
        w.tabs.setCurrentIndex(3)
        assert wait(app, lambda: "piece" in w.sheet_panel.info.text())

        from pathlib import Path
        w.project.path = Path(tmp_path / "proj.yaml")
        assert w.save()
        from papermini.settings import load_project
        p = load_project(tmp_path / "proj.yaml")
        assert p.figures[0].settings.height_mm == 30
        assert p.figures[0].settings.crop == [0.1, 0.1, 0.9, 0.9]
    finally:
        w._modified = False
        w.close()


def test_bad_model_reports_error_and_recovers(app, tmp_path):
    """Regression: an unusable model used to kill the build silently, and the
    figure never rebuilt again."""
    from dataclasses import replace

    from papermini.gui.window import MainWindow

    im = np.full((600, 500, 3), 255, np.uint8)
    cv2.circle(im, (250, 300), 150, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "hero.png")
    Image.fromarray(np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)).save(tmp_path / "m.png")

    w = MainWindow()
    try:
        w.add_images([tmp_path / "hero.png"], FigureSettings(model="no-such-model"))
        fig = w.current()
        assert wait(app, lambda: fig.error is not None), "build died without reporting"
        assert "unknown model" in fig.error and fig.queued is None

        # 'alpha' on an image without transparency is an error, not a full-image mask
        w._settings_changed(replace(fig.entry.settings, model="alpha"))
        assert wait(app, lambda: fig.error is not None) and "transparency" in fig.error

        # fixing the setting rebuilds
        w._settings_changed(replace(fig.entry.settings, model="mask", mask=str(tmp_path / "m.png")))
        assert wait(app, lambda: fig.up_to_date), fig.error
        assert fig.error is None and "figure" in w.info.text()
    finally:
        w._modified = False
        w.close()


def test_crop_handles(app):
    """Draw a crop box, then resize it by a corner handle, move it, and clear it."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest

    from papermini.gui.views import CropView

    v = CropView()
    v.resize(600, 600)
    img = QImage(1000, 1000, QImage.Format_RGB888)
    img.fill(Qt.white)
    v.set_image(img)
    v.show()
    app.processEvents()
    v.fit()
    got = []
    v.cropChanged.connect(got.append)
    vp = v.viewport()

    def at(x, y):  # image px -> viewport point
        return v.mapFromScene(x, y)

    def drag(a, b):
        QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
        QTest.mouseMove(vp, (a + b) / 2)
        QTest.mouseMove(vp, b)
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, b)
        app.processEvents()

    drag(at(200, 200), at(600, 700))                       # draw
    assert got[-1] == pytest.approx([0.2, 0.2, 0.6, 0.7], abs=0.01)
    assert v._hit(at(600, 700)) == "br" and v._hit(at(400, 450)) == "move"
    assert v._hit(at(200, 450)) == "l" and v._hit(at(900, 900)) == "new"

    drag(at(600, 700), at(800, 900))                       # resize by the bottom-right handle
    assert got[-1] == pytest.approx([0.2, 0.2, 0.8, 0.9], abs=0.01)

    drag(at(400, 400), at(300, 350))                       # move from inside
    assert got[-1] == pytest.approx([0.1, 0.15, 0.7, 0.85], abs=0.01)

    drag(at(500, 500), at(2000, 2000))                     # move is clamped to the image
    assert got[-1][2] == pytest.approx(1.0) and got[-1][3] == pytest.approx(1.0)

    n = len(got)
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at(50, 50))  # a click keeps the box
    assert len(got) == n and v.crop_box() is not None

    QTest.keyClick(v, Qt.Key_Delete)                       # Delete clears it
    assert got[-1] is None and v.crop_box() is None
    v.close()


def test_review_regressions(app, tmp_path):
    """Debounce survives selection, wheel does not edit unfocused fields, copies do
    not rebuild, export waits for background builds, loaded values stay exact."""
    from dataclasses import replace

    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    from papermini.gui.window import MainWindow

    im = np.full((600, 500, 3), 255, np.uint8)
    cv2.circle(im, (250, 300), 150, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "hero.png")
    Image.fromarray(np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)).save(tmp_path / "m.png")

    w = MainWindow()
    try:
        w.add_images([tmp_path / "hero.png"],
                     FigureSettings(mask=str(tmp_path / "m.png"), height_mm=42.25, dpi=3000))
        fig = w.current()
        assert wait(app, lambda: fig.up_to_date), fig.error
        # 1. selecting a figure must not zero the debounce interval
        assert w._build_timer.interval() == 250

        # 2. a wheel tick over an unfocused spin box changes nothing
        spin = w.panel._w["threshold"][1]
        before = spin.value()
        ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                         Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        app.sendEvent(spin, ev)
        assert spin.value() == before

        # 3. copies only change the sheet: same Mini object, no rebuild
        mini = fig.mini
        w.panel.copies.setValue(3)
        assert fig.entry.settings.copies == 3
        app.processEvents()
        assert fig.up_to_date and fig.mini is mini

        # 4. editing one field keeps the exact loaded values of the others
        w.panel._w["margin_mm"][1].setValue(2.0)
        s = fig.entry.settings
        assert s.margin_mm == 2.0 and s.height_mm == 42.25 and s.dpi == 3000

        # 5. export waits for the (background) rebuild, then runs
        w._settings_changed(replace(fig.entry.settings, height_mm=30))
        assert not fig.up_to_date
        done = []
        w._when_built([fig], lambda: done.append(fig.mini.figure_height_mm))
        assert wait(app, lambda: done)
        assert done[0] == pytest.approx(30, abs=0.05)
    finally:
        w._modified = False
        w.close()



def test_panel_choices_round_trip(app):
    """Combo boxes show readable names but store the setting values."""
    from papermini.gui.panels import FigurePanel

    p = FigurePanel()
    s = FigureSettings(tab_shape="round", label="", tab_color="#3b6e2a",
                       margin_fill="image", double_sided=True, back="text")
    p.set_settings(s, "x", "x")
    assert p._w["tab_shape"][1].currentText().startswith("Round")
    assert p.settings() == s
    assert not p.is_shown("tab_height_mm")               # a half disc has no separate height
    assert not p.is_shown("margin_color")                # the image fills the margin
    assert p.is_shown("tab_color") and not p.is_shown("label_size_mm")
    assert p.is_shown("back_text") and p.is_shown("back_color")
    assert p.no_label.isChecked()                       # no label = a plain coloured tab
    assert not p.is_shown("label") and p.is_shown("no_label")
    assert p.is_shown("tab_radius_mm") and not p.is_shown("tab_width_mm")
    got = []
    p.changed.connect(got.append)
    p._w["tab_shape"][1].setCurrentIndex(p._w["tab_shape"][1].findData("square"))
    assert got[-1].tab_shape == "square" and p.is_shown("tab_height_mm")
    # a blank back has a colour but no text fields
    p._w["back"][1].setCurrentIndex(p._w["back"][1].findData("blank"))
    assert p.is_shown("back_color") and not p.is_shown("back_text")
    assert not p.is_shown("back_text_color")
    # no back side at all: none of the back options
    p._w["double_sided"][1].setChecked(False)
    assert not any(p.is_shown(n) for n in ("back", "back_color", "back_text"))
    # no tab: none of the tab options, including the label
    p._w["no_tab"][1].setChecked(True)
    assert not any(p.is_shown(n) for n in ("tab_shape", "tab_width_mm", "tab_color",
                                           "_tab_label", "no_label", "label", "label_color"))



def test_colour_dialog_does_not_inherit_button_colour(app):
    """Regression: the button's style sheet coloured the whole colour dialog."""
    from PySide6.QtWidgets import QWidget

    from papermini.gui.panels import ColorButton

    b = ColorButton()
    b.set_color("#3b6e2a")
    child = QWidget(b)
    assert "QPushButton" in b.styleSheet()          # scoped to the button itself
    assert child.palette().window().color().name() != "#3b6e2a"



def test_mask_file_is_a_model_choice(app):
    from papermini.gui.panels import FigurePanel

    p = FigurePanel()
    p.set_settings(FigureSettings(), "x", "x")
    assert not p.is_shown("mask")                        # auto: no file field
    combo = p._w["model"][1]
    combo.setCurrentText("alpha"); combo.activated.emit(0)
    assert not p.is_shown("mask")                        # alpha uses the image itself
    combo.setCurrentText("mask image file"); combo.activated.emit(0)
    assert p.is_shown("mask") and p.settings().model == "mask"
    # no label as its own checkbox
    p.no_label.setChecked(True)
    assert p.settings().label == "" and not p.is_shown("label")
    p.no_label.setChecked(False)
    assert p.settings().label is None and p.is_shown("label")


def test_bleed_only_with_cutter(app):
    from papermini.gui.panels import FigurePanel

    p = FigurePanel()
    p.set_settings(FigureSettings(), "x", "x")
    assert not p.is_shown("bleed_mm")
    p._w["cutter"][1].setChecked(True)
    assert p.is_shown("bleed_mm") and not p.is_shown("cut_color")
    assert p.settings().cutter and p.settings().bleed_mm == 1.0



def test_new_window_shows_sheet_settings(app):
    """Regression: a new project's sheet bar showed 0 mm margins and an empty title
    (and editing it would have saved those)."""
    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        assert w.sheet_panel.margin.value() == 12 and w.sheet_panel.gap.value() == 7
        assert w.sheet_panel.title.text() == "Paper miniatures"
        assert not any(sec.isVisibleTo(w.panel) for sec in w.panel.sections)  # empty state
    finally:
        w.close()



def test_side_panels_can_be_resized_freely(app):
    """Regression: the sheet bar held the canvas at ~760 px, so the side panels
    could hardly be dragged wider."""
    from PySide6.QtCore import Qt

    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        w.setAttribute(Qt.WA_DontShowOnScreen)
        w.resize(1440, 900)
        w.show()
        app.processEvents()
        canvas = w.splitter.widget(1)
        assert canvas.minimumSizeHint().width() < 400
        w.splitter.setSizes([520, 400, 520])                  # much wider side panels
        app.processEvents()
        sizes = w.splitter.sizes()
        assert sizes[0] > 480 and sizes[2] > 480
        assert w.splitter.isCollapsible(0) and w.splitter.isCollapsible(2)
        assert not w.splitter.isCollapsible(1)
    finally:
        w.close()



def test_side_panel_toggles(app):
    """The header buttons and View menu collapse and reopen both side panels,
    and follow panels that were dragged shut."""
    from PySide6.QtCore import Qt

    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        w.setAttribute(Qt.WA_DontShowOnScreen)
        w.resize(1440, 900)
        w.show()
        app.processEvents()
        width = w.splitter.sizes()[0]
        assert w.side_visible(0) and w.side_visible(2) and w.a_left.isChecked()

        w.btn_left.click()                                   # header button hides it
        app.processEvents()
        assert w.splitter.sizes()[0] == 0 and not w.a_left.isChecked()
        assert w.btn_left.isVisible()                        # still there to bring it back
        w.btn_left.click()
        app.processEvents()
        assert w.splitter.sizes()[0] == width and w.a_left.isChecked()

        w.a_right.trigger()                                  # menu item hides it
        app.processEvents()
        assert w.splitter.sizes()[2] == 0 and "Show" in w.btn_right.toolTip()
        w.a_right.trigger()
        app.processEvents()
        assert w.splitter.sizes()[2] >= w.splitter.widget(2).minimumWidth()

        w.splitter.setSizes([0] + w.splitter.sizes()[1:])   # as if dragged shut
        w.splitter.splitterMoved.emit(0, 1)
        assert not w.a_left.isChecked()
        assert "View" in [a.text() for a in w.menu.actions()]
    finally:
        w.close()


def test_paper_has_no_graphics_effect(app):
    """Regression: QGraphicsDropShadowEffect re-rendered the whole paper at the current
    zoom on every repaint, so the canvas took seconds per frame when zoomed in far."""
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QGraphicsScene

    from papermini.gui.views import PaperItem, _paper

    sc = QGraphicsScene()
    item = _paper(sc, QRectF(0, 0, 50, 70))
    assert isinstance(item, PaperItem)
    assert all(it.graphicsEffect() is None for it in sc.items())
    assert item.boundingRect().contains(QRectF(-1, -1, 52, 72))  # room for the shadow


def test_drag_closed_panel_reopens_at_dragged_width(app):
    from PySide6.QtCore import Qt

    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        w.setAttribute(Qt.WA_DontShowOnScreen)
        w.resize(1440, 900)
        w.show()
        app.processEvents()
        s = w.splitter.sizes()
        w.splitter.setSizes([420, s[1] - 160, s[2]])       # dragged wider...
        w.splitter.splitterMoved.emit(420, 1)
        s = w.splitter.sizes()
        w.splitter.setSizes([0, s[1] + s[0], s[2]])        # ...then dragged shut
        w.splitter.splitterMoved.emit(0, 1)
        w.set_side_visible(0, True)
        app.processEvents()
        assert abs(w.splitter.sizes()[0] - 420) <= 2
    finally:
        w.close()



def test_panel_layout_is_remembered(app):
    """Collapsed panels and their widths come back after a restart."""
    from PySide6.QtCore import QSettings, Qt

    from papermini.gui import prefs
    from papermini.gui.window import MainWindow

    assert prefs.store().format() == QSettings.IniFormat   # not the real settings

    def window():
        w = MainWindow()
        w.setAttribute(Qt.WA_DontShowOnScreen)
        w.resize(1440, 900)
        w.show()
        app.processEvents()
        return w

    w = window()
    s = w.splitter.sizes()
    w.splitter.setSizes([400, s[1] + s[0] - 400, s[2]])
    w.splitter.splitterMoved.emit(400, 1)
    w.set_side_visible(2, False)
    right = w._side_width[2]
    w.close()

    w = window()
    try:
        assert not w.side_visible(2) and not w.a_right.isChecked()
        assert abs(w.splitter.sizes()[0] - 400) <= 2
        w.set_side_visible(2, True)
        assert abs(w.splitter.sizes()[2] - right) <= 2
        assert w.btn_left.accessibleName() == "Hide the figure list"
        assert w.btn_left.focusPolicy() == Qt.TabFocus
    finally:
        w.close()
