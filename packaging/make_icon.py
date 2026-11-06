"""Render the app icon (packaging/icon.png) from the logo in the GUI theme.

    python packaging/make_icon.py

PyInstaller converts the PNG to .ico (Windows) and .icns (macOS) at build time.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from PySide6.QtCore import QByteArray, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

from papermini.gui import theme  # noqa: E402  (accent colour)

SIZE = 1024


def main() -> None:
    app = QGuiApplication([])  # noqa: F841 - needed for painting
    img = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    # rounded square in the accent colour (macOS-style proportions: ~10% inset)
    inset = SIZE * 0.08
    tile = QRectF(inset, inset, SIZE - 2 * inset, SIZE - 2 * inset)
    path = QPainterPath()
    path.addRoundedRect(tile, tile.width() * 0.22, tile.width() * 0.22)
    p.fillPath(path, QColor(theme.LIGHT.accent))
    # the logo in white, with a heavier stroke so it reads at small sizes
    # (same ghost as the "logo" theme icon, cropped, with solid eyes)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="4.5 4.5 15 18" fill="none" '
           'stroke="#ffffff" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
           '<path d="M8 19.5V9.5a4 4 0 0 1 8 0v10l-2-1.4-2 1.4-2-1.4z"/>'
           '<circle cx="10.5" cy="10.2" r="0.9" fill="#ffffff" stroke="none"/>'
           '<circle cx="13.5" cy="10.2" r="0.9" fill="#ffffff" stroke="none"/>'
           '<path d="M5.5 21.5h13"/></svg>')
    m = tile.width() * 0.2
    logo = QRectF(0, 0, tile.width() - 2 * m, (tile.width() - 2 * m) * 18 / 15)
    logo.moveCenter(tile.center())
    QSvgRenderer(QByteArray(svg.encode())).render(p, logo)
    p.end()
    out = HERE / "icon.png"
    img.save(str(out))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
