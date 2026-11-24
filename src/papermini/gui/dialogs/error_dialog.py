from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QVBoxLayout,
)


class ErrorDialog(QDialog):
    """The dialog for an unexpected error: what happened in a sentence, and the
    traceback folded away. A button unfolds the traceback in a large box, and the
    window can then be resized. Beside the button that closes the dialog (or quits
    while papermini is starting) is one to report the problem. After ``exec()``,
    ``reported`` says whether the user chose to report it."""

    def __init__(self, parent, summary: str, details: str, quit_: bool = False):
        super().__init__(parent)
        self.setWindowTitle("papermini")
        self.setObjectName("ErrorDialog")
        self.reported = False
        v = QVBoxLayout(self)
        v.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(14)
        icon = QLabel()
        icon.setPixmap(
            self.style().standardIcon(QStyle.SP_MessageBoxCritical).pixmap(40, 40)
        )
        icon.setAlignment(Qt.AlignTop)
        top.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(8)
        title = QLabel("<b>Something went wrong</b>")
        title.setTextFormat(Qt.RichText)
        col.addWidget(title)
        if quit_:
            what = (
                "papermini ran into an unexpected problem while starting and cannot "
                "continue. It has been written to the log."
            )
        else:
            what = (
                "papermini ran into an unexpected problem. It has been written to the "
                "log. You can keep working, but save your project soon."
            )
        for text in (what, summary):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setMinimumWidth(380)
            col.addWidget(label)
        col.addStretch(1)
        top.addLayout(col, 1)
        v.addLayout(top)

        self.details = QPlainTextEdit(details)
        self.details.setObjectName("ErrorDetails")
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.details.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.details.setMinimumSize(320, 160)
        self.details.hide()
        v.addWidget(self.details, 1)

        buttons = QHBoxLayout()
        self.toggle = QPushButton("Show details")
        self.toggle.clicked.connect(self._toggle_details)
        self.copy = QPushButton("Copy details")
        self.copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(details))
        self.copy.hide()
        report = QPushButton("Report a problem…")
        report.clicked.connect(self._report)
        go_on = QPushButton("Quit" if quit_ else "Continue")
        go_on.setProperty("primary", True)
        go_on.clicked.connect(self.accept)
        go_on.setDefault(True)
        for b in (self.toggle, self.copy):
            buttons.addWidget(b)
        buttons.addStretch(1)
        for b in (report, go_on):
            buttons.addWidget(b)
        for b in (self.toggle, self.copy, report, go_on):
            b.setCursor(Qt.PointingHandCursor)
        v.addLayout(buttons)
        self.setSizeGripEnabled(True)

    def _report(self):
        self.reported = True
        self.accept()

    def _toggle_details(self):
        show = not self.details.isVisible()
        self.details.setVisible(show)
        self.copy.setVisible(show)
        self.toggle.setText("Hide details" if show else "Show details")
        if show:  # room for a traceback, within the screen
            screen = (
                self.screen() or QGuiApplication.primaryScreen()
            ).availableGeometry()
            self.resize(
                min(max(self.width(), 760), screen.width() - 80),
                min(max(self.height(), 520), screen.height() - 80),
            )
        else:
            QTimer.singleShot(0, lambda: self.resize(self.minimumSizeHint()))
