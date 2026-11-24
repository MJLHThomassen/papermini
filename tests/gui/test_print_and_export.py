"""Tests of printing and exporting from the app."""

import sys

import pytest
from PIL import Image

pytest.importorskip("PySide6")

from papermini.gui.step import Step

pytestmark = pytest.mark.usefixtures("fake_default_model")


def test_the_print_is_true_to_size_and_follows_the_page_range(
    output, fonts, app, square_mini
):
    """The printed sheet must be exactly to scale: its calibration bar is as long on
    paper as its label says."""
    from PySide6.QtGui import QColor, QImage

    from papermini.gui.views.drawing import print_sheet
    from papermini.output.sheet_layout import BAR_ABOVE_MM, BAR_MM

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
    lay = output.packer.pack([(m, 30)], "a4", 12, 7)
    assert lay.pages > 1
    pr = ImagePrinter()
    assert print_sheet(pr, lay, "test", fonts) == lay.pages == pr.pages
    k = 100 / 25.4
    y = round((12 + lay.header_mm - BAR_ABOVE_MM) * k)  # the scale bar's row
    dark = [x for x in range(pr.width()) if QColor(pr.pixel(x, y)).lightness() < 100]
    end = next(
        a for a, b in zip(dark, dark[1:] + [None]) if b != a + 1
    )  # the bar alone,
    assert (
        abs(dark[0] - 12 * k) <= 2 and abs(end - (12 + BAR_MM) * k) <= 2
    )  # not the "50 mm" next to it
    assert QColor(pr.pixel(2, 2)).lightness() > 250  # white paper from the very corner

    pr = ImagePrinter(2, 2)  # "pages 2 to 2" in the dialog
    assert print_sheet(pr, lay, "test", fonts) == 1 and pr.pages == 1


def test_the_print_button_prints_the_sheet(
    app, tmp_path, monkeypatch, new_window, wait
):
    from PySide6.QtPrintSupport import QPrinter

    from papermini.gui.exporting.export_dialogs import ExportDialogs

    im = Image.new("RGBA", (300, 450), (0, 0, 0, 0))
    from PIL import ImageDraw

    ImageDraw.Draw(im).ellipse((30, 30, 270, 420), fill=(200, 40, 30, 255))
    im.save(tmp_path / "hero.png")
    out = tmp_path / "printed.pdf"
    seen = []

    def fake_dialog(self, parent, printer, pages):  # instead of the print dialog
        seen.append((printer.fullPage(), printer.pageLayout().pageSize().id(), pages))
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(out))
        return True

    monkeypatch.setattr(ExportDialogs, "print_options", fake_dialog)
    w = new_window()
    w.add_images([tmp_path / "hero.png"])
    w.tabs.setCurrentIndex(Step.SHEET)
    assert w.sheet_panel.print_btn.isVisibleTo(w.sheet_panel)
    w.sheet_panel.print_btn.click()  # builds first if needed, then prints
    assert wait(lambda: out.exists() and out.stat().st_size > 1000)
    from PySide6.QtGui import QPageSize

    assert seen == [(True, QPageSize.A4, 1)]  # true size on the sheet's paper
    assert out.read_bytes().startswith(b"%PDF")


def test_the_export_dialog_writes_only_the_ticked_files(app, prefs, output, tmp_path):
    """The Export dialog shows the files it writes (named after the sheet's title),
    writes only what is ticked, and remembers the ticks."""
    from PySide6.QtWidgets import QDialog

    from papermini.gui.dialogs.export_dialog import ExportDialog

    d = ExportDialog(
        prefs, output.cut_files, tmp_path, "My minis", pages=3, machine=True
    )
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
    again = ExportDialog(
        prefs, output.cut_files, tmp_path, "My minis", pages=1, machine=True
    )
    assert not again.pdf.isChecked() and again.cut.isChecked()  # remembered
    hand = ExportDialog(
        prefs, output.cut_files, tmp_path, "My minis", pages=1, machine=False
    )
    hand.pdf.setChecked(True)
    assert hand.chosen() == [tmp_path / "My minis.pdf"]  # cut by hand: no cut file
    assert not hand.cut.isVisibleTo(hand)


