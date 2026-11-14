"""GUI smoke test (offscreen). Skipped when PySide6 is not installed."""

import os
import time
from dataclasses import replace

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


class DarkSegmenter:
    """Stands in for a real model: everything darker than mid-grey is the figure."""

    def __init__(self, path, *a, **k):
        self.path = path

    def __call__(self, im):
        return np.where(np.asarray(im.convert("L")) < 128, 255, 0).astype(np.uint8)


@pytest.fixture(autouse=True)
def fake_default_model(monkeypatch, isolated_model_cache):
    """The default model is "downloaded" (a dummy file) and segments by darkness, so
    figures build without the real model and without a download prompt; the other
    models stay missing."""
    from papermini import segment

    monkeypatch.setattr(segment, "OnnxSegmenter", DarkSegmenter)
    path = segment.model_path(segment.DEFAULT_MODEL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a real model")


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
        assert fig.mini.figure_height_mm == pytest.approx(32, abs=0.05)  # Medium
        assert fig.mini.source_outline and w.crop_view._outline_items  # on the source
        # defaults (fold and overlap 0) on a wide joint: no note under the overlap field
        assert fig.mini.tab_overlap_used and fig.mini.tab_joint_mm > 10
        assert not w.panel.overlap_hint.isVisibleTo(w.panel)

        # edit through the panel -> rebuild with the new height
        w.panel.size_field.h.setValue(30)
        assert fig.entry.settings.height_mm == 30
        assert wait(app, lambda: fig.up_to_date and fig.mini.figure_height_mm < 31), fig.error
        assert fig.mini.figure_height_mm == pytest.approx(30, abs=0.05)

        # crop from the source view lands in the settings
        w.crop_view.cropChanged.emit([0.1, 0.1, 0.9, 0.9])
        assert fig.entry.settings.crop == [0.1, 0.1, 0.9, 0.9]

        # sheet tab builds a layout
        w.tabs.setCurrentIndex(w.SHEET)
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
        field = w.panel._w["strength"][1]
        before = field.value()
        for part in (field.slider, field.spin):  # nor over an unfocused slider
            ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                             Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
            app.sendEvent(part, ev)
        assert field.value() == before

        # 3. copies (on the figure's card) only change the sheet: same Mini, no rebuild
        mini = fig.mini
        click_copies(w, 0, "+", 2)
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
    assert not p.label_switch.isChecked()               # no label = a plain colored tab
    assert not p.is_shown("label") and p.is_shown("no_label")
    assert p.is_shown("tab_radius_mm") and not p.is_shown("tab_width_mm")
    got = []
    p.changed.connect(got.append)
    p._w["tab_shape"][1].setCurrentIndex(p._w["tab_shape"][1].findData("square"))
    assert got[-1].tab_shape == "square" and p.is_shown("tab_height_mm")
    # a blank back has a color but no text fields
    p._w["back"][1].setCurrentIndex(p._w["back"][1].findData("blank"))
    assert p.is_shown("back_color") and not p.is_shown("back_text")
    assert not p.is_shown("back_text_color")
    # no back side at all: none of the back options
    p._w["double_sided"][1].setChecked(False)
    assert not any(p.is_shown(n) for n in ("back", "back_color", "back_text"))
    # no tab: none of the tab options, and the label group cannot be turned on
    p._w["no_tab"][1].setChecked(False)
    assert p.settings().no_tab
    assert not any(p.is_shown(n) for n in ("tab_shape", "tab_width_mm", "tab_color",
                                           "no_label", "label", "label_color"))


def test_groups_are_switched_on_and_off_in_their_header(app):
    """Back side, Tab and Label each have a checkbox at the right of their header:
    ticked = the group is on (for the tab and label too, whose settings are "no_tab"
    and an empty label); unticked, the group shows only its header."""
    from papermini.gui.panels import FigurePanel

    p = FigurePanel()
    p.set_settings(FigureSettings(), "x", "x")
    heads = {s.header.text(): s for s in p.sections}
    for title, name in (("Back side", "double_sided"), ("Tab", "no_tab"),
                        ("Label", "no_label")):
        box = heads[title]
        assert box.switch is not None and box.switch.isChecked()   # all on by default
        assert box.switch.accessibleName().startswith("Print a ")
        assert box.switch.parent() is box                          # in the header row
        assert box.switch.toolTip().startswith("Print a ")
    assert heads["Outline and cut line"].switch is None
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
    tab.setChecked(True)                                   # on: open as it was
    assert not p.settings().no_tab and t.body.isVisibleTo(t) and p.is_shown("label")
    p.set_settings(FigureSettings(no_tab=True, double_sided=False, label=""), "x", "x")
    assert not any(heads[t].switch.isChecked() for t in ("Back side", "Tab", "Label"))



def test_settings_side_never_cuts_off_controls(app, tmp_path):
    """The settings side cannot be made narrower than its widest step needs, so the
    header checkboxes and fields stay visible; a long figure name does not widen it."""
    from PySide6.QtCore import Qt

    from papermini.gui.window import MainWindow

    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "a.png")
    w = MainWindow()
    w.setAttribute(Qt.WA_DontShowOnScreen)
    try:
        w.resize(1300, 900)
        w.show()
        w.add_images([tmp_path / "a.png"])
        w.figures[0].entry.name = "a-very-long-figure-name-" * 4
        w._show_current()
        p = w.panel
        for step in range(3):
            w.tabs.setCurrentIndex(step)
            sizes = w.splitter.sizes()
            w.splitter.setSizes([sizes[0], sizes[1] + sizes[2] - 1, 1])  # narrowest
            for _ in range(3):  # (the scroll bar may appear, then the body follows)
                app.processEvents()
            assert w.splitter.sizes()[2] >= p.minimumSizeHint().width()
            assert p.widget().width() <= p.viewport().width(), step   # nothing clipped
            for box in p.sections:
                if box.switch is not None and box.switch.isVisibleTo(p):
                    right = box.switch.mapTo(p.widget(), box.switch.rect().topRight()).x()
                    assert right <= p.viewport().width(), box.header.text()
    finally:
        w._modified = False
        w.close()


def test_color_dialog_does_not_inherit_button_color(app):
    """Regression: the button's style sheet colored the whole color dialog."""
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
    # no label: the Label group's switch
    p.label_switch.setChecked(False)
    assert p.settings().label == "" and not p.is_shown("label")
    p.label_switch.setChecked(True)
    assert p.settings().label is None and p.is_shown("label")


def test_sheet_bar_cut_by_machine(app):
    """Bleed, marks and the cut file only show (and only matter) when cut by machine."""
    from papermini.gui.panels import SheetPanel
    from papermini.settings import SheetSettings

    p = SheetPanel()
    got = []
    p.changed.connect(got.append)
    p.set_settings(SheetSettings())
    for w in (p.bleed, p.marks, p.cut_folds):
        assert not p.is_shown(w)
    p.cut.setCurrentIndex(p.cut.findData("machine"))
    assert got[-1].cut == "machine" and got[-1].bleed_mm == 1.0
    for w in (p.bleed, p.marks, p.cut_folds):
        assert p.is_shown(w)
    p.marks.setCurrentIndex(p.marks.findData("silhouette"))
    p.cut_folds.setChecked(True)
    assert got[-1].marks == "silhouette" and got[-1].cut_folds
    p.set_settings(SheetSettings(cut="machine", bleed_mm=2.0))
    assert p.bleed.value() == 2.0 and p.is_shown(p.bleed)
    p.marks.setCurrentIndex(p.marks.findData("none"))
    assert got[-1].marks == "none"



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
        w.resize(1900, 900)  # (room for the settings side's minimum)
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


