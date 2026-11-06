"""Desktop app (Qt / PySide6). Start with ``papermini gui`` or ``papermini-gui``."""

from __future__ import annotations

import sys
from typing import List, Optional


def run(files: Optional[List[str]] = None) -> int:
    from PySide6.QtWidgets import QApplication

    from .window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("papermini")
    app.setOrganizationName("papermini")
    from . import prefs

    from . import theme

    theme.apply(app, prefs.store().value("theme", "system", type=str))
    w = MainWindow()
    if files:
        w.open_paths(files)
    w.show()
    return app.exec()


def main() -> int:
    return run(sys.argv[1:])
