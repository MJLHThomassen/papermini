from __future__ import annotations

import html
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLayout,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ...pipeline.segmentation import segment
from ...pipeline.segmentation.cache_folder import CacheFolder
from ...pipeline.segmentation.segmenter_registry import SegmenterRegistry
from .model_info import MB, _host, _label, licence_link, ui_log


class _Signals(QObject):
    """Signals the download thread sends to the dialog."""

    progress = Signal(int, int)  # done bytes, total bytes (0 = unknown)
    finished = Signal(str)  # "" on success, else the error message


class DownloadDialog(QDialog):
    """Asks before downloading a built-in model (``ask``), then shows its progress.
    A non-commercial model always asks: Download stays disabled until the user accepts
    that they will not use it commercially.

    Accepted once the model is on disk; rejected when the user says no, cancels,
    or closes the dialog after a failed download.
    """

    def __init__(
        self,
        model: str,
        segmenters: SegmenterRegistry,
        parent=None,
        ask: bool = True,
        force: bool = False,
    ):
        super().__init__(parent)
        self._segmenters = segmenters
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
        folder = html.escape(str(CacheFolder.path()))
        restricted = SegmenterRegistry.non_commercial(
            model
        )  # (its licence gets a box of its own)
        self.body = _label(
            f"papermini uses <b>{html.escape(spec['title'])}</b> to separate the figure from "
            f"the background. It is downloaded once (about {spec['mb']} MB) from "
            f"{html.escape(_host(model))} and kept in<br><code>{folder}</code>"
            + ("" if restricted else f"<br><br>{licence_link(model)}"),
            "Muted",
        )
        self.body.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.body.setMinimumWidth(440)  # sets the dialog width (its height follows)
        v.addWidget(self.body)
        self.accept_licence = self.licence_note = None  # (for a non-commercial model)
        if restricted:
            ask = True  # (also from Models and cache: the licence must be accepted)
            rest = SegmenterRegistry.licence_notice(model).split(". ", 1)[1]
            note = _label(
                f'<b>Licence: <a href="{html.escape(spec["licence_url"])}">'
                f"non-commercial use only</a>.</b> {html.escape(rest)}",
                "LicenceBox",
            )
            note.setTextInteractionFlags(Qt.TextBrowserInteraction)
            self.licence_note = note
            note.setMinimumWidth(440)
            v.addWidget(note)
            self.accept_licence = QCheckBox(
                f"I will only use {spec['title']} non-commercially"
            )
            self.accept_licence.toggled.connect(self._sync_go)
            v.addWidget(self.accept_licence)
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
            self._sync_go()
        else:
            self.start()

    @property
    def downloading(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _sync_go(self):
        """Download only once the licence is accepted (for a non-commercial model)."""
        self.btn_go.setEnabled(
            self.accept_licence is None or self.accept_licence.isChecked()
        )

    def start(self):
        spec = segment.ONNX_MODELS[self.model]
        if self.accept_licence is not None:
            if not self.accept_licence.isChecked():
                return
            if self.accept_licence.isEnabled():
                ui_log.info(
                    "Accepted that %s is for non-commercial use only", spec["title"]
                )
            self.accept_licence.setEnabled(
                False
            )  # (accepted: a retry needs no new tick)
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
                self._segmenters.fetch(
                    self.model,
                    force=self.force,
                    cancel=self._cancel,
                    progress=lambda done, total, _msg: sig.progress.emit(
                        done, total or 0
                    ),
                )
            except Exception as e:  # noqa: BLE001 - always report back
                sig.finished.emit(str(e) or type(e).__name__)
            else:
                sig.finished.emit("")

        self._thread = threading.Thread(
            target=run, name=f"download-{self.model}", daemon=True
        )
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
            ui_log.warning("Downloading the %s model failed: %s", self.model, error)
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
