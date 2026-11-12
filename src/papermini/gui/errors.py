"""Unexpected errors in the desktop app: write them to the log, show them in a dialog
with Report a problem…, and keep running. Also the crash offer at start and the report
itself (a prefilled GitHub issue, plus the log folder to attach the log from)."""

from __future__ import annotations

import logging
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Qt, QtMsgType, QTimer, QUrl, Signal, qInstallMessageHandler
from PySide6.QtGui import QDesktopServices, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QPushButton, QStyle, QVBoxLayout)

from .. import log

logger = logging.getLogger("papermini.error")
qt_logger = logging.getLogger("papermini.qt")

_QT_LEVELS = {QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}


class ErrorDialog(QDialog):
    """"Something went wrong": what happened in a sentence, the traceback folded away
    (Show details unfolds it in a large box, and the window can then be resized), and
    Report a problem… beside Continue (or Quit while papermini is starting). After
    ``exec()``, ``reported`` says whether Report a problem… was clicked."""

    def __init__(self, parent, summary: str, details: str, quit_: bool = False):
        super().__init__(parent)
        self.setWindowTitle("papermini")
        self.setObjectName("ErrorDialog")
        self.reported = False
        v = QVBoxLayout(self)
        v.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(14)
        icon = QLabel()
        icon.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxCritical).pixmap(40, 40))
        icon.setAlignment(Qt.AlignTop)
        top.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(8)
        title = QLabel("<b>Something went wrong</b>")
        title.setTextFormat(Qt.RichText)
        col.addWidget(title)
        if quit_:
            what = ("papermini ran into an unexpected problem while starting and cannot "
                    "continue. It has been written to the log.")
        else:
            what = ("papermini ran into an unexpected problem. It has been written to the "
                    "log. You can keep working, but save your project soon.")
        for text in (what, summary):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setMinimumWidth(380)
            col.addWidget(label)
        col.addStretch(1)
        top.addLayout(col, 1)
        v.addLayout(top)

        self.details = QPlainTextEdit(details)
        self.details.setObjectName("ErrorDetails")
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.details.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.details.setMinimumSize(320, 160)
        self.details.hide()
        v.addWidget(self.details, 1)

        buttons = QHBoxLayout()
        self.toggle = QPushButton("Show details")
        self.toggle.clicked.connect(self._toggle_details)
        self.copy = QPushButton("Copy details")
        self.copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(details))
        self.copy.hide()
        report = QPushButton("Report a problem…")
        report.clicked.connect(self._report)
        go_on = QPushButton("Quit" if quit_ else "Continue")
        go_on.setProperty("primary", True)
        go_on.clicked.connect(self.accept)
        go_on.setDefault(True)
        for b in (self.toggle, self.copy):
            buttons.addWidget(b)
        buttons.addStretch(1)
        for b in (report, go_on):
            buttons.addWidget(b)
        for b in (self.toggle, self.copy, report, go_on):
            b.setCursor(Qt.PointingHandCursor)
        v.addLayout(buttons)
        self.setSizeGripEnabled(True)

    def _report(self):
        self.reported = True
        self.accept()

    def _toggle_details(self):
        show = not self.details.isVisible()
        self.details.setVisible(show)
        self.copy.setVisible(show)
        self.toggle.setText("Hide details" if show else "Show details")
        if show:  # room for a traceback, within the screen
            screen = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
            self.resize(min(max(self.width(), 760), screen.width() - 80),
                        min(max(self.height(), 520), screen.height() - 80))
        else:
            QTimer.singleShot(0, lambda: self.resize(self.minimumSizeHint()))


class _Reporter(QObject):
    """Brings errors from any thread to the GUI thread, where the dialog is shown."""

    error = Signal(str, str, str)  # (key: type and place, one-line summary, traceback)


