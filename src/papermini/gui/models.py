"""Model downloads: the approve-and-download dialog and the Models window."""

from __future__ import annotations

import html
import threading
import urllib.parse

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QLayout, QMessageBox,
                               QProgressBar,
                               QPushButton, QVBoxLayout)

from .. import segment

MB = 1024 * 1024


def _host(model: str) -> str:
    return urllib.parse.urlsplit(segment.ONNX_MODELS[model]["url"]).hostname or "the internet"


def _label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    lab.setTextFormat(Qt.RichText)
    lab.setOpenExternalLinks(True)  # links open in the browser
    return lab


def licence_link(model: str) -> str:
    """"Licence: <name>" with the name linking to the licence (rich text)."""
    spec = segment.ONNX_MODELS[model]
    return (f"Licence: <a href=\"{html.escape(spec['licence_url'])}\">"
            f"{html.escape(spec['licence'])}</a>")


class _Signals(QObject):
    progress = Signal(int, int)  # done bytes, total bytes (0 = unknown)
    finished = Signal(str)       # "" on success, else the error message


class DownloadDialog(QDialog):
    """Asks before downloading a built-in model (``ask``), then shows its progress.

    Accepted once the model is on disk; rejected when the user says no, cancels,
    or closes the dialog after a failed download.
    """

    def __init__(self, model: str, parent=None, ask: bool = True, force: bool = False):
        super().__init__(parent)
        self.setObjectName("DownloadDialog")
        self.model, self.force = model, force
        spec = segment.ONNX_MODELS[model]
        self.setWindowTitle("Download model")
        self.setModal(True)
        self._cancel = threading.Event()
        self._thread = None
        self._sig = _Signals(self)
        self._sig.progress.connect(self._on_progress)
        self._sig.finished.connect(self._on_finished)

        v = QVBoxLayout(self)
        v.setSizeConstraint(QLayout.SetFixedSize)  # as tall as the content, no gaps
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(10)
        self.title = _label(name="DialogTitle", wrap=False)
        v.addWidget(self.title)
        folder = html.escape(str(segment.cache_dir()))
        self.body = _label(
            f"papermini uses <b>{html.escape(spec['title'])}</b> to separate the figure from "
            f"the background. It is downloaded once (about {spec['mb']} MB) from "
            f"{html.escape(_host(model))} and kept in<br><code>{folder}</code>"
            f"<br><br>{licence_link(model)}", "Muted")
        self.body.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.body.setMinimumWidth(440)  # sets the dialog width (its height follows)
        v.addWidget(self.body)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.status = _label("", "Hint")
        v.addSpacing(4)
        v.addWidget(self.bar)
        v.addWidget(self.status)
        v.addSpacing(6)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_no = QPushButton("Not now")
        self.btn_no.clicked.connect(self.reject)
        self.btn_go = QPushButton("Download")
        self.btn_go.setProperty("primary", True)
        self.btn_go.setDefault(True)
        self.btn_go.clicked.connect(self.start)
        row.addWidget(self.btn_no)
        row.addWidget(self.btn_go)
        v.addLayout(row)

        if ask:
            self.title.setText(f"Download the {html.escape(spec['title'])} model?")
            self.bar.hide()
            self.status.hide()
        else:
            self.start()

    @property
    def downloading(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        spec = segment.ONNX_MODELS[self.model]
        self.title.setText(f"Downloading {html.escape(spec['title'])}…")
        self.bar.setRange(0, 0)  # busy until the size is known
        self.bar.show()
        self.status.setText("Connecting…")
        self.status.show()
        self.btn_go.hide()
        self.btn_no.setText("Cancel")
        self.btn_no.setEnabled(True)
        self._cancel.clear()
        sig = self._sig

        def run():
            try:
                segment.fetch_model(self.model, force=self.force, cancel=self._cancel,
                                    progress=lambda done, total, _msg:
                                    sig.progress.emit(done, total or 0))
            except (Exception, SystemExit) as e:  # noqa: BLE001 - always report back
                sig.finished.emit(str(e) or type(e).__name__)
            else:
                sig.finished.emit("")

        self._thread = threading.Thread(target=run, name=f"download-{self.model}", daemon=True)
        self._thread.start()

    def _on_progress(self, done: int, total: int):
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(1000 * done / total))
            self.status.setText(f"{done / MB:.0f} of {total / MB:.0f} MB")
        else:
            self.status.setText(f"{done / MB:.0f} MB")

    def _on_finished(self, error: str):
        self._thread = None
        if not error:
            self.accept()
        elif self._cancel.is_set():
            super().reject()
        else:  # keep the dialog open so the user sees why, and can retry
            self.title.setText("The download failed")
            self.bar.hide()
            self.status.setText(html.escape(error))
            self.btn_go.setText("Try again")
            self.btn_go.show()
            self.btn_no.setText("Close")

    def reject(self):
        """Cancel a running download first; the dialog closes once it has stopped."""
        if self.downloading:
            self._cancel.set()
            self.btn_no.setEnabled(False)
            self.status.setText("Cancelling…")
            return
        super().reject()

    def closeEvent(self, e):
        if self.downloading:
            self.reject()
            e.ignore()
        else:
            super().closeEvent(e)