def test_the_print_sets_the_paper_size_and_orientation(
    app, tmp_path, monkeypatch, new_window, wait
):
    from PySide6.QtGui import QPageLayout

    from papermini.gui.exporting.export_dialogs import ExportDialogs
    from papermini.project.sheet_settings import SheetSettings

    Image.new("RGBA", (300, 450), (200, 40, 30, 255)).save(tmp_path / "hero.png")
    seen = []

    def fake_dialog(self, parent, printer, pages):
        r = printer.pageLayout().fullRect(QPageLayout.Millimeter)
        seen.append((round(r.width()), round(r.height())))
        return False

    monkeypatch.setattr(ExportDialogs, "print_options", fake_dialog)
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


# region every export and print path
SVG_FILTER = "SVG, to print or cut (*.svg)"
PNG_FILTER = "PNG, for a virtual tabletop (*.png)"


class Modal:
    """Stands in for the modal dialogs of exporting and printing. It records what
    each dialog shows and gives the answer set for it. A dialog without an answer is
    cancelled, and a question without one is answered No."""

    def __init__(self):
        self.warnings: list[str] = []
        self.questions: list[str] = []
        self.yes = False  # the answer to every yes or no question
        self.save_as: tuple[str, str] | None = None  # (path, filter) to save as
        self.folder: str | None = None  # the folder to pick
        self.file_dialogs: list[tuple] = []
        self.format: str | None = None  # the button to click in the format question
        self.format_boxes: list[tuple] = []
        self.export = None  # fill(dialog) for the Export dialog; True exports
        self.export_dialogs: list[dict] = []
        self.print = None  # fill(dialog) for the print dialog; True prints
        self.print_dialogs: list[dict] = []


@pytest.fixture
def modal(app, monkeypatch):
    """Replaces the modal dialogs of exporting and printing with a ``Modal``."""
    from PySide6.QtGui import QPageLayout
    from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog
    from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

    from papermini.gui.dialogs.export_dialog import ExportDialog

    m = Modal()

    def warning(parent, title, text, *a, **k):
        m.warnings.append(text)
        return QMessageBox.StandardButton.Ok

    def question(parent, title, text, *a, **k):
        m.questions.append(text)
        return (
            QMessageBox.StandardButton.Yes if m.yes else QMessageBox.StandardButton.No
        )

    def save_file(parent, caption, start, filters, *a, **k):
        m.file_dialogs.append(("save", caption, start, filters))
        return m.save_as or ("", "")

    def folder(parent, caption, start, *a, **k):
        m.file_dialogs.append(("folder", caption, start))
        return m.folder or ""

    def ask(box):
        texts = {b.text().replace("&", ""): b for b in box.buttons()}
        m.format_boxes.append((box.windowTitle(), box.text(), sorted(texts)))
        texts[m.format or "Cancel"].click()
        return box.result()

    def export(dlg):
        m.export_dialogs.append(
            {
                "folder": dlg.folder.text(),
                "name": dlg.name.text(),
                "machine": dlg.cut.isVisibleTo(dlg),
            }
        )
        ok = m.export is not None and m.export(dlg)
        return QDialog.DialogCode.Accepted if ok else QDialog.DialogCode.Rejected

    def print_dialog(dlg):
        p = dlg.printer()
        size = p.pageLayout().pageSize()
        m.print_dialogs.append(
            {
                "title": dlg.windowTitle(),
                "pages": (dlg.minPage(), dlg.maxPage()),
                "page_range": dlg.testOption(
                    QAbstractPrintDialog.PrintDialogOption.PrintPageRange
                ),
                "doc": p.docName(),
                "full_page": p.fullPage(),
                "from_to": (p.fromPage(), p.toPage()),
                "paper": size.id(),
                "landscape": p.pageLayout().orientation()
                == QPageLayout.Orientation.Landscape,
            }
        )
        ok = m.print is not None and m.print(dlg)
        return QDialog.DialogCode.Accepted if ok else QDialog.DialogCode.Rejected

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(warning))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    monkeypatch.setattr(QMessageBox, "exec", ask)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(save_file))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(folder))
    monkeypatch.setattr(ExportDialog, "exec", export)
    monkeypatch.setattr(QPrintDialog, "exec", print_dialog)
    return m


def _status(w) -> str:
    return w.statusBar().currentMessage()


