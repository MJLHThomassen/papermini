"""Catches the app's unexpected errors, logs them and shows them in a dialog."""

from __future__ import annotations

import logging
import os
import sys
import threading
import traceback

from PySide6.QtCore import QObject, QtMsgType, Signal, qInstallMessageHandler

from ..support import log
from .dialogs.error_dialog import ErrorDialog
from .errors import report_problem

logger = logging.getLogger("papermini.error")
qt_logger = logging.getLogger("papermini.qt")

_QT_LEVELS = {
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}


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

    # region catching
    def _excepthook(self, etype, value, tb):
        if issubclass(etype, KeyboardInterrupt):
            return sys.__excepthook__(etype, value, tb)
        self.report_exception(etype, value, tb)

    def _threadhook(self, args):
        if args.exc_type is SystemExit:
            return
        self.report_exception(
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
            f" in thread {args.thread.name}" if args.thread else "",
        )

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

    # endregion

    # region the dialog
    def _show(self, key: str, summary: str, details: str) -> None:
        if self.showing or (key in self.shown and not self.starting):
            return  # (it is in the log)
        self.shown.add(key)
        self.showing = True
        try:
            quit_ = self.starting
            box = ErrorDialog(
                self.window, log.redact(summary), log.redact(details), quit_
            )
            box.exec()
            if box.reported:
                report_problem(self.window, details)
        finally:
            self.showing = False
        if quit_:
            log.stop()
            os._exit(1)

    # endregion


_handler: ErrorHandler | None = None


def install() -> ErrorHandler:
    """Catch, log and show the app's unexpected errors from now on (once)."""
    global _handler
    if _handler is None:
        _handler = ErrorHandler()
        _handler.install()
    return _handler
