"""Starts the desktop app."""

from __future__ import annotations

import sys


def run(files: list[str] | None = None) -> int:
    from PySide6 import __version__ as qt_version
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from ..support import log

    log.start(qt_version)  # first, so start-up problems are in the log
    app = QApplication.instance() or QApplication(sys.argv[:1])
    from . import error_handler, errors

    handler = error_handler.install()
    try:
        w = _start(app, files)
    except Exception:  # noqa: BLE001 - shown with Quit, then papermini exits
        handler.report_exception(*sys.exc_info())
        QApplication.processEvents()  # (the dialog comes through a queued signal)
        return 1
    handler.started(w)
    QTimer.singleShot(0, lambda: errors.offer_crash_report(w))
    return app.exec()


def _start(app, files):
    """Set up the application and show the main window (with ``files`` opened)."""
    from .window.main_window import MainWindow

    app.setApplicationName("papermini")
    app.setOrganizationName("papermini")
    if sys.platform == "win32":
        # its own taskbar entry and icon, not those of python.exe
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("papermini")
    from ..pipeline.pipeline import Pipeline
    from ..project.project_store import ProjectStore
    from ..project.size_calculator import SizeCalculator
    from . import theme
    from .preferences import Preferences

    prefs = Preferences()
    size_calculator = SizeCalculator()
    theme.apply(app, prefs.theme())
    app.setWindowIcon(theme.app_icon())
    w = MainWindow(prefs, ProjectStore(size_calculator), size_calculator, Pipeline())
    if files:
        w.open_paths(files)
    w.show()
    return w


def main() -> int:
    return run(sys.argv[1:])