def _export_to(folder, pdf=True, cut=False):
    """Returns a fill for the Export dialog that exports as "sheet" to ``folder``."""

    def fill(dlg):
        dlg.folder.setText(str(folder))
        dlg.name.setText("sheet")
        dlg.pdf.setChecked(pdf)
        dlg.cut.setChecked(cut)
        return True

    return fill


def _print_to(pdf, paper=None):
    """Returns a fill for the print dialog that prints into the PDF file ``pdf``, on
    the printer's paper or on ``paper``."""
    from PySide6.QtGui import QPageSize
    from PySide6.QtPrintSupport import QPrinter

    def fill(dlg):
        p = dlg.printer()
        p.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        p.setOutputFileName(str(pdf))
        if paper is not None:
            p.setPageSize(QPageSize(paper))
        return True

    return fill


def _add_big_figure(w, wait, height_mm=150):
    """Adds a second figure, labelled Big and ``height_mm`` high, to the window
    ``w``."""
    from dataclasses import replace

    w.add_images([w.figures[0].entry.image])
    big = w.figures[-1]
    big.entry.settings = replace(
        big.entry.settings, height_mm=height_mm, dpi=100, label="Big"
    )
    assert wait(lambda: all(f.up_to_date for f in w.figures))


def test_with_no_figures_the_export_and_print_actions_do_nothing(window, modal):
    for action in (window.a_svg, window.a_svgs, window.a_pdf, window.a_print):
        action.trigger()
    assert modal.file_dialogs == modal.format_boxes == []
    assert modal.export_dialogs == modal.print_dialogs == []
    assert _status(window) == ""


def test_a_cancelled_export_writes_nothing(built_window, modal, tmp_path):
    """Export opens the save dialog at the figure's name next to its image."""
    w = built_window
    before, files = _status(w), set(tmp_path.iterdir())
    w.export_current()
    assert modal.file_dialogs == [
        ("save", "Export", str(tmp_path / "hero.svg"), f"{SVG_FILTER};;{PNG_FILTER}")
    ]
    assert set(tmp_path.iterdir()) == files and _status(w) == before


def test_an_export_reports_the_files_it_saved(built_window, modal, tmp_path, wait):
    from dataclasses import replace

    w = built_window
    out = tmp_path / "out"
    modal.save_as = (str(out / "a.svg"), SVG_FILTER)
    w.export_current()
    assert _status(w) == f"Saved {out / 'a.svg'}"
    fig = w.current()
    fig.entry.settings = replace(fig.entry.settings, tab_front="number", copies=2)
    modal.save_as = (str(out / "b"), PNG_FILTER)
    w.export_current()  # (rebuilds first)
    assert wait(lambda: "PNGs" in _status(w))
    assert _status(w) == f"Saved 2 PNGs, one per numbered copy, to {out}"
    assert sorted(p.name for p in out.iterdir()) == ["a.svg", "b-1.png", "b-2.png"]


def test_a_failed_write_shows_the_error(built_window, modal, tmp_path):
    """Export, Export all and Export sheet show the error of a file they cannot
    write, and report no saved files."""
    w = built_window
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the folder should be")
    before = _status(w)
    modal.save_as = (str(blocker / "a.svg"), SVG_FILTER)
    w.export_current()
    modal.format, modal.folder = "SVG", str(blocker / "all")
    w.export_all()
    modal.export = _export_to(blocker / "sheet")
    w.export_pdf()
    assert len(modal.warnings) == 3
    shown = repr(str(blocker))[:-1]  # (the error quotes the path)
    assert all(shown in text for text in modal.warnings), modal.warnings
    assert _status(w) == before


def test_a_figure_that_fails_to_build_stops_the_export(
    built_window, modal, no_builds, wait
):
    """The export waits for the build, then shows the figure's error instead."""
    from dataclasses import replace

    w = built_window
    fig = w.current()
    w.panel.changed.emit(replace(fig.entry.settings, height_mm=30))
    w.export_all()
    assert wait(lambda: modal.warnings)
    assert modal.warnings == ["hero.png: not built in this test"]
    assert modal.format_boxes == []
    assert _status(w) == "hero.png: not built in this test"


