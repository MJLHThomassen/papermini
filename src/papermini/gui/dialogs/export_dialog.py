from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...output.cut_file_writer import CutFileWriter
from ...project.figure_entry import safe_name
from ..preferences import Preferences


class ExportDialog(QDialog):
    """Pick a folder and a name, and tick what to save: the sheet to print (PDF) and,
    cut by machine, the cut file (one SVG per page). Shows the exact file names, and
    remembers the ticks (so "only the cut file", after printing from the app, stays
    one click away)."""

    def __init__(
        self,
        prefs: Preferences,
        cut_files: CutFileWriter,
        folder: Path,
        title: str,
        pages: int,
        machine: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._prefs = prefs
        self._cut_files = cut_files
        self.setWindowTitle("Export sheet")
        self.setObjectName("ExportDialog")
        self._pages, self._machine = max(1, pages), machine
        v = QVBoxLayout(self)
        v.setSpacing(12)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        self.folder = QLineEdit(str(folder))
        browse = QToolButton()
        browse.setText("…")
        browse.setToolTip("Choose the folder")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("Folder", holder)
        self.name = QLineEdit(safe_name(title or "minis"))
        form.addRow("Name", self.name)
        v.addLayout(form)

        self.pdf = QCheckBox("Sheet to print (PDF)")
        self.pdf.setChecked(prefs.export_pdf())
        self.pdf_files = self._files_label()
        v.addWidget(self.pdf)
        v.addWidget(self.pdf_files)
        self.cut = QCheckBox(
            "Cut file for your cutting machine (SVG"
            + (", one per page)" if self._pages > 1 else ")")
        )
        self.cut.setChecked(prefs.export_cut())
        self.cut_files = self._files_label()
        v.addWidget(self.cut)
        v.addWidget(self.cut_files)
        for w in (self.cut, self.cut_files):
            w.setVisible(machine)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.export_btn = self.buttons.addButton("Export", QDialogButtonBox.AcceptRole)
        self.export_btn.setDefault(True)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        v.addWidget(self.buttons)
        for sig in (
            self.folder.textChanged,
            self.name.textChanged,
            self.pdf.toggled,
            self.cut.toggled,
        ):
            sig.connect(self._sync)
        self._sync()
        self.setMinimumWidth(460)

    @staticmethod
    def _files_label() -> QLabel:
        lab = QLabel()
        lab.setObjectName("Hint")
        lab.setTextFormat(Qt.RichText)
        lab.setContentsMargins(26, 0, 0, 0)
        lab.setWordWrap(True)
        return lab

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Export to", self.folder.text())
        if d:
            self.folder.setText(d)

    # what will be written -------------------------------------------------------------
    def pdf_path(self) -> Path | None:
        name = safe_name(self.name.text().strip()) if self.name.text().strip() else ""
        return Path(self.folder.text().strip()) / f"{name}.pdf" if name else None

    def cut_paths(self) -> list[Path]:
        pdf = self.pdf_path()
        if not pdf:
            return []
        return self._cut_files.paths(self._cut_files.default_path(pdf), self._pages)

    def chosen(self) -> list[Path]:
        """Every file the export writes, with the boxes as they are ticked."""
        out = [self.pdf_path()] if self.pdf.isChecked() and self.pdf_path() else []
        return out + (
            self.cut_paths() if self._machine and self.cut.isChecked() else []
        )

    def _sync(self, *_):
        pdf, cut = self.pdf_path(), self.cut_paths()
        self.pdf_files.setText(html.escape(pdf.name) if pdf else "")
        if len(cut) > 2:
            names = (
                f"{html.escape(cut[0].name)}, {html.escape(cut[1].name)} … "
                f"{html.escape(cut[-1].name)}"
            )
        else:
            names = ", ".join(html.escape(c.name) for c in cut)
        self.cut_files.setText(names)
        for box, lab in ((self.pdf, self.pdf_files), (self.cut, self.cut_files)):
            lab.setEnabled(box.isChecked())
        self.export_btn.setEnabled(bool(self.chosen()))

    def _accept(self):
        files = self.chosen()
        if not files:
            return
        folder = Path(self.folder.text().strip())
        if not folder.is_dir():
            QMessageBox.warning(
                self, "Export sheet", f"The folder {folder} does not exist."
            )
            return
        there = [f for f in files if f.exists()]
        if (
            there
            and QMessageBox.question(
                self,
                "Export sheet",
                "Replace these files?\n\n" + "\n".join(f.name for f in there),
            )
            != QMessageBox.Yes
        ):
            return
        self._prefs.set_export_pdf(self.pdf.isChecked())
        if self._machine:
            self._prefs.set_export_cut(self.cut.isChecked())
        self.accept()
