from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsView

from papermini.gui import theme

from .panel import Panel

PAD = 16  # logical pixels around and between the panels
HEAD = 52  # the height of a panel's title and caption
MIN_WIDTH = 260  # a panel's least width, so that its caption fits


class PictureComposer:
    """Puts pictures side by side, and cuts pictures out of views."""

    def __init__(self, ratio: float):
        self._ratio = ratio  # device pixels per logical pixel

    def panels(self, items: Sequence[Panel]) -> QImage:
        """Put ``items`` side by side in the light theme, each with its title and
        caption above it and centred in a row as high as the highest."""
        t = theme.resolve("light")
        sizes = [item.pixmap.deviceIndependentSize() for item in items]
        height = max(size.height() for size in sizes)
        total = PAD + sum(max(size.width(), MIN_WIDTH) + PAD for size in sizes)
        out = QImage(
            int(total * self._ratio),
            int((HEAD + height + PAD) * self._ratio),
            QImage.Format.Format_ARGB32,
        )
        out.setDevicePixelRatio(self._ratio)
        out.fill(QColor(t.bg))
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bold, small = QFont(), QFont()
        bold.setPointSizeF(11.5)
        bold.setBold(True)
        small.setPointSizeF(9.5)
        x = PAD
        for item, size in zip(items, sizes):
            width = max(size.width(), MIN_WIDTH)
            p.setPen(QColor(t.text))
            p.setFont(bold)
            p.drawText(
                QRectF(x, 6, width, 24),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                item.title,
            )
            p.setPen(QColor(t.muted))
            p.setFont(small)
            p.drawText(
                QRectF(x, 28, width, 20),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                item.caption,
            )
            p.drawPixmap(
                QPointF(
                    x + (width - size.width()) / 2,
                    HEAD + (height - size.height()) / 2,
                ),
                item.pixmap,
            )
            x += width + PAD
        p.end()
        return out

    def view_shot(
        self,
        view: QGraphicsView,
        scene_rect: QRectF,
        pad: int = 28,
        paint: Callable[[QPainter], None] | None = None,
    ) -> QPixmap:
        """Grab the part of ``view`` around ``scene_rect``, with ``pad`` pixels more
        for its shadow. ``paint(painter)`` draws on top, in view coordinates."""
        vp = view.viewport()
        r = view.mapFromScene(scene_rect).boundingRect().adjusted(-pad, -pad, pad, pad)
        r = r.intersected(vp.rect())
        pix = vp.grab(r)
        if paint is not None:
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.translate(-r.x(), -r.y())
            paint(p)
            p.end()
        return pix
