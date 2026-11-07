"""Small building blocks of the window: figure cards, canvas overlays, header bits."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLayout, QPushButton,
                               QSizePolicy, QStyle, QStyledItemDelegate, QToolButton, QVBoxLayout,
                               QWidget)

from . import theme

SUBTITLE_ROLE = Qt.UserRole + 1


class FigureDelegate(QStyledItemDelegate):
    """Figure list entries as cards: thumbnail, name and a one-line status."""

    H = 68

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.H)

    def paint(self, p: QPainter, option, index):
        t = theme.current
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(6, 3, -6, -3)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        if selected or hover:
            path = QPainterPath()
            path.addRoundedRect(r, 9, 9)
            p.fillPath(path, QColor(t.accent_soft if selected else t.surface2))
            if selected:
                p.setPen(QPen(QColor(t.accent), 1))
                p.drawPath(path)
        # thumbnail on a small canvas tile
        tile = QRectF(r.left() + 8, r.top() + 6, r.height() - 12, r.height() - 12)
        tp = QPainterPath()
        tp.addRoundedRect(tile, 7, 7)
        p.fillPath(tp, QColor(t.canvas))
        icon = index.data(Qt.DecorationRole)
        if icon is not None:
            pm = icon.pixmap(QSize(int(tile.width()) - 8, int(tile.height()) - 8))
            if not pm.isNull():
                s = pm.deviceIndependentSize()
                p.drawPixmap(int(tile.center().x() - s.width() / 2),
                             int(tile.center().y() - s.height() / 2), pm)
        # text
        x = tile.right() + 12
        w = r.right() - x - 8
        f = QFont(option.font)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(t.text))
        name = p.fontMetrics().elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight, int(w))
        p.drawText(QRectF(x, r.top() + 13, w, 20), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.setFont(option.font)
        p.setPen(QColor(t.muted))
        sub = index.data(SUBTITLE_ROLE) or ""
        sub = p.fontMetrics().elidedText(sub, Qt.ElideRight, int(w))
        p.drawText(QRectF(x, r.top() + 33, w, 18), Qt.AlignLeft | Qt.AlignVCenter, sub)
        p.restore()


class Segmented(QFrame):
    """A row of mutually exclusive buttons (a segmented control)."""

    changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        h = QHBoxLayout(self)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for i, (text, tip) in enumerate(labels):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            self.group.addButton(b, i)
            h.addWidget(b)
        self.group.idClicked.connect(self.changed)
        self.group.button(0).setChecked(True)

    def set_index(self, i: int):
        self.group.button(i).setChecked(True)


class ZoomBar(QFrame):
    """Floating zoom controls for the canvas."""

    zoomIn = Signal()
    zoomOut = Signal()
    fit = Signal()
    actual = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ZoomBar")
        h = QHBoxLayout(self)
        h.setContentsMargins(4, 3, 4, 3)
        h.setSpacing(0)
        self.buttons = {}
        for name, tip, sig in (("zoom_out", "Zoom out", self.zoomOut),):
            h.addWidget(self._button(name, tip, sig))
        self.label = QLabel("100%")
        self.label.setMinimumWidth(44)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setToolTip("Zoom (100% = actual size)")
        h.addWidget(self.label)
        for name, tip, sig in (("zoom_in", "Zoom in", self.zoomIn),
                               ("fit", "Fit to window  (Ctrl+0)", self.fit)):
            h.addWidget(self._button(name, tip, sig))
        one = QToolButton()
        one.setText("1:1")
        one.setToolTip("Actual size  (Ctrl+1)")
        one.setAccessibleName("Actual size")
        one.clicked.connect(self.actual)
        one.setCursor(Qt.PointingHandCursor)
        h.addWidget(one)

    def _button(self, name, tip, sig):
        b = QToolButton()
        b.setToolTip(tip)
        b.setAccessibleName(tip.split("  (")[0])
        b.setIconSize(QSize(16, 16))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(sig)
        self.buttons[name] = b
        return b

    def refresh_icons(self):
        for name, b in self.buttons.items():
            b.setIcon(theme.icon(name, theme.current.text, 16))

    def set_zoom(self, z: float):
        self.label.setText(f"{z * 100:.0f}%")


class EmptyState(QFrame):
    """Shown on the canvas when there is nothing to preview yet."""

    addClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyCard")
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 32, 40, 32)
        v.setSpacing(10)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        title = QLabel("Start with a drawing")
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        text = QLabel("Drop images or a project (.yaml) anywhere in this window, "
                      "or pick them from your computer.")
        text.setObjectName("Muted")
        text.setAlignment(Qt.AlignCenter)
        text.setWordWrap(True)
        self.setMaximumWidth(460)
        self.button = QPushButton("Add images…")
        self.button.setProperty("primary", True)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.addClicked)
        v.addWidget(self.icon)
        v.addWidget(title)
        v.addWidget(text)
        v.addSpacing(6)
        v.addWidget(self.button, 0, Qt.AlignCenter)

    def refresh_icons(self):
        self.icon.setPixmap(theme.logo_pixmap(104))


class Banner(QFrame):
    """A message card on top of the canvas (e.g. why a miniature could not be built)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ErrorBanner")
        self.setMaximumWidth(560)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 16, 12)
        h.setSpacing(12)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignTop)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        h.addWidget(self.icon)
        h.addWidget(self.text, 1)

    def show_message(self, title: str, body: str):
        self.icon.setPixmap(theme.pixmap("warning", theme.current.danger, 20))
        self.text.setText(f"<b>{title}</b><br>{body}")
        self.show()


class FlowLayout(QLayout):
    """Lays items out left to right and wraps onto the next line when the row is
    full, so a bar of controls never forces its parent to stay wide."""

    def __init__(self, parent=None, spacing: int = 8, line_spacing: int = 6):
        super().__init__(parent)
        self._items = []
        self._h, self._v = spacing, line_spacing

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, apply: bool) -> int:
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = r.x(), r.y(), 0
        for it in self._items:
            if it.widget() is not None and not it.widget().isVisible() and apply:
                continue
            hint = it.sizeHint()
            if x > r.x() and x + hint.width() > r.right() + 1:
                x, y, line_h = r.x(), y + line_h + self._v, 0
            if apply:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._h
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


def overlay_wrap(w: QWidget, margins=(16, 16, 16, 16)) -> QWidget:
    """Wrap an overlay so it keeps a margin from the canvas edge."""
    box = QWidget()
    box.setAttribute(Qt.WA_TranslucentBackground)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(*margins)
    lay.addWidget(w)
    return box
