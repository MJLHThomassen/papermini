"""Model downloads and the cache: the approve-and-download dialog and the Cache
Management window."""

from __future__ import annotations

import html
import logging
import threading
import urllib.parse

from PySide6.QtCore import QObject, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLayout,
                               QMessageBox, QProgressBar, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from .. import remote, segment

ui_log = logging.getLogger("papermini.ui")

MB = 1024 * 1024
CONTENT_WIDTH = 644  # the Cache Management window's content opens this wide


def _size(files) -> str:
    """The total size of ``files``, in MB (with a decimal below 10 MB)."""
    total = 0
    for f in files:
        try:
            total += f.stat().st_size
        except OSError:
            pass
    mb = total / MB
    return f"{mb:.1f} MB" if mb < 10 else f"{mb:.0f} MB"


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


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
    A non-commercial model always asks: Download stays disabled until the user accepts
    that they will not use it commercially.

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
        restricted = segment.non_commercial(model)  # (its licence gets a box of its own)
        self.body = _label(
            f"papermini uses <b>{html.escape(spec['title'])}</b> to separate the figure from "
            f"the background. It is downloaded once (about {spec['mb']} MB) from "
            f"{html.escape(_host(model))} and kept in<br><code>{folder}</code>"
            + ("" if restricted else f"<br><br>{licence_link(model)}"), "Muted")
        self.body.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.body.setMinimumWidth(440)  # sets the dialog width (its height follows)
        v.addWidget(self.body)
        self.accept_licence = self.licence_note = None  # (for a non-commercial model)
        if restricted:
            ask = True  # (also from Cache management: the licence must be accepted)
            rest = segment.licence_notice(model).split(". ", 1)[1]
            note = _label(f"<b>Licence: <a href=\"{html.escape(spec['licence_url'])}\">"
                          f"non-commercial use only</a>.</b> {html.escape(rest)}",
                          "LicenceBox")
            note.setTextInteractionFlags(Qt.TextBrowserInteraction)
            self.licence_note = note
            note.setMinimumWidth(440)
            v.addWidget(note)
            self.accept_licence = QCheckBox(
                f"I will only use {spec['title']} non-commercially")
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
        self.btn_go.setEnabled(self.accept_licence is None or self.accept_licence.isChecked())

    def start(self):
        spec = segment.ONNX_MODELS[self.model]
        if self.accept_licence is not None:
            if not self.accept_licence.isChecked():
                return
            if self.accept_licence.isEnabled():
                ui_log.info("Accepted that %s is for non-commercial use only", spec["title"])
            self.accept_licence.setEnabled(False)  # (accepted: a retry needs no new tick)
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


class ModelCard(QFrame):
    """One built-in model in the Cache Management window: what it is, where it is,
    actions."""

    def __init__(self, model: str, dialog: "CacheDialog"):
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
        restricted = segment.non_commercial(model)
        self.licence = _label(licence_link(model), "LicenceNote" if restricted else "Muted")
        self.licence.setTextInteractionFlags(Qt.TextBrowserInteraction)
        if restricted:
            self.licence.setToolTip(segment.licence_notice(model))
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


class CacheCard(QFrame):
    """A kind of cached file in the Cache Management window: what it is, how much
    there is, and Clear."""

    def __init__(self, title: str, about: str, clear):
        super().__init__()
        self.setObjectName("ModelCard")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 14, 12)
        h.setSpacing(14)
        v = QVBoxLayout()
        v.setSpacing(3)
        v.addWidget(_label(f"<b>{html.escape(title)}</b>"))
        v.addWidget(_label(html.escape(about), "Muted"))
        self.state = _label("", "Hint")
        v.addWidget(self.state)
        h.addLayout(v, 1)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setAccessibleName(f"Clear {title.lower()}")
        self.btn_clear.clicked.connect(clear)
        h.addWidget(self.btn_clear, 0, Qt.AlignVCenter)

    def show_state(self, text: str, can_clear: bool):
        self.state.setText(text)
        self.btn_clear.setEnabled(can_clear)


