from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from ...output.output import Output
from ...output.paper_sizes import PaperSizes
from ...output.sheet_layout import SheetLayout
from ...support.font_library import FontLibrary
from ..preferences import Preferences
from ..views.drawing import print_sheet
from ..window.figure import Figure
from .export_dialogs import ExportDialogs
from .pending_export import PendingExport

if TYPE_CHECKING:
    from PySide6.QtGui import QPageSize
    from PySide6.QtPrintSupport import QPrinter

    from ...project.sheet_settings import SheetSettings
    from ..window.main_window import MainWindow

ui_log = logging.getLogger("papermini.ui")  # what the user does


class ExportController(QObject):
    """Exports the figures and the sheet, and prints the sheet, each once its
    figures are built. ``output`` packs the sheet and writes the files; the printed
    sheet's text is in its fonts from ``fonts``."""

    status = Signal(str)  # a message for the status bar
    warning = Signal(str)  # a problem to show the user
    build = Signal(object)  # a Figure to build

    def __init__(
        self,
        window: MainWindow,
        prefs: Preferences,
        dialogs: ExportDialogs,
        fonts: FontLibrary,
        output: Output,
        printers: Callable[[], QPrinter] | None = None,
    ):
        super().__init__(window)
        self._window = window
        self._prefs = prefs
        self._dialogs = dialogs
        self._fonts = fonts
        self._output = output
        self._printers = printers or self._high_resolution_printer
        self._pending: PendingExport | None = None

    # region waiting for builds
    def _when_built(self, figs: list[Figure], then: Callable[[], None]) -> None:
        """Build stale figures in the background (the UI stays responsive), then
        call ``then``."""
        todo = [f for f in figs if not f.up_to_date]
        if not todo:
            then()
            return
        progress = QProgressDialog(
            "Building miniatures…", "Cancel", 0, len(todo), self._window
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.canceled.connect(self._drop)
        self._pending = PendingExport(figs, then, progress, len(todo))
        for f in todo:
            f.error = f.cancelled = None  # retry figures that failed or were stopped
            self.build.emit(f)
        self.check()

    def _drop(self) -> None:
        self._pending = None

    def check(self) -> None:
        """Go on with the waiting export once its figures are built, or stop it when
        one of them failed."""
        pending = self._pending
        if pending is None:
            return
        figs = [f for f in pending.figures if f in self._window.figures]
        failed = [
            (f, f.error) for f in figs if not f.up_to_date and f.error is not None
        ]
        left = [f for f in figs if not f.up_to_date]
        if failed:
            self._pending = None
            pending.progress.close()
            f, error = failed[0]
            self.warning.emit(f"{f.entry.image.name}: {error.splitlines()[0]}")
        elif not left:
            self._pending = None
            pending.progress.close()
            pending.then()
        else:
            pending.progress.setValue(pending.count - len(left))
            pending.progress.setLabelText(f"Building {left[0].entry.image.name}…")

    # endregion

    # region figures
    def export_figure(self, fig: Figure) -> None:
        """Save one figure as an SVG or a PNG, where the user chooses."""
        self._when_built([fig], lambda: self._save_figure(fig))

    def _save_figure(self, fig: Figure) -> None:
        start = self._window.out_dir() / fig.entry.svg_name()
        chosen = self._dialogs.save_figure(self._window, start)
        if chosen is None:
            return
        path, fmt = chosen
        try:
            paths = self._write(fig, path, fmt)
        except OSError as e:
            self.warning.emit(str(e))
            return
        ui_log.info("Exported %s", ", ".join(map(str, paths)))
        self.status.emit(
            f"Saved {paths[0]}"
            if len(paths) == 1
            else f"Saved {len(paths)} {fmt.upper()}s, one per numbered copy, to "
            f"{paths[0].parent}"
        )

    def export_all(self) -> None:
        """Save every figure as an SVG, a PNG or both, in a folder the user
        chooses."""
        if self._window.figures:
            self._when_built(list(self._window.figures), self._save_all)

    def _save_all(self) -> None:
        fmt = self._dialogs.ask_format(self._window)
        if fmt is None:
            return
        folder = self._dialogs.folder(self._window, self._window.out_dir())
        if not folder:
            return
        kinds = ("svg", "png") if fmt == "both" else (fmt,)
        try:
            n = sum(
                len(self._write(f, Path(folder) / f.entry.svg_name(), k))
                for f in self._window.figures
                for k in kinds
            )
        except OSError as e:
            self.warning.emit(str(e))
            return
        ui_log.info("Exported %d file(s) to %s", n, folder)
        self.status.emit(f"Saved {n} file{'s' * (n != 1)} to {folder}")

    def _write(self, fig: Figure, path: Path, fmt: str) -> list[Path]:
        """Write a figure as ``fmt`` ("svg" or "png") at ``path``, one file per
        numbered copy."""
        copies = fig.entry.settings.copies
        if fmt == "png":
            return self._output.png.write_copies(
                fig.mini, path.with_suffix(".png"), self._png_scale(), copies
            )
        return self._output.svg.write_copies(fig.mini, path.with_suffix(".svg"), copies)

    def _png_scale(self) -> float:
        """Pixels per mm of an exported PNG, as the preferences set it (pixels per
        grid square on the project's grid, or a dpi)."""
        return self._prefs.png_px_per_mm(self._window.project.sizes.grid_mm)

    # endregion

    # region the sheet
    def export_sheet(self) -> None:
        """Save the sheet to print (PDF) and, cut by machine, its cut files."""
        if self._window.figures:
            self._when_built(list(self._window.figures), self._save_sheet)

    def _save_sheet(self) -> None:
        project = self._window.project
        sh = project.sheet
        # named after the sheet's title, in the project's sheet folder (or next to
        # the images)
        folder = project.sheet_path.parent if project.path else self._window.out_dir()
        lay = self._layout("Export")
        if lay is None:
            return
        dlg = self._dialogs.export_sheet(
            self._window, folder, sh.title, lay.pages, lay.machine
        )
        if dlg is None:
            return
        path = dlg.pdf_path()
        pdf = path if dlg.pdf.isChecked() else None
        cut_file = (
            self._output.cut_files.default_path(path)
            if path is not None and lay.machine and dlg.cut.isChecked()
            else None
        )
        try:
            if pdf is not None:
                self._output.pdf.write(lay, pdf, sh.title)
            files = ([pdf] if pdf is not None else []) + (
                self._output.cut_files.write(lay, cut_file, sh.cut_folds, sh.title)
                if cut_file is not None
                else []
            )
        except OSError as e:
            self.warning.emit(str(e))
            return
        ui_log.info(
            "Exported the sheet: %s (%d pieces, %d page(s))",
            ", ".join(str(f) for f in files),
            len(lay.placements),
            lay.pages,
        )
        self.status.emit(
            f"Saved {', '.join(f.name for f in files)} in {files[0].parent} "
            f"({len(lay.placements)} pieces, {lay.pages} page(s))"
        )

    def print_sheet(self) -> None:
        """Print the sheet at its real size."""
        if self._window.figures:
            self._when_built(list(self._window.figures), self._print)

    def _print(self) -> None:
        sh = self._window.project.sheet
        lay = self._layout("Print")
        if lay is None:
            return
        printer = self._printers()
        self._set_up(printer, sh, lay)
        if not self._dialogs.print_options(self._window, printer, lay.pages):
            return
        if not self._paper_matches(printer, sh, lay):
            return
        n = print_sheet(printer, lay, sh.title, self._fonts)
        name = printer.printerName() or "the printer"
        ui_log.info("Printed %d of %d page(s) on %s", n, lay.pages, name)
        if n:
            self.status.emit(f"Sent {n} page(s) to {name}")
        else:
            self.warning.emit("Could not print: the printer did not start.")

    def _set_up(self, printer: QPrinter, sh: SheetSettings, lay: SheetLayout) -> None:
        """Set ``printer`` to the sheet's paper, at true size, for every page."""
        from PySide6.QtGui import QPageLayout

        pw, ph = lay.paper
        printer.setPageSize(self._page_size(sh, lay))
        printer.setPageOrientation(
            QPageLayout.Orientation.Landscape
            if pw > ph
            else QPageLayout.Orientation.Portrait
        )
        printer.setFullPage(True)  # true size: no scaling to the printable area
        path = self._window.project.path
        printer.setDocName(path.stem if path else "papermini sheet")
        printer.setFromTo(0, 0)

    @staticmethod
    def _page_size(sh: SheetSettings, lay: SheetLayout) -> QPageSize:
        """The sheet's paper as Qt names it: a standard size, or a custom size given
        upright and turned with the orientation."""
        from PySide6.QtCore import QSizeF
        from PySide6.QtGui import QPageSize

        mm = QPageSize.Unit.Millimeter
        if sh.paper in PaperSizes.PAPER:
            size = QSizeF(*PaperSizes.PAPER[sh.paper])
            return QPageSize(
                QPageSize.id(size, mm, QPageSize.SizeMatchPolicy.FuzzyMatch)
            )
        pw, ph = lay.paper
        return QPageSize(
            QSizeF(min(pw, ph), max(pw, ph)),
            mm,
            "Custom",
            QPageSize.SizeMatchPolicy.ExactMatch,
        )

    def _paper_matches(
        self, printer: QPrinter, sh: SheetSettings, lay: SheetLayout
    ) -> bool:
        """Whether the printer is set to the sheet's paper, or the user wants to
        print on its other paper anyway."""
        from PySide6.QtGui import QPageLayout

        pw, ph = lay.paper
        chosen = printer.pageLayout().fullRect(QPageLayout.Unit.Millimeter)
        if abs(chosen.width() - pw) <= 1 and abs(chosen.height() - ph) <= 1:
            return True
        turned = " landscape" if chosen.width() > chosen.height() else ""
        return (
            QMessageBox.question(
                self._window,
                "papermini",
                f"The sheet is laid out for {sh.paper_text()} paper, but the printer "
                f"is set to {printer.pageLayout().pageSize().name()}{turned}. The "
                "minis still print at their real size, but parts of the sheet may be "
                "cut off.\n\nPrint anyway?",
            )
            == QMessageBox.StandardButton.Yes
        )

    def _layout(self, verb: str) -> SheetLayout | None:
        """Lay out the sheet before ``verb`` (Export or Print). Returns None, after
        telling the user why, when it cannot be laid out or the user stops because
        figures are too big for the paper."""
        # (every figure was built before the export went on)
        built = [
            (f.mini, f.entry.settings.copies)
            for f in self._window.figures
            if f.mini is not None
        ]
        try:
            lay = self._window.project.sheet.layout(
                self._output.packer, built, leave_out=True
            )
        except ValueError as e:
            self.warning.emit(str(e))
            return None
        return lay if self._all_fit(lay, verb) else None

    def _all_fit(self, lay: SheetLayout, verb: str) -> bool:
        """Whether to go on when figures are too big for the paper. They are left
        off, and the user is asked first."""
        if not lay.left_out:
            return True
        intro, names, advice = self._window.too_big(lay)
        if not lay.placements:
            self.warning.emit(
                f"{self._too_big_plain(intro, names, advice)}\n\nNothing fits on the "
                f"paper, so there is nothing to {verb.lower()}."
            )
            return False
        left = "It is" if len(names) == 1 else "They are"
        return (
            QMessageBox.question(
                self._window,
                "papermini",
                f"{self._too_big_plain(intro, names)}\n\n{left} left off the "
                f"sheet. {verb} the other figures anyway?",
            )
            == QMessageBox.StandardButton.Yes
        )

    @staticmethod
    def _too_big_plain(intro: str, names: list[str], advice: str = "") -> str:
        """The too-big message as plain text, a bullet per figure, for a dialog."""
        lines = "\n".join(f"• {n}" for n in names)
        return f"{intro}\n{lines}" + (f"\n\n{advice}" if advice else "")

    @staticmethod
    def _high_resolution_printer() -> QPrinter:
        from PySide6.QtPrintSupport import QPrinter

        return QPrinter(QPrinter.PrinterMode.HighResolution)

    # endregion
