from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from ..theme_service import ThemeService

# a preset entry's notes, a line each
NOTES_ROLE = Qt.ItemDataRole.UserRole + 1

# the widest and the narrowest a list of presets gets as its window is resized
LIST_MAX_WIDTH, LIST_MIN_WIDTH = 250, 150


class PresetEntryDelegate(QStyledItemDelegate):
    """Paints an entry of a list of presets: the name, and below it, smaller and
    muted, a line for each of its notes (``NOTES_ROLE``). Painted rather than a widget
    per entry: item widgets of a list that is filled again are deleted later, which can
    crash Qt when papermini quits."""

    PAD_X, PAD_Y = 8, 5
    # a scaled display rounds the line height down, which would cut off descenders
    _ALIGN = (
        Qt.AlignmentFlag.AlignLeft
        | Qt.AlignmentFlag.AlignVCenter
        | Qt.TextFlag.TextDontClip
    )

    def __init__(self, themes: ThemeService, parent=None):
        super().__init__(parent)
        self._themes = themes

    @staticmethod
    def _fonts(option) -> tuple[QFont, QFont]:
        notes = QFont(option.font)
        notes.setPointSizeF(8.5)  # (as #Hint)
        return QFont(option.font), notes

    @staticmethod
    def _lines(index) -> list[str]:
        return [n for n in (index.data(NOTES_ROLE) or "").split("\n") if n]

    def sizeHint(self, option, index) -> QSize:
        name, notes = self._fonts(option)
        lines = self._lines(index)
        h = QFontMetrics(name).height() + len(lines) * (
            QFontMetrics(notes).height() + 1
        )
        return QSize(200, h + 2 * self.PAD_Y)

    def paint(self, p, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""  # (the background and selection only)
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, p, opt.widget)
        name_font, notes_font = self._fonts(option)
        r = option.rect.adjusted(self.PAD_X, self.PAD_Y, -self.PAD_X, -self.PAD_Y)
        p.save()
        fm = QFontMetrics(name_font)
        p.setFont(name_font)
        p.setPen(QColor(self._themes.current.text))
        p.drawText(
            QRect(r.left(), r.top(), r.width(), fm.height()),
            self._ALIGN,
            fm.elidedText(
                index.data(Qt.ItemDataRole.DisplayRole) or "",
                Qt.TextElideMode.ElideRight,
                r.width(),
            ),
        )
        y = r.top() + fm.height() + 1
        fn = QFontMetrics(notes_font)
        p.setFont(notes_font)
        p.setPen(QColor(self._themes.current.muted))
        for line in self._lines(index):
            p.drawText(
                QRect(r.left(), y, r.width(), fn.height()),
                self._ALIGN,
                fn.elidedText(line, Qt.TextElideMode.ElideRight, r.width()),
            )
            y += fn.height() + 1
        p.restore()
