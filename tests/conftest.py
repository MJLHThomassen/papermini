"""Shared test setup. No test may use the real models, the network, the user's cache,
the user's log folder or the user's preferences, and the desktop app runs off-screen."""

import base64
import importlib
import io
import logging
import os
import re
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


# region isolation
@pytest.fixture(autouse=True)
def isolated_log(monkeypatch, tmp_path_factory):
    """Every test gets an empty log folder, and leaves no logger level or error hook
    behind. The ``logs`` fixture stops its log session."""
    from papermini.support import log_session

    monkeypatch.setenv(
        log_session.LOG_ENV, str(tmp_path_factory.mktemp("papermini-logs"))
    )
    hooks = sys.excepthook, threading.excepthook
    yield
    log_session.logger.setLevel(logging.NOTSET)
    log_session.logger.propagate = True
    sys.excepthook, threading.excepthook = hooks


@pytest.fixture(autouse=True)
def isolated_model_cache(monkeypatch, tmp_path_factory):
    """Every test gets an empty model and mask cache, no download hooks, and fetching a
    URL fails loudly.

    Tests that exercise downloads give their pipeline a fake ``downloader``, or replace
    ``urlopen`` with a fake.
    """
    from papermini.pipeline.segmentation import segment

    monkeypatch.setenv(
        "PAPERMINI_CACHE", str(tmp_path_factory.mktemp("papermini-cache"))
    )
    monkeypatch.setattr(segment, "PROGRESS_HOOK", None)
    monkeypatch.setattr(segment, "CONFIRM_DOWNLOAD", None)

    def no_network(req, *a, **k):
        url = getattr(req, "full_url", req)
        raise AssertionError(f"tests must not use the network (tried {url})")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)


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
    windows and dialogs the test left behind. It undoes a theme the test applied."""
    if "app" not in request.fixturenames:
        yield
        return
    app = request.getfixturevalue("app")
    store = request.getfixturevalue("settings_store")
    from PySide6.QtCore import QEvent

    store.clear()
    look = app.style().name(), app.font(), app.palette(), app.styleSheet()
    yield
    for widget in app.topLevelWidgets():
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    store.clear()
    if (app.style().name(), app.font(), app.palette(), app.styleSheet()) != look:
        style, font, palette, sheet = look
        app.setStyleSheet(sheet)
        app.setStyle(style)
        app.setFont(font)
        app.setPalette(palette)


@pytest.fixture
def settings_store(app):
    """Returns the QSettings store the app's preferences are saved in, in the
    temporary folder."""
    from PySide6.QtCore import QSettings

    return QSettings(
        QSettings.defaultFormat(), QSettings.Scope.UserScope, "papermini", "papermini"
    )


@pytest.fixture
def prefs(app):
    """Returns the app's preferences. They start empty."""
    from papermini.gui.preferences import Preferences

    return Preferences()


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
def fonts():
    """Returns the fonts, without installed fonts (only Times and the bundled ones): the
    system's font folders are never scanned."""
    from papermini.support.font_library import FontLibrary

    return FontLibrary(folders=[])


@pytest.fixture
def images_from_web():
    """Returns the service that downloads images from links."""
    from papermini.support.image_fetcher import ImageFetcher

    return ImageFetcher()


@pytest.fixture
def updates():
    """Returns the service that checks for and installs updates."""
    from papermini.support.update_service import UpdateService

    return UpdateService()


@pytest.fixture
def logs(updates):
    """Returns the desktop app's log session, not yet started. It is stopped after the
    test."""
    from papermini.support.log_session import LogSession

    logs = LogSession(updates)
    yield logs
    logs.stop()


@pytest.fixture
def size_calculator():
    """Returns the service that calculates size tables and figure sizes."""
    from papermini.project.size_calculator import SizeCalculator

    return SizeCalculator()


@pytest.fixture
def project_store(size_calculator, images_from_web):
    """Returns the service that loads and saves project files."""
    from papermini.project.project_store import ProjectStore

    return ProjectStore(size_calculator, images_from_web)


