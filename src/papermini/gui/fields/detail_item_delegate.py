from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from ..theme_service import ThemeService

# the role that holds an item's detail lines, separated by newlines
DETAIL_ROLE = Qt.ItemDataRole.UserRole + 1
_PAD_X, _PAD_Y = 8, 5  # space around an item's text, in px
_GAP = 2  # space between the name and the detail lines, in px


class DetailItemDelegate(QStyledItemDelegate):
    """Draws a list item as its name with muted detail lines under it."""

    def __init__(self, themes: ThemeService, parent=None):
        super().__init__(parent)
        self._themes = themes

    def sizeHint(self, option, index):
        name, lines = self._texts(index)
        bold = QFontMetrics(self._bold(option.font))
        plain = QFontMetrics(option.font)
        width = max(
            [bold.horizontalAdvance(name)] + [plain.horizontalAdvance(s) for s in lines]
        )
        height = bold.height() + (_GAP + plain.height() * len(lines) if lines else 0)
        return QSize(width + 2 * _PAD_X, height + 2 * _PAD_Y)

    def paint(self, p: QPainter, option, index):
        t = self._themes.current
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(1, 1, -1, -1)
        if option.state & (
            QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver
        ):
            path = QPainterPath()
            path.addRoundedRect(r, 5, 5)
            p.fillPath(path, QColor(t.accent_soft))
        name, lines = self._texts(index)
        x, y, w = r.left() + _PAD_X, r.top() + _PAD_Y, r.width() - 2 * _PAD_X
        p.setFont(self._bold(option.font))
        p.setPen(QColor(t.text))
        height = p.fontMetrics().height()
        p.drawText(
            QRectF(x, y, w, height),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )
        y += height + _GAP
        p.setFont(option.font)
        p.setPen(QColor(t.muted))
        height = p.fontMetrics().height()
        for line in lines:
            p.drawText(
                QRectF(x, y, w, height),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                line,
            )
            y += height
        p.restore()

    @staticmethod
    def _texts(index) -> tuple[str, list[str]]:
        name = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        return name, str(index.data(DETAIL_ROLE) or "").splitlines()

    @staticmethod
    def _bold(font: QFont) -> QFont:
        bold = QFont(font)
        bold.setWeight(QFont.Weight.DemiBold)
        return bold