def test_source_image_lies_on_paper_with_a_shadow(app):
    """The Source view shows the image on the same shadowed paper as the Miniature
    and Print sheet views (painted by the item, not a graphics effect)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage

    from papermini.gui.views import CropView, PaperItem

    v = CropView()
    img = QImage(400, 300, QImage.Format_RGB32)
    img.fill(0x808080)
    v.set_image(img)
    paper = [it for it in v.scene().items() if isinstance(it, PaperItem)]
    assert len(paper) == 1 and paper[0].rect() == QRectF(0, 0, 400, 300)
    assert paper[0].zValue() < 0                                  # under the image
    assert paper[0].boundingRect().contains(QRectF(-10, -10, 420, 320))
    assert all(it.graphicsEffect() is None for it in v.scene().items())
    v.set_image(None)
    assert not v.scene().items()


def test_drag_closed_panel_reopens_at_dragged_width(app):
    from PySide6.QtCore import Qt

    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        w.setAttribute(Qt.WA_DontShowOnScreen)
        w.resize(1900, 900)  # (room for the settings side's minimum)
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
        w.resize(1900, 900)  # (room for the settings side's minimum)
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


@pytest.fixture
def model_cache(monkeypatch, tmp_path):
    """An empty model folder and a fake download (no network, no real model)."""
    from papermini import segment

    monkeypatch.setenv("PAPERMINI_CACHE", str(tmp_path / "cache"))
    calls = []

    def fake_download(url, dest, progress=None, cancel=None, **_):
        calls.append(dest.name)
        for i in range(1, 4):
            if cancel is not None and cancel.is_set():
                raise segment.ModelError("model download cancelled")
            if progress:
                progress(i * 10, 30, "")
            time.sleep(0.01)
        dest.write_bytes(b"x" * 30)
        return dest

    monkeypatch.setattr(segment, "download", fake_download)
    return calls


def test_download_dialog_asks_then_downloads(app, model_cache):
    from PySide6.QtWidgets import QDialog

    from papermini import segment
    from papermini.gui.models import DownloadDialog

    d = DownloadDialog("rmbg-1.4")
    assert "Download the BRIA RMBG-1.4 model?" in d.title.text()
    assert "176 MB" in d.body.text()
    assert "non-commercial use only" in d.licence_note.text()
    assert "You are responsible for not using it commercially" in d.licence_note.text()
    assert d.btn_go.text() == "Download"
    d.btn_no.click()                                   # "Not now"
    assert d.result() == QDialog.Rejected and model_cache == []

    d = DownloadDialog("rmbg-1.4")
    assert not d.btn_go.isEnabled()                    # the licence is not accepted yet
    d.start()                                          # (Enter: still nothing happens)
    assert model_cache == [] and d.title.text().startswith("Download the")
    d.accept_licence.setChecked(True)
    assert d.btn_go.isEnabled()
    d.btn_go.click()                                   # "Download"
    assert d.btn_no.text() == "Cancel" and not d.accept_licence.isEnabled()
    assert wait(app, lambda: d.result() == QDialog.Accepted, 10)
    assert d.bar.value() == 1000 and d.status.text() == "0 of 0 MB"  # 30 bytes
    assert segment.model_path("rmbg-1.4").exists() and model_cache == ["rmbg-1.4.onnx"]


def test_download_dialog_cancel(app, model_cache, monkeypatch):
    import threading

    from PySide6.QtWidgets import QDialog

    from papermini import segment
    from papermini.gui.models import DownloadDialog

    gate = threading.Event()
    real = segment.download

    def slow(url, dest, progress=None, cancel=None, **k):
        gate.wait(5)
        return real(url, dest, progress=progress, cancel=cancel, **k)

    monkeypatch.setattr(segment, "download", slow)
    d = DownloadDialog("birefnet-lite", ask=False)
    d.reject()                                         # Cancel / Esc while downloading
    assert d.isVisible() is False and d.result() != QDialog.Accepted
    assert "Cancelling" in d.status.text()
    gate.set()
    assert wait(app, lambda: not d.downloading, 10)
    assert d.result() == QDialog.Rejected
    assert not segment.model_path("birefnet-lite").exists()


def test_build_asks_before_downloading(app, tmp_path, model_cache, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from papermini import segment
    from papermini.gui import models
    from papermini.gui.window import MainWindow

    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "plain.png")
    asked = []

    class Refuse:
        def __init__(self, model, parent=None):
            asked.append(model)

        def exec(self):
            return QDialog.Rejected

    monkeypatch.setattr("papermini.gui.window.DownloadDialog", Refuse)
    w = MainWindow()
    try:
        w.add_images([tmp_path / "plain.png"], FigureSettings(model="birefnet-lite"))
        fig = w.current()
        assert wait(app, lambda: fig.error is not None, 30)
        assert asked == ["birefnet-lite"] and "not downloaded" in fig.error
        assert "Models and cache" in w.banner.text.text() and "lower strength" not in w.banner.text.text()
        assert model_cache == []
        assert w._confirm_download("birefnet-lite") is False   # declined: not asked again
        assert asked == ["birefnet-lite"]

        # the Models and cache page lists every model, downloads one, and the figure is retried
        from papermini.gui.preferences import PreferencesDialog

        dlg = PreferencesDialog(w, "cache").cache
        assert set(dlg.cards) == set(segment.ONNX_MODELS)
        card = dlg.cards["birefnet-lite"]
        assert "Not downloaded" in card.state.text() and not card.btn_del.isEnabled()
        monkeypatch.setattr(models.DownloadDialog, "exec",
                            lambda self: segment.fetch_model(self.model, self.force) and 1)
        card.btn_get.click()
        assert "Downloaded" in card.state.text() and card.btn_get.text() == "Download again"
        assert "birefnet-lite.onnx" in card.state.text() and str(segment.cache_dir()) in dlg.folder.text()
        assert "birefnet-lite" not in w._declined and fig.error is None

        monkeypatch.setattr(models.QMessageBox, "question", lambda *a, **k: models.QMessageBox.Yes)
        card.btn_del.click()
        assert not segment.model_path("birefnet-lite").exists()
        assert "Not downloaded" in card.state.text()
    finally:
        w._modified = False
        w.close()


def test_preferences_menu_entry(app):
    """Preferences… is in the menu (Ctrl+,) and holds the settings that used to be menu
    items: the theme, automatic updates, the detailed log and cache management."""
    from PySide6.QtGui import QKeySequence

    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        assert w.a_prefs in w.menu.actions()
        assert w.a_prefs.shortcut() == QKeySequence("Ctrl+,")
        texts = [a.text() for a in w.menu.actions()]
        for gone in ("Theme", "Cache management…", "Creature sizes…", "Log",
                     "Update automatically"):
            assert gone not in texts
        assert "Open log folder" in texts
    finally:
        w.close()


def test_cache_management_clears_masks_images_and_everything(app, model_cache, monkeypatch):
    """The Models and cache page counts the masks and images from links, clears each,
    keeps the images open figures use, and Clear cache also deletes the models."""
    from papermini import remote, segment
    from papermini.gui import models

    masks = segment.masks_dir()
    masks.mkdir(parents=True)
    for i in range(3):
        (masks / f"m{i}.png").write_bytes(b"x" * 1000)
    images = []
    for key in ("aaa", "bbb"):
        (remote._cache_dir() / key).mkdir(parents=True)
        images.append(remote._cache_dir() / key / f"{key}.png")
        images[-1].write_bytes(b"x" * 1000)
    model = segment.model_path(segment.DEFAULT_MODEL)
    model.write_bytes(b"model")

    dlg = models.CachePage(in_use=lambda: [images[0]])
    assert str(segment.cache_dir()) in dlg.folder.text()
    assert dlg.masks.state.text().startswith("3 masks")
    assert dlg.images.state.text().startswith("2 images")
    assert "1 in use by open figures" in dlg.images.state.text()
    dlg.masks.btn_clear.click()
    assert dlg.masks.state.text() == "No masks" and not dlg.masks.btn_clear.isEnabled()
    dlg.images.btn_clear.click()
    assert images[0].exists() and not images[1].exists()
    assert not dlg.images.btn_clear.isEnabled()  # (only the image in use is left)
    assert model.exists() and dlg.btn_all.isEnabled()

    changed = []
    dlg.changed.connect(changed.append)
    asked = []
    monkeypatch.setattr(models.QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or models.QMessageBox.Yes)
    dlg.btn_all.click()
    assert "also deletes the downloaded models" in asked[0]
    assert not model.exists() and images[0].exists()
    assert changed == [segment.DEFAULT_MODEL] and not dlg.btn_all.isEnabled()
    assert "Not downloaded" in dlg.cards[segment.DEFAULT_MODEL].state.text()


def test_cache_page_scrolls_when_short(app, model_cache):
    """The Preferences window can be resized smaller than the Models and cache page,
    which then scrolls, and Close stays in view."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton

    from papermini.gui.preferences import PreferencesDialog
    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        dlg = PreferencesDialog(w, "cache")
        assert dlg.isSizeGripEnabled() and dlg.stack.currentWidget() is dlg.cache
        dlg.setAttribute(Qt.WA_DontShowOnScreen)
        dlg.show()
        app.processEvents()
        dlg.resize(dlg.width(), 300)  # (as short as the other pages allow)
        app.processEvents()
        assert dlg.height() < 450 and dlg.cache.scroll.verticalScrollBar().isVisible()
        close = [b for b in dlg.findChildren(QPushButton) if b.text() == "Close"][0]
        assert not dlg.cache.scroll.isAncestorOf(close)
        dlg.close()
    finally:
        w.close()


def test_licences_are_links(app, model_cache):
    from papermini import segment
    from papermini.gui.models import CachePage, DownloadDialog

    for model, spec in segment.ONNX_MODELS.items():
        assert spec["licence_url"].startswith("https://")
        d = DownloadDialog(model)
        label = d.licence_note if segment.non_commercial(model) else d.body
        assert f'<a href="{spec["licence_url"]}">' in label.text()
        assert label.openExternalLinks()
    dlg = CachePage()
    card = dlg.cards["birefnet"]
    assert 'href="https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE"' in card.licence.text()
    assert card.licence.openExternalLinks()


def test_a_non_commercial_model_always_asks_to_accept_its_licence(app, model_cache):
    """RMBG-1.4 only downloads once the user accepts it is for non-commercial use, also
    from the Models and cache page (which otherwise downloads at once); BiRefNet just
    downloads."""
    from PySide6.QtWidgets import QDialog

    from papermini.gui.models import CachePage, DownloadDialog

    d = DownloadDialog("rmbg-1.4", ask=False)          # the Models and cache page's Download
    assert d.accept_licence is not None and not d.btn_go.isEnabled()
    assert model_cache == [] and d.bar.isHidden()
    d.accept_licence.setChecked(True)
    d.btn_go.click()
    assert wait(app, lambda: d.result() == QDialog.Accepted, 10)
    d = DownloadDialog("birefnet-lite")
    assert d.accept_licence is None and d.licence_note is None and d.btn_go.isEnabled()
    card = CachePage().cards["rmbg-1.4"]
    assert card.licence.objectName() == "LicenceNote"
    assert "responsible for not using it commercially" in card.licence.toolTip()
    assert CachePage().cards["birefnet"].licence.objectName() == "Muted"


def test_the_settings_show_the_licence_of_the_model_in_use(app, tmp_path, model_cache):
    from papermini import segment
    from papermini.gui.window import MainWindow

    Image.new("RGB", (300, 400), (40, 40, 40)).save(tmp_path / "a.png")
    w = MainWindow()
    segment.CONFIRM_DOWNLOAD = lambda model: False  # (no download prompt)
    try:
        w.add_images([tmp_path / "a.png"])
        p = w.panel
        combo = p._w["model"][1]

        def pick(model):
            combo.setCurrentText(model)
            combo.activated.emit(combo.currentIndex())
            app.processEvents()

        pick("rmbg-1.4")
        assert p.licence_hint.isVisibleTo(p) and "Non-commercial use only" in p.licence_hint.text()
        pick("birefnet")
        assert not p.licence_hint.isVisibleTo(p)
        pick("auto")
        p.set_auto_method("rmbg-1.4")  # (auto picked it: the image has no transparency)
        assert p.licence_hint.isVisibleTo(p)
        p.set_auto_method("alpha")
        assert not p.licence_hint.isVisibleTo(p)
    finally:
        w._modified = False
        w.close()