class ModelCard(QFrame):
    """One built-in model in the Models window: what it is, where it is, actions."""

    def __init__(self, model: str, dialog: "ModelsDialog"):
        super().__init__()
        self.setObjectName("ModelCard")
        self.model, self.dialog = model, dialog
        spec = segment.ONNX_MODELS[model]
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 14, 12)
        h.setSpacing(14)
        v = QVBoxLayout()
        v.setSpacing(3)
        v.addWidget(_label(f"<b>{html.escape(spec['title'])}</b>"
                           f"&nbsp;&nbsp;<span style='font-weight:400'>{model}</span>"))
        v.addWidget(_label(html.escape(spec["about"]), "Muted"))
        self.licence = _label(licence_link(model), "Muted")
        self.licence.setTextInteractionFlags(Qt.TextBrowserInteraction)
        v.addWidget(self.licence)
        self.state = _label("", "Hint")
        self.state.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.state)
        h.addLayout(v, 1)
        self.btn_get = QPushButton()
        self.btn_get.clicked.connect(lambda: dialog.download(model))
        self.btn_del = QPushButton("Delete")
        self.btn_del.clicked.connect(lambda: dialog.delete(model))
        for b in (self.btn_get, self.btn_del):
            h.addWidget(b, 0, Qt.AlignVCenter)
        self.refresh()

    def refresh(self):
        spec = segment.ONNX_MODELS[self.model]
        path = segment.model_path(self.model)
        have = path.exists()
        if have:
            size = path.stat().st_size / MB
            self.state.setText(f"Downloaded · {size:.0f} MB · {html.escape(path.name)}")
        else:
            self.state.setText(f"Not downloaded · about {spec['mb']} MB from "
                               f"{html.escape(_host(self.model))}")
        self.btn_get.setText("Download again" if have else "Download")
        self.btn_get.setAccessibleName(f"{self.btn_get.text()} {spec['title']}")
        self.btn_del.setEnabled(have)
        self.btn_del.setAccessibleName(f"Delete {spec['title']}")


class ModelsDialog(QDialog):
    """Which background-removal models are downloaded, where, and actions on them."""

    changed = Signal(str)  # a model was downloaded or deleted

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModelsDialog")
        self.setWindowTitle("Models")
        v = QVBoxLayout(self)
        v.setSizeConstraint(QLayout.SetFixedSize)  # as tall as the content, no gaps
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(10)
        v.addWidget(_label("Background-removal models", "DialogTitle", wrap=False))
        intro = _label(
            "Models are downloaded once and kept on this computer. Delete one to free disk "
            "space: papermini asks before downloading it again when you next use it.", "Muted")
        intro.setMinimumWidth(600)  # sets the dialog width (its height follows)
        v.addWidget(intro)
        folder = QHBoxLayout()
        self.folder = _label(f"Folder: {html.escape(str(segment.cache_dir()))}", "Hint")
        self.folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_open = QPushButton("Open folder")
        btn_open.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(segment.cache_dir()))))
        folder.addWidget(self.folder, 1)
        folder.addWidget(btn_open)
        v.addLayout(folder)
        v.addSpacing(4)
        self.cards = {m: ModelCard(m, self) for m in segment.ONNX_MODELS}
        for card in self.cards.values():
            v.addWidget(card)
        v.addSpacing(6)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        v.addLayout(row)

    def download(self, model: str):
        DownloadDialog(model, self, ask=False,
                       force=segment.model_path(model).exists()).exec()
        self.cards[model].refresh()
        if segment.model_path(model).exists():
            self.changed.emit(model)

    def delete(self, model: str):
        spec = segment.ONNX_MODELS[model]
        ok = QMessageBox.question(
            self, "Delete model",
            f"Delete {spec['title']}? papermini asks to download it again "
            f"(about {spec['mb']} MB) the next time a figure needs it.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if ok != QMessageBox.Yes:
            return
        try:
            segment.delete_model(model)
        except OSError as e:
            QMessageBox.warning(self, "Delete model", f"Could not delete the file: {e}")
        self.cards[model].refresh()
        self.changed.emit(model)
