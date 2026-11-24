from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSpinBox, QStyle, QStyledItemDelegate, QToolTip

from ..theme_service import ThemeService

SUBTITLE_ROLE = Qt.ItemDataRole.UserRole + 1
COPIES_ROLE = (
    Qt.ItemDataRole.UserRole + 2
)  # copies on the sheet (None: no copies control)
MAX_COPIES = 999


class FigureDelegate(QStyledItemDelegate):
    """Figure list entries as cards: thumbnail, name, a one-line status and the copies
    on the sheet (- n +: click - or +, or click the number to type one)."""

    H = 68
    TILE = 50  # thumbnail
    BTN, NUM = 18, 26  # copies control: button and number width (px)
    COPIES_TEXT = "Amount"  # right before the control, so it is clear what it counts
    COPIES_TIP = (
        "How many of this figure go on the print sheet.\n"
        "Click − or +, or click the number to type one."
    )
    copiesChanged = Signal(object, int)  # figure uid (Qt.ItemDataRole.UserRole), copies

    def __init__(self, themes: ThemeService, parent=None):
        super().__init__(parent)
        self._themes = themes

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.H)

    def copies_rects(self, rect):
        """Return the minus, number and plus rectangles of the copies control at the
        bottom right of the card in ``rect``."""
        r = QRectF(rect).adjusted(6, 3, -6, -3)
        y = r.top() + 33
        plus = QRectF(r.right() - 10 - self.BTN, y - 1, self.BTN, self.BTN)
        num = QRectF(plus.left() - self.NUM, y - 1, self.NUM, self.BTN)
        minus = QRectF(num.left() - self.BTN, y - 1, self.BTN, self.BTN)
        return minus, num, plus

    def _set_copies(self, index, n: int):
        n = max(0, min(MAX_COPIES, n))
        if n != index.data(COPIES_ROLE):
            self.copiesChanged.emit(index.data(Qt.ItemDataRole.UserRole), n)

    def editorEvent(self, event, model, option, index):
        n = index.data(COPIES_ROLE)
        if (
            n is not None
            and event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            minus, num, plus = self.copies_rects(option.rect)
            pos = event.position()
            if minus.contains(pos):
                self._set_copies(index, n - 1)
                return True
            if plus.contains(pos):
                self._set_copies(index, n + 1)
                return True
            if num.contains(pos):
                self.parent().edit(
                    index
                )  # (a spin box over the number, see createEditor)
                return True
        return super().editorEvent(event, model, option, index)

    def createEditor(self, parent, option, index):
        box = QSpinBox(parent)
        box.setRange(0, MAX_COPIES)  # (no arrows: the theme hides spin box buttons)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setObjectName("CopiesEditor")
        return box

    def setEditorData(self, editor, index):
        editor.setValue(index.data(COPIES_ROLE) or 0)
        editor.selectAll()

    def setModelData(self, editor, model, index):
        editor.interpretText()
        self._set_copies(index, editor.value())

    def updateEditorGeometry(self, editor, option, index):
        _, num, _ = self.copies_rects(option.rect)
        editor.setGeometry(num.toRect().adjusted(-2, -1, 2, 1))

    def paint(self, p: QPainter, option, index):
        t = self._themes.current
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(6, 3, -6, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            path = QPainterPath()
            path.addRoundedRect(r, 9, 9)
            p.fillPath(path, QColor(t.accent_soft if selected else t.surface2))
            if selected:
                p.setPen(QPen(QColor(t.accent), 1))
                p.drawPath(path)
        # thumbnail on a small canvas tile
        tile = QRectF(
            r.left() + 8, r.center().y() - self.TILE / 2, self.TILE, self.TILE
        )
        tp = QPainterPath()
        tp.addRoundedRect(tile, 7, 7)
        p.fillPath(tp, QColor(t.canvas))
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon is not None:
            pm = icon.pixmap(QSize(int(tile.width()) - 8, int(tile.height()) - 8))
            if not pm.isNull():
                s = pm.deviceIndependentSize()
                p.drawPixmap(
                    int(tile.center().x() - s.width() / 2),
                    int(tile.center().y() - s.height() / 2),
                    pm,
                )
        # text
        x = tile.right() + 12
        w = r.right() - x - 8
        copies = index.data(COPIES_ROLE)
        f = QFont(option.font)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(t.text))
        name = p.fontMetrics().elidedText(
            index.data(Qt.ItemDataRole.DisplayRole) or "",
            Qt.TextElideMode.ElideRight,
            int(w),
        )
        p.drawText(
            QRectF(x, r.top() + 13, w, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name,
        )
        p.setFont(option.font)
        p.setPen(QColor(t.muted))
        sub_w = w
        if copies is not None:  # when narrow, the height gives way, then COPIES_TEXT
            sub_w = max(0.0, w - self._copies_width(p, self._show_word(p, w)) - 8)
        sub = index.data(SUBTITLE_ROLE) or ""
        sub = p.fontMetrics().elidedText(sub, Qt.TextElideMode.ElideRight, int(sub_w))
        p.drawText(
            QRectF(x, r.top() + 33, sub_w, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            sub,
        )
        if copies is not None:
            self._paint_copies(p, option, copies, t, selected, self._show_word(p, w))
        p.restore()

    def helpEvent(self, event, view, option, index):
        if index.data(COPIES_ROLE) is not None:
            minus, _, plus = self.copies_rects(option.rect)
            area = minus.united(plus).adjusted(-60, -2, 0, 2)  # (COPIES_TEXT too)
            if area.contains(event.pos()):
                QToolTip.showText(event.globalPos(), self.COPIES_TIP, view)
                return True
        return super().helpEvent(event, view, option, index)

    def _copies_width(self, p: QPainter, word: bool = True) -> float:
        """Return the width of the control, with COPIES_TEXT before it when ``word``."""
        control = 2 * self.BTN + self.NUM
        return control + (
            p.fontMetrics().horizontalAdvance(self.COPIES_TEXT) + 6 if word else 0
        )

    def _show_word(self, p: QPainter, w: float) -> bool:
        """Return whether COPIES_TEXT fits beside the control in a text column ``w``
        wide."""
        return w >= self._copies_width(p) + 8

    def _paint_copies(
        self, p: QPainter, option, n: int, t, selected: bool, word: bool = True
    ):
        minus, num, plus = self.copies_rects(option.rect)
        p.setPen(QColor(t.muted))
        if word:
            p.drawText(
                QRectF(minus.left() - 66, minus.top(), 60, minus.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self.COPIES_TEXT,
            )
        box = minus.united(plus)
        path = QPainterPath()
        path.addRoundedRect(box, 6, 6)
        p.fillPath(path, QColor(t.surface if selected else t.surface2))
        p.setPen(QPen(QColor(t.border), 1))
        p.drawPath(path)
        p.setPen(QColor(t.muted if n == 0 else t.text))
        p.drawText(minus, Qt.AlignmentFlag.AlignCenter, "\u2212")
        p.setPen(QColor(t.text))
        p.drawText(plus, Qt.AlignmentFlag.AlignCenter, "+")
        f = QFont(option.font)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(num, Qt.AlignmentFlag.AlignCenter, str(n))
        p.setFont(option.font)