def test_no_figure_hides_the_settings(app, tmp_path):
    """Regression: with no figure selected the whole form stayed visible, greyed out,
    under a small heading (the sections were looked up before they had a parent)."""
    from papermini.gui.window import MainWindow

    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "a.png")
    w = MainWindow()
    try:
        p = w.panel
        shown = lambda x: x.isVisibleTo(p)  # noqa: E731
        assert len(p.sections) > 3
        assert shown(p.empty_box) and p.empty_title.text() == "No figure selected"
        assert "Add images" in p.empty_text.text()
        assert not any(shown(s) for s in p.sections + [p.apply_all, p.title, p.subtitle])
        assert p.isEnabled()  # a disabled panel would grey out the message too

        w.add_images([tmp_path / "a.png"])
        assert not shown(p.empty_box) and any(shown(s) for s in p.sections)
        assert all(shown(s) == (st == p.step()) for s, st in zip(p.sections, p._section_steps))
        assert shown(p.title) and shown(p.apply_all)

        w.list.setCurrentRow(-1)  # figures, but none selected
        assert shown(p.empty_box) and "Select a figure" in p.empty_text.text()
        assert not any(shown(s) for s in p.sections)

        w.list.setCurrentRow(0)
        w.remove_current()
        assert shown(p.empty_box) and "Add images" in p.empty_text.text()
    finally:
        w._modified = False
        w.close()


def test_decimal_fields_take_a_point_in_any_locale(app):
    """Regression: on a system with a decimal comma (e.g. Dutch) the fields showed
    "42,00 mm" and a typed "12.5" was not read as 12.5."""
    from PySide6.QtCore import QLocale, Qt
    from PySide6.QtTest import QTest

    from papermini.gui.panels import DoubleSpinBox, FigurePanel

    old = QLocale()
    QLocale.setDefault(QLocale(QLocale.Dutch, QLocale.Netherlands))
    try:
        p = FigurePanel()
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


def test_source_view_shows_the_detected_outline(app, tmp_path):
    """Step 1 shows what background removal found, without the margin and tab of the
    miniature, and forgets it when another image is shown."""
    from papermini.gui.views import load_qimage
    from papermini.gui.window import MainWindow

    im = np.full((900, 700, 3), 255, np.uint8)
    cv2.ellipse(im, (350, 450), (200, 300), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "b.png")
    w = MainWindow()
    try:
        assert [w.tabs.tabText(i) for i in range(w.tabs.count())] == \
            ["Source", "Miniature", "Print sheet"]
        assert w.tabs.currentIndex() == w.SOURCE  # the first step
        assert [b.text() for b in w.views.group.buttons()] == \
            ["1  Source", "2  Miniature", "3  Print sheet"]
        w.add_images([tmp_path / "a.png"], FigureSettings(margin_mm=5))
        fig = w.current()
        assert wait(app, lambda: fig.up_to_date), fig.error
        cv = w.crop_view
        shade, line = cv._outline_items
        assert shade.scene() is cv.scene()
        r = line.path().boundingRect()                    # the ellipse itself: no margin
        assert abs(r.left() - 150) < 3 and abs(r.top() - 150) < 3
        assert abs(r.right() - 551) < 3 and abs(r.bottom() - 751) < 3

        cv.refresh_theme()                                 # redrawn, not duplicated
        assert len(cv._outline_items) == 2
        cv.set_busy(True)                                  # a model runs: dimmed, no outline
        assert len(cv._outline_items) == 1
        cv.set_busy(False)
        cv.set_image(load_qimage(tmp_path / "b.png"))    # another image: no stale outline
        assert cv._outline is None and cv._outline_items == []
    finally:
        w._modified = False
        w.close()


def _crop_view(app, size=(400, 300)):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from papermini.gui.views import CropView

    v = CropView()
    v.setAttribute(Qt.WA_DontShowOnScreen)
    v.resize(500, 400)
    v.show()
    img = QImage(*size, QImage.Format_RGB32)
    img.fill(0x808080)
    v.set_image(img)
    app.processEvents()
    v.fit()
    app.processEvents()
    return v


