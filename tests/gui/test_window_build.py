"""Tests of building figures in the main window. Off-screen, with a stand-in
for the default model."""

import sys
import time
import types
from dataclasses import replace

import cv2
import numpy as np
import pytest
from PIL import Image

pytest.importorskip("PySide6")

from papermini.project.figure_settings import FigureSettings

pytestmark = pytest.mark.usefixtures("fake_default_model")


def test_a_figure_builds_rebuilds_after_an_edit_and_saves(
    app,
    tmp_path,
    new_window,
    wait,
    crop_view_marks,
    project_store,
):
    im = np.full((900, 700, 3), 255, np.uint8)
    cv2.ellipse(im, (350, 450), (200, 300), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "hero.png")
    Image.fromarray(np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)).save(
        tmp_path / "m.png"
    )

    w = new_window()
    w.add_images([tmp_path / "hero.png"], FigureSettings(mask=str(tmp_path / "m.png")))
    fig = w.current()
    assert wait(lambda: fig.up_to_date), fig.error
    assert fig.mini.figure_height_mm == pytest.approx(32, abs=0.05)  # Medium
    assert fig.mini.source_outline and crop_view_marks(w.crop_view)  # on the source
    # defaults (fold and overlap 0) on a wide joint: no note under the overlap field
    assert fig.mini.tab_overlap_used and fig.mini.tab_joint_mm > 10
    assert not w.panel.overlap_hint.isVisibleTo(w.panel)

    # edit through the panel -> rebuild with the new height
    w.panel.size_field.h.setValue(30)
    assert fig.entry.settings.height_mm == 30
    assert wait(lambda: fig.up_to_date and fig.mini.figure_height_mm < 31), fig.error
    assert fig.mini.figure_height_mm == pytest.approx(30, abs=0.05)

    # crop from the source view lands in the settings
    w.crop_view.cropChanged.emit([0.1, 0.1, 0.9, 0.9])
    assert fig.entry.settings.crop == [0.1, 0.1, 0.9, 0.9]

    # sheet tab builds a layout
    w.tabs.setCurrentIndex(w.SHEET)
    assert wait(lambda: "piece" in w.sheet_panel.info.text())

    from pathlib import Path

    w.project.path = Path(tmp_path / "proj.yaml")
    assert w.save()

    p = project_store.load(tmp_path / "proj.yaml")
    assert p.figures[0].settings.height_mm == 30
    assert p.figures[0].settings.crop == [0.1, 0.1, 0.9, 0.9]


def test_a_bad_model_reports_an_error_and_the_figure_recovers(
    app, tmp_path, new_window, wait
):
    """Regression: an unusable model used to kill the build silently, and the
    figure never rebuilt again."""
    from dataclasses import replace

    im = np.full((600, 500, 3), 255, np.uint8)
    cv2.circle(im, (250, 300), 150, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "hero.png")
    Image.fromarray(np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)).save(
        tmp_path / "m.png"
    )

    w = new_window()
    w.add_images([tmp_path / "hero.png"], FigureSettings(model="no-such-model"))
    fig = w.current()
    assert wait(lambda: fig.error is not None), "build died without reporting"
    assert "unknown model" in fig.error and fig.queued is None

    # 'alpha' on an image without transparency is an error, not a full-image mask
    w.panel.changed.emit(replace(fig.entry.settings, model="alpha"))
    assert wait(lambda: fig.error is not None) and "transparency" in fig.error

    # fixing the setting rebuilds
    w.panel.changed.emit(
        replace(fig.entry.settings, model="mask", mask=str(tmp_path / "m.png"))
    )
    assert wait(lambda: fig.up_to_date), fig.error
    assert fig.error is None and "figure" in w.info.text()


