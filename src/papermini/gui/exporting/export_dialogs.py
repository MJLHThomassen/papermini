from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QWidget

from ..dialogs.export_dialog import ExportDialog
from ..preferences import Preferences

if TYPE_CHECKING:
    from PySide6.QtPrintSupport import QPrinter


class ExportDialogs:
    """Opens the dialogs of exporting and printing, and returns what the user chose."""

    SVG_FILTER = "SVG, to print or cut (*.svg)"
    PNG_FILTER = "PNG, for a virtual tabletop (*.png)"

    def __init__(self, prefs: Preferences):
        self._prefs = prefs

    def save_figure(self, parent: QWidget, start: Path) -> tuple[Path, str] | None:
        """Ask where to save a figure. Returns the path and the format, "svg" or
        "png", or None when the user cancels."""
        f, chosen = QFileDialog.getSaveFileName(
            parent,
            "Export",
            str(start),
            f"{self.SVG_FILTER};;{self.PNG_FILTER}",
        )
        if not f:
            return None
        path = Path(f)
        suffix = path.suffix.lower()
        png = suffix == ".png" or (suffix != ".svg" and chosen == self.PNG_FILTER)
        return path, "png" if png else "svg"

    def folder(self, parent: QWidget, start: Path) -> str:
        """Ask for the folder Export all saves to. Returns "" when the user
        cancels."""
        return QFileDialog.getExistingDirectory(parent, "Export all to", str(start))

    def ask_format(self, parent: QWidget) -> str | None:
        """Ask which files Export all writes: "svg", "png", "both", or None when the
        user cancels."""
        box = QMessageBox(
            QMessageBox.Icon.Question,
            "Export all",
            "Save every figure as an SVG (to print or cut), a PNG (for a "
            "virtual tabletop) or both?",
            parent=parent,
        )
        buttons = {
            box.addButton(text, QMessageBox.ButtonRole.AcceptRole): fmt
            for text, fmt in (("SVG", "svg"), ("PNG", "png"), ("Both", "both"))
        }
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return buttons.get(box.clickedButton())

    def export_sheet(
        self, parent: QWidget, folder: Path, title: str, pages: int, machine: bool
    ) -> ExportDialog | None:
        """Open the Export dialog of the sheet. Returns the dialog with the user's
        choices, or None when the user cancels."""
        dlg = ExportDialog(self._prefs, folder, title, pages, machine, parent)
        return dlg if dlg.exec() == QDialog.DialogCode.Accepted else None

    def print_options(self, parent: QWidget, printer: QPrinter, pages: int) -> bool:
        """Open the print dialog for ``printer``, which sets it up. Returns whether
        the user chose to print."""
        from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog

        dlg = QPrintDialog(printer, parent)
        dlg.setWindowTitle("Print sheet")
        dlg.setMinMax(1, pages)
        dlg.setOption(QAbstractPrintDialog.PrintDialogOption.PrintPageRange, pages > 1)
        return dlg.exec() == QDialog.DialogCode.Accepted