class CacheDialog(QDialog):
    """The Cache Management window: the cache folder, which background-removal models
    are downloaded (with actions on them), and papermini's other cached files (masks,
    images from links), which it can clear. Resizable: the content scrolls when the
    window is too small for it. ``in_use()`` gives the image files of the open
    figures, which clearing keeps."""

    changed = Signal(str)  # a model was downloaded or deleted

    def __init__(self, parent=None, in_use=lambda: ()):
        super().__init__(parent)
        self.setObjectName("CacheDialog")
        self.setWindowTitle("Cache Management")
        self.setSizeGripEnabled(True)
        self.in_use = in_use
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 18)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("CacheScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName("CacheContent")
        v = QVBoxLayout(content)
        v.setContentsMargins(22, 20, 22, 6)
        v.setSpacing(10)

        v.addWidget(_label("Cache", "DialogTitle", wrap=False))
        about = _label("papermini keeps its downloaded models and other cached files in "
                       "one folder.", "Muted")
        v.addWidget(about)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.folder = _label(html.escape(str(segment.cache_dir())), "Hint")
        self.folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_open = QPushButton("Open folder")
        btn_open.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(segment.cache_dir()))))
        self.btn_all = QPushButton("Clear cache…")
        self.btn_all.setToolTip("Delete everything in the cache folder: the downloaded "
                                "models, the masks and the images from links")
        self.btn_all.clicked.connect(self.delete_all)
        top.addWidget(self.folder, 1)
        top.addWidget(btn_open, 0, Qt.AlignVCenter)
        top.addWidget(self.btn_all, 0, Qt.AlignVCenter)
        v.addLayout(top)

        v.addSpacing(10)
        v.addWidget(_label("Background-removal models", "DialogTitle", wrap=False))
        v.addWidget(_label(
            "Models are downloaded once and kept on this computer. Delete one to free disk "
            "space: papermini asks before downloading it again when you next use it.",
            "Muted"))
        v.addSpacing(4)
        self.cards = {m: ModelCard(m, self) for m in segment.ONNX_MODELS}
        for card in self.cards.values():
            v.addWidget(card)

        v.addSpacing(10)
        v.addWidget(_label("Other cached files", "DialogTitle", wrap=False))
        v.addWidget(_label("papermini keeps these to open figures quickly. Clear them to "
                           "free disk space: papermini makes or downloads them again "
                           "when it needs them.", "Muted"))
        self.masks = CacheCard(
            "Masks", "The background removal of each image, so a figure need not run "
            "the model again.", self.clear_masks)
        self.images = CacheCard(
            "Images from links", "The images of figures added from a link. Images that "
            "open figures use are kept.", self.clear_images)
        v.addWidget(self.masks)
        v.addWidget(self.images)
        v.addStretch(1)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll, 1)

        row = QHBoxLayout()  # (outside the scrolling part: always in view)
        row.setContentsMargins(22, 12, 22, 0)
        row.addStretch(1)
        close = QPushButton("Close")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        outer.addLayout(row)
        self.refresh_cache()
        self._fit(content)

    def _fit(self, content: QWidget):
        """Open as large as the content, but no larger than the screen allows."""
        inner = max(CONTENT_WIDTH, content.minimumSizeHint().width())
        width = inner + self.scroll.verticalScrollBar().sizeHint().width()
        lay = content.layout()
        height = (lay.totalHeightForWidth(inner) if lay.hasHeightForWidth()
                  else content.sizeHint().height())
        want = QSize(width, height + self.layout().sizeHint().height()
                     - self.scroll.sizeHint().height() + 2)  # (+ the Close row)
        screen = (self.parent().screen() if self.parent() is not None
                  else QGuiApplication.primaryScreen())
        if screen is not None:
            room = screen.availableGeometry().size() * 0.9
            want = want.boundedTo(QSize(int(room.width()), int(room.height())))
        self.resize(want)

    def download(self, model: str):
        DownloadDialog(model, self, ask=False,
                       force=segment.model_path(model).exists()).exec()
        self.cards[model].refresh()
        self.refresh_cache()
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
        ui_log.info("Deleting the %s model", model)
        try:
            segment.delete_model(model)
        except OSError as e:
            ui_log.warning("Could not delete the %s model: %s", model, e)
            QMessageBox.warning(self, "Delete model", f"Could not delete the file: {e}")
        self.cards[model].refresh()
        self.refresh_cache()
        self.changed.emit(model)

    def _kept(self) -> list:
        """The downloaded images that open figures use."""
        folder = remote.cached_images()
        use = {str(p) for p in self.in_use()}
        return [p for p in folder if str(p) in use]

    def refresh_cache(self):
        masks = segment.cached_masks()
        self.masks.show_state(f"{_count(len(masks), 'mask', 'masks')} · {_size(masks)}"
                              if masks else "No masks", bool(masks))
        images, kept = remote.cached_images(), self._kept()
        text = (f"{_count(len(images), 'image', 'images')} · {_size(images)}" if images
                else "No images")
        if kept:
            text += f" · {len(kept)} in use by open figures"
        self.images.show_state(text, len(images) > len(kept))
        self.btn_all.setEnabled(bool(self._downloaded() or masks or len(images) > len(kept)))

    def _downloaded(self) -> list:
        """The built-in models that are downloaded."""
        return [m for m in segment.ONNX_MODELS if segment.model_path(m).exists()]

    def delete_all(self):
        """Delete the downloaded models, the masks and the images from links (except
        those open figures use), after asking."""
        models = self._downloaded()
        kept = set(map(str, self._kept()))
        files = ([segment.model_path(m) for m in models] + segment.cached_masks()
                 + [p for p in remote.cached_images() if str(p) not in kept])
        ok = QMessageBox.question(
            self, "Clear cache",
            f"Clear the whole cache ({_size(files)})? This also deletes the downloaded "
            "models, not only the masks and images from links."
            "\n\npapermini asks before downloading a model again, the next time a figure "
            "needs it. Images that open figures use are kept.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if ok != QMessageBox.Yes:
            return
        ui_log.info("Clearing the whole cache")
        failed = []
        for m in models:
            try:
                segment.delete_model(m)
            except OSError as e:
                failed.append(f"{segment.model_path(m).name}: {e}")
        segment.clear_masks()
        remote.clear_images(keep=self._kept())
        for card in self.cards.values():
            card.refresh()
        self.refresh_cache()
        for m in models:
            self.changed.emit(m)
        if failed:
            ui_log.warning("Could not delete: %s", "; ".join(failed))
            QMessageBox.warning(self, "Clear cache", "Could not delete:\n" + "\n".join(failed))

    def clear_masks(self):
        ui_log.info("Cleared %d cached mask(s)", segment.clear_masks())
        self.refresh_cache()

    def clear_images(self):
        ui_log.info("Cleared %d downloaded image(s)", remote.clear_images(keep=self._kept()))
        self.refresh_cache()
