"""Shared test setup. No test may use the real models, the network, the user's cache,
the user's log folder or the user's preferences, and the desktop app runs off-screen."""

import importlib
import io
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


# region isolation
@pytest.fixture(autouse=True)
def isolated_log(monkeypatch, tmp_path_factory):
    """Every test gets an empty log folder, and leaves no log session, logger level or
    error hook behind."""
    from papermini.support import log

    monkeypatch.setenv(log.LOG_ENV, str(tmp_path_factory.mktemp("papermini-logs")))
    hooks = sys.excepthook, threading.excepthook
    yield
    log.stop()
    log.logger.setLevel(logging.NOTSET)
    log.logger.propagate = True
    sys.excepthook, threading.excepthook = hooks


@pytest.fixture(autouse=True)
def isolated_model_cache(monkeypatch, tmp_path_factory):
    """Every test gets an empty model and mask cache, no download hooks, and fetching a
    URL fails loudly.

    Tests that exercise downloads replace ``segment.download`` or ``urlopen`` with fakes.
    """
    from papermini.pipeline.segmentation import segment

    monkeypatch.setenv(
        "PAPERMINI_CACHE", str(tmp_path_factory.mktemp("papermini-cache"))
    )
    monkeypatch.setattr(
        segment, "_SEGMENTERS", {}
    )  # no session left over from another test
    monkeypatch.setattr(segment, "PROGRESS_HOOK", None)
    monkeypatch.setattr(segment, "CONFIRM_DOWNLOAD", None)

    def no_network(req, *a, **k):
        url = getattr(req, "full_url", req)
        raise AssertionError(f"tests must not use the network (tried {url})")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)


@pytest.fixture(autouse=True)
def no_installed_fonts(monkeypatch):
    """Tests see no installed fonts (only Times and the bundled ones): the system's font
    folders are never scanned. Tests of the scan give ``fonts.font_dirs`` folders of their
    own."""
    from papermini.support import fonts

    monkeypatch.setattr(fonts, "font_dirs", list)
    monkeypatch.setattr(fonts, "_installed", None)


# endregion


# region the desktop app
@pytest.fixture(scope="session")
def app(tmp_path_factory):
    """Starts the Qt application, with its preferences in a folder of its own."""
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path_factory.mktemp("settings")),
    )
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def fresh_app(request):
    """Clears the preferences before each test of the desktop app, and deletes the
    windows and dialogs the test left behind."""
    if "app" not in request.fixturenames:
        yield
        return
    app = request.getfixturevalue("app")
    from PySide6.QtCore import QEvent

    from papermini.gui import prefs

    prefs.store().clear()
    yield
    for widget in app.topLevelWidgets():
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    prefs.store().clear()


@pytest.fixture
def prefs(app):
    """Returns the app's preferences module. The preferences start empty."""
    from papermini.gui import prefs

    return prefs


@pytest.fixture
def wait(app):
    """Returns ``wait(cond, timeout)``, which processes the app's events until ``cond()``
    is true. It returns False if that takes over ``timeout`` seconds."""

    def wait(cond, timeout=180):  # (generous: CI runners can be slow)
        end = time.time() + timeout
        while time.time() < end:
            app.processEvents()
            if cond():
                return True
            time.sleep(0.02)
        return False

    return wait


@pytest.fixture
def new_window(app):
    """Returns ``new_window()``, which opens a main window. The windows close after the
    test without asking to save."""
    from papermini.gui.window.main_window import MainWindow

    made = []

    def new_window():
        made.append(MainWindow())
        return made[-1]

    yield new_window
    for w in made:
        w._modified = False  # (no "Save changes?" question)
        w.close()


@pytest.fixture
def window(new_window):
    """Opens a main window."""
    return new_window()


@pytest.fixture
def downloaded_default_model(isolated_model_cache):
    """Puts a dummy file where the default model goes, so nothing asks to download it."""
    from papermini.pipeline.segmentation import segment

    path = segment.model_path(segment.DEFAULT_MODEL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a real model")


@pytest.fixture
def no_builds(monkeypatch):
    """Makes every figure in the app fail to build at once, for tests without a model."""
    from papermini.gui.window import build_job

    def fail(*a, **k):
        raise ValueError("not built in this test")

    monkeypatch.setattr(build_job, "build_mini", fail)


# endregion


# region test data
@pytest.fixture
def figure_image():
    """Returns ``figure_image(path, size, mask)``, which saves a dark figure on white at
    ``path``. With ``mask`` it also saves the figure's mask beside it, named
    ``<name>_mask.png``. It returns the image's path and the mask's."""

    def figure_image(path, size=(400, 600), mask=True):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        w, h = size
        im = np.full((h, w, 3), 255, np.uint8)
        top_left = round(w * 0.3), round(h / 6)
        bottom_right = round(w * 0.7), round(h * 13 / 15)
        cv2.rectangle(im, top_left, bottom_right, (40, 40, 40), -1)
        Image.fromarray(im).save(path)
        mask_path = path.with_name(f"{path.stem}_mask.png")
        if mask:
            figure = np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)
            Image.fromarray(figure).save(mask_path)
        return path, mask_path

    return figure_image


@pytest.fixture
def square_mini():
    """Returns ``square_mini(name, w, h, px_per_mm, folds)``, which makes a built figure
    that is a plain red rectangle, ``w`` by ``h`` mm."""
    from papermini.pipeline.cut_path import CutPath
    from papermini.pipeline.mini import Mini

    def square_mini(name="sq", w=30.0, h=40.0, px_per_mm=10, folds=()):
        cut = CutPath(np.array([[0, 0], [w, 0], [w, h], [0, h]], float))
        size = int(w * px_per_mm), int(h * px_per_mm)
        art = Image.new("RGBA", size, (200, 40, 30, 255))
        return Mini(name, w, h, art, cut, folds=list(folds))

    return square_mini


@pytest.fixture
def fake_web(monkeypatch):
    """Replaces the web: ``fake_web[url] = bytes``, or an exception to raise. Other links
    give a 404. ``fake_web.asked`` lists each request's link and user agent."""

    class Web(dict):
        asked: list

    pages, asked = Web(), []

    def urlopen(req, timeout=None):
        url = req.full_url
        asked.append((url, req.get_header("User-agent")))
        body = pages.get(url)
        if isinstance(body, Exception):
            raise body
        if body is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", Message(), None)
        return io.BytesIO(body)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    pages.asked = asked
    return pages


@pytest.fixture
def scripts(monkeypatch):
    """Returns ``scripts(name)``, which imports ``scripts/<name>.py``."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module


# endregion
