"""Tests of printing and exporting from the app."""

import pytest
from PIL import Image

pytest.importorskip("PySide6")


pytestmark = pytest.mark.usefixtures("fake_default_model")


def test_the_print_is_true_to_size_and_follows_the_page_range(app, square_mini):
    """The printed sheet must be exactly to scale: its 50 mm bar is 50 mm on paper."""
    from PySide6.QtGui import QColor, QImage

    from papermini.gui.views.drawing import print_sheet
    from papermini.output.sheet import pack

    class ImagePrinter(QImage):  # a "printer" that prints onto an image, 100 dpi
        def __init__(self, first=0, last=0):
            super().__init__(
                round(210 / 25.4 * 100), round(297 / 25.4 * 100), QImage.Format_RGB32
            )
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

    m = square_mini("m")
    lay = pack([(m, 30)], "a4", 12, 7)
    assert lay.pages > 1
    pr = ImagePrinter()
    assert print_sheet(pr, lay, "test") == lay.pages == pr.pages
    k = 100 / 25.4
    y = round((12 + lay.header_mm - 4) * k)  # the scale bar's row
    dark = [x for x in range(pr.width()) if QColor(pr.pixel(x, y)).lightness() < 100]
    end = next(
        a for a, b in zip(dark, dark[1:] + [None]) if b != a + 1
    )  # the bar alone,
    assert (
        abs(dark[0] - 12 * k) <= 2 and abs(end - 62 * k) <= 2
    )  # not the "50 mm" next to it
    assert QColor(pr.pixel(2, 2)).lightness() > 250  # white paper from the very corner

    pr = ImagePrinter(2, 2)  # "pages 2 to 2" in the dialog
    assert print_sheet(pr, lay, "test") == 1 and pr.pages == 1


def test_the_print_button_prints_the_sheet(
    app, tmp_path, monkeypatch, new_window, wait
):
    from PySide6.QtPrintSupport import QPrinter

    from papermini.gui.window.main_window import MainWindow

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
    w = new_window()
    w.add_images([tmp_path / "hero.png"])
    w.tabs.setCurrentIndex(w.SHEET)
    assert w.sheet_panel.print_btn.isVisibleTo(w.sheet_panel)
    w.sheet_panel.print_btn.click()  # builds first if needed, then prints
    assert wait(lambda: out.exists() and out.stat().st_size > 1000)
    from PySide6.QtGui import QPageSize

    assert seen == [(True, QPageSize.A4, 1)]  # true size on the sheet's paper
    assert out.read_bytes().startswith(b"%PDF")


def test_the_export_dialog_writes_only_the_ticked_files(app, prefs, tmp_path):
    """The Export dialog shows the files it writes (named after the sheet's title),
    writes only what is ticked, and remembers the ticks."""
    from PySide6.QtWidgets import QDialog

    from papermini.gui.dialogs.export_dialog import ExportDialog

    d = ExportDialog(prefs, tmp_path, "My minis", pages=3, machine=True)
    assert d.pdf_path() == tmp_path / "My minis.pdf"
    assert [p.name for p in d.cut_paths()] == [
        "My minis-cut.svg",
        "My minis-cut-2.svg",
        "My minis-cut-3.svg",
    ]
    assert (
        "My minis-cut-3.svg" in d.cut_files.text()
        and d.pdf_files.text() == "My minis.pdf"
    )
    d.pdf.setChecked(False)  # only the cut file, after printing from the app
    assert d.chosen() == d.cut_paths()
    d.cut.setChecked(False)
    assert d.chosen() == [] and not d.export_btn.isEnabled()
    d.cut.setChecked(True)
    d.export_btn.click()
    assert d.result() == QDialog.Accepted
    again = ExportDialog(prefs, tmp_path, "My minis", pages=1, machine=True)
    assert not again.pdf.isChecked() and again.cut.isChecked()  # remembered
    hand = ExportDialog(prefs, tmp_path, "My minis", pages=1, machine=False)
    hand.pdf.setChecked(True)
    assert hand.chosen() == [tmp_path / "My minis.pdf"]  # cut by hand: no cut file
    assert not hand.cut.isVisibleTo(hand)


def test_the_print_sets_the_paper_size_and_orientation(
    app, tmp_path, monkeypatch, new_window, wait
):
    from PySide6.QtGui import QPageLayout

    from papermini.gui.window.main_window import MainWindow
    from papermini.project.sheet_settings import SheetSettings

    Image.new("RGBA", (300, 450), (200, 40, 30, 255)).save(tmp_path / "hero.png")
    seen = []

    def fake_dialog(self, printer, pages):
        r = printer.pageLayout().fullRect(QPageLayout.Millimeter)
        seen.append((round(r.width()), round(r.height())))
        return False

    monkeypatch.setattr(MainWindow, "_print_dialog", fake_dialog)
    w = new_window()
    w.add_images([tmp_path / "hero.png"])
    assert wait(lambda: w.figures[0].mini is not None and w.figures[0].up_to_date)
    for sheet in (
        SheetSettings(paper="a3", orientation="landscape"),
        SheetSettings(paper="tabloid"),
        SheetSettings(paper="custom", paper_width_mm=300, paper_height_mm=200),
    ):
        w.sheet_panel.changed.emit(sheet)
        w.print_sheet()
    assert seen == [(420, 297), (279, 432), (300, 200)]


def test_an_export_waits_for_a_running_build(app, built_window, monkeypatch, wait):
    from dataclasses import replace

    from PySide6.QtWidgets import QFileDialog

    fig = built_window.current()
    built_window.panel.changed.emit(replace(fig.entry.settings, height_mm=30))
    app.processEvents()
    assert not fig.up_to_date
    done = []
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *a: done.append(fig.mini.figure_height_mm) or ("", "")),
    )
    built_window.export_current()
    assert wait(lambda: done)
    assert done[0] == pytest.approx(30, abs=0.05)