def test_source_view_shows_the_adjusted_picture_without_running_the_model(
    app, tmp_path, wait, new_window, monkeypatch
):
    """The Source view follows the color sliders (a preview at the original's size),
    and a color change rebuilds the miniature from the cached mask: the model does not
    run again and the outline stays."""
    from PySide6.QtWidgets import QGraphicsPixmapItem

    from papermini.gui.views.images import PREVIEW_PX
    from papermini.pipeline.segmentation import segment

    im = np.full((2400, 1800, 3), 255, np.uint8)  # larger than a preview
    cv2.circle(im, (900, 1200), 500, (200, 40, 40), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    runs = []
    real = segment.OnnxSegmenter.__call__
    monkeypatch.setattr(
        segment.OnnxSegmenter,
        "__call__",
        lambda self, x: runs.append(1) or real(self, x),
    )
    w = new_window()
    w.add_images([tmp_path / "a.png"])
    fig = w.current()
    assert wait(lambda: fig.up_to_date), fig.error
    assert len(runs) == 1 and w.crop_view.picture_size() == (1800, 2400)
    outline = fig.mini.source_outline
    w.panel.changed.emit(replace(fig.entry.settings, greyscale=True))
    assert wait(lambda: fig.up_to_date and w.crop_view.picture_size() != (1800, 2400))
    assert max(w.crop_view.picture_size()) == PREVIEW_PX  # a smaller preview...
    shown = w.crop_view.sceneRect()  # ...in the original's pixels
    assert (shown.width(), shown.height()) == (1800, 2400)
    picture = next(
        it for it in w.crop_view.scene().items() if isinstance(it, QGraphicsPixmapItem)
    )
    pm = picture.pixmap().toImage()
    c = pm.pixelColor(pm.width() // 2, pm.height() // 2)
    assert c.red() == c.green() == c.blue()  # shown in grey
    assert len(runs) == 1  # the model did not run again
    assert len(fig.mini.source_outline) == len(outline)
    art = np.asarray(fig.mini.art.convert("RGB")).astype(int)
    mid = art[art.shape[0] // 2, art.shape[1] // 2]
    assert abs(mid[0] - mid[1]) <= 2  # and printed grey
    w.panel.changed.emit(replace(fig.entry.settings, greyscale=False))
    assert wait(lambda: w.crop_view.picture_size() == (1800, 2400))  # the original


class SlowSegmenter:
    """Stands in for the onnxruntime session of a model that runs until it is
    terminated (or, with ``block`` off, at once). Dark pixels are the figure."""

    block = True
    calls = 0
    running = 0  # runs in progress
    started = None  # threading.Event, set when a run starts

    def __init__(self, path, providers=None):
        pass

    def get_inputs(self):
        return [
            types.SimpleNamespace(
                name="input", shape=[1, 3, 64, 64], type="tensor(float)"
            )
        ]

    def run(self, _names, feeds, run_options):
        SlowSegmenter.calls += 1
        if not SlowSegmenter.block:
            return [-feeds["input"].mean(axis=1)]
        SlowSegmenter.running += 1
        try:
            SlowSegmenter.started.set()
            while not run_options.terminate:
                time.sleep(0.01)
            raise RuntimeError("terminated")
        finally:
            SlowSegmenter.running -= 1


class FakeRunOptions:
    """Stands in for the onnxruntime options of one model run."""

    terminate = False


def _run_models_on(monkeypatch, session):
    """Runs the ONNX models through the real segmenter on ``session``, a fake
    onnxruntime session class."""
    from papermini.pipeline.segmentation import segment
    from papermini.pipeline.segmentation.onnx_segmenter import OnnxSegmenter

    onnxruntime = types.SimpleNamespace(
        InferenceSession=session,
        RunOptions=FakeRunOptions,
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", onnxruntime)
    monkeypatch.setattr(segment, "OnnxSegmenter", OnnxSegmenter)


def test_background_removal_shows_progress_and_can_be_cancelled(
    app, tmp_path, monkeypatch, new_window, wait, crop_view_dimmed, crop_view_marks
):
    """A running model shows a card with Cancel on the dimmed image; Cancel really stops
    it and nothing restarts on its own; Run again does. A new crop stops the old run."""
    import threading

    from papermini.pipeline.segmentation import segment

    _run_models_on(monkeypatch, SlowSegmenter)
    SlowSegmenter.block, SlowSegmenter.calls = True, 0
    SlowSegmenter.started = threading.Event()
    im = np.full((400, 300, 3), 255, np.uint8)
    cv2.circle(im, (150, 200), 80, (40, 40, 40), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    w = new_window()
    w.add_images([tmp_path / "a.png"])
    fig = w.current()
    assert wait(lambda: w.work_box.isVisibleTo(w) and crop_view_dimmed(w.crop_view), 30)
    assert (
        w.work.button.text() == "Cancel"
        and "Removing the background" in w.work.title.text()
    )
    assert segment.DEFAULT_MODEL in w.work.detail.text()

    # a new crop: the old run stops at once and the new one starts
    SlowSegmenter.started.clear()
    w.crop_view.cropChanged.emit([0.1, 0.1, 0.9, 0.9])
    assert wait(lambda: SlowSegmenter.started.is_set() and SlowSegmenter.calls == 2, 30)
    assert fig.cancelled is None

    w.work.button.click()  # Cancel
    assert fig.stopped  # at once
    assert wait(lambda: SlowSegmenter.running == 0, 30)  # and the run really stops
    assert wait(lambda: segment.cancel_runs() == 0, 30)  # nothing left to stop
    assert w.work.button.text() == "Run again" and "cancelled" in w.work.title.text()
    assert not crop_view_dimmed(w.crop_view) and not fig.up_to_date
    from papermini.gui.widgets.figure_delegate import SUBTITLE_ROLE

    assert w.list.item(0).data(SUBTITLE_ROLE).startswith("Cancelled")
    assert wait(lambda: w.pool.activeThreadCount() == 0, 30)
    w.list.setCurrentRow(-1)
    w.list.setCurrentRow(0)  # nothing restarts on its own, not even when selected again
    app.processEvents()  # (selecting it builds it soon after, when it needs a build)
    assert fig.queued is None and w.work.button.text() == "Run again"
    assert w.pool.activeThreadCount() == 0 and SlowSegmenter.calls == 2

    SlowSegmenter.block = False
    w.work.button.click()  # Run again
    assert wait(lambda: fig.up_to_date, 30), fig.error
    assert not w.work_box.isVisibleTo(w) and crop_view_marks(w.crop_view)


class SlowLoadSegmenter:
    """A model that takes until ``loaded`` is set to load, then segments by
    darkness at once."""

    loading = loaded = None  # threading.Event
    calls = 0

    def __init__(self, *a, **k):
        SlowLoadSegmenter.loading.set()
        assert SlowLoadSegmenter.loaded.wait(60)

    def __call__(self, im):
        SlowLoadSegmenter.calls += 1
        return np.where(np.asarray(im.convert("L")) < 128, 255, 0).astype(np.uint8)


def test_cancel_works_while_the_model_loads(
    app, tmp_path, monkeypatch, wait, new_window
):
    """Loading a model can take longer than running it (BiRefNet-lite: ~10 s). Cancel
    then marks the figure cancelled at once and the model never runs; other settings
    (a margin) do not start it again, Run again does."""
    import threading

    from papermini.gui.widgets.figure_delegate import SUBTITLE_ROLE
    from papermini.pipeline.segmentation import segment

    monkeypatch.setattr(segment, "OnnxSegmenter", SlowLoadSegmenter)
    SlowLoadSegmenter.loading, SlowLoadSegmenter.loaded = (
        threading.Event(),
        threading.Event(),
    )
    SlowLoadSegmenter.calls = 0
    im = np.full((400, 300, 3), 255, np.uint8)
    cv2.circle(im, (150, 200), 80, (40, 40, 40), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    w = new_window()
    try:
        w.add_images([tmp_path / "a.png"])
        fig = w.current()
        assert wait(
            lambda: SlowLoadSegmenter.loading.is_set() and w.work_box.isVisibleTo(w),
            30,
        )
        assert "loading" in w.work.detail.text()
        w.work.button.click()  # Cancel, while it loads
        assert fig.stopped and w.work.button.text() == "Run again"
        assert "Cancelled" in w.list.item(0).data(SUBTITLE_ROLE)
        SlowLoadSegmenter.loaded.set()
        assert wait(lambda: w.pool.activeThreadCount() == 0, 30)
        assert SlowLoadSegmenter.calls == 0 and not fig.up_to_date

        w.panel.changed.emit(replace(fig.entry.settings, margin_mm=4))  # not the mask
        end = time.time() + 0.8  # (past the build debounce)
        while time.time() < end:
            app.processEvents()
            time.sleep(0.02)
        assert w.pool.activeThreadCount() == 0 and SlowLoadSegmenter.calls == 0
        assert fig.stopped and w.work.button.text() == "Run again"

        w.work.button.click()  # Run again
        assert wait(lambda: fig.up_to_date, 30), fig.error
        assert SlowLoadSegmenter.calls == 1 and not w.work_box.isVisibleTo(w)
    finally:
        SlowLoadSegmenter.loaded.set()


def test_a_new_image_waits_for_a_running_model_with_cancel(
    app, tmp_path, monkeypatch, new_window, wait, crop_view_dimmed
):
    """An image added while another figure's model runs waits for that run: the card
    says so, and Cancel stops that run so the new image goes next."""
    import threading

    from papermini.gui.widgets.figure_delegate import SUBTITLE_ROLE
    from papermini.pipeline.segmentation import segment

    _run_models_on(monkeypatch, SlowSegmenter)
    SlowSegmenter.block, SlowSegmenter.calls = True, 0
    SlowSegmenter.started = threading.Event()
    im = np.full((400, 300, 3), 255, np.uint8)
    cv2.circle(im, (150, 200), 80, (40, 40, 40), -1)
    for n in "ab":
        Image.fromarray(im).save(tmp_path / f"{n}.png")
    w = new_window()
    w.add_images([tmp_path / "a.png"])
    a = w.current()
    assert wait(
        lambda: SlowSegmenter.started.is_set() and w.work_box.isVisibleTo(w),
        30,
    )
    SlowSegmenter.started.clear()
    w.add_images([tmp_path / "b.png"])
    b = w.current()
    assert b is not a
    assert wait(
        lambda: w.work_box.isVisibleTo(w) and w.work.title.text() == "Waiting for a",
        30,
    )
    assert w.work.button.text() == "Cancel it" and not crop_view_dimmed(w.crop_view)
    assert not w.busy_box.isVisibleTo(w)  # the card says it all

    w.work.button.click()  # stops a's run
    assert a.stopped and not b.stopped
    assert wait(lambda: SlowSegmenter.started.is_set(), 30)  # b goes next
    assert wait(lambda: "Removing the background" in w.work.title.text(), 30)
    assert w.work.button.text() == "Cancel" and SlowSegmenter.calls == 2
    w.work.button.click()  # and b's own run
    assert b.stopped and wait(lambda: SlowSegmenter.running == 0, 30)
    assert wait(lambda: segment.cancel_runs() == 0, 30)
    assert "Cancelled" in w.list.item(0).data(SUBTITLE_ROLE)  # a's card


def test_a_stretched_figure_builds_at_both_sizes(app, tmp_path, new_window, wait):
    im = np.full((900, 700, 3), 255, np.uint8)
    cv2.ellipse(im, (350, 450), (200, 300), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    w = new_window()
    w.add_images([tmp_path / "a.png"])
    fig = w.current()
    assert wait(lambda: fig.up_to_date), fig.error
    f = w.panel.size_field
    assert f.w.value() == pytest.approx(32 * 401 / 601, abs=0.1)  # follows the figure
    f.link.click()
    f.w.setValue(40)
    assert (fig.entry.settings.height_mm, fig.entry.settings.width_mm) == (32, 40)
    assert fig.entry.settings.size == "custom"  # (a width of its own: not Medium's)
    assert wait(lambda: fig.up_to_date), fig.error
    assert fig.mini.figure_width_mm == pytest.approx(40, abs=0.05)
    assert fig.mini.figure_height_mm == pytest.approx(32, abs=0.05)
    assert "figure 40.0 × 32.0 mm" in w.info.text()


def test_auto_model_says_which_method_it_used(app, tmp_path, new_window, wait):
    """Model "auto" shows under the model box how it found the figure: the image's own
    transparency, or the default model for an image without it."""
    from papermini.pipeline.segmentation import segment

    im = np.full((600, 500, 3), 255, np.uint8)
    cv2.ellipse(im, (250, 300), (150, 220), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "flat.png")
    rgba = np.dstack([im, np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)])
    Image.fromarray(rgba, "RGBA").save(tmp_path / "cutout.png")

    w = new_window()
    w.add_images([tmp_path / "flat.png", tmp_path / "cutout.png"])
    flat, cutout = w.figures
    assert flat.entry.settings.model == "auto"
    w.list.setCurrentRow(0)
    assert wait(lambda: flat.up_to_date), flat.error
    assert flat.mini.method == segment.DEFAULT_MODEL
    hint = w.panel.auto_hint
    assert hint.isVisibleTo(w.panel) and segment.DEFAULT_MODEL in hint.text()
    assert "Chosen method" in hint.text()
    assert "no transparency" in hint.text()

    w.list.setCurrentRow(1)
    assert wait(lambda: cutout.up_to_date), cutout.error
    assert cutout.mini.method == "alpha"
    assert hint.isVisibleTo(w.panel) and "own transparency" in hint.text()

    # another model than auto: nothing to explain
    box = w.panel.field("model")
    box.setCurrentText("alpha")
    box.activated.emit(box.currentIndex())  # (as when the user picks it)
    assert not hint.isVisibleTo(w.panel)


def test_selecting_a_figure_keeps_the_build_debounce(app, built_window):
    """An edit after selecting a figure waits for the debounce instead of building at
    once."""
    from dataclasses import replace

    fig = built_window.current()
    built_window.panel.changed.emit(replace(fig.entry.settings, height_mm=30))
    app.processEvents()
    assert not fig.up_to_date and fig.queued is None
