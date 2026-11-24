"""Tests of model downloads, the cache page and the model licences in the app."""

import pytest
from PIL import Image

pytest.importorskip("PySide6")

from papermini.project.figure_settings import FigureSettings

pytestmark = pytest.mark.usefixtures("fake_default_model")


@pytest.fixture
def downloader(fake_downloader):
    """The pipeline downloads its models with the fake (no network, no real model)."""
    return fake_downloader


@pytest.fixture
def model_cache(monkeypatch, tmp_path, fake_downloader):
    """An empty model folder; returns the files downloaded into it."""
    monkeypatch.setenv("PAPERMINI_CACHE", str(tmp_path / "cache"))
    return fake_downloader.got


def test_download_dialog_asks_then_downloads(app, model_cache, pipeline, wait):
    from PySide6.QtWidgets import QDialog

    from papermini.gui.dialogs.download_dialog import DownloadDialog

    segmenters = pipeline.segmenters
    d = DownloadDialog("rmbg-1.4", segmenters)
    assert "Download the BRIA RMBG-1.4 model?" in d.title.text()
    assert "176 MB" in d.body.text()
    assert "non-commercial use only" in d.licence_note.text()
    assert "You are responsible for not using it commercially" in d.licence_note.text()
    assert d.btn_go.text() == "Download"
    d.btn_no.click()  # "Not now"
    assert d.result() == QDialog.DialogCode.Rejected and model_cache == []

    d = DownloadDialog("rmbg-1.4", segmenters)
    assert not d.btn_go.isEnabled()  # the licence is not accepted yet
    d.start()  # (Enter: still nothing happens)
    assert model_cache == [] and d.title.text().startswith("Download the")
    d.accept_licence.setChecked(True)
    assert d.btn_go.isEnabled()
    d.btn_go.click()  # "Download"
    assert d.btn_no.text() == "Cancel" and not d.accept_licence.isEnabled()
    assert wait(lambda: d.result() == QDialog.DialogCode.Accepted, 10)
    assert d.bar.value() == 1000 and d.status.text() == "0 of 0 MB"  # 30 bytes
    assert segmenters.path("rmbg-1.4").exists() and model_cache == ["rmbg-1.4.onnx"]


def test_cancelling_a_download_stops_it_and_keeps_no_model(
    app, model_cache, fake_downloader, pipeline, wait
):
    import threading

    from PySide6.QtWidgets import QDialog

    from papermini.gui.dialogs.download_dialog import DownloadDialog

    gate = fake_downloader.gate = threading.Event()
    d = DownloadDialog("birefnet-lite", pipeline.segmenters, ask=False)
    d.reject()  # Cancel / Esc while downloading
    assert d.isVisible() is False and d.result() != QDialog.DialogCode.Accepted
    assert "Cancelling" in d.status.text()
    gate.set()
    assert wait(lambda: not d.downloading, 10)
    assert d.result() == QDialog.DialogCode.Rejected
    assert not pipeline.segmenters.path("birefnet-lite").exists()


def test_build_asks_before_downloading(
    app, tmp_path, model_cache, monkeypatch, new_window, pipeline, wait
):
    from PySide6.QtWidgets import QDialog

    from papermini.gui.dialogs import cache_page
    from papermini.pipeline.segmentation import segment
    from papermini.support.cache_folder import CacheFolder

    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "plain.png")
    asked = []

    class Refuse:
        def __init__(self, model, segmenters, parent=None):
            asked.append(model)

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr("papermini.gui.window.main_window.DownloadDialog", Refuse)
    w = new_window()
    w.add_images([tmp_path / "plain.png"], FigureSettings(model="birefnet-lite"))
    fig = w.current()
    assert wait(lambda: fig.error is not None, 30)
    assert asked == ["birefnet-lite"] and "not downloaded" in fig.error
    assert (
        "Models and cache" in w.banner.text.text()
        and "Lower the strength" not in w.banner.text.text()
    )
    assert model_cache == []
    confirm = w.builds.downloads.confirm  # (what a build calls before a download)
    assert confirm is not None
    assert confirm("birefnet-lite") is False  # declined: not asked again
    assert asked == ["birefnet-lite"]

    # the Models and cache page lists every model, downloads one, and the figure is retried
    dlg = w.preferences_dialog("cache").cache
    assert set(dlg.cards) == set(segment.ONNX_MODELS)
    card = dlg.cards["birefnet-lite"]
    assert "Not downloaded" in card.state.text() and not card.btn_del.isEnabled()
    monkeypatch.setattr(
        cache_page.DownloadDialog,
        "exec",
        lambda self: pipeline.segmenters.fetch(self.model, self.force) and 1,
    )
    card.btn_get.click()
    assert "Downloaded" in card.state.text() and card.btn_get.text() == "Download again"
    assert (
        "birefnet-lite.onnx" in card.state.text()
        and str(CacheFolder.path()) in dlg.folder.text()
    )
    assert confirm("birefnet-lite") is True and fig.error is None

    monkeypatch.setattr(
        cache_page.QMessageBox,
        "question",
        lambda *a, **k: cache_page.QMessageBox.StandardButton.Yes,
    )
    card.btn_del.click()
    assert not pipeline.segmenters.path("birefnet-lite").exists()
    assert "Not downloaded" in card.state.text()