class ErrorHandler:
    """Catches the errors nothing else caught (``sys.excepthook``, ``threading.excepthook``
    and Qt's warnings), logs them, and shows one dialog at a time: each error (its type
    and place) once per session, logged every time. Until ``started()`` is called (the
    window is up) the dialog offers Quit instead of Continue."""

    def __init__(self):
        self.window = None
        self.starting = True
        self.showing = False
        self.shown = set()
        self.reporter = _Reporter()
        self.reporter.error.connect(self._show)

    def install(self) -> None:
        sys.excepthook = self._excepthook
        threading.excepthook = self._threadhook
        qInstallMessageHandler(self._qt_message)

    def started(self, window) -> None:
        self.window, self.starting = window, False

    # ------------------------------------------------------------ catching
    def _excepthook(self, etype, value, tb):
        if issubclass(etype, KeyboardInterrupt):
            return sys.__excepthook__(etype, value, tb)
        self.report_exception(etype, value, tb)

    def _threadhook(self, args):
        if args.exc_type is SystemExit:
            return
        self.report_exception(args.exc_type, args.exc_value, args.exc_traceback,
                              f" in thread {args.thread.name}" if args.thread else "")

    def _qt_message(self, mode, context, message):
        level = _QT_LEVELS.get(mode)
        if level is not None:
            where = f" ({context.file}:{context.line})" if context.file else ""
            qt_logger.log(level, "%s%s", message, where)

    def report_exception(self, etype, value, tb, where: str = "") -> None:
        """Log an uncaught exception with its traceback, and show the dialog for it."""
        logger.error("Unexpected error%s", where, exc_info=(etype, value, tb))
        frames = traceback.extract_tb(tb)
        place = f"{frames[-1].filename}:{frames[-1].lineno}" if frames else ""
        details = "".join(traceback.format_exception(etype, value, tb))
        summary = f"{etype.__name__}: {value}".strip().rstrip(":")
        self.reporter.error.emit(f"{etype.__name__}@{place}", summary, details)

    # ------------------------------------------------------------ the dialog
    def _show(self, key: str, summary: str, details: str) -> None:
        if self.showing or (key in self.shown and not self.starting):
            return  # (it is in the log)
        self.shown.add(key)
        self.showing = True
        try:
            quit_ = self.starting
            box = ErrorDialog(self.window, log.redact(summary), log.redact(details), quit_)
            box.exec()
            if box.reported:
                report_problem(self.window, details)
        finally:
            self.showing = False
        if quit_:
            log.stop()
            os._exit(1)


_handler: Optional[ErrorHandler] = None


def install() -> ErrorHandler:
    """Catch, log and show the app's unexpected errors from now on (once)."""
    global _handler
    if _handler is None:
        _handler = ErrorHandler()
        _handler.install()
    return _handler


# ------------------------------------------------------------ reporting
def open_log_folder() -> None:
    s = log.session()
    folder = s.log.parent if s else log.log_dir()
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def report_problem(parent=None, details: str = "", files: Optional[List[Path]] = None) -> None:
    """Open a new bug report on GitHub with the version, the operating system and how
    papermini runs filled in (and ``details``, a traceback, when given), open the log
    folder, and say which file to attach: ``files``, or the newest log."""
    QDesktopServices.openUrl(QUrl(log.issue_url(details), QUrl.StrictMode))
    s = log.session()
    if files is None:
        files = [s.log] if s else []
    if files:
        open_log_folder()
        names = "\n".join(f"  {f.name}" for f in files)
        text = ("A new issue opened in your browser. Describe what happened and how to make "
                "it happen again, then drag this from the log folder into its Log file "
                f"field:\n\n{names}")
    else:
        text = ("A new issue opened in your browser. Describe what happened and how to make "
                "it happen again. (papermini could not write a log this time.)")
    QMessageBox.information(parent, "Report a problem", text)


def offer_crash_report(parent=None) -> None:
    """At start: offer to report the newest crash of an earlier session, once. Every
    crash found is marked as offered, whatever the answer."""
    found = log.crashes()
    if not found:
        return
    crash, crash_log = found[0]
    box = QMessageBox(QMessageBox.Warning, "papermini", "papermini closed unexpectedly",
                      parent=parent)
    box.setInformativeText("The last time, papermini stopped because of a problem. "
                           "Reporting it helps to get it fixed.")
    report = box.addButton("Report a problem…", QMessageBox.AcceptRole)
    box.addButton("Not now", QMessageBox.RejectRole)
    box.exec()
    for c, _ in found:
        log.mark_offered(c)
    if box.clickedButton() is report:
        done = log.reported(crash)
        files = [done if done.exists() else crash]
        if crash_log.exists():
            files.append(crash_log)
        report_problem(parent, files=files)

