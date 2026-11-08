"""Render the app icon (packaging/icon.png) from the logo (src/papermini/gui/logo.svg).

    python packaging/make_icon.py

PyInstaller converts the PNG to .ico (Windows) and .icns (macOS) at build time.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

from papermini.gui.theme import LOGO  # noqa: E402

SIZE = 1024
MARGIN = 0.03  # the logo's white sticker border already gives it room


def main() -> None:
    app = QGuiApplication([])  # noqa: F841 - needed for painting
    img = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    r = QSvgRenderer(str(LOGO))
    vb = r.viewBoxF()
    k = SIZE * (1 - 2 * MARGIN) / max(vb.width(), vb.height())
    w, h = vb.width() * k, vb.height() * k
    p = QPainter(img)
    r.render(p, QRectF((SIZE - w) / 2, (SIZE - h) / 2, w, h))
    p.end()
    out = HERE / "icon.png"
    img.save(str(out))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