def _mouse(v, kind, scene_pt, button=None):
    """Send a mouse press/move/release at a scene point to a CropView."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    pos = QPointF(v.mapFromScene(QPointF(*scene_pt)))
    t = {"press": QEvent.MouseButtonPress, "move": QEvent.MouseMove,
         "release": QEvent.MouseButtonRelease}[kind]
    b = Qt.LeftButton if kind != "move" else Qt.NoButton
    held = Qt.LeftButton if (kind == "move" and button) else Qt.NoButton
    if kind == "press":
        held = Qt.LeftButton
    ev = QMouseEvent(t, pos, v.viewport().mapToGlobal(pos), b, held, Qt.NoModifier)
    {"press": v.mousePressEvent, "move": v.mouseMoveEvent,
     "release": v.mouseReleaseEvent}[kind](ev)


def test_crop_view_guides_the_user(app):
    """Without a crop box a hint says to drag one; over the image, guide lines show
    where a new box would start; over the box, the part a drag grabs is shown."""
    v = _crop_view(app)
    assert v.show_hint()                                   # no box yet: say how...
    img = v._image_view_rect()
    pill = v.hint_rect()                                   # ...beside the image, not on it
    assert not pill.intersects(img) and v.viewport().rect().contains(pill.toRect())
    _mouse(v, "move", (200, 150))
    assert v._hover is not None and v._hover_part == "new"  # guide lines through the mouse
    v.grab()                                               # (paints without errors)
    v.set_crop([0.25, 0.25, 0.75, 0.75])
    assert not v.show_hint()                               # a box: no hint
    _mouse(v, "move", (200, 150))
    assert v._hover_part == "move"                         # inside: move the whole box
    _mouse(v, "move", (100, 150))
    assert v._hover_part == "l"                            # on the left edge
    _mouse(v, "move", (100, 75))
    assert v._hover_part == "tl"                           # on a corner handle
    v.grab()
    v.leaveEvent(None)
    assert v._hover is None and v._hover_part is None


def test_a_click_on_the_crop_view_changes_nothing(app):
    """A click (or a press that barely moves) never draws, moves or clears a box, so it
    never starts a model run by accident; a real drag does."""
    v = _crop_view(app)
    got = []
    v.cropChanged.connect(got.append)
    _mouse(v, "press", (200, 150))
    _mouse(v, "release", (200, 150))
    assert got == [] and v.crop_box() is None              # a click: no box
    v.set_crop([0.25, 0.25, 0.75, 0.75])
    box = v.crop_box()
    s = 1 / v.transform().m11()                            # scene units per screen px
    _mouse(v, "press", (200, 150))                         # inside: would move it...
    _mouse(v, "move", (200 + 2 * s, 150), button=True)     # ...but 2 px is a jitter
    _mouse(v, "release", (200 + 2 * s, 150))
    assert got == [] and v.crop_box() == box
    _mouse(v, "press", (200, 150))
    _mouse(v, "move", (230, 150), button=True)             # a real drag moves it
    _mouse(v, "release", (230, 150))
    moved = v.crop_box()                                   # (to a whole screen pixel)
    assert len(got) == 1 and abs(moved.left() - box.left() - 30) < 2 * s
    assert moved.size() == box.size() and moved.top() == box.top()


def test_crop_changes_can_be_undone_and_cleared(app, tmp_path):
    """Ctrl+Z puts the crop back as it was (also for another figure); the Clear crop
    button on the canvas removes it, and shows only on the Source view with a crop."""
    from papermini.gui.window import MainWindow

    for n in "ab":
        Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / f"{n}.png")
    w = MainWindow()
    try:
        w.add_images([tmp_path / "a.png", tmp_path / "b.png"])
        a, b = w.figures
        w.list.setCurrentRow(0)
        assert not w.clear_crop_card.isVisibleTo(w)
        w.crop_view.cropChanged.emit([0.1, 0.1, 0.9, 0.9])
        w.crop_view.cropChanged.emit([0.2, 0.2, 0.8, 0.8])
        assert a.entry.settings.crop == [0.2, 0.2, 0.8, 0.8]
        assert w.clear_crop_card.isVisibleTo(w)
        w.tabs.setCurrentIndex(w.MINI)                     # only on the Source view
        assert not w.clear_crop_card.isVisibleTo(w)
        w.tabs.setCurrentIndex(w.SOURCE)
        w.list.setCurrentRow(1)
        w.btn_clear_crop.click()                           # nothing to clear on b...
        assert b.entry.settings.crop is None
        w.list.setCurrentRow(0)
        w.btn_clear_crop.click()                           # ...on a it clears the box
        assert a.entry.settings.crop is None and not w.clear_crop_card.isVisibleTo(w)
        w.list.setCurrentRow(1)
        w.a_undo_crop.trigger()                            # back on a, as it was
        assert w.current() is a and a.entry.settings.crop == [0.2, 0.2, 0.8, 0.8]
        assert w.crop_view.crop_box() is not None
        w.a_undo_crop.trigger()
        assert a.entry.settings.crop == [0.1, 0.1, 0.9, 0.9]
        w.a_undo_crop.trigger()
        assert a.entry.settings.crop is None
        w.a_undo_crop.trigger()                            # nothing left: no change
        assert a.entry.settings.crop is None
    finally:
        w._modified = False
        w.close()


def test_color_sliders_snap_to_their_centre(app):
    """A slider around 0 (the color adjustments) fills from the middle, marks 0 with a
    short line, snaps to 0 when dragged close by (typed values are kept), and goes back to
    0 on a double-click. Sliders that start at 0 (strength) stay as they were."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QColor, QMouseEvent

    from papermini.gui import theme
    from papermini.gui.panels import SNAP_PX, SliderField

    theme.apply(app, "light")                                # (as the window does)
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
        return sl._handle_rect(v).center().x()

    def send(kind, x, held=Qt.LeftButton):
        t = {"press": QEvent.MouseButtonPress, "move": QEvent.MouseMove,
             "release": QEvent.MouseButtonRelease, "double": QEvent.MouseButtonDblClick}[kind]
        pos = QPointF(x, sl.height() / 2)
        b = Qt.NoButton if kind == "move" else Qt.LeftButton
        app.sendEvent(sl, QMouseEvent(t, pos, sl.mapToGlobal(pos), b,
                                      Qt.NoButton if kind == "release" else held,
                                      Qt.NoModifier))

    def drag(to_x):
        send("press", x_of(sl.value()))
        send("move", to_x)
        send("release", to_x)
        return f.value()

    assert drag(x_of(50)) == 50                              # far away: where it is put
    assert drag(x_of(0) + SNAP_PX - 2) == 0                  # close by: snapped to 0
    assert drag(x_of(-60)) == -60
    assert drag(x_of(0) - SNAP_PX + 2) == 0
    assert drag(x_of(0) + 3 * SNAP_PX) > 0                   # past the snap: free again
    f.spin.setValue(2)
    assert f.value() == 2                                    # typed values are kept
    send("press", x_of(2))
    send("release", x_of(2))
    send("double", x_of(2))
    send("release", x_of(2))
    assert f.value() == 0 and got[-1] == 0                   # double-click: back to 0

    t = theme.current
    f.setValue(60)
    img = f.grab().toImage()
    cy = sl.mapTo(f, sl.rect().center()).y()
    off = sl.mapTo(f, sl.rect().topLeft()).x()
    accent, border = QColor(t.accent), QColor(t.border)

    def near(c, ref):
        return max(abs(c.red() - ref.red()), abs(c.green() - ref.green()),
                   abs(c.blue() - ref.blue())) < 40

    cx, vx = off + int(sl.centre_x()), off + x_of(60)
    assert near(img.pixelColor((cx + vx) // 2, cy), accent)      # filled from 0 to 60
    assert near(img.pixelColor(off + x_of(-50), cy), border)     # not left of 0
    mark = QColor(t.muted)
    assert any(near(img.pixelColor(cx + dx, cy - 5), mark) for dx in (-1, 0, 1))  # the 0 mark
    f.close()


def test_image_adjustments_panel(app):
    """Step 1 has color sliders; greyscale hides saturation and hue (nothing to turn);
    Reset puts all of them back in one change, and is off while there is nothing to reset."""
    from papermini.gui.panels import SOURCE, FigurePanel

    p = FigurePanel()
    p.set_settings(FigureSettings(), "x", "x")
    p.set_step(SOURCE)
    box = [b for b in p.sections if b.header.text() == "Image adjustments"][0]
    assert box.isVisibleTo(p)
    reset = p._resets["_reset_adjust"][0]
    assert not reset.isEnabled()                         # nothing to reset yet
    got = []
    p.changed.connect(got.append)
    p._w["brightness"][1].spin.setValue(30)
    p._w["hue"][1].slider.setValue(-90)
    assert (got[-1].brightness, got[-1].hue) == (30, -90) and reset.isEnabled()
    p._w["greyscale"][1].setChecked(True)
    assert got[-1].greyscale and not p.is_shown("saturation") and not p.is_shown("hue")
    assert p.is_shown("brightness") and p.is_shown("contrast")
    n = len(got)
    reset.click()
    assert len(got) == n + 1                             # one change, not five
    assert got[-1].adjustments().is_identity() and not reset.isEnabled()
    assert p.is_shown("saturation")
    assert "_reset_adjust" not in p.step_settings()      # (a button, not a setting)
    assert {"greyscale", "brightness", "hue"} <= p.step_settings()


def test_source_view_shows_the_adjusted_picture_without_running_the_model(app, tmp_path):
    """The Source view follows the color sliders (a preview at the original's size),
    and a color change rebuilds the miniature from the cached mask: the model does not
    run again and the outline stays."""
    from papermini import segment
    from papermini.gui.views import PREVIEW_PX
    from papermini.gui.window import MainWindow

    im = np.full((2400, 1800, 3), 255, np.uint8)                # larger than a preview
    cv2.circle(im, (900, 1200), 500, (200, 40, 40), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    runs = []
    real = segment.OnnxSegmenter.__call__
    segment.OnnxSegmenter.__call__ = lambda self, x: runs.append(1) or real(self, x)
    w = MainWindow()
    try:
        w.add_images([tmp_path / "a.png"])
        fig = w.current()
        assert wait(app, lambda: fig.up_to_date), fig.error
        assert len(runs) == 1 and w.crop_view.picture_size() == (1800, 2400)
        outline = fig.mini.source_outline
        w._settings_changed(replace(fig.entry.settings, greyscale=True))
        assert wait(app, lambda: fig.up_to_date and w.crop_view.picture_size() != (1800, 2400))
        assert max(w.crop_view.picture_size()) == PREVIEW_PX     # a smaller preview...
        assert w.crop_view._img_size == (1800, 2400)              # ...in the original's pixels
        pm = w.crop_view._pix_item.pixmap().toImage()
        c = pm.pixelColor(pm.width() // 2, pm.height() // 2)
        assert c.red() == c.green() == c.blue()                  # shown in grey
        assert len(runs) == 1                                    # the model did not run again
        assert len(fig.mini.source_outline) == len(outline)
        art = np.asarray(fig.mini.art.convert("RGB")).astype(int)
        mid = art[art.shape[0] // 2, art.shape[1] // 2]
        assert abs(mid[0] - mid[1]) <= 2                         # and printed grey
        w._settings_changed(replace(fig.entry.settings, greyscale=False))
        assert wait(app, lambda: w.crop_view.picture_size() == (1800, 2400))  # the original
    finally:
        segment.OnnxSegmenter.__call__ = real
        w._modified = False
        w.close()


def test_source_view_has_a_legend(app, tmp_path):
    """The Source view explains its marks (outline, faded background, crop box) in a
    legend, only there and only with an image. Its texts never change, crop box or
    not. It lets the mouse through to the crop handles under it."""
    from PySide6.QtCore import Qt

    from papermini.gui.window import MainWindow

    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "a.png")
    w = MainWindow()
    try:
        legend = w.legend
        assert not w.legend_box.isVisibleTo(w)                 # no image yet
        w.add_images([tmp_path / "a.png"])
        assert w.legend_box.isVisibleTo(w)
        texts = ["Detected outline", "Removed background", "Crop area"]
        assert [t.text() for t in legend.texts] == texts
        assert all(not sw.pixmap().isNull() for sw in legend.swatches)
        assert legend.testAttribute(Qt.WA_TransparentForMouseEvents)
        assert w.legend_box.testAttribute(Qt.WA_TransparentForMouseEvents)
        w.crop_view.cropChanged.emit([0.1, 0.1, 0.9, 0.9])     # a crop box drawn
        assert [t.text() for t in legend.texts] == texts       # the same words
        w.tabs.setCurrentIndex(w.MINI)                          # only on the Source view
        assert not w.legend_box.isVisibleTo(w)
        w.tabs.setCurrentIndex(w.SOURCE)
        assert w.legend_box.isVisibleTo(w)
        w._settings_changed(replace(w.current().entry.settings, crop=None))
        assert [t.text() for t in legend.texts] == texts
    finally:
        w._modified = False
        w.close()


def test_settings_panel_follows_the_step(app, tmp_path):
    """Each step shows its own settings; "Apply to all" copies only those."""
    from papermini.gui.panels import MINIATURE, PRINT, SOURCE
    from papermini.gui.window import MainWindow

    for n in "ab":
        Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / f"{n}.png")
    w = MainWindow()
    try:
        w.add_images([tmp_path / "a.png", tmp_path / "b.png"])
        p = w.panel
        titles = lambda: [s.header.text() for s in p.sections if s.isVisibleTo(p)]  # noqa: E731
        expected = [["Crop", "Background removal", "Image adjustments"],
                    ["Size", "Back side", "Outline and cut line", "Tab", "Label", "Text",
                         "Number"],
                    []]
        for i, want in enumerate(expected):
            w.views.group.button(i).click()               # the step buttons in the header
            assert w.tabs.currentIndex() == i and p.step() == i and titles() == want
            # the Print sheet step shows the sheet's own settings instead
            assert w.side.currentWidget() is (w.sheet_panel if i == PRINT else p)
            assert p.export_svg.isVisibleTo(p) == (i == MINIATURE)  # (this figure's SVG)
        w.tabs.setCurrentIndex(w.SOURCE)
        assert "Crop" in p.step_hint.text() and p.step() == SOURCE

        a, b = w.figures
        w.list.setCurrentRow(0)
        w._settings_changed(replace(a.entry.settings, height_mm=30, margin_mm=3, strength=90))
        w._copies_changed(a.uid, 4)
        w.tabs.setCurrentIndex(w.MINI)
        assert "miniature" in p.apply_all.text()
        p.apply_all.click()
        assert b.entry.settings.height_mm == 30            # the Miniature step's settings...
        assert b.entry.settings.margin_mm == 3
        assert b.entry.settings.strength == FigureSettings().strength  # ...not the others
        assert b.entry.settings.copies == 1                # copies stay per figure
    finally:
        w._modified = False
        w.close()


def test_size_fields_keep_proportions_until_unlinked(app):
    """Linked, the field typed in sets the size and the other follows the figure's
    proportions; unlinked, both are set (the figure is stretched)."""
    from papermini.gui.panels import FigurePanel

    p = FigurePanel()
    p.set_settings(FigureSettings(height_mm=40), "x", "x")
    f = p.size_field
    assert f.linked() and f.w.text() == "—"                # proportions not known yet
    p.set_aspect(0.5)
    assert f.w.value() == 20
    f.w.setValue(30)                                       # typing the width
    s = p.settings()
    assert (s.height_mm, s.width_mm) == (None, 30) and f.h.value() == 60
    f.link.click()                                         # unlink: both as shown
    s = p.settings()
    assert (s.height_mm, s.width_mm) == (60, 30) and not f.linked()
    f.h.setValue(50)                                       # the width stays
    assert (p.settings().height_mm, p.settings().width_mm) == (50, 30)
    f.link.click()                                         # linked again: by height
    s = p.settings()
    assert (s.height_mm, s.width_mm) == (50, None) and f.w.value() == 25
    p.set_settings(FigureSettings(height_mm=42, width_mm=10), "x", "x")
    assert not f.linked() and (f.h.value(), f.w.value()) == (42, 10)


class SlowSegmenter(DarkSegmenter):
    """A model that runs until it is cancelled (or, with ``block`` off, at once)."""

    block = True
    calls = 0
    started = None  # threading.Event, set when a run starts

    class _Run:
        terminate = False

    def __call__(self, im):
        from papermini import segment

        SlowSegmenter.calls += 1
        if not SlowSegmenter.block:
            return super().__call__(im)
        ro = SlowSegmenter._Run()
        with segment._RUNS_LOCK:
            segment._RUNS.add(ro)
        try:
            SlowSegmenter.started.set()
            while not ro.terminate:
                time.sleep(0.01)
            raise segment.Cancelled("cancelled")
        finally:
            with segment._RUNS_LOCK:
                segment._RUNS.discard(ro)


def test_background_removal_shows_progress_and_can_be_cancelled(app, tmp_path, monkeypatch):
    """A running model shows a card with Cancel on the dimmed image; Cancel really stops
    it and nothing restarts on its own; Run again does. A new crop stops the old run."""
    import threading

    from papermini import segment
    from papermini.gui.window import MainWindow

    monkeypatch.setattr(segment, "OnnxSegmenter", SlowSegmenter)
    SlowSegmenter.block, SlowSegmenter.calls = True, 0
    SlowSegmenter.started = threading.Event()
    im = np.full((400, 300, 3), 255, np.uint8)
    cv2.circle(im, (150, 200), 80, (40, 40, 40), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    w = MainWindow()
    try:
        w.add_images([tmp_path / "a.png"])
        fig = w.current()
        assert wait(app, lambda: w.work_box.isVisibleTo(w) and w.crop_view._busy, 30)
        assert w.work.button.text() == "Cancel" and "Removing the background" in w.work.title.text()
        assert segment.DEFAULT_MODEL in w.work.detail.text()

        # a new crop: the old run stops at once and the new one starts
        SlowSegmenter.started.clear()
        w.crop_view.cropChanged.emit([0.1, 0.1, 0.9, 0.9])
        assert wait(app, lambda: SlowSegmenter.started.is_set() and SlowSegmenter.calls == 2, 30)
        assert fig.cancelled is None

        w.work.button.click()                             # Cancel
        assert fig.stopped                                # at once
        assert wait(app, lambda: not segment._RUNS, 30)  # and the run really stops
        assert w.work.button.text() == "Run again" and "cancelled" in w.work.title.text()
        assert not w.crop_view._busy and not fig.up_to_date
        from papermini.gui.widgets import SUBTITLE_ROLE
        assert w.list.item(0).data(SUBTITLE_ROLE).startswith("Cancelled")
        w._build_current()                                # nothing restarts on its own
        for _ in range(20):
            app.processEvents()
            time.sleep(0.01)
        assert SlowSegmenter.calls == 2

        SlowSegmenter.block = False
        w.work.button.click()                             # Run again
        assert wait(app, lambda: fig.up_to_date, 30), fig.error
        assert not w.work_box.isVisibleTo(w) and w.crop_view._outline_items
    finally:
        w._modified = False
        w.close()


class SlowLoadSegmenter(DarkSegmenter):
    """A model that takes until ``loaded`` is set to load, then runs at once."""

    loading = loaded = None  # threading.Event
    calls = 0

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        SlowLoadSegmenter.loading.set()
        assert SlowLoadSegmenter.loaded.wait(60)

    def __call__(self, im):
        SlowLoadSegmenter.calls += 1
        return super().__call__(im)


def test_cancel_works_while_the_model_loads(app, tmp_path, monkeypatch):
    """Loading a model can take longer than running it (BiRefNet-lite: ~10 s). Cancel
    then marks the figure cancelled at once and the model never runs; other settings
    (a margin) do not start it again, Run again does."""
    import threading

    from papermini import segment
    from papermini.gui.widgets import SUBTITLE_ROLE
    from papermini.gui.window import MainWindow

    monkeypatch.setattr(segment, "OnnxSegmenter", SlowLoadSegmenter)
    SlowLoadSegmenter.loading, SlowLoadSegmenter.loaded = threading.Event(), threading.Event()
    SlowLoadSegmenter.calls = 0
    im = np.full((400, 300, 3), 255, np.uint8)
    cv2.circle(im, (150, 200), 80, (40, 40, 40), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    w = MainWindow()
    try:
        w.add_images([tmp_path / "a.png"])
        fig = w.current()
        assert wait(app, lambda: SlowLoadSegmenter.loading.is_set() and w.work_box.isVisibleTo(w), 30)
        assert "loading" in w.work.detail.text()
        w.work.button.click()                             # Cancel, while it loads
        assert fig.stopped and w.work.button.text() == "Run again"
        assert "Cancelled" in w._list_item(fig).data(SUBTITLE_ROLE)
        SlowLoadSegmenter.loaded.set()
        assert wait(app, lambda: w.pool.activeThreadCount() == 0, 30)
        assert SlowLoadSegmenter.calls == 0 and not fig.up_to_date

        w._settings_changed(replace(fig.entry.settings, margin_mm=4))  # not the mask
        end = time.time() + 0.8                          # (past the build debounce)
        while time.time() < end:
            app.processEvents()
            time.sleep(0.02)
        assert w.pool.activeThreadCount() == 0 and SlowLoadSegmenter.calls == 0
        assert fig.stopped and w.work.button.text() == "Run again"

        w.work.button.click()                             # Run again
        assert wait(app, lambda: fig.up_to_date, 30), fig.error
        assert SlowLoadSegmenter.calls == 1 and not w.work_box.isVisibleTo(w)
    finally:
        SlowLoadSegmenter.loaded.set()
        w._modified = False
        w.close()


def test_a_new_image_waits_for_a_running_model_with_cancel(app, tmp_path, monkeypatch):
    """An image added while another figure's model runs waits for that run: the card
    says so, and Cancel stops that run so the new image goes next."""
    import threading

    from papermini import segment
    from papermini.gui.widgets import SUBTITLE_ROLE
    from papermini.gui.window import MainWindow

    monkeypatch.setattr(segment, "OnnxSegmenter", SlowSegmenter)
    SlowSegmenter.block, SlowSegmenter.calls = True, 0
    SlowSegmenter.started = threading.Event()
    im = np.full((400, 300, 3), 255, np.uint8)
    cv2.circle(im, (150, 200), 80, (40, 40, 40), -1)
    for n in "ab":
        Image.fromarray(im).save(tmp_path / f"{n}.png")
    w = MainWindow()
    try:
        w.add_images([tmp_path / "a.png"])
        a = w.current()
        assert wait(app, lambda: SlowSegmenter.started.is_set() and w.work_box.isVisibleTo(w), 30)
        SlowSegmenter.started.clear()
        w.add_images([tmp_path / "b.png"])
        b = w.current()
        assert b is not a
        assert wait(app, lambda: w.work_box.isVisibleTo(w)
                    and w.work.title.text() == "Waiting for a", 30)
        assert w.work.button.text() == "Cancel it" and not w.crop_view._busy
        assert not w.busy_box.isVisibleTo(w)              # the card says it all

        w.work.button.click()                             # stops a's run
        assert a.stopped and not b.stopped
        assert wait(app, lambda: SlowSegmenter.started.is_set(), 30)  # b goes next
        assert wait(app, lambda: "Removing the background" in w.work.title.text(), 30)
        assert w.work.button.text() == "Cancel" and SlowSegmenter.calls == 2
        w.work.button.click()                             # and b's own run
        assert b.stopped and wait(app, lambda: not segment._RUNS, 30)
        assert "Cancelled" in w._list_item(a).data(SUBTITLE_ROLE)
    finally:
        w._modified = False
        w.close()


def test_stretched_figure_gets_both_sizes(app, tmp_path):
    from papermini.gui.window import MainWindow

    im = np.full((900, 700, 3), 255, np.uint8)
    cv2.ellipse(im, (350, 450), (200, 300), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    w = MainWindow()
    try:
        w.add_images([tmp_path / "a.png"])
        fig = w.current()
        assert wait(app, lambda: fig.up_to_date), fig.error
        f = w.panel.size_field
        assert f.w.value() == pytest.approx(32 * 401 / 601, abs=0.1)  # follows the figure
        f.link.click()
        f.w.setValue(40)
        assert (fig.entry.settings.height_mm, fig.entry.settings.width_mm) == (32, 40)
        assert fig.entry.settings.size == "custom"  # (a width of its own: not Medium's)
        assert wait(app, lambda: fig.up_to_date), fig.error
        assert fig.mini.figure_width_mm == pytest.approx(40, abs=0.05)
        assert fig.mini.figure_height_mm == pytest.approx(32, abs=0.05)
        assert "figure 40.0 × 32.0 mm" in w.info.text()
    finally:
        w._modified = False
        w.close()


def test_closed_window_never_asks_to_download(app, monkeypatch):
    """Regression: a build waiting for the download question when the window closed
    left the question queued, and a later event loop opened a real dialog for it."""
    from PySide6.QtCore import QRunnable

    from papermini.gui.window import MainWindow

    asked = []  # (an exception raised in a Qt slot would only be printed)

    class Dialog:
        def __init__(self, model, parent=None):
            asked.append(model)

        def exec(self):
            return 0

    monkeypatch.setattr("papermini.gui.window.DownloadDialog", Dialog)
    w = MainWindow()
    got = []
    w.pool.start(QRunnable.create(lambda: got.append(w._confirm_download("birefnet"))))
    time.sleep(0.2)          # the question is queued; the window closes before it is shown
    w._modified = False
    w.close()
    assert got == [False]
    for _ in range(20):      # deliver the stale question: it must be dropped
        app.processEvents()
        time.sleep(0.01)
    assert asked == []


def test_logo_in_the_header_welcome_card_and_window_icon(app):
    from PySide6.QtCore import QSize

    from papermini.gui import theme
    from papermini.gui.window import MainWindow

    def colors(pm):
        img = pm.toImage()
        return {img.pixelColor(x, y).name() for x in range(img.width()) for y in range(img.height())
                if img.pixelColor(x, y).alpha() == 255}

    assert theme.LOGO.is_file()  # shipped as package data (pyproject.toml, papermini.spec)
    pm = theme.logo_pixmap(64)
    assert pm.width() == 128  # 2x for sharp rendering on high-DPI screens
    assert {"#fd3c1b", "#000d1d", "#ffffff"} <= colors(pm)  # full color, not a line icon
    assert pm.toImage().pixelColor(0, 0).alpha() == 0  # transparent around the sticker

    sizes = theme.app_icon().availableSizes()
    assert QSize(16, 16) in sizes and QSize(256, 256) in sizes

    w = MainWindow()
    try:
        assert "#fd3c1b" in colors(w.logo.pixmap())
        assert "#fd3c1b" in colors(w.empty.icon.pixmap())
        w.set_theme("dark")  # re-theming must not swap the logo for a tinted line icon
        assert "#fd3c1b" in colors(w.logo.pixmap())
        assert "#fd3c1b" in colors(w.empty.icon.pixmap())
    finally:
        w.close()


def test_strength_and_gap_filling_sliders(app):
    """Strength and gap filling are sliders with a number box; gap filling has an
    Auto checkbox (it used to be a spin box where 0 meant auto, so 0 = off was impossible)."""
    from papermini.gui.panels import FigurePanel

    p = FigurePanel()
    p.set_settings(FigureSettings(strength=60, fill_gaps=None), "x", "x")
    th, cl = p._w["strength"][1], p._w["fill_gaps"][1]
    assert th.slider.value() == th.spin.value() == 60 and th.auto is None
    assert cl.auto.isChecked() and not cl.slider.isEnabled() and not cl.spin.isEnabled()
    got = []
    p.changed.connect(got.append)

    th.slider.setValue(80)                       # slider and box stay in step
    assert th.spin.value() == 80 and got[-1].strength == 80
    th.spin.setValue(25)
    assert th.slider.value() == 25 and got[-1].strength == 25

    p.set_auto_fill_gaps(14)                         # what the last build picked
    assert cl.spin.value() == 14 and p.settings().fill_gaps is None
    cl.auto.setChecked(False)                    # carry on from the automatic value
    assert cl.slider.isEnabled() and got[-1].fill_gaps == 14
    cl.slider.setValue(0)                        # 0 = no gap filling, now possible
    assert got[-1].fill_gaps == 0
    cl.spin.setValue(300)                        # past the slider's end: typed in the box
    assert got[-1].fill_gaps == 300 and cl.slider.value() == cl.slider.maximum()
    cl.auto.setChecked(True)
    assert got[-1].fill_gaps is None and cl.spin.value() == 14

    p.set_settings(FigureSettings(fill_gaps=0), "x", "x")
    assert not cl.auto.isChecked() and cl.spin.value() == 0 and p.settings().fill_gaps == 0


def test_start_card_offers_images_and_a_project(app, monkeypatch):
    from papermini.gui import window
    from papermini.gui.window import MainWindow

    asked = []
    monkeypatch.setattr(window.QFileDialog, "getOpenFileNames",
                        lambda parent, caption, folder, filters: (asked.append((caption, filters)), ([], ""))[1])
    w = MainWindow()
    try:
        assert w.empty.button.text() == "Add images…"
        assert w.empty.open_button.text() == "Open project…"
        w.empty.button.click()
        w.empty.open_button.click()
        assert asked[0][0] == "Add images"
        assert asked[1][1].startswith(window.PROJECT_FILTER)  # projects listed first
    finally:
        w.close()


def test_add_images_from_links_paste_and_browser_drops(app, monkeypatch, tmp_path):
    import io
    import urllib.request

    from pathlib import Path

    from PySide6.QtCore import QMimeData, QUrl

    from papermini import remote
    from papermini.gui import window
    from papermini.gui.window import MainWindow

    buf = io.BytesIO()
    Image.new("RGBA", (200, 300), (200, 40, 30, 255)).save(buf, "WEBP")
    site = {"https://example.com/img/goblin.webp": buf.getvalue()}
    asked = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    def urlopen(req, timeout=None):
        asked.append(req.full_url)
        if req.full_url not in site:
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        return Resp(site[req.full_url])

    import urllib.error
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    warned = []
    monkeypatch.setattr(window.QMessageBox, "warning", lambda *a: warned.append(a[2]))
    w = MainWindow()
    try:
        url = "https://example.com/img/goblin.webp"
        w.add_links([url])                       # downloads in the background
        assert wait(app, lambda: len(w.figures) == 1)
        fig = w.figures[0]
        assert fig.entry.source == url and fig.entry.image == remote.cached_image(url)
        assert w.list.item(0).toolTip() == url and w.list.item(0).text() == "goblin"

        w.add_links(["https://example.com/gone.png"])
        assert wait(app, lambda: warned)
        assert "404" in warned[0] and len(w.figures) == 1

        # a picture copied in a browser: the HTML has the image's own address, while the
        # URL is often the page it links to; the image address wins
        mime = QMimeData()
        mime.setHtml(f'<a href="https://example.com/page"><img alt="g" src="{url}"></a>')
        mime.setUrls([QUrl("https://example.com/page"), QUrl.fromLocalFile(str(tmp_path / "a.png"))])
        files, links = MainWindow._sources(mime)
        assert links == [url] and [Path(f) for f in files] == [tmp_path / "a.png"]

        n = len(asked)
        QApplication.clipboard().setText(url)
        w.paste()                                 # Ctrl+V outside a text field
        assert len(w.figures) == 2 and len(asked) == n  # second time from the cache
    finally:
        w._modified = False
        w.close()


def test_link_bar_on_top_of_the_figure_list(app, monkeypatch):
    """Paste a link in the bar above the figures and press Enter (or Add) to add it.
    The add-images button sits in the figure list, not in the header."""
    from PySide6.QtWidgets import QFrame, QToolButton

    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        header_tips = [b.toolTip() for b in w.findChild(QFrame, "Header").findChildren(QToolButton)]
        assert not any("Add images" in t for t in header_tips)
        left = w.splitter.widget(0)
        assert any("Add images" in b.toolTip() for b in left.findChildren(QToolButton))
        assert w.link_edit.parent() is left and not w.link_add.isEnabled()
        lay = left.layout()
        row = [i for i in range(lay.count()) if lay.itemAt(i).layout()
               and lay.itemAt(i).layout().indexOf(w.link_edit) >= 0]
        assert row and row[0] < lay.indexOf(w.list)          # right above the list

        added = []
        monkeypatch.setattr(w, "add_links", lambda links, *a: added.append(links))
        url = "https://example.com/art/goblin.webp"
        w.link_edit.setText(f"  {url} ")
        assert w.link_add.isEnabled()
        w.link_edit.returnPressed.emit()
        assert added == [[url]] and w.link_edit.text() == ""

        w.link_edit.setText("goblin.webp")              # not a link: kept, nothing added
        w.link_add.click()
        assert added == [[url]] and w.link_edit.text() == "goblin.webp"
        assert "not a link" in w.statusBar().currentMessage()

        w.link_edit.clear()
        QApplication.clipboard().setText(url)
        w.set_side_visible(0, False)
        w.a_add_link.trigger()                          # Ctrl+L: shows the list, fills in the link
        assert w.side_visible(0) and w.link_edit.text() == url
        w.empty.link_button.click()                     # the start card's link does the same
        assert w.link_edit.text() == url
    finally:
        w._modified = False
        w.close()


def test_print_is_true_to_size_and_follows_the_page_range(app):
    """The printed sheet must be exactly to scale: its 50 mm bar is 50 mm on paper."""
    from PySide6.QtGui import QColor, QImage

    from papermini.gui.views import print_sheet
    from papermini.mini import Mini
    from papermini.geometry import CutPath
    from papermini.sheet import pack

    class ImagePrinter(QImage):  # a "printer" that prints onto an image, 100 dpi
        def __init__(self, first=0, last=0):
            super().__init__(round(210 / 25.4 * 100), round(297 / 25.4 * 100), QImage.Format_RGB32)
            self.fill(0xFF808080)
            self.range, self.pages = (first, last), 1

        def fromPage(self):
            return self.range[0]

        def toPage(self):
            return self.range[1]

        def resolution(self):
            return 100

        def newPage(self):
            self.pages += 1
            return True

    sq = CutPath(np.array([[0, 0], [30, 0], [30, 40], [0, 40]], float))
    m = Mini("m", 30, 40, Image.new("RGBA", (300, 400), (200, 40, 30, 255)), sq)
    lay = pack([(m, 30)], "a4", 12, 7)
    assert lay.pages > 1
    pr = ImagePrinter()
    assert print_sheet(pr, lay, "test") == lay.pages == pr.pages
    k = 100 / 25.4
    y = round((12 + lay.header_mm - 4) * k)             # the scale bar's row
    dark = [x for x in range(pr.width()) if QColor(pr.pixel(x, y)).lightness() < 100]
    end = next(a for a, b in zip(dark, dark[1:] + [None]) if b != a + 1)  # the bar alone,
    assert abs(dark[0] - 12 * k) <= 2 and abs(end - 62 * k) <= 2  # not the "50 mm" next to it
    assert QColor(pr.pixel(2, 2)).lightness() > 250       # white paper from the very corner

    pr = ImagePrinter(2, 2)                                # "pages 2 to 2" in the dialog
    assert print_sheet(pr, lay, "test") == 1 and pr.pages == 1


def test_print_button_prints_the_sheet(app, tmp_path, monkeypatch):
    from PySide6.QtPrintSupport import QPrinter

    from papermini.gui.window import MainWindow

    im = Image.new("RGBA", (300, 450), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(im).ellipse((30, 30, 270, 420), fill=(200, 40, 30, 255))
    im.save(tmp_path / "hero.png")
    out = tmp_path / "printed.pdf"
    seen = []

    def fake_dialog(self, printer, pages):  # instead of the system print dialog
        seen.append((printer.fullPage(), printer.pageLayout().pageSize().id(), pages))
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(out))
        return True

    monkeypatch.setattr(MainWindow, "_print_dialog", fake_dialog)
    w = MainWindow()
    try:
        w.add_images([tmp_path / "hero.png"])
        w.tabs.setCurrentIndex(w.SHEET)
        assert w.sheet_panel.print_btn.isVisibleTo(w.sheet_panel)
        w.sheet_panel.print_btn.click()                   # builds first if needed, then prints
        assert wait(app, lambda: out.exists() and out.stat().st_size > 1000)
        from PySide6.QtGui import QPageSize
        assert seen == [(True, QPageSize.A4, 1)]          # true size on the sheet's paper
        assert out.read_bytes().startswith(b"%PDF")
    finally:
        w._modified = False
        w.close()


def test_auto_model_says_which_method_it_used(app, tmp_path):
    """Model "auto" shows under the model box how it found the figure: the image's own
    transparency, or the default model for an image without it."""
    from papermini import segment
    from papermini.gui.window import MainWindow

    im = np.full((600, 500, 3), 255, np.uint8)
    cv2.ellipse(im, (250, 300), (150, 220), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "flat.png")
    rgba = np.dstack([im, np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)])
    Image.fromarray(rgba, "RGBA").save(tmp_path / "cutout.png")

    w = MainWindow()
    try:
        w.add_images([tmp_path / "flat.png", tmp_path / "cutout.png"])
        flat, cutout = w.figures
        assert flat.entry.settings.model == "auto"
        w.list.setCurrentRow(0)
        assert wait(app, lambda: flat.up_to_date), flat.error
        assert flat.mini.method == segment.DEFAULT_MODEL
        hint = w.panel.auto_hint
        assert hint.isVisibleTo(w.panel) and segment.DEFAULT_MODEL in hint.text()
        assert "Chosen method" in hint.text()
        assert "no transparency" in hint.text()

        w.list.setCurrentRow(1)
        assert wait(app, lambda: cutout.up_to_date), cutout.error
        assert cutout.mini.method == "alpha"
        assert hint.isVisibleTo(w.panel) and "own transparency" in hint.text()

        # another model than auto: nothing to explain
        box = w.panel._w["model"][1]
        box.setCurrentText("alpha")
        box.activated.emit(box.currentIndex())  # (as when the user picks it)
        assert not hint.isVisibleTo(w.panel)
    finally:
        w._modified = False
        w.close()


def test_cut_by_machine_rebuilds_with_bleed_and_exports_the_cut_file(app, tmp_path, monkeypatch):
    """Switching the sheet to machine cutting builds every figure with the bleed, and
    Export PDF also writes the cut file."""
    from papermini.gui.window import MainWindow

    im = np.full((600, 500, 3), 255, np.uint8)
    cv2.ellipse(im, (250, 300), (150, 220), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "hero.png")
    w = MainWindow()
    try:
        w.add_images([tmp_path / "hero.png"])
        fig = w.current()
        assert wait(app, lambda: fig.up_to_date), fig.error
        hand_w = fig.mini.width_mm
        w.sheet_panel.cut.setCurrentIndex(w.sheet_panel.cut.findData("machine"))
        assert w.project.sheet.machine and fig.bleed_mm == 1.0 and not fig.up_to_date
        assert wait(app, lambda: fig.up_to_date), fig.error
        assert fig.mini.width_mm > hand_w + 1  # the bleed on both sides

        out = tmp_path / "sheet.pdf"
        seen = {}

        def run(dlg):  # instead of showing the Export dialog: save both, as "sheet"
            seen["name"] = dlg.name.text()
            dlg.folder.setText(str(tmp_path))
            dlg.name.setText("sheet")
            dlg.pdf.setChecked(True)
            dlg.cut.setChecked(True)
            return True

        monkeypatch.setattr(w, "_run_export_dialog", run)
        w.export_pdf()
        assert seen["name"] == "Paper miniatures"  # (named after the sheet's title)
        assert wait(app, lambda: (tmp_path / "sheet-cut.svg").exists())
        assert out.exists() and 'id="registration"' in (tmp_path / "sheet-cut.svg").read_text()
    finally:
        w._modified = False
        w.close()


def click_copies(w, row: int, which: str, times: int = 1):
    """Click - or + of the copies control on a figure's card."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    lst = w.list
    minus, _, plus = lst.itemDelegate()._copies_rects(lst.visualItemRect(lst.item(row)))
    at = (plus if which == "+" else minus).center().toPoint()
    for _ in range(times):
        QTest.mouseClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier, at)


def test_copies_on_the_figure_card(app, tmp_path):
    """Each card has "Amount - n +": - and + change the copies, a click on the number
    types one; never below 0, and nothing rebuilds."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QSpinBox

    from papermini.gui.widgets import COPIES_ROLE
    from papermini.gui.window import MainWindow

    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "a.png")
    w = MainWindow()
    w.resize(1300, 800)
    w.show()
    try:
        w.add_images([tmp_path / "a.png"])
        fig = w.figures[0]
        app.processEvents()
        click_copies(w, 0, "+", 3)
        assert fig.entry.settings.copies == 4 and w.list.item(0).data(COPIES_ROLE) == 4
        assert w._modified
        click_copies(w, 0, "-", 9)
        assert fig.entry.settings.copies == 0  # (not below 0)
        lst = w.list
        _, num, _ = lst.itemDelegate()._copies_rects(lst.visualItemRect(lst.item(0)))
        QTest.mouseClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier, num.center().toPoint())
        app.processEvents()
        box = [b for b in lst.findChildren(QSpinBox) if b.isVisible()][0]
        QTest.keyClicks(box, "12")
        QTest.keyClick(box, Qt.Key_Return)
        app.processEvents()
        assert fig.entry.settings.copies == 12
        # an edit in the panel keeps the copies set on the card
        w.panel._w["margin_mm"][1].setValue(2.0)
        assert fig.entry.settings.copies == 12 and fig.entry.settings.margin_mm == 2.0
    finally:
        w._modified = False
        w.close()


def test_export_dialog(app, tmp_path):
    """The Export dialog shows the files it writes (named after the sheet's title),
    writes only what is ticked, and remembers the ticks."""
    from PySide6.QtWidgets import QDialog

    from papermini.gui.export import ExportDialog

    d = ExportDialog(tmp_path, "My minis", pages=3, machine=True)
    assert d.pdf_path() == tmp_path / "My minis.pdf"
    assert [p.name for p in d.cut_paths()] == ["My minis-cut.svg", "My minis-cut-2.svg",
                                               "My minis-cut-3.svg"]
    assert "My minis-cut-3.svg" in d.cut_files.text() and d.pdf_files.text() == "My minis.pdf"
    d.pdf.setChecked(False)  # only the cut file, after printing from the app
    assert d.chosen() == d.cut_paths()
    d.cut.setChecked(False)
    assert d.chosen() == [] and not d.export_btn.isEnabled()
    d.cut.setChecked(True)
    d._accept()
    assert d.result() == QDialog.Accepted
    again = ExportDialog(tmp_path, "My minis", pages=1, machine=True)
    assert not again.pdf.isChecked() and again.cut.isChecked()  # remembered
    hand = ExportDialog(tmp_path, "My minis", pages=1, machine=False)
    hand.pdf.setChecked(True)
    assert hand.chosen() == [tmp_path / "My minis.pdf"]  # cut by hand: no cut file
    assert not hand.cut.isVisibleTo(hand)


def test_header_steps_stay_centred(app, tmp_path):
    """The step buttons sit in the middle of the window, whatever the header holds."""
    from PySide6.QtCore import Qt

    from papermini.gui.window import MainWindow

    w = MainWindow()
    w.setAttribute(Qt.WA_DontShowOnScreen)
    w.resize(1360, 820)
    w.show()
    try:
        for change in (lambda: None, w._set_modified):
            change()
            for _ in range(5):
                app.processEvents()
            centre = w.views.mapTo(w, w.views.rect().center()).x()
            assert abs(centre - w.width() / 2) <= 2
    finally:
        w._modified = False
        w.close()


@pytest.fixture
def fake_updates(monkeypatch, tmp_path):
    """A newer release that this copy can install, without network or helper: records
    what would be downloaded and installed."""
    from papermini import update

    calls = {"download": [], "install": []}
    rel = update.Release("99.0.0", "https://example.invalid/release")
    monkeypatch.setattr(update, "latest_release", lambda *a, **k: rel)
    monkeypatch.setattr(update, "unsupported", lambda: None)

    def download(r, progress=None, step=None, **k):
        calls["download"].append(r.version)
        if progress:
            progress(50, 100)
            progress(100, 100)
        for name in ("verifying", "unpacking"):
            if step:
                step(name)
        app = tmp_path / "new" / "papermini"
        app.mkdir(parents=True, exist_ok=True)
        return app

    monkeypatch.setattr(update, "download", download)
    monkeypatch.setattr(update, "install_on_exit",
                        lambda app, restart=False: calls["install"].append((app, restart)))
    return calls


def test_about_window_shows_each_update_state(app):
    from papermini.gui.about import AboutDialog
    from papermini.gui.window import MainWindow
    from papermini.update import Release

    w = MainWindow()
    try:
        d = AboutDialog(w)
        rel = Release("99.0.0", "")
        for state, data, text, button in (
                ("checking", None, "Checking", None),
                ("latest", rel, "latest version", None),
                ("available", (rel, None), "99.0.0", "Update"),
                ("available", (rel, "runs from source"), "runs from source", "Release page"),
                ("downloading", rel, "Downloading", None),
                ("ready", (rel, None), "ready", "Restart now"),
                ("error", "Could not check for updates: offline", "offline", "Try again")):
            d.update_state(state, data)
            assert text in d.status.text(), state
            assert d.action.isVisibleTo(d) == (button is not None), state
            if button:
                assert d.action.text() == button
        d.update_state("downloading", rel)
        d.update_state("progress", (58_000_000, 129_000_000))
        assert d.progress.isVisibleTo(d) and "58 of 129 MB" in d.progress.format()
        d.update_state("ready", (rel, None))
        assert not d.progress.isVisibleTo(d)
    finally:
        w._modified = False
        w.close()


def test_update_from_the_about_window(app, fake_updates):
    """About checks, Update downloads with progress, the bar shows it is ready, and
    closing papermini installs it (and starts it again after Restart now)."""
    from papermini.gui.about import AboutDialog
    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        about = AboutDialog(w)
        w._about = about  # (as show_about does, without the modal exec)
        w.check_updates(source="about")
        assert wait(app, lambda: about.action.isVisibleTo(about), 20)
        assert about.action.text() == "Update" and "99.0.0" in about.status.text()
        assert fake_updates["download"] == []  # the About window asks first
        about.action.click()
        assert wait(app, lambda: w._update_ready is not None, 20)
        assert fake_updates["download"] == ["99.0.0"]
        assert about.action.text() == "Restart now"
        assert w.update_bar.isVisibleTo(w) and "99.0.0" in w.update_text.text()
        w._about = None
        w._modified = False
        w._restart_for_update()  # closes the window: the helper installs and restarts
        assert len(fake_updates["install"]) == 1 and fake_updates["install"][0][1] is True
    finally:
        w._modified = False
        w.close()


def test_daily_update_check(app, fake_updates, monkeypatch, tmp_path):
    """Only an installed copy checks, at most once a day; with Update automatically off
    it announces the new version instead of downloading it."""
    from papermini import update
    from papermini.gui import prefs
    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        asked = []
        real_check = w.check_updates
        monkeypatch.setattr(w, "check_updates", lambda *a, **k: asked.append(k or a))
        monkeypatch.delenv(update.INSTALL_ENV, raising=False)
        w._startup_updates()
        assert asked == []  # run from source: no daily check
        monkeypatch.setenv(update.INSTALL_ENV, str(tmp_path / "installed"))
        prefs.store().setValue("updates/last_check", time.time())
        w._startup_updates()
        assert asked == []  # checked today already
        prefs.store().setValue("updates/last_check", 0.0)
        w._startup_updates()
        assert len(asked) == 1
        # automatic updating off: the daily check announces, and downloads nothing
        w.set_auto_updates(False)
        real_check(source="auto")
        assert wait(app, lambda: w.update_bar.isVisibleTo(w), 20)
        assert "available" in w.update_text.text() and w.update_restart.text() == "Update…"
        assert fake_updates["download"] == []
        assert prefs.store().value("updates/auto", type=bool) is False
    finally:
        w._modified = False
        w.close()


def test_update_menu_items(app):
    """Check for updates is in the menu; Update automatically is in Preferences, on by
    default, and its tick box sets the preference."""
    from papermini.gui import prefs
    from papermini.gui.preferences import PreferencesDialog
    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        texts = [a.text() for a in w.menu.actions()]
        assert "Check for updates…" in texts
        assert w.auto_updates()  # on by default
        dlg = PreferencesDialog(w, "updates")
        assert dlg.auto_updates.isChecked()
        dlg.auto_updates.setChecked(False)
        assert not w.auto_updates() and prefs.store().value("updates/auto", type=bool) is False
        dlg.close()
    finally:
        w._modified = False
        w.close()


def test_the_font_field(app):
    """The bundled fonts first, the installed ones once found; a font this computer does
    not have is kept, marked and warned about."""
    from papermini import fonts
    from papermini.gui.panels import FigurePanel

    p = FigurePanel()
    w = p._w["font"][1]
    names = lambda: [w.itemData(i) for i in range(w.count()) if w.itemData(i)]  # noqa: E731
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


def test_number_fields_follow_the_back_side(app):
    from papermini.gui.panels import FigurePanel

    p = FigurePanel()
    p.set_settings(FigureSettings(double_sided=True, back="number", tab_front="number"), "x", "x")
    assert p._w["tab_front"][1].currentData() == "number"
    assert p.is_shown("tab_front") and p.is_shown("tab_back")
    assert p.is_shown("back_text_color") and not p.is_shown("back_text")
    p._w["back"][1].setCurrentIndex(p._w["back"][1].findData("text_number"))
    assert p.is_shown("back_text") and p.is_shown("back_text_color")
    p._w["back"][1].setCurrentIndex(p._w["back"][1].findData("mirror"))
    assert not p.is_shown("back_text_color") and not p.is_shown("back_color")
    p._w["double_sided"][1].setChecked(False)
    assert p.is_shown("tab_front") and not p.is_shown("tab_back")  # (no back tab)
    assert p.settings().tab_front == "number"


def test_about_names_the_font_licence(app, monkeypatch):
    """About lists the bundled fonts and their licence, with a link to their folder."""
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QLabel

    from papermini import fonts
    from papermini.gui.about import AboutDialog
    from papermini.gui.window import MainWindow

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url))
    w = MainWindow()
    try:
        d = AboutDialog(w)
        label = next(lb for lb in d.findChildren(QLabel) if "Open Font License" in lb.text())
        assert all(name in label.text() for name in fonts.BUNDLED)
        label.linkActivated.emit("fonts")
        assert [u.toLocalFile() for u in opened] == [fonts.HERE.as_posix()]
        assert (fonts.HERE / "kalam" / "OFL.txt").is_file()
    finally:
        w._modified = False
        w.close()


def test_sheet_panel_paper_orientation_and_custom_size(app):
    """Orientation for a named paper, a width and height for Custom (starting at the
    paper chosen before); the mat only when cut by machine, with its warning."""
    from papermini.gui.panels import SheetPanel
    from papermini.settings import SheetSettings

    p = SheetPanel()
    got = []
    p.changed.connect(got.append)
    p.set_settings(SheetSettings())
    assert [p.paper.itemText(i) for i in range(p.paper.count())] == [
        "A3 (297 \u00d7 420 mm)", "A4 (210 \u00d7 297 mm)", "A5 (148 \u00d7 210 mm)",
        "Letter (8.5 \u00d7 11 in)", "Legal (8.5 \u00d7 14 in)", "Tabloid (11 \u00d7 17 in)",
        "Custom"]
    assert p.paper.currentData() == "a4" and p.is_shown(p.orientation)
    assert not p.is_shown(p.paper_w) and not p.is_shown(p.mat)
    p.paper.setCurrentIndex(p.paper.findData("a3"))
    p.orientation.setCurrentIndex(p.orientation.findData("landscape"))
    assert (got[-1].paper, got[-1].orientation) == ("a3", "landscape")
    assert got[-1].paper_width_mm is None
    p.paper.setCurrentIndex(p.paper.findData("custom"))   # starts at A3 landscape
    assert (got[-1].paper_width_mm, got[-1].paper_height_mm) == (420, 297)
    assert p.is_shown(p.paper_w) and p.is_shown(p.paper_h) and not p.is_shown(p.orientation)
    p.paper_h.setValue(350)
    assert got[-1].page == (420, 350)
    p.paper.setCurrentIndex(p.paper.findData("letter"))
    assert got[-1].paper_width_mm is None and got[-1].paper_height_mm is None
    # the mat: cut by machine only, and a warning when the paper is bigger
    p.set_settings(SheetSettings(paper="tabloid", cut="machine"))
    assert p.is_shown(p.mat) and not p.is_shown(p.mat_warning)
    p.mat.setCurrentIndex(p.mat.findData("12x12"))
    assert got[-1].mat == "12x12" and p.is_shown(p.mat_warning)
    assert p.mat_warning.text().startswith("Tabloid (279 \u00d7 432 mm) is bigger than")
    p.mat.setCurrentIndex(p.mat.findData("12x24"))
    assert not p.is_shown(p.mat_warning)
    p.cut.setCurrentIndex(p.cut.findData("hand"))         # hidden, but kept
    assert not p.is_shown(p.mat) and got[-1].mat == "12x24"
    p.set_settings(SheetSettings(paper="custom", paper_width_mm=300, paper_height_mm=450))
    assert (p.paper_w.value(), p.paper_h.value()) == (300, 450) and p.is_shown(p.paper_w)


def test_figure_too_big_for_the_paper(app, tmp_path, monkeypatch):
    """The sheet stays empty with a message, a list of the figures under Paper, and
    Print asks before leaving them off."""
    from PySide6.QtWidgets import QMessageBox

    from papermini.gui.window import MainWindow
    from papermini.settings import SheetSettings

    im = Image.new("RGBA", (300, 450), (0, 0, 0, 0))
    from PIL import ImageDraw
    ImageDraw.Draw(im).ellipse((30, 30, 270, 420), fill=(200, 40, 30, 255))
    im.save(tmp_path / "hero.png")
    im.save(tmp_path / "imp.png")
    asked, printed = [], []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.No)
    monkeypatch.setattr(MainWindow, "_print_dialog",
                        lambda self, printer, pages: printed.append(pages) or False)
    w = MainWindow()
    try:
        w.add_images([tmp_path / "hero.png", tmp_path / "imp.png"])
        hero, imp = w.figures
        hero.entry.settings = replace(hero.entry.settings, height_mm=150, label="Hero")
        w.tabs.setCurrentIndex(w.SHEET)
        w._refresh_sheet()                                 # (builds what is missing)
        assert wait(app, lambda: all(f.mini is not None and f.up_to_date for f in w.figures))
        w._sheet_changed(SheetSettings(paper="a5", orientation="landscape"))
        w._refresh_sheet()
        sp = w.sheet_panel
        assert w.sheet_banner_box.isVisibleTo(w) and w.sheet_view.scene().items() == []
        assert sp.is_shown(sp.fit_warning)
        text = sp.fit_warning.text()
        assert text.startswith("The following figure is too large to fit on the selected paper:")
        assert "<li>Hero</li>" in text and "imp" not in text
        assert "Pick bigger paper" in text
        w._print()                                         # asks; No: does not print
        assert len(asked) == 1 and "\u2022 Hero" in asked[0] and "left off" in asked[0]
        assert printed == []
        w._sheet_changed(SheetSettings(paper="a3"))  # everything fits again
        w._refresh_sheet()
        assert not w.sheet_banner_box.isVisibleTo(w) and not sp.is_shown(sp.fit_warning)
        assert w.sheet_view.scene().items()
    finally:
        w._modified = False
        w.close()


def test_print_sets_the_paper_size_and_orientation(app, tmp_path, monkeypatch):
    from PySide6.QtGui import QPageLayout

    from papermini.gui.window import MainWindow
    from papermini.settings import SheetSettings

    Image.new("RGBA", (300, 450), (200, 40, 30, 255)).save(tmp_path / "hero.png")
    seen = []

    def fake_dialog(self, printer, pages):
        r = printer.pageLayout().fullRect(QPageLayout.Millimeter)
        seen.append((round(r.width()), round(r.height())))
        return False

    monkeypatch.setattr(MainWindow, "_print_dialog", fake_dialog)
    w = MainWindow()
    try:
        w.add_images([tmp_path / "hero.png"])
        assert wait(app, lambda: w.figures[0].mini is not None and w.figures[0].up_to_date)
        for sheet in (SheetSettings(paper="a3", orientation="landscape"),
                      SheetSettings(paper="tabloid"),
                      SheetSettings(paper="custom", paper_width_mm=300, paper_height_mm=200)):
            w._sheet_changed(sheet)
            w._print()
        assert seen == [(420, 297), (279, 432), (300, 200)]
    finally:
        w._modified = False
        w.close()
