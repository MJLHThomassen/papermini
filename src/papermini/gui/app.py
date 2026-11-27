from __future__ import annotations

import sys


class App:
    """The desktop app: creates its services and the main window, and passes the
    services in."""

    def run(self, files: list[str] | None = None) -> int:
        """Start the app with ``files`` opened, and wait until it closes."""
        from PySide6 import __version__ as qt_version
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from ..support.log_session import LogSession
        from ..support.update_service import UpdateService

        updates = UpdateService()
        logs = LogSession(updates)
        logs.start(qt_version)  # first, so start-up problems are in the log
        app = QApplication.instance() or QApplication(sys.argv[:1])
        from .error_handler import ErrorHandler
        from .problem_reporter import ProblemReporter

        problems = ProblemReporter(logs)
        handler = ErrorHandler(logs, problems)
        handler.install()
        try:
            w = self._start(app, files, updates, logs, problems)
        except Exception:  # noqa: BLE001 - shown with Quit, then papermini exits
            handler.report_exception(*sys.exc_info())
            QApplication.processEvents()  # (the dialog comes through a queued signal)
            return 1
        handler.started(w)
        QTimer.singleShot(0, lambda: problems.offer_crash_report(w))
        return app.exec()

    @staticmethod
    def main() -> int:
        """Start the app with the files on the command line."""
        return App().run(sys.argv[1:])

    def _start(self, app, files, updates, logs, problems):
        """Set up the application and show the main window (with ``files`` opened), with
        the services the app shares."""
        from .window.main_window import MainWindow

        app.setApplicationName("papermini")
        app.setOrganizationName("papermini")
        if sys.platform == "win32":
            # its own taskbar entry and icon, not those of python.exe
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("papermini")
        from ..output.output import Output
        from ..pipeline.pipeline import Pipeline
        from ..project.figure_builder import FigureBuilder
        from ..project.project_store import ProjectStore
        from ..project.size_calculator import SizeCalculator
        from ..project.style_preset_file import StylePresetFile
        from ..support.font_library import FontLibrary
        from ..support.image_fetcher import ImageFetcher
        from .preferences import Preferences
        from .style_library import StyleLibrary
        from .theme_service import ThemeService
        from .views.mini_renderer import MiniRenderer
        from .views.qt_fonts import QtFonts
        from .views.qt_images import QtImages
        from .views.sheet_renderer import SheetRenderer

        prefs = Preferences()
        size_calculator = SizeCalculator()
        fonts = FontLibrary()
        images_from_web = ImageFetcher()
        pipeline = Pipeline(fonts)
        themes = ThemeService()
        qt_fonts = QtFonts(fonts)
        images = QtImages()
        minis = MiniRenderer(fonts, qt_fonts, themes, images)
        themes.apply(app, prefs.theme())
        app.setWindowIcon(themes.app_icon())
        w = MainWindow(
            prefs,
            ProjectStore(size_calculator, images_from_web),
            size_calculator,
            pipeline,
            FigureBuilder(pipeline),
            fonts,
            Output(fonts),
            images_from_web,
            updates,
            logs,
            themes,
            qt_fonts,
            images,
            minis,
            SheetRenderer(minis),
            problems,
            StyleLibrary(prefs),
            StylePresetFile(),
        )
        if files:
            w.open_paths(files)
        w.show()
        return w
