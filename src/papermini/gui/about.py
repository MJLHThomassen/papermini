"""The About window: the version, whether a newer papermini is out (with Update and its
progress), and the licences."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLayout, QProgressBar,
                               QPushButton, QVBoxLayout)

from .. import __version__, fonts
from . import theme


def _font_note() -> str:
    """The fonts that come with papermini, their licence, and a link to their folder."""
    names = [f.name for f in fonts.bundled() if f.regular is not None]
    listed = ", ".join(names[:-1]) + " and " + names[-1]
    return (f"The fonts {html.escape(listed)} come with papermini. They are free fonts "
            "under the SIL Open Font License, also for commercial use. Each font's "
            "licence (OFL.txt) is in its folder: <a href='fonts'>open the font folder</a>.")


def open_font_folder(_link: str = "") -> None:
    """Open the folder of the fonts that come with papermini (and their licences)."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(fonts.HERE)))


class AboutDialog(QDialog):
    """A dialog with the app's version and licences, and the state of the update check
    under the version, with the one action that fits that state (download, restart,
    open the release page or check again). The main window keeps the state current
    through ``update_state``."""

    def __init__(self, window):
        super().__init__(window)
        self.window_ = window
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
        self.status.setObjectName("MethodBox")  # (the same framed note as Chosen method)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        self.status.setFixedWidth(400)  # (a wrapping label needs a fixed width for its height)
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
            f"{_font_note()}<br><br>"
            "Projects are saved as batch YAML files, so you can also run them from the "
            "command line: <code>papermini batch project.yaml</code>")
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setFixedWidth(400)
        text.linkActivated.connect(open_font_folder)
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
    def _log_label() -> QLabel:
        """Where this session's log is, as a link that opens the log folder."""
        from .. import log
        from .errors import open_log_folder

        s = log.session()
        if s is None:
            label = QLabel("papermini could not write a log this time.")
        else:
            folder = html.escape(log.redact(str(s.log.parent)))
            label = QLabel(f"Log: <a href='#'>{folder}</a><br>"
                           f"<span style='font-size:small'>{html.escape(s.log.name)}</span>")
            label.setTextFormat(Qt.RichText)
            label.linkActivated.connect(lambda _: open_log_folder())
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

    def update_state(self, state: str, data, version: str = ""):
        """Show a state of the update check (the main window's states, see its
        check_updates) and offer the action that fits it."""
        w = self.window_
        busy = state in ("downloading", "progress", "verifying", "unpacking")
        self.progress.setVisible(busy)
        if not busy:
            self._offer("")
        if state == "checking":
            self.status.setText("Checking for updates…")
        elif state == "latest":
            self.status.setText("This is the latest version.")
        elif state == "available":
            rel, why = data
            if why is None:
                self.status.setText(f"<b>papermini {html.escape(rel.version)}</b> is "
                                    "available.")
                self._offer("Update", lambda: w.download_update(rel, "about"))
            else:
                self.status.setText(f"<b>papermini {html.escape(rel.version)}</b> is "
                                    f"available. {html.escape(why)}")
                self._offer("Release page", w._open_release_page)
        elif state == "downloading":
            self._offer("")
            self.status.setText(f"Downloading papermini {html.escape(data.version)}…")
            self.progress.setRange(0, 0)  # (busy, until the size is known)
        elif state == "progress":
            done, total = data
            if total:
                self.progress.setRange(0, 1000)
                self.progress.setValue(int(1000 * done / total))
                self.progress.setFormat(f"{done / 1e6:.0f} of {total / 1e6:.0f} MB")
        elif state in ("verifying", "unpacking"):
            self.status.setText("Checking the download…" if state == "verifying"
                                else "Unpacking the update…")
            self.progress.setRange(0, 0)
        elif state == "ready":
            version = version or data[0].version
            self.status.setText(f"<b>papermini {html.escape(version)}</b> is ready: it is "
                                "installed when you close papermini.")
            self._offer("Restart now", lambda: (self.accept(), w._restart_for_update()))
        elif state == "error":
            self.status.setText(html.escape(str(data)))
            self._offer("Try again", lambda: (self.update_state("checking", None),
                                              w.check_updates(source="about")))
        self.adjustSize()  # (the notice may now take more lines)
