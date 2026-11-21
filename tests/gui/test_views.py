"""Tests of the source, crop and paper views."""

from dataclasses import replace

import cv2
import numpy as np
import pytest
from PIL import Image

pytest.importorskip("PySide6")

from papermini.project.figure_settings import FigureSettings

pytestmark = pytest.mark.usefixtures("fake_default_model")


def test_a_crop_box_is_drawn_resized_moved_and_cleared(app):
    """Draw a crop box, then resize it by a corner handle, move it, and clear it."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest

    from papermini.gui.views.crop_view import CropView

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

    def cursor_at(x, y):  # the cursor shown over image px (x, y)
        QTest.mouseMove(vp, at(x, y))
        return vp.cursor().shape()

    drag(at(200, 200), at(600, 700))  # draw
    assert got[-1] == pytest.approx([0.2, 0.2, 0.6, 0.7], abs=0.01)
    assert cursor_at(600, 700) == Qt.CursorShape.SizeFDiagCursor  # a corner handle
    assert cursor_at(400, 450) == Qt.CursorShape.SizeAllCursor  # inside: move it
    assert cursor_at(200, 450) == Qt.CursorShape.SizeHorCursor  # the left edge
    assert cursor_at(900, 900) == Qt.CursorShape.CrossCursor  # outside: a new box

    drag(at(600, 700), at(800, 900))  # resize by the bottom-right handle
    assert got[-1] == pytest.approx([0.2, 0.2, 0.8, 0.9], abs=0.01)

    drag(at(400, 400), at(300, 350))  # move from inside
    assert got[-1] == pytest.approx([0.1, 0.15, 0.7, 0.85], abs=0.01)

    drag(at(500, 500), at(2000, 2000))  # move is clamped to the image
    assert got[-1][2] == pytest.approx(1.0) and got[-1][3] == pytest.approx(1.0)

    n = len(got)
    QTest.mouseClick(
        vp, Qt.LeftButton, Qt.NoModifier, at(50, 50)
    )  # a click keeps the box
    assert len(got) == n and v.crop_box() is not None

    QTest.keyClick(v, Qt.Key_Delete)  # Delete clears it
    assert got[-1] is None and v.crop_box() is None
    v.close()


def test_the_paper_has_no_graphics_effect(app):
    """Regression: QGraphicsDropShadowEffect re-rendered the whole paper at the current
    zoom on every repaint, so the canvas took seconds per frame when zoomed in far."""
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QGraphicsScene

    from papermini.gui.views.drawing import _paper
    from papermini.gui.views.paper_item import PaperItem

    sc = QGraphicsScene()
    item = _paper(sc, QRectF(0, 0, 50, 70))
    assert isinstance(item, PaperItem)
    assert all(it.graphicsEffect() is None for it in sc.items())
    assert item.boundingRect().contains(QRectF(-1, -1, 52, 72))  # room for the shadow


def test_the_source_image_lies_on_shadowed_paper(app):
    """The Source view shows the image on the same shadowed paper as the Miniature
    and Print sheet views (painted by the item, not a graphics effect)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage

    from papermini.gui.views.crop_view import CropView
    from papermini.gui.views.paper_item import PaperItem

    v = CropView()
    img = QImage(400, 300, QImage.Format_RGB32)
    img.fill(0x808080)
    v.set_image(img)
    paper = [it for it in v.scene().items() if isinstance(it, PaperItem)]
    assert len(paper) == 1 and paper[0].rect() == QRectF(0, 0, 400, 300)
    assert paper[0].zValue() < 0  # under the image
    assert paper[0].boundingRect().contains(QRectF(-10, -10, 420, 320))
    assert all(it.graphicsEffect() is None for it in v.scene().items())
    v.set_image(None)
    assert not v.scene().items()


