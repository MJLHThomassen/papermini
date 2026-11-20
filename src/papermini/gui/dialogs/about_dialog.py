from __future__ import annotations

import html

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ... import __version__
from ...support.font_library import FontLibrary
from ...support.log_session import LogSession
from .. import theme
from ..updating.update_state import UpdateState


class AboutDialog(QDialog):
    """A dialog with the app's version and licences, and the state of the update check
    under the version, with the one action that fits that state (download, restart,
    open the release page or check again). The update controller keeps the state
    current through ``update_state``, and the actions come out as signals."""

    updateRequested = Signal(object)  # the release to download
    releasePageRequested = Signal()
    restartRequested = Signal()
    checkRequested = Signal()

    def __init__(self, logs: LogSession, parent=None):
        super().__init__(parent)
        self._logs = logs
        self.setWindowTitle("About papermini")
        self.setObjectName("AboutDialog")
        v = QVBoxLayout(self)
        v.setSpacing(12)
        v.setSizeConstraint(QLayout.SetMinimumSize)  # grows when the notice does
        top = QHBoxLayout()
        top.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(theme.logo_pixmap(56))
        logo.setAlignment(Qt.AlignTop)
        top.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(8)
        title = QLabel(f"<b>papermini {html.escape(__version__)}</b>")
        title.setTextFormat(Qt.RichText)
        col.addWidget(title)
        # the update notice, right under the version it is about
        self.status = QLabel()
        self.status.setObjectName(
            "MethodBox"
        )  # (the same framed note as Chosen method)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        self.status.setFixedWidth(
            400
        )  # (a wrapping label needs a fixed width for its height)
        col.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(400)
        self.progress.setTextVisible(True)
        self.progress.hide()
        col.addWidget(self.progress)
        text = QLabel(
            "Turns illustrations into print-ready paper miniatures.<br><br>"
            "The default background-removal model, BRIA RMBG-1.4, is licensed for "
            "<b>non-commercial use only</b>: you are responsible for not using it "
            "commercially, for example to make minis you sell. The BiRefNet models are "
            "MIT-licensed, also for commercial use.<br><br>"
            f"{self._font_note()}<br><br>"
            "Projects are saved as batch YAML files, so you can also run them from the "
            "command line: <code>papermini batch project.yaml</code>"
        )
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setFixedWidth(400)
        text.linkActivated.connect(self._open_font_folder)
        col.addSpacing(4)
        col.addWidget(text)
        col.addWidget(self._log_label())
        top.addLayout(col, 1)
        v.addLayout(top)

        buttons = QHBoxLayout()  # what you can do about the update, beside Close
        buttons.addStretch(1)
        self.action = QPushButton()
        self.action.setProperty("primary", True)
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.clicked.connect(self._act)
        self.action.hide()
        close = QPushButton("Close")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.reject)
        buttons.addWidget(self.action)
        buttons.addWidget(close)
        v.addLayout(buttons)
        self._do = None

    @staticmethod
    def _font_note() -> str:
        """Name the fonts that come with papermini and their licence, with a link to
        their folder."""
        names = list(FontLibrary.BUNDLED)
        listed = ", ".join(names[:-1]) + " and " + names[-1]
        return (
            f"The fonts {html.escape(listed)} come with papermini. They are free fonts "
            "under the SIL Open Font License, also for commercial use. Each font's "
            "licence (OFL.txt) is in its folder: <a href='fonts'>open the font "
            "folder</a>."
        )

    @staticmethod
    def _open_font_folder(_link: str = "") -> None:
        """Open the folder of the fonts that come with papermini and their licences."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(FontLibrary.FOLDER)))

    def _log_label(self) -> QLabel:
        """Where this session's log is, as a link that opens the log folder."""
        from ..errors import open_log_folder

        s = self._logs.session()
        if s is None:
            label = QLabel("papermini could not write a log this time.")
        else:
            folder = html.escape(LogSession.redact(str(s.log.parent)))
            label = QLabel(
                f"Log: <a href='#'>{folder}</a><br>"
                f"<span style='font-size:small'>{html.escape(s.log.name)}</span>"
            )
            label.setTextFormat(Qt.RichText)
            label.linkActivated.connect(lambda _: open_log_folder(self._logs))
            label.setToolTip("Open the log folder")
        label.setWordWrap(True)
        label.setFixedWidth(400)
        return label

    def _offer(self, text: str, do=None):
        self.action.setText(text)
        self._do = do
        self.action.setVisible(do is not None)

    def _act(self):
        if self._do is not None:
            self._do()

    def update_state(self, state: UpdateState, data):
        """Show a state of the update check, with its payload, and offer the action
        that fits it."""
        self.progress.setVisible(state.busy)
        if not state.busy:
            self._offer("")
        if state is UpdateState.CHECKING:
            self.status.setText("Checking for updates…")
        elif state is UpdateState.LATEST:
            self.status.setText("This is the latest version.")
        elif state is UpdateState.AVAILABLE:
            rel, why = data.release, data.why
            if why is None:
                self.status.setText(
                    f"<b>papermini {html.escape(rel.version)}</b> is available."
                )
                self._offer("Update", lambda: self.updateRequested.emit(rel))
            else:
                self.status.setText(
                    f"<b>papermini {html.escape(rel.version)}</b> is "
                    f"available. {html.escape(why)}"
                )
                self._offer("Release page", self.releasePageRequested.emit)
        elif state is UpdateState.DOWNLOADING:
            self._offer("")
            self.status.setText(f"Downloading papermini {html.escape(data.version)}…")
            self.progress.setRange(0, 0)  # (busy, until the size is known)
        elif state is UpdateState.PROGRESS:
            done, total = data.done, data.total
            if total:
                self.progress.setRange(0, 1000)
                self.progress.setValue(int(1000 * done / total))
                self.progress.setFormat(f"{done / 1e6:.0f} of {total / 1e6:.0f} MB")
        elif state in (UpdateState.VERIFYING, UpdateState.UNPACKING):
            self.status.setText(
                "Checking the download…"
                if state is UpdateState.VERIFYING
                else "Unpacking the update…"
            )
            self.progress.setRange(0, 0)
        elif state is UpdateState.READY:
            self.status.setText(
                f"<b>papermini {html.escape(data.version)}</b> is ready: it is "
                "installed when you close papermini."
            )
            self._offer(
                "Restart now", lambda: (self.accept(), self.restartRequested.emit())
            )
        elif state is UpdateState.ERROR:
            self.status.setText(html.escape(str(data)))
            self._offer(
                "Try again",
                lambda: (
                    self.update_state(UpdateState.CHECKING, None),
                    self.checkRequested.emit(),
                ),
            )
        self.adjustSize()  # (the notice may now take more lines)