def test_the_cache_page_clears_masks_images_and_everything(
    images_from_web, app, model_cache, monkeypatch, pipeline
):
    """The Models and cache page counts the masks and images from links, clears each,
    keeps the images open figures use, and Clear cache also deletes the models."""
    from papermini.gui.dialogs import cache_page
    from papermini.pipeline.segmentation import segment
    from papermini.support.cache_folder import CacheFolder

    masks = pipeline.masks.folder()
    masks.mkdir(parents=True)
    for i in range(3):
        (masks / f"m{i}.png").write_bytes(b"x" * 1000)
    images = []
    for key in ("aaa", "bbb"):
        (images_from_web.folder() / key).mkdir(parents=True)
        images.append(images_from_web.folder() / key / f"{key}.png")
        images[-1].write_bytes(b"x" * 1000)
    model = pipeline.segmenters.path(segment.DEFAULT_MODEL)
    model.write_bytes(b"model")

    dlg = cache_page.CachePage(
        pipeline.segmenters,
        pipeline.masks,
        images_from_web,
        in_use=lambda: [images[0]],
    )
    assert str(CacheFolder.path()) in dlg.folder.text()
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
    monkeypatch.setattr(
        cache_page.QMessageBox,
        "question",
        lambda *a, **k: asked.append(a[2]) or cache_page.QMessageBox.StandardButton.Yes,
    )
    dlg.btn_all.click()
    assert "also deletes the downloaded models" in asked[0]
    assert not model.exists() and images[0].exists()
    assert changed == [segment.DEFAULT_MODEL] and not dlg.btn_all.isEnabled()
    assert "Not downloaded" in dlg.cards[segment.DEFAULT_MODEL].state.text()