def test_cancelling_the_build_progress_drops_the_export(
    app, built_window, figure_builder, modal, wait
):
    import threading
    from dataclasses import replace

    from PySide6.QtWidgets import QProgressDialog, QPushButton

    release = threading.Event()
    real = figure_builder.make
    figure_builder.make = lambda *a, **k: release.wait(60) and real(*a, **k)
    w = built_window
    fig = w.current()
    w.panel.changed.emit(replace(fig.entry.settings, height_mm=30))
    w.export_current()
    progress = w.findChildren(QProgressDialog)[-1]
    assert progress.labelText() == "Building hero.png…"
    progress.findChild(QPushButton).click()  # Cancel
    release.set()
    assert wait(lambda: fig.up_to_date)
    app.processEvents()
    assert modal.file_dialogs == []


def test_export_all_asks_which_files_to_write(built_window, modal, tmp_path):
    w = built_window
    w.export_all()  # Cancel
    [(title, text, buttons)] = modal.format_boxes
    assert text == (
        "Save every figure as an SVG (to print or cut), a PNG (for a virtual "
        "tabletop) or both?"
    )
    assert buttons == ["Both", "Cancel", "PNG", "SVG"]
    if sys.platform != "darwin":  # (macOS shows no title on a message box)
        assert title == "Export all"
    assert modal.file_dialogs == []
    modal.format = "SVG"
    w.export_all()  # the folder dialog cancelled
    assert modal.file_dialogs == [("folder", "Export all to", str(tmp_path))]
    for fmt, files in (
        ("SVG", ["hero.svg"]),
        ("PNG", ["hero.png"]),
        ("Both", ["hero.png", "hero.svg"]),
    ):
        out = tmp_path / fmt
        modal.format, modal.folder = fmt, str(out)
        w.export_all()
        assert sorted(p.name for p in out.iterdir()) == files
        n = len(files)
        assert _status(w) == f"Saved {n} file{'s' * (n != 1)} to {out}"


def test_export_sheet_writes_the_ticked_files(built_window, modal, tmp_path, wait):
    """Export sheet opens the Export dialog in the images' folder, named after the
    sheet's title, and reports the files it saved."""
    w = built_window
    before = _status(w)
    w.export_pdf()  # cancelled
    assert modal.export_dialogs == [
        {"folder": str(tmp_path), "name": "Paper miniatures", "machine": False}
    ]
    assert _status(w) == before
    modal.export = _export_to(tmp_path / "pdf")
    w.export_pdf()
    assert (tmp_path / "pdf" / "sheet.pdf").exists()
    assert _status(w) == (
        f"Saved sheet.pdf in {tmp_path / 'pdf'} (1 pieces, 1 page(s))"
    )
    w.sheet_panel.cut.setCurrentIndex(w.sheet_panel.cut.findData("machine"))
    modal.export = _export_to(tmp_path / "cut", pdf=False, cut=True)
    w.export_pdf()  # (rebuilds with the bleed first)
    assert wait(lambda: (tmp_path / "cut").exists())
    assert modal.export_dialogs[-1]["machine"]
    assert sorted(p.name for p in (tmp_path / "cut").iterdir()) == ["sheet-cut.svg"]
    assert _status(w) == (
        f"Saved sheet-cut.svg in {tmp_path / 'cut'} (1 pieces, 1 page(s))"
    )
    modal.export = _export_to(tmp_path / "both", pdf=True, cut=True)
    w.export_pdf()
    assert _status(w) == (
        f"Saved sheet.pdf, sheet-cut.svg in {tmp_path / 'both'} (1 pieces, 1 page(s))"
    )


def test_export_sheet_of_a_saved_project_starts_in_its_sheet_folder(
    built_window, modal, tmp_path
):
    w = built_window
    modal.save_as = (str(tmp_path / "minis.yaml"), "")
    assert w.save()
    w.export_pdf()
    assert modal.export_dialogs[-1]["folder"] == str(w.project.sheet_path.parent)


def test_a_sheet_that_cannot_be_laid_out_shows_why(built_window, modal):
    from papermini.project.sheet_settings import SheetSettings

    w = built_window
    w.sheet_panel.changed.emit(SheetSettings(cut="bogus"))
    w.export_pdf()
    w.print_sheet()
    assert modal.warnings == ["cut must be one of hand, machine, not 'bogus'"] * 2
    assert modal.export_dialogs == modal.print_dialogs == []


