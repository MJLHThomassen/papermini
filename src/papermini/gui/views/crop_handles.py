from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsScene

from .crop_style import CROP_COLOR, DRAG_PX, HANDLE_PX


class CropHandles:
    """The square handles on a box that the mouse resizes in a zoom view.

    The handles keep their size on screen at any zoom. The class also tells a drag
    from a click, and builds a figure's outline as a path.
    """

    ALL = ("tl", "t", "tr", "r", "br", "b", "bl", "l")
    CORNERS = ("tl", "tr", "br", "bl")

    def __init__(self, scene: QGraphicsScene, names: tuple[str, ...], z: float):
        """Add a handle for each of ``names`` to ``scene``, at height ``z``."""
        self._items: dict[str, QGraphicsRectItem] = {}
        for name in names:
            h = scene.addRect(
                QRectF(-HANDLE_PX / 2, -HANDLE_PX / 2, HANDLE_PX, HANDLE_PX),
                QPen(QColor("#222"), 1),
                QBrush(QColor(CROP_COLOR)),
            )
            h.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
            h.setZValue(z)
            self._items[name] = h

    def place(self, r: QRectF) -> None:
        """Move the handles onto the box ``r``."""
        points = self.points(r)
        for name, h in self._items.items():
            h.setPos(points[name])

    def set_visible(self, visible: bool) -> None:
        for h in self._items.values():
            h.setVisible(visible)

    @staticmethod
    def points(r: QRectF, names: tuple[str, ...] = ALL) -> dict[str, QPointF]:
        """Return where each of ``names`` sits on the box ``r``: a corner, or the
        middle of an edge."""
        c = r.center()
        every = {
            "tl": r.topLeft(),
            "t": QPointF(c.x(), r.top()),
            "tr": r.topRight(),
            "r": QPointF(r.right(), c.y()),
            "br": r.bottomRight(),
            "b": QPointF(c.x(), r.bottom()),
            "bl": r.bottomLeft(),
            "l": QPointF(r.left(), c.y()),
        }
        return {name: every[name] for name in names}

    @staticmethod
    def is_drag(moved: QPoint) -> bool:
        """Tell whether the mouse moved far enough since its press (``moved``, view
        pixels) for a drag; a shorter move is a click."""
        return max(abs(moved.x()), abs(moved.y())) >= DRAG_PX

    @staticmethod
    def outline_path(contours) -> QPainterPath:
        """Return the closed path through the figure's outer edges and holes (point
        arrays); the holes are left out of its inside."""
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        for c in contours:
            path.moveTo(*c[0])
            for x, y in c[1:]:
                path.lineTo(x, y)
            path.closeSubpath()
        return path
