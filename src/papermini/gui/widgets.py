"""Small building blocks of the window: figure cards, canvas overlays, header bits."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QLayout, QPushButton, QSizePolicy, QSpinBox, QStyle,
                               QStyledItemDelegate, QToolButton, QToolTip, QVBoxLayout,
                               QWidget)

from . import theme

SUBTITLE_ROLE = Qt.UserRole + 1
COPIES_ROLE = Qt.UserRole + 2   # copies on the sheet (None: no copies control)
MAX_COPIES = 999


class FigureDelegate(QStyledItemDelegate):
    """Figure list entries as cards: thumbnail, name, a one-line status and the copies
    on the sheet (- n +: click - or +, or click the number to type one)."""

    H = 68
    TILE = 50          # thumbnail
    BTN, NUM = 18, 26  # copies control: button and number width (px)
    COPIES_TEXT = "Amount"  # right before the control, so it is clear what it counts
    COPIES_TIP = ("How many of this figure go on the print sheet.\n"
                  "Click − or +, or click the number to type one.")
    copiesChanged = Signal(object, int)  # figure uid (Qt.UserRole), copies

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.H)

    def _copies_rects(self, rect):
        """(minus, number, plus) of the copies control at the bottom right of a card."""
        r = QRectF(rect).adjusted(6, 3, -6, -3)
        y = r.top() + 33
        plus = QRectF(r.right() - 10 - self.BTN, y - 1, self.BTN, self.BTN)
        num = QRectF(plus.left() - self.NUM, y - 1, self.NUM, self.BTN)
        minus = QRectF(num.left() - self.BTN, y - 1, self.BTN, self.BTN)
        return minus, num, plus

    def _set_copies(self, index, n: int):
        n = max(0, min(MAX_COPIES, n))
        if n != index.data(COPIES_ROLE):
            self.copiesChanged.emit(index.data(Qt.UserRole), n)

    def editorEvent(self, event, model, option, index):
        n = index.data(COPIES_ROLE)
        if n is not None and event.type() == QEvent.MouseButtonRelease \
                and event.button() == Qt.LeftButton:
            minus, num, plus = self._copies_rects(option.rect)
            pos = event.position()
            if minus.contains(pos):
                self._set_copies(index, n - 1)
                return True
            if plus.contains(pos):
                self._set_copies(index, n + 1)
                return True
            if num.contains(pos):
                self.parent().edit(index)  # (a spin box over the number, see createEditor)
                return True
        return super().editorEvent(event, model, option, index)

    def createEditor(self, parent, option, index):
        box = QSpinBox(parent)
        box.setRange(0, MAX_COPIES)  # (no arrows: the theme hides spin box buttons)
        box.setAlignment(Qt.AlignCenter)
        box.setObjectName("CopiesEditor")
        return box

    def setEditorData(self, editor, index):
        editor.setValue(index.data(COPIES_ROLE) or 0)
        editor.selectAll()

    def setModelData(self, editor, model, index):
        editor.interpretText()
        self._set_copies(index, editor.value())

    def updateEditorGeometry(self, editor, option, index):
        _, num, _ = self._copies_rects(option.rect)
        editor.setGeometry(num.toRect().adjusted(-2, -1, 2, 1))

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
        tile = QRectF(r.left() + 8, r.center().y() - self.TILE / 2, self.TILE, self.TILE)
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
        copies = index.data(COPIES_ROLE)
        f = QFont(option.font)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(t.text))
        name = p.fontMetrics().elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight, int(w))
        p.drawText(QRectF(x, r.top() + 13, w, 20), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.setFont(option.font)
        p.setPen(QColor(t.muted))
        sub_w = w
        if copies is not None:  # in a narrow list the height gives way, then "Amount"
            sub_w = max(0.0, w - self._copies_width(p, self._show_word(p, w)) - 8)
        sub = index.data(SUBTITLE_ROLE) or ""
        sub = p.fontMetrics().elidedText(sub, Qt.ElideRight, int(sub_w))
        p.drawText(QRectF(x, r.top() + 33, sub_w, 18), Qt.AlignLeft | Qt.AlignVCenter, sub)
        if copies is not None:
            self._paint_copies(p, option, copies, t, selected, self._show_word(p, w))
        p.restore()

    def helpEvent(self, event, view, option, index):
        if index.data(COPIES_ROLE) is not None:
            minus, _, plus = self._copies_rects(option.rect)
            area = minus.united(plus).adjusted(-60, -2, 0, 2)  # (the word "Amount" too)
            if area.contains(event.pos()):
                QToolTip.showText(event.globalPos(), self.COPIES_TIP, view)
                return True
        return super().helpEvent(event, view, option, index)

    def _copies_width(self, p: QPainter, word: bool = True) -> float:
        """The control, and the word "Amount" before it."""
        control = 2 * self.BTN + self.NUM
        return control + (p.fontMetrics().horizontalAdvance(self.COPIES_TEXT) + 6 if word else 0)

    def _show_word(self, p: QPainter, w: float) -> bool:
        """Whether "Amount" fits beside the control in a text column ``w`` wide."""
        return w >= self._copies_width(p) + 8

    def _paint_copies(self, p: QPainter, option, n: int, t, selected: bool, word: bool = True):
        minus, num, plus = self._copies_rects(option.rect)
        p.setPen(QColor(t.muted))
        if word:
            p.drawText(QRectF(minus.left() - 66, minus.top(), 60, minus.height()),
                       Qt.AlignRight | Qt.AlignVCenter, self.COPIES_TEXT)
        box = minus.united(plus)
        path = QPainterPath()
        path.addRoundedRect(box, 6, 6)
        p.fillPath(path, QColor(t.surface if selected else t.surface2))
        p.setPen(QPen(QColor(t.border), 1))
        p.drawPath(path)
        p.setPen(QColor(t.muted if n == 0 else t.text))
        p.drawText(minus, Qt.AlignCenter, "\u2212")
        p.setPen(QColor(t.text))
        p.drawText(plus, Qt.AlignCenter, "+")
        f = QFont(option.font)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.drawText(num, Qt.AlignCenter, str(n))
        p.setFont(option.font)


class Segmented(QFrame):
    """A row of mutually exclusive buttons (a segmented control). With ``steps`` the
    buttons are numbered workflow steps with a chevron between them; any step can
    still be picked at any time."""

    changed = Signal(int)

    def __init__(self, labels, parent=None, steps: bool = False):
        super().__init__(parent)
        self.setObjectName("Segmented")
        h = QHBoxLayout(self)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._chevrons = []
        for i, (text, tip) in enumerate(labels):
            if steps and i:
                arrow = QLabel()
                arrow.setObjectName("StepArrow")
                self._chevrons.append(arrow)
                h.addWidget(arrow)
            b = QPushButton(f"{i + 1}  {text}" if steps else text)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            self.group.addButton(b, i)
            h.addWidget(b)
        self.group.idClicked.connect(self.changed)
        self.group.button(0).setChecked(True)
        self.refresh_icons()

    def refresh_icons(self):
        for arrow in self._chevrons:
            arrow.setPixmap(theme.pixmap("chevron_right", theme.current.muted, 14))

    def set_index(self, i: int):
        self.group.button(i).setChecked(True)


class Spinner(QWidget):
    """A small turning arc: something is being worked on. Turns only while shown."""

    def __init__(self, size: int = 22, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self, interval=50, timeout=self._turn)

    def _turn(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def showEvent(self, e):
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        track = QColor(theme.current.border)
        p.setPen(QPen(track, 3))
        p.drawEllipse(r)
        pen = QPen(QColor(theme.current.accent), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, -self._angle * 16, 100 * 16)


class ElidedLabel(QLabel):
    """A one-line label that ends in "…" when it gets less room than its text needs
    (a long figure name), instead of clipping it or growing its parent."""

    def minimumSizeHint(self) -> QSize:
        return QSize(40, super().minimumSizeHint().height())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        r = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, r.width())
        p.drawText(r, int(Qt.AlignLeft | Qt.AlignVCenter), text)


class WorkCard(QFrame):
    """A card in the middle of the canvas for slow work: what is happening, how long
    it has taken, and a button (Cancel while working, Run again once cancelled)."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WorkCard")
        self.setMinimumWidth(440)  # room for a figure name before it ends in "…"
        self.setMaximumWidth(520)
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 14, 14, 14)
        h.setSpacing(14)
        self.spinner = Spinner()
        self.icon = QLabel()
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = ElidedLabel()  # (a long figure name ends in "…")
        self.title.setObjectName("WorkTitle")
        self.detail = ElidedLabel()
        self.detail.setObjectName("Muted")
        text.addWidget(self.title)
        text.addWidget(self.detail)
        self.button = QPushButton()
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.clicked)
        h.addWidget(self.spinner, 0, Qt.AlignVCenter)
        h.addWidget(self.icon, 0, Qt.AlignVCenter)
        h.addLayout(text, 1)
        h.addWidget(self.button, 0, Qt.AlignVCenter)

    def show_working(self, title: str, detail: str, button: str = "Cancel"):
        self.spinner.show()
        self.icon.hide()
        self._set(title, detail, button)

    def show_stopped(self, title: str, detail: str, button: str):
        self.spinner.hide()
        self.icon.setPixmap(theme.pixmap("warning", theme.current.muted, 20))
        self.icon.show()
        self._set(title, detail, button)

    def _set(self, title: str, detail: str, button: str):
        self.title.setText(title)
        self.detail.setText(detail)
        self.button.setText(button)


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
    openClicked = Signal()
    linkClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyCard")
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 32, 28, 32)
        v.setSpacing(10)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        title = QLabel("Start with a drawing")
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        text = QLabel("Drop images, image links or a project (.yaml) anywhere in this "
                      "window, or pick them from your computer.")
        text.setObjectName("Muted")
        text.setAlignment(Qt.AlignCenter)
        text.setWordWrap(True)
        self.setMaximumWidth(460)
        self.button = QPushButton("Add images…")
        self.button.setProperty("primary", True)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.addClicked)
        self.open_button = QPushButton("Open project…")
        self.open_button.setCursor(Qt.PointingHandCursor)
        self.open_button.clicked.connect(self.openClicked)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(self.button)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        self.link_button = QPushButton("or add from a link…")
        self.link_button.setObjectName("LinkButton")
        self.link_button.setCursor(Qt.PointingHandCursor)
        self.link_button.clicked.connect(self.linkClicked)
        v.addWidget(self.icon)
        v.addWidget(title)
        v.addWidget(text)
        v.addSpacing(6)
        v.addLayout(buttons)
        v.addWidget(self.link_button, 0, Qt.AlignCenter)

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