def test_nothing_is_exported_or_printed_when_no_figure_fits(built_window, modal, wait):
    from dataclasses import replace

    w = built_window
    fig = w.current()
    w.panel.changed.emit(replace(fig.entry.settings, height_mm=400, dpi=100))
    assert wait(lambda: fig.up_to_date)
    w.export_pdf()
    w.print_sheet()
    assert modal.warnings == [
        "The following figure is too large to fit on the selected paper:\n"
        "• hero\n\n"
        "Pick bigger paper, or make the figure smaller in step 2 (Miniature).\n\n"
        f"Nothing fits on the paper, so there is nothing to {verb}."
        for verb in ("export", "print")
    ]
    assert modal.export_dialogs == modal.print_dialogs == []


def test_export_and_print_ask_before_leaving_figures_off(
    built_window, modal, tmp_path, wait
):
    w = built_window
    _add_big_figure(w, wait)
    w.export_pdf()  # No
    w.print_sheet()  # No
    assert modal.questions == [
        "The following figure is too large to fit on the selected paper:\n"
        f"• Big\n\nIt is left off the sheet. {verb} the other figures anyway?"
        for verb in ("Export", "Print")
    ]
    assert modal.export_dialogs == modal.print_dialogs == []
    modal.yes = True
    w.export_pdf()
    w.print_sheet()
    assert len(modal.export_dialogs) == len(modal.print_dialogs) == 1


def test_a_cancelled_print_prints_nothing(built_window, modal):
    """The print dialog opens on the sheet's paper, at true size, for all pages."""
    from PySide6.QtGui import QPageSize

    w = built_window
    before = _status(w)
    w.print_sheet()
    assert modal.print_dialogs == [
        {
            "title": "Print sheet",
            "pages": (1, 1),
            "page_range": False,
            "doc": "papermini sheet",
            "full_page": True,
            "from_to": (0, 0),
            "paper": QPageSize.PageSizeId.A4,
            "landscape": False,
        }
    ]
    assert _status(w) == before


def test_printing_reports_the_pages_sent(built_window, modal, tmp_path, wait):
    from PySide6.QtPrintSupport import QPrinter

    w = built_window
    out = tmp_path / "printed.pdf"
    modal.print = _print_to(out)
    w.print_sheet()
    assert out.read_bytes().startswith(b"%PDF")
    name = QPrinter(QPrinter.PrinterMode.HighResolution)
    name.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    assert _status(w) == f"Sent 1 page(s) to {name.printerName() or 'the printer'}"


def test_the_print_dialog_offers_a_page_range_for_several_pages(
    built_window, modal, tmp_path
):
    from dataclasses import replace

    w = built_window
    fig = w.current()
    fig.entry.settings = replace(fig.entry.settings, copies=60)
    modal.save_as = (str(tmp_path / "goblins.yaml"), "")
    assert w.save()
    w.print_sheet()
    first, last = modal.print_dialogs[-1]["pages"]
    assert first == 1 and last > 1 and modal.print_dialogs[-1]["page_range"]
    assert modal.print_dialogs[-1]["doc"] == "goblins"


def test_printing_on_other_paper_asks_first(built_window, modal, tmp_path):
    from PySide6.QtGui import QPageSize

    w = built_window
    out = tmp_path / "printed.pdf"
    before = _status(w)
    modal.print = _print_to(out, QPageSize.PageSizeId.A3)
    w.print_sheet()  # No
    assert modal.questions == [
        (
            "The sheet is laid out for A4 paper, but the printer is set to A3. The minis "
            "still print at their real size, but parts of the sheet may be cut off.\n\n"
            "Print anyway?"
        )
    ]
    assert not out.exists() and _status(w) == before
    modal.yes = True
    w.print_sheet()
    assert out.exists() and _status(w).startswith("Sent 1 page(s) to ")


def test_a_printer_that_does_not_start_shows_a_warning(built_window, modal, tmp_path):
    w = built_window
    before = _status(w)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the folder should be")
    modal.print = _print_to(blocker / "printed.pdf")
    w.print_sheet()
    assert modal.warnings == ["Could not print: the printer did not start."]
    assert _status(w) == before


