from __future__ import annotations

from papermini.gui.window.main_window import MainWindow

from .shot_context import FLYING, RED, ShotContext
from .window_driver import WindowDriver


class AppShots:
    """Screenshots of the whole window: the flying dragon being edited, and the sheet
    with all three figures."""

    def __init__(self, ctx: ShotContext, windows: WindowDriver):
        self._ctx = ctx
        self._windows = windows

    def run(self) -> None:
        """Save the screenshots of the window."""
        self._shot("light", "app-miniature", FLYING, MainWindow.MINI)
        self._shot("light", "app-source", FLYING, MainWindow.SOURCE)
        self._shot("light", "app-sheet", FLYING, MainWindow.SHEET)
        self._shot("dark", "app-dark", RED, MainWindow.MINI)

    def _shot(self, mode: str, name: str, row: int, tab: int) -> None:
        w = self._windows.open(mode)
        self._windows.show(w, row, tab)
        self._ctx.save(w.grab(), name)
        self._windows.close(w)