def test_the_cache_page_scrolls_when_the_window_is_short(app, model_cache, new_window):
    """The Preferences window can be resized smaller than the Models and cache page,
    which then scrolls, and Close stays in view."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton

    w = new_window()
    dlg = w.preferences_dialog("cache")
    assert dlg.isSizeGripEnabled() and dlg.stack.currentWidget() is dlg.cache
    dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    dlg.show()
    app.processEvents()
    dlg.resize(dlg.width(), 300)  # (as short as the other pages allow)
    app.processEvents()
    assert dlg.height() < 450 and dlg.cache.scroll_area.verticalScrollBar().isVisible()
    close = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Close")
    assert not dlg.cache.scroll_area.isAncestorOf(close)
    dlg.close()


def test_the_model_licences_are_links(images_from_web, app, model_cache, pipeline):
    from papermini.gui.dialogs.cache_page import CachePage
    from papermini.gui.dialogs.download_dialog import DownloadDialog
    from papermini.pipeline.segmentation import segment

    segmenters = pipeline.segmenters
    for model, spec in segment.ONNX_MODELS.items():
        assert spec.licence_url.startswith("https://")
        d = DownloadDialog(model, segmenters)
        label = d.licence_note if segmenters.non_commercial(model) else d.body
        assert f'<a href="{spec.licence_url}">' in label.text()
        assert label.openExternalLinks()
    dlg = CachePage(segmenters, pipeline.masks, images_from_web)
    card = dlg.cards["birefnet"]
    assert (
        'href="https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE"'
        in card.licence.text()
    )
    assert card.licence.openExternalLinks()


def test_a_non_commercial_model_always_asks_to_accept_its_licence(
    images_from_web, app, model_cache, pipeline, wait
):
    """RMBG-1.4 only downloads once the user accepts it is for non-commercial use, also
    from the Models and cache page (which otherwise downloads at once); BiRefNet just
    downloads."""
    from PySide6.QtWidgets import QDialog

    from papermini.gui.dialogs.cache_page import CachePage
    from papermini.gui.dialogs.download_dialog import DownloadDialog

    segmenters, masks = pipeline.segmenters, pipeline.masks
    # the Models and cache page's Download
    d = DownloadDialog("rmbg-1.4", segmenters, ask=False)
    assert d.accept_licence is not None and not d.btn_go.isEnabled()
    assert model_cache == [] and d.bar.isHidden()
    d.accept_licence.setChecked(True)
    d.btn_go.click()
    assert wait(lambda: d.result() == QDialog.DialogCode.Accepted, 10)
    d = DownloadDialog("birefnet-lite", segmenters)
    assert d.accept_licence is None and d.licence_note is None and d.btn_go.isEnabled()
    card = CachePage(segmenters, masks, images_from_web).cards["rmbg-1.4"]
    assert card.licence.objectName() == "LicenceNote"
    assert "responsible for not using it commercially" in card.licence.toolTip()
    assert CachePage(segmenters, masks, images_from_web).cards[
        "birefnet"
    ].licence.objectName() == ("Muted")


def test_the_settings_show_the_licence_of_the_model_in_use(
    app, tmp_path, model_cache, new_window, monkeypatch
):
    from papermini.pipeline.segmentation.download_hooks import DownloadHooks

    Image.new("RGB", (300, 400), (40, 40, 40)).save(tmp_path / "a.png")
    w = new_window()
    no = DownloadHooks(confirm=lambda model: False)  # (no prompt)
    monkeypatch.setattr(w.builds, "downloads", no)
    w.add_images([tmp_path / "a.png"])
    p = w.panel
    combo = p.field("model")

    def pick(model):
        combo.setCurrentText(model)
        combo.activated.emit(combo.currentIndex())
        app.processEvents()

    pick("rmbg-1.4")
    assert (
        p.licence_hint.isVisibleTo(p)
        and "Non-commercial use only" in p.licence_hint.text()
        and "pick birefnet or birefnet-lite." in p.licence_hint.text()
    )
    pick("birefnet")
    assert not p.licence_hint.isVisibleTo(p)
    pick("auto")
    p.set_auto_method("rmbg-1.4")  # (auto picked it: the image has no transparency)
    assert p.licence_hint.isVisibleTo(p)
    p.set_auto_method("alpha")
    assert not p.licence_hint.isVisibleTo(p)


def test_closed_window_never_asks_to_download(app, monkeypatch, new_window):
    """Regression: a build waiting for the download question when the window closed
    left the question queued, and a later event loop opened a real dialog for it."""
    import threading

    from PySide6.QtCore import QRunnable, Qt

    asked = []  # (an exception raised in a Qt slot would only be printed)

    class Dialog:
        def __init__(self, model, segmenters, parent=None):
            asked.append(model)

        def exec(self):
            return 0

    monkeypatch.setattr("papermini.gui.window.main_window.DownloadDialog", Dialog)
    w = new_window()
    questions = []  # the done event of each question the build asks
    queued = threading.Event()

    def question(model, answer, done):  # (on the build thread, as it asks)
        questions.append(done)
        queued.set()

    w.sig.ask_download.connect(question, Qt.ConnectionType.DirectConnection)
    got = []
    confirm = w.builds.downloads.confirm  # (what a build calls before a download)
    assert confirm is not None
    w.builds.pool.start(QRunnable.create(lambda: got.append(confirm("birefnet"))))
    assert queued.wait(30)  # the window closes before the question is shown
    w.close()
    assert got == [False]
    app.sendPostedEvents()  # deliver the stale question: it must be dropped
    assert questions[0].is_set() and asked == []  # (delivered, and no dialog)
