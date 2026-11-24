from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt

from papermini.gui.preferences import Preferences
from papermini.gui.step import Step
from papermini.gui.window.main_window import MainWindow

from .shot_context import ShotContext

WINDOW_SIZE = (1360, 820)  # logical pixels


class WindowDriver:
    """Opens the project in a main window off-screen, and puts the window in the
    state a picture needs."""

    def __init__(self, ctx: ShotContext):
        self._ctx = ctx

    def open(self, mode: str, size: tuple[int, int] = WINDOW_SIZE) -> MainWindow:
        """Open the project in a window with the theme ``mode``, once every figure is
        built."""
        ctx = self._ctx
        ctx.themes.apply(ctx.app, mode)
        w = MainWindow(
            Preferences(),
            ctx.project_store,
            ctx.size_calculator,
            ctx.pipeline,
            ctx.figure_builder,
            ctx.fonts,
            ctx.output,
            ctx.images_from_web,
            ctx.updates,
            ctx.logs,
            ctx.themes,
            ctx.qt_fonts,
            ctx.images,
            ctx.minis,
            ctx.sheets,
            ctx.problems,
        )
        w.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
        w.resize(*size)
        w.show()
        w.load(ctx.project)
        w.tabs.setCurrentIndex(Step.SHEET)  # the sheet builds every figure
        ctx.settle(lambda: all(f.up_to_date for f in w.figures))
        return w

    def show(self, w: MainWindow, row: int, tab: int) -> None:
        """Select the figure in ``row`` and open ``tab``, fitted to the window."""
        w.list.setCurrentRow(row)
        w.tabs.setCurrentIndex(tab)
        self._ctx.settle(
            lambda: all(f.up_to_date for f in [w.current()] if f is not None)
        )
        self._fit(w)

    def change(self, w: MainWindow, **settings) -> None:
        """Change the selected figure's ``settings`` and wait until it is rebuilt."""
        fig = w.current()
        assert fig is not None, "no figure is selected"
        w.apply_settings(replace(fig.entry.settings, **settings))
        self._ctx.settle(lambda: fig.up_to_date)
        self._fit(w)

    def close(self, w: MainWindow) -> None:
        """Close ``w`` without saving."""
        w.discard_changes()
        w.close()

    def _fit(self, w: MainWindow) -> None:
        w.fit_view()
        self._ctx.settle()
