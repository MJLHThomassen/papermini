"""Tests of adding images and of the figure cards."""

import pytest
from PIL import Image

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

pytestmark = pytest.mark.usefixtures("fake_default_model")


def test_images_are_added_from_links_paste_and_browser_drops(
    images_from_web, app, monkeypatch, tmp_path, new_window, wait, fake_web
):
    import io
    from pathlib import Path

    from PySide6.QtCore import QMimeData, QUrl

    from papermini.gui.window import main_window
    from papermini.gui.window.main_window import MainWindow

    buf = io.BytesIO()
    Image.new("RGBA", (200, 300), (200, 40, 30, 255)).save(buf, "WEBP")
    fake_web["https://example.com/img/goblin.webp"] = buf.getvalue()
    warned = []
    monkeypatch.setattr(
        main_window.QMessageBox, "warning", lambda *a: warned.append(a[2])
    )
    w = new_window()
    url = "https://example.com/img/goblin.webp"
    w.add_links([url])  # downloads in the background
    assert wait(lambda: len(w.figures) == 1)
    fig = w.figures[0]
    assert fig.entry.source == url and fig.entry.image == images_from_web.cached_image(
        url
    )
    assert w.list.item(0).toolTip() == url and w.list.item(0).text() == "goblin"

    w.add_links(["https://example.com/gone.png"])
    assert wait(lambda: warned)
    assert "404" in warned[0] and len(w.figures) == 1

    # a picture copied in a browser: the HTML has the image's own address, while the
    # URL is often the page it links to; the image address wins
    mime = QMimeData()
    mime.setHtml(f'<a href="https://example.com/page"><img alt="g" src="{url}"></a>')
    mime.setUrls(
        [
            QUrl("https://example.com/page"),
            QUrl.fromLocalFile(str(tmp_path / "a.png")),
        ]
    )
    files, links = MainWindow._sources(mime)
    assert links == [url] and [Path(f) for f in files] == [tmp_path / "a.png"]

    n = len(fake_web.asked)
    QApplication.clipboard().setText(url)
    w.paste()  # Ctrl+V outside a text field
    assert (
        len(w.figures) == 2 and len(fake_web.asked) == n
    )  # second time from the cache


def test_an_image_that_cannot_be_cached_ends_its_download_with_a_warning(
    images_from_web, app, monkeypatch, new_window, wait, fake_web
):
    import io

    from papermini.gui.window import main_window

    buf = io.BytesIO()
    Image.new("RGB", (20, 30)).save(buf, "PNG")
    url = "https://example.com/goblin.png"
    fake_web[url] = buf.getvalue()
    # a file where the folder of downloaded images should be
    images_from_web.folder().write_text("", encoding="utf-8")
    warned = []
    monkeypatch.setattr(
        main_window.QMessageBox, "warning", lambda *a: warned.append(a[2])
    )
    w = new_window()
    w.add_links([url])
    assert wait(lambda: warned, 30)
    assert warned[0].startswith("Could not add the image.") and not w.figures
    assert w.statusBar().currentMessage() == "Could not add the image"


def test_a_link_pasted_in_the_link_bar_is_added(app, monkeypatch, new_window):
    """Paste a link in the bar above the figures and press Enter (or Add) to add it.
    The add-images button sits in the figure list, not in the header."""
    from PySide6.QtWidgets import QFrame, QToolButton

    w = new_window()
    header_tips = [
        b.toolTip() for b in w.findChild(QFrame, "Header").findChildren(QToolButton)
    ]
    assert not any("Add images" in t for t in header_tips)
    left = w.splitter.widget(0)
    assert any("Add images" in b.toolTip() for b in left.findChildren(QToolButton))
    assert w.link_edit.parent() is left and not w.link_add.isEnabled()
    lay = left.layout()
    row = [
        i
        for i in range(lay.count())
        if lay.itemAt(i).layout() and lay.itemAt(i).layout().indexOf(w.link_edit) >= 0
    ]
    assert row and row[0] < lay.indexOf(w.list)  # right above the list

    added = []
    monkeypatch.setattr(w, "add_links", lambda links, *a: added.append(links))
    url = "https://example.com/art/goblin.webp"
    w.link_edit.setText(f"  {url} ")
    assert w.link_add.isEnabled()
    w.link_edit.returnPressed.emit()
    assert added == [[url]] and w.link_edit.text() == ""

    w.link_edit.setText("goblin.webp")  # not a link: kept, nothing added
    w.link_add.click()
    assert added == [[url]] and w.link_edit.text() == "goblin.webp"
    assert "not a link" in w.statusBar().currentMessage()

    w.link_edit.clear()
    QApplication.clipboard().setText(url)
    w.set_side_visible(0, False)
    w.a_add_link.trigger()  # Ctrl+L: shows the list, fills in the link
    assert w.side_visible(0) and w.link_edit.text() == url
    w.empty.link_button.click()  # the start card's link does the same
    assert w.link_edit.text() == url


def click_copies(w, row: int, which: str, times: int = 1):
    """Click - or + of the copies control on a figure's card."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    lst = w.list
    minus, _, plus = lst.itemDelegate().copies_rects(lst.visualItemRect(lst.item(row)))
    at = (plus if which == "+" else minus).center().toPoint()
    for _ in range(times):
        QTest.mouseClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier, at)


def test_the_figure_card_changes_the_copies(app, tmp_path, new_window, unsaved):
    """Each card has "Amount - n +": - and + change the copies, a click on the number
    types one; never below 0, and nothing rebuilds."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QSpinBox

    from papermini.gui.widgets.figure_delegate import COPIES_ROLE

    Image.new("RGB", (300, 400), (255, 255, 255)).save(tmp_path / "a.png")
    w = new_window()
    w.resize(1300, 800)
    w.show()
    w.add_images([tmp_path / "a.png"])
    fig = w.figures[0]
    app.processEvents()
    click_copies(w, 0, "+", 3)
    assert fig.entry.settings.copies == 4 and w.list.item(0).data(COPIES_ROLE) == 4
    assert unsaved(w)
    click_copies(w, 0, "-", 9)
    assert fig.entry.settings.copies == 0  # (not below 0)
    lst = w.list
    _, num, _ = lst.itemDelegate().copies_rects(lst.visualItemRect(lst.item(0)))
    QTest.mouseClick(
        lst.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        num.center().toPoint(),
    )
    app.processEvents()
    box = next(b for b in lst.findChildren(QSpinBox) if b.isVisible())
    QTest.keyClicks(box, "12")
    QTest.keyClick(box, Qt.Key.Key_Return)
    app.processEvents()
    assert fig.entry.settings.copies == 12
    # an edit in the panel keeps the copies set on the card
    w.panel.field("margin_mm").setValue(2.0)
    assert fig.entry.settings.copies == 12 and fig.entry.settings.margin_mm == 2.0


def test_changing_the_copies_keeps_the_built_mini(app, built_window):
    """The copies only change the sheet: the figure keeps its mini and doesn't rebuild."""
    fig = built_window.current()
    mini = fig.mini
    click_copies(built_window, 0, "+", 2)
    assert fig.entry.settings.copies == 3
    app.processEvents()
    assert fig.up_to_date and fig.mini is mini
