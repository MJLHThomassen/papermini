"""Regenerate the README screenshots of the desktop app from the sample project.

    python scripts/screenshots.py            # writes docs/screenshots/*.png

Renders off-screen at 1.5x scale with an English locale and default preferences
(a temporary settings folder), so the result does not depend on your own setup.
The first run builds the sample miniatures, which needs the segmentation model.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "screenshots")
    ap.add_argument("--project", type=Path, default=ROOT / "examples" / "sample" / "sample.yaml")
    ap.add_argument("--scale", default="1.5", help="Qt scale factor (default 1.5)")
    args = ap.parse_args()

    os.environ["QT_SCALE_FACTOR"] = args.scale
    from PySide6.QtCore import QLocale, QSettings, Qt
    from PySide6.QtWidgets import QApplication

    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tempfile.mkdtemp("papermini"))

    sys.path.insert(0, str(ROOT / "src"))
    from papermini.gui import theme
    from papermini.gui.window import MainWindow

    args.out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])

    def settle(cond=lambda: True, timeout=300):
        end = time.time() + timeout
        while time.time() < end:
            app.processEvents()
            time.sleep(0.05)
            if cond():
                break
        for _ in range(10):
            app.processEvents()
            time.sleep(0.03)

    def shot(mode: str, name: str, row: int, tab: int):
        theme.apply(app, mode)
        w = MainWindow()
        w.setAttribute(Qt.WA_DontShowOnScreen)
        w.resize(1360, 820)
        w.show()
        w.load(args.project)
        w.tabs.setCurrentIndex(w.SHEET)  # the sheet builds every figure
        settle(lambda: all(f.up_to_date for f in w.figures))
        w.list.setCurrentRow(row)
        w.tabs.setCurrentIndex(tab)
        settle(lambda: all(f.up_to_date for f in [w.current()] if f is not None))
        w._fit()
        settle()
        path = args.out / f"{name}.png"
        w.grab().save(str(path))
        print(f"wrote {path}")
        w._modified = False
        w.close()

    # (theme, file name, figure row in the sample project, view: the workflow step,
    #  0 source, 1 miniature, 2 print sheet)
    shot("light", "app-source", 0, 0)
    shot("light", "app-miniature", 1, 1)
    shot("light", "app-sheet", 0, 2)
    shot("dark", "app-dark", 2, 1)


if __name__ == "__main__":
    main()