@pytest.fixture
def new_window(
    prefs,
    project_store,
    size_calculator,
    pipeline,
    fonts,
    images_from_web,
    updates,
    logs,
):
    """Returns ``new_window(pipeline)``, which opens a main window with the ``prefs``
    preferences, the services of the fixtures and ``pipeline``, by default the
    ``pipeline`` fixture's. The windows close after the test without asking to save."""
    from papermini.gui.window.main_window import MainWindow

    made = []
    shared = pipeline

    def new_window(pipeline=shared):
        made.append(
            MainWindow(
                prefs,
                project_store,
                size_calculator,
                pipeline,
                fonts,
                images_from_web,
                updates,
                logs,
            )
        )
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
    from papermini.pipeline.segmentation.segmenter_registry import SegmenterRegistry

    path = SegmenterRegistry.path(segment.DEFAULT_MODEL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a real model")


@pytest.fixture
def no_builds(monkeypatch):
    """Makes every figure in the app fail to build at once, for tests without a model."""
    from papermini.gui.window import build_job

    def fail(*a, **k):
        raise ValueError("not built in this test")

    monkeypatch.setattr(build_job, "build_mini", fail)


@pytest.fixture
def crop_view_marks():
    """Returns ``crop_view_marks(view)``, which returns the marks a crop view
    draws between its picture and the crop box: the washed-out background and the
    figure's outline, or the dimming while a model runs."""

    def crop_view_marks(view):
        from PySide6.QtWidgets import QGraphicsPathItem

        marks = [
            it
            for it in view.scene().items()
            if isinstance(it, QGraphicsPathItem) and 0 < it.zValue() < 1
        ]
        return sorted(marks, key=lambda it: it.zValue())

    return crop_view_marks


@pytest.fixture
def crop_view_dimmed(crop_view_marks):
    """Returns ``crop_view_dimmed(view)``, which tells whether a crop view dims
    its picture, as it does while a model runs."""

    def crop_view_dimmed(view):
        return len(crop_view_marks(view)) == 1

    return crop_view_dimmed


@pytest.fixture
def unsaved():
    """Returns ``unsaved(w)``, which tells whether the title of the window ``w``
    marks unsaved changes."""

    def unsaved(w):
        return " * " in w.windowTitle()

    return unsaved


class FakeDownloader:
    """Stands in for the model downloads: records each file it is asked for and writes
    ``content`` there, reporting progress in three steps. With a ``gate`` event it waits
    for that first, and a set ``cancel`` event stops it."""

    def __init__(self):
        self.got: list[str] = []
        self.urls: list[str] = []
        self.content = b"x" * 30
        self.gate: threading.Event | None = None

    def download(self, url, dest, timeout=30.0, progress=None, cancel=None):
        from papermini.pipeline.segmentation.model_error import ModelError

        if self.gate is not None:
            self.gate.wait(5)
        self.got.append(dest.name)
        self.urls.append(url)
        for i in range(1, 4):
            if cancel is not None and cancel.is_set():
                raise ModelError("model download cancelled")
            if progress:
                progress(i * 10, 30, "")
            time.sleep(0.01)
        dest.write_bytes(self.content)
        return dest


@pytest.fixture
def fake_downloader():
    """Returns a ``FakeDownloader``."""
    return FakeDownloader()


class DarkSegmenter:
    """Stands in for a real model: everything darker than mid-grey is the figure."""

    def __init__(self, path, *a, **k):
        self.path = path

    def __call__(self, im):
        return np.where(np.asarray(im.convert("L")) < 128, 255, 0).astype(np.uint8)


@pytest.fixture
def fake_default_model(downloaded_default_model):
    """The default model is "downloaded" (a dummy file) and the ``pipeline`` fixture's
    models segment by darkness, so figures build without the real model and without a
    download prompt; the other models stay missing."""


@pytest.fixture
def downloader():
    """Returns the downloader of the ``pipeline`` fixture: the real one, which fails
    loudly because tests have no network. Tests of downloads override this fixture."""
    from papermini.pipeline.segmentation.downloader import Downloader

    return Downloader()


@pytest.fixture
def make_segmenter(request):
    """Returns what the ``pipeline`` fixture makes its segmenters with: a fake that
    segments by darkness when the test uses ``fake_default_model``, otherwise the real
    ONNX segmenter."""
    from papermini.pipeline.segmentation.onnx_segmenter import OnnxSegmenter

    return (
        DarkSegmenter if "fake_default_model" in request.fixturenames else OnnxSegmenter
    )


@pytest.fixture
def pipeline(fonts, downloader, make_segmenter):
    """Returns the pipeline's services, wired as the entry points wire them, with the
    ``fonts``, ``downloader`` and ``make_segmenter`` fixtures' fonts, downloads and
    models."""
    from papermini.pipeline.pipeline import Pipeline

    return Pipeline(fonts, downloader, make_segmenter)


@pytest.fixture
def built_window(window, wait, tmp_path, figure_image):
    """Opens a main window with one figure, built from ``figure_image`` and its mask at
    42.25 mm and 3000 dpi."""
    from papermini.project.figure_settings import FigureSettings

    image, mask = figure_image(tmp_path / "hero.png")
    window.add_images(
        [image], FigureSettings(mask=str(mask), height_mm=42.25, dpi=3000)
    )
    fig = window.current()
    assert wait(lambda: fig.up_to_date), fig.error
    return window


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


@pytest.fixture
def hero_figure(tmp_path):
    """A dark figure on white, exactly 700 px high, plus its mask."""
    im = np.full((1000, 800, 3), 255, np.uint8)
    cv2.ellipse(im, (400, 300), (150, 120), 0, 0, 360, (40, 40, 40), -1)
    cv2.rectangle(
        im, (300, 300), (500, 899), (40, 40, 40), -1
    )  # rows 180..899 -> 720 px
    mask = np.where(im[..., 0] < 128, 255, 0).astype(np.uint8)
    Image.fromarray(im).save(tmp_path / "hero.png")
    Image.fromarray(mask).save(tmp_path / "hero_mask.png")
    return tmp_path / "hero.png", tmp_path / "hero_mask.png"


@pytest.fixture
def goblin_figure(tmp_path, figure_image):
    """A dark figure on white, plus its mask."""
    return figure_image(tmp_path / "goblin.png")


@pytest.fixture
def red_disc(tmp_path):
    """A red disc on white, with its own mask (no model)."""
    import cv2

    im = np.full((600, 500, 3), 255, np.uint8)
    cv2.circle(im, (250, 300), 150, (200, 40, 40), -1)
    Image.fromarray(im).save(tmp_path / "f.png")
    mask = np.zeros((600, 500), np.uint8)
    cv2.circle(mask, (250, 300), 150, 255, -1)
    Image.fromarray(mask).save(tmp_path / "m.png")
    return tmp_path / "f.png", tmp_path / "m.png"


@pytest.fixture
def transparent_figure():
    """Returns ``transparent_figure(path, size)``, which saves a red figure (an
    ellipse) on a transparent background at ``path``. It returns ``path``."""

    def transparent_figure(path: Path, size=(300, 400)) -> Path:
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        w, h = size
        ImageDraw.Draw(im).ellipse(
            [w * 0.2, h * 0.1, w * 0.8, h * 0.9], fill=(200, 40, 30, 255)
        )
        im.save(path)
        return path

    return transparent_figure


@pytest.fixture
def build_token(size_calculator, pipeline):
    """Returns ``build_token(path, **settings)``, which builds a token of the
    picture at ``path``, cut out by the picture's transparency."""
    from papermini.project.settings import build_mini

    def build_token(path, **kw):
        s = size_calculator.settings_with_size(dict(kind="token", model="alpha", **kw))
        return build_mini(path, s, pipeline=pipeline, log=lambda *a: None)

    return build_token


@pytest.fixture
def numbered_mini(pipeline):
    """Returns ``numbered_mini(figure, **settings)``, which builds the mini of
    ``figure``, an image and its mask, labelled Goblin."""
    from papermini.project.figure_settings import FigureSettings
    from papermini.project.settings import build_mini

    def numbered_mini(figure, **settings):
        img, mask = figure
        return build_mini(
            img,
            FigureSettings(mask=str(mask), label="Goblin", **settings),
            pipeline=pipeline,
            log=lambda *_: None,
        )

    return numbered_mini


@pytest.fixture
def media_box_mm():
    """Returns ``media_box_mm(pdf)``, which reads the page size of a PDF file in
    whole millimetres."""

    def media_box_mm(pdf) -> tuple:
        w, h = re.search(
            rb"/MediaBox \[ 0 0 ([\d.]+) ([\d.]+) \]", pdf.read_bytes()
        ).groups()
        return round(float(w) / 72 * 25.4), round(float(h) / 72 * 25.4)

    return media_box_mm


@pytest.fixture
def figure_bytes():
    """Returns ``figure_bytes(fmt, size)``, which encodes a red oval on a
    transparent background as an image file. The alpha channel is the mask, so no
    model is needed."""

    def figure_bytes(fmt="PNG", size=(300, 450)) -> bytes:
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse(
            (30, 30, size[0] - 30, size[1] - 30), fill=(200, 40, 30, 255)
        )
        buf = io.BytesIO()
        (im.convert("RGB") if fmt == "JPEG" else im).save(buf, fmt)
        return buf.getvalue()

    return figure_bytes


@pytest.fixture
def monsters(tmp_path, figure_image) -> Path:
    """A folder with images directly in it and in subfolders, two files with the same
    name in different subfolders, a hidden folder and files that are not images."""
    root = tmp_path / "Monsters"
    for rel in (
        "leader.png",
        "goblins/goblin 10.png",
        "goblins/goblin 2.png",
        "goblins/leader.png",
        "orcs/leader.webp",
        ".hidden/x.png",
    ):
        figure_image(root / rel, (80, 120), mask=False)
    (root / "notes.txt").write_text("not an image")
    (root / "orcs" / "readme.md").write_text("not an image")
    return root


@pytest.fixture
def keys():
    """A throwaway release key pair: (private, public), base64."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    pub = k.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return base64.b64encode(priv).decode(), base64.b64encode(pub).decode()


@pytest.fixture
def sign(scripts):
    """Returns ``sign(data, private)``, which signs ``data`` as a release is signed."""
    return scripts("sign_release").sign


# endregion


# region a fake onnxruntime
class FakeInput:
    def __init__(self, type_="tensor(float)"):
        self.name, self.shape, self.type = "input", [1, 3, "h", "w"], type_


class FakeSession:
    """Records the model input and returns a fixed output."""

    output = None
    seen = None
    input_type = "tensor(float)"

    def __init__(self, path, providers=None):
        pass

    def get_inputs(self):
        return [FakeInput(FakeSession.input_type)]

    def run(self, _names, feeds, run_options=None):
        FakeSession.seen = feeds["input"]
        if FakeSession.block is not None:  # a long run: wait until it is terminated
            FakeSession.block.set()
            while not run_options.terminate:
                time.sleep(0.01)
            raise RuntimeError("Exiting due to terminate flag being set to true.")
        return [FakeSession.output]

    block = None


class FakeRunOptions:
    terminate = False


@pytest.fixture
def fake_ort(monkeypatch):
    """Replaces onnxruntime with a fake whose session records its input and returns
    ``FakeSession.output``."""
    mod = types.SimpleNamespace(InferenceSession=FakeSession, RunOptions=FakeRunOptions)
    FakeSession.block = None
    monkeypatch.setitem(sys.modules, "onnxruntime", mod)
    FakeSession.input_type = "tensor(float)"
    return FakeSession


# endregion


# region pipeline inputs
@pytest.fixture
def ghost():
    """Returns ``ghost(h, w, touch_border, ring)``, which makes the 0/255 mask of a blob
    figure, ``w`` by ``h`` px, with an optional see-through ring (a hole) and an arm
    that touches the left edge."""

    def ghost(h=1400, w=1100, touch_border=False, ring=False):
        m = np.zeros((h, w), np.uint8)
        cv2.ellipse(m, (w // 2, 450), (220, 260), 0, 0, 360, 255, -1)  # head/body
        cv2.rectangle(m, (w // 2 - 160, 450), (w // 2 + 160, 1200), 255, -1)  # robe
        if ring:
            cv2.circle(m, (w // 2, 700), 90, 0, -1)  # translucent hole
        if touch_border:
            cv2.rectangle(m, (0, 600), (w // 2, 680), 255, -1)  # arm to the left edge
        return m

    return ghost


@pytest.fixture
def rgb_like():
    """Returns ``rgb_like(mask)``, which makes a grey picture of a mask: the figure
    darker than the paper."""

    def rgb_like(m):
        return np.dstack([255 - m // 2] * 3).astype(np.uint8)

    return rgb_like


@pytest.fixture
def params():
    """Returns ``params(**fields)``, which makes the layout parameters of a one-sided
    mini with the default figure settings, with ``fields`` changed."""
    from dataclasses import replace

    from papermini.project.figure_settings import FigureSettings

    def params(**fields):
        return replace(FigureSettings(double_sided=False).params(), **fields)

    return params


@pytest.fixture
def mask_options():
    """Returns ``mask_options(**fields)``, which makes the background-removal options
    of the default figure settings, with ``fields`` changed."""
    from dataclasses import replace

    from papermini.project.figure_settings import FigureSettings

    def mask_options(**fields):
        return replace(FigureSettings().mask_options(), **fields)

    return mask_options


@pytest.fixture
def pipeline_mini(pipeline, params, mask_options):
    """Returns ``pipeline_mini(image, prm, mask, **arguments)``, which builds the mini
    of ``image`` with the ``pipeline`` fixture's ``MiniBuilder`` and logs nothing.
    ``prm`` and ``mask`` default to ``params()`` and ``mask_options()``, and every other
    argument not given comes from the default figure settings."""
    from papermini.project.figure_settings import FigureSettings

    def pipeline_mini(image, prm=None, mask=None, **arguments):
        s = FigureSettings()
        defaults: dict[str, Any] = {
            "label": s.label,
            "back_text": s.back_text,
            "tab_front": s.tab_front,
            "tab_back": s.tab_back,
            "dpi": s.dpi,
            "simplify_mm": s.simplify_mm,
            "smooth_path": not s.no_smooth,
            "bleed_mm": 0.0,
            "adjust": s.adjustments(),
            "style": s.style(),
            "log": lambda *_: None,
        }
        return pipeline.minis.make(
            image,
            params() if prm is None else prm,
            mask_options() if mask is None else mask,
            **(defaults | arguments),
        )

    return pipeline_mini


# endregion