def test_source_view_shows_a_large_high_dpi_scan(app, tmp_path):
    """A scan too large for Qt's default image reading limit shows in the Source
    view. The reader refused it, and the view stayed empty."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    from papermini.gui.views.crop_view import CropView
    from papermini.gui.views.images import load_qimage

    side = 8200  # read as 4 bytes per pixel: just over Qt's default 256 MB limit
    assert side * side * 4 > 256 * 2**20
    Image.new("RGB", (side, side), (200, 40, 40)).save(
        tmp_path / "scan.png", dpi=(1200, 1200)
    )
    v = CropView()
    v.setAttribute(Qt.WA_DontShowOnScreen)
    v.resize(500, 400)
    v.show()
    v.set_image(load_qimage(tmp_path / "scan.png"))
    app.processEvents()
    v.fit()
    assert v.picture_size() == (side, side)
    shot = v.viewport().grab().toImage()
    assert shot.pixelColor(shot.rect().center()) == QColor(200, 40, 40)


def test_source_view_shows_the_detected_outline(
    app, tmp_path, new_window, wait, crop_view_marks
):
    """Step 1 shows what background removal found, without the margin and tab of the
    miniature, and forgets it when another image is shown."""
    from papermini.gui.views.images import load_qimage

    im = np.full((900, 700, 3), 255, np.uint8)
    cv2.ellipse(im, (350, 450), (200, 300), 0, 0, 360, (60, 60, 60), -1)
    Image.fromarray(im).save(tmp_path / "a.png")
    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "b.png")
    w = new_window()
    assert [w.tabs.tabText(i) for i in range(w.tabs.count())] == [
        "Source",
        "Miniature",
        "Print sheet",
    ]
    assert w.tabs.currentIndex() == w.SOURCE  # the first step
    assert [b.text() for b in w.views.group.buttons()] == [
        "1  Source",
        "2  Miniature",
        "3  Print sheet",
    ]
    w.add_images([tmp_path / "a.png"], FigureSettings(margin_mm=5))
    fig = w.current()
    assert wait(lambda: fig.up_to_date), fig.error
    cv = w.crop_view
    shade, line = crop_view_marks(cv)
    assert shade.scene() is cv.scene()
    r = line.path().boundingRect()  # the ellipse itself: no margin
    assert abs(r.left() - 150) < 3 and abs(r.top() - 150) < 3
    assert abs(r.right() - 551) < 3 and abs(r.bottom() - 751) < 3

    cv.refresh_theme()  # redrawn, not duplicated
    assert len(crop_view_marks(cv)) == 2
    cv.set_busy(True)  # a model runs: dimmed, no outline
    assert len(crop_view_marks(cv)) == 1
    cv.set_busy(False)
    cv.set_image(load_qimage(tmp_path / "b.png"))  # another image: no stale outline
    assert crop_view_marks(cv) == []


def _crop_view(app, size=(400, 300)):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    from papermini.gui.views.crop_view import CropView

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
    t = {
        "press": QEvent.MouseButtonPress,
        "move": QEvent.MouseMove,
        "release": QEvent.MouseButtonRelease,
    }[kind]
    b = Qt.LeftButton if kind != "move" else Qt.NoButton
    held = Qt.LeftButton if (kind == "move" and button) else Qt.NoButton
    if kind == "press":
        held = Qt.LeftButton
    ev = QMouseEvent(t, pos, v.viewport().mapToGlobal(pos), b, held, Qt.NoModifier)
    {
        "press": v.mousePressEvent,
        "move": v.mouseMoveEvent,
        "release": v.mouseReleaseEvent,
    }[kind](ev)


def test_crop_view_guides_the_user(app):
    """Without a crop box a hint says to drag one; over the image, guide lines show
    where a new box would start; over the box, the part a drag grabs is shown."""
    from PySide6.QtCore import QRectF, Qt

    v = _crop_view(app)
    cursor = lambda: v.viewport().cursor().shape()
    assert v.show_hint()  # no box yet: say how...
    img = QRectF(v.mapFromScene(v.sceneRect()).boundingRect())
    pill = v.hint_rect()  # ...beside the image, not on it
    assert not pill.intersects(img) and v.viewport().rect().contains(pill.toRect())
    plain = v.grab().toImage()
    _mouse(v, "move", (200, 150))
    assert cursor() == Qt.CursorShape.CrossCursor
    assert v.grab().toImage() != plain  # guide lines through the mouse
    v.set_crop([0.25, 0.25, 0.75, 0.75])
    assert not v.show_hint()  # a box: no hint
    _mouse(v, "move", (200, 150))
    assert cursor() == Qt.CursorShape.SizeAllCursor  # inside: move the whole box
    _mouse(v, "move", (100, 150))
    assert cursor() == Qt.CursorShape.SizeHorCursor  # on the left edge
    _mouse(v, "move", (100, 75))
    assert cursor() == Qt.CursorShape.SizeFDiagCursor  # on a corner handle
    lit = v.grab().toImage()
    v.leaveEvent(None)
    untouched = _crop_view(app)
    untouched.set_crop([0.25, 0.25, 0.75, 0.75])
    left = v.grab().toImage()
    assert left != lit and left == untouched.grab().toImage()  # nothing lit any more
    untouched.close()


def test_a_click_on_the_crop_view_changes_nothing(app):
    """A click (or a press that barely moves) never draws, moves or clears a box, so it
    never starts a model run by accident; a real drag does."""
    v = _crop_view(app)
    got = []
    v.cropChanged.connect(got.append)
    _mouse(v, "press", (200, 150))
    _mouse(v, "release", (200, 150))
    assert got == [] and v.crop_box() is None  # a click: no box
    v.set_crop([0.25, 0.25, 0.75, 0.75])
    box = v.crop_box()
    s = 1 / v.transform().m11()  # scene units per screen px
    _mouse(v, "press", (200, 150))  # inside: would move it...
    _mouse(v, "move", (200 + 2 * s, 150), button=True)  # ...but 2 px is a jitter
    _mouse(v, "release", (200 + 2 * s, 150))
    assert got == [] and v.crop_box() == box
    _mouse(v, "press", (200, 150))
    _mouse(v, "move", (230, 150), button=True)  # a real drag moves it
    _mouse(v, "release", (230, 150))
    moved = v.crop_box()  # (to a whole screen pixel)
    assert len(got) == 1 and abs(moved.left() - box.left() - 30) < 2 * s
    assert moved.size() == box.size() and moved.top() == box.top()


def test_crop_changes_can_be_undone_and_cleared(app, tmp_path, new_window):
    """Ctrl+Z puts the crop back as it was (also for another figure); the Clear crop
    button on the canvas removes it, and shows only on the Source view with a crop."""

    for n in "ab":
        Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / f"{n}.png")
    w = new_window()
    w.add_images([tmp_path / "a.png", tmp_path / "b.png"])
    a, b = w.figures
    w.list.setCurrentRow(0)
    assert not w.clear_crop_card.isVisibleTo(w)
    w.crop_view.cropChanged.emit([0.1, 0.1, 0.9, 0.9])
    w.crop_view.cropChanged.emit([0.2, 0.2, 0.8, 0.8])
    assert a.entry.settings.crop == [0.2, 0.2, 0.8, 0.8]
    assert w.clear_crop_card.isVisibleTo(w)
    w.tabs.setCurrentIndex(w.MINI)  # only on the Source view
    assert not w.clear_crop_card.isVisibleTo(w)
    w.tabs.setCurrentIndex(w.SOURCE)
    w.list.setCurrentRow(1)
    w.btn_clear_crop.click()  # nothing to clear on b...
    assert b.entry.settings.crop is None
    w.list.setCurrentRow(0)
    w.btn_clear_crop.click()  # ...on a it clears the box
    assert a.entry.settings.crop is None and not w.clear_crop_card.isVisibleTo(w)
    w.list.setCurrentRow(1)
    w.a_undo_crop.trigger()  # back on a, as it was
    assert w.current() is a and a.entry.settings.crop == [0.2, 0.2, 0.8, 0.8]
    assert w.crop_view.crop_box() is not None
    w.a_undo_crop.trigger()
    assert a.entry.settings.crop == [0.1, 0.1, 0.9, 0.9]
    w.a_undo_crop.trigger()
    assert a.entry.settings.crop is None
    w.a_undo_crop.trigger()  # nothing left: no change
    assert a.entry.settings.crop is None


def test_the_source_view_explains_its_marks_in_a_legend(app, tmp_path, new_window):
    """The Source view explains its marks (outline, faded background, crop box) in a
    legend, only there and only with an image. Its texts never change, crop box or
    not. It lets the mouse through to the crop handles under it."""
    from PySide6.QtCore import Qt

    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "a.png")
    w = new_window()
    legend = w.legend
    assert not w.legend_box.isVisibleTo(w)  # no image yet
    w.add_images([tmp_path / "a.png"])
    assert w.legend_box.isVisibleTo(w)
    texts = ["Detected outline", "Removed background", "Crop area"]
    assert [t.text() for t in legend.texts] == texts
    assert all(not sw.pixmap().isNull() for sw in legend.swatches)
    assert legend.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert w.legend_box.testAttribute(Qt.WA_TransparentForMouseEvents)
    w.crop_view.cropChanged.emit([0.1, 0.1, 0.9, 0.9])  # a crop box drawn
    assert [t.text() for t in legend.texts] == texts  # the same words
    w.tabs.setCurrentIndex(w.MINI)  # only on the Source view
    assert not w.legend_box.isVisibleTo(w)
    w.tabs.setCurrentIndex(w.SOURCE)
    assert w.legend_box.isVisibleTo(w)
    w.panel.changed.emit(replace(w.current().entry.settings, crop=None))
    assert [t.text() for t in legend.texts] == texts