def test_the_print_uses_the_sheets_named_paper(built_window, modal, wait):
    from PySide6.QtGui import QPageSize

    from papermini.project.sheet_settings import SheetSettings

    w = built_window
    for paper in ("a3", "a4", "a5", "letter", "legal", "tabloid"):
        w.sheet_panel.changed.emit(SheetSettings(paper=paper))
        w.print_sheet()
    w.sheet_panel.changed.emit(SheetSettings(paper="a4", orientation="landscape"))
    w.print_sheet()
    w.sheet_panel.changed.emit(
        SheetSettings(paper="custom", paper_width_mm=300, paper_height_mm=200)
    )
    w.print_sheet()
    ids = QPageSize.PageSizeId
    assert [(d["paper"], d["landscape"]) for d in modal.print_dialogs] == [
        (ids.A3, False),
        (ids.A4, False),
        (ids.A5, False),
        (ids.Letter, False),
        (ids.Legal, False),
        (ids.Tabloid, False),
        (ids.A4, True),
        (ids.Custom, True),
    ]


def test_the_export_controller_prints_on_a_printer_from_its_factory(
    fonts, output, built_window, prefs, tmp_path
):
    """The controller prints with the dialogs and the printer factory it is given."""
    from PySide6.QtPrintSupport import QPrinter

    from papermini.gui.exporting.export_controller import ExportController
    from papermini.gui.exporting.export_dialogs import ExportDialogs

    class PrintEverything(ExportDialogs):
        def print_options(self, parent, printer, pages):
            return True

    out = tmp_path / "sheet.pdf"

    def pdf_printer():
        printer = QPrinter()
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(out))
        return printer

    sent = []
    exporter = ExportController(
        built_window,
        prefs,
        PrintEverything(prefs, output.cut_files),
        fonts,
        output,
        pdf_printer,
    )
    exporter.status.connect(sent.append)
    exporter.print_sheet()
    assert out.read_bytes().startswith(b"%PDF")
    assert len(sent) == 1 and sent[0].startswith("Sent 1 page(s) to ")


def _drag_enter(mime):
    """Return a drag entering at (10, 10) with ``mime``. PySide6 6.12 takes the position
    as a QPointF and deprecates the QPoint that older versions take."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QDragEnterEvent

    args = (
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    try:
        return QDragEnterEvent(QPointF(10, 10), *args)
    except TypeError:
        return QDragEnterEvent(QPoint(10, 10), *args)


def test_dropped_image_files_are_added(app, window, tmp_path, figure_image):
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDropEvent

    image, _ = figure_image(tmp_path / "hero.png")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(image))])
    enter = _drag_enter(mime)
    app.sendEvent(window, enter)
    assert enter.isAccepted()
    drop = QDropEvent(
        QPointF(10, 10),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    app.sendEvent(window, drop)
    assert [f.entry.image for f in window.figures] == [image]


def test_a_drag_without_images_or_links_is_refused(app, window):
    from PySide6.QtCore import QMimeData

    mime = QMimeData()
    mime.setText("just some words")
    enter = _drag_enter(mime)
    app.sendEvent(window, enter)
    assert not enter.isAccepted()


def test_a_picture_dropped_from_a_browser_is_downloaded_by_its_own_link(
    app, window, fake_web, figure_bytes, wait
):
    """A picture dragged from a web page carries a link to the page around it; the
    picture's own address in the HTML wins."""
    from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
    from PySide6.QtGui import QDropEvent

    picture = "https://example.com/goblin.png"
    fake_web[picture] = figure_bytes()
    mime = QMimeData()
    mime.setUrls([QUrl("https://example.com/goblins.html")])
    mime.setHtml(
        f'<a href="https://example.com/goblins.html"><img src="{picture}"></a>'
    )
    args = Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton
    enter = _drag_enter(mime)
    app.sendEvent(window, enter)
    assert enter.isAccepted()
    app.sendEvent(
        window, QDropEvent(QPointF(10, 10), *args, Qt.KeyboardModifier.NoModifier)
    )
    assert wait(lambda: len(window.figures) == 1)
    assert [url for url, _agent in fake_web.asked] == [picture]


# endregion
