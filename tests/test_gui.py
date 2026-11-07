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
        assert fig.mini.figure_height_mm == pytest.approx(42, abs=0.05)
        assert fig.mini.source_cut is not None and w.crop_view._cut_items  # on the source
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
    assert "176 MB" in d.body.text() and "non-commercial" in d.body.text()
    assert d.btn_go.text() == "Download"
    d.btn_no.click()                                   # "Not now"
    assert d.result() == QDialog.Rejected and model_cache == []

    d = DownloadDialog("rmbg-1.4")
    d.btn_go.click()                                   # "Download"
    assert d.btn_no.text() == "Cancel"
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
        assert "Models" in w.banner.text.text() and "lower strength" not in w.banner.text.text()
        assert model_cache == []
        assert w._confirm_download("birefnet-lite") is False   # declined: not asked again
        assert asked == ["birefnet-lite"]

        # the Models window lists every model, downloads one, and the figure is retried
        dlg = models.ModelsDialog(w)
        dlg.changed.connect(w._models_changed)
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


def test_models_menu_entry(app):
    from papermini.gui.window import MainWindow

    w = MainWindow()
    try:
        assert w.a_models in w.menu.actions()
    finally:
        w.close()


def test_licences_are_links(app, model_cache):
    from papermini import segment
    from papermini.gui.models import DownloadDialog, ModelsDialog

    for model, spec in segment.ONNX_MODELS.items():
        assert spec["licence_url"].startswith("https://")
        d = DownloadDialog(model)
        assert f'<a href="{spec["licence_url"]}">' in d.body.text()
        assert d.body.openExternalLinks()
    dlg = ModelsDialog()
    card = dlg.cards["birefnet"]
    assert 'href="https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE"' in card.licence.text()
    assert card.licence.openExternalLinks()


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
        assert not shown(p.empty_box) and all(shown(s) for s in p.sections)
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
        box = p._w["height_mm"][1]
        assert isinstance(box, DoubleSpinBox) and box.text() == "42.00 mm"
        for typed in ("12.5", "12,5"):
            box.lineEdit().selectAll()
            QTest.keyClicks(box.lineEdit(), typed)
            QTest.keyClick(box.lineEdit(), Qt.Key_Return)
            assert box.value() == 12.5 and box.text() == "12.50 mm", typed
        assert p.settings().height_mm == 12.5
    finally:
        QLocale.setDefault(old)


def test_source_view_shows_the_cut_line(app, tmp_path):
    """The Cut-away view is gone: the Source view draws the cut line on the original
    image instead, and forgets it when another image is shown."""
    from papermini.gui.views import load_qimage
    from papermini.gui.window import MainWindow

    im = np.full((900, 700, 3), 255, np.uint8)
    cv2.ellipse(im, (350, 450), (200, 300), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "b.png")
    w = MainWindow()
    try:
        assert [w.tabs.tabText(i) for i in range(w.tabs.count())] ==             ["Miniature", "Source", "Print sheet"]
        assert w.tabs.tabText(w.SHEET) == "Print sheet"
        w.add_images([tmp_path / "a.png"])
        fig = w.current()
        assert wait(app, lambda: fig.up_to_date), fig.error
        cv = w.crop_view
        shade, clip, folds = cv._cut_items
        assert shade.scene() is cv.scene() and len(clip.childItems()) == 1   # the cut line
        assert folds.path().elementCount() == 2                               # the tab fold
        r = clip.childItems()[0].path().boundingRect()
        assert 120 < r.left() < 150 and 120 < r.top() < 150                 # 150 - margin

        cv.refresh_theme()                                 # redrawn, not duplicated
        assert len(cv._cut_items) == 3
        cv.set_image(load_qimage(tmp_path / "b.png"))    # another image: no stale cut line
        assert cv._cut is None and cv._cut_items == []
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

    def colours(pm):
        img = pm.toImage()
        return {img.pixelColor(x, y).name() for x in range(img.width()) for y in range(img.height())
                if img.pixelColor(x, y).alpha() == 255}

    assert theme.LOGO.is_file()  # shipped as package data (pyproject.toml, papermini.spec)
    pm = theme.logo_pixmap(64)
    assert pm.width() == 128  # 2x for sharp rendering on high-DPI screens
    assert {"#fd3c1b", "#000d1d", "#ffffff"} <= colours(pm)  # full colour, not a line icon
    assert pm.toImage().pixelColor(0, 0).alpha() == 0  # transparent around the sticker

    sizes = theme.app_icon().availableSizes()
    assert QSize(16, 16) in sizes and QSize(256, 256) in sizes

    w = MainWindow()
    try:
        assert "#fd3c1b" in colours(w.logo.pixmap())
        assert "#fd3c1b" in colours(w.empty.icon.pixmap())
        w.set_theme("dark")  # re-theming must not swap the logo for a tinted line icon
        assert "#fd3c1b" in colours(w.logo.pixmap())
        assert "#fd3c1b" in colours(w.empty.icon.pixmap())
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
        clip = QMimeData()
        clip.setText(url)
        QApplication.clipboard().setMimeData(clip)
        w.paste()                                 # Ctrl+V outside a text field
        assert len(w.figures) == 2 and len(asked) == n  # second time from the cache
    finally:
        w._modified = False
        w.close()


