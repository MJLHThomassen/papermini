from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..theme_service import ThemeService
from .recent_project import RecentProject


class EmptyState(QFrame):
    """Shown on the canvas when there is nothing to preview yet: how to add images or
    open a project, and the projects opened last."""

    RECENT_SHOWN = 5

    addClicked = Signal()
    openClicked = Signal()
    linkClicked = Signal()
    folderClicked = Signal()
    recentClicked = Signal(str)  # the project's path

    def __init__(self, themes: ThemeService, parent=None):
        super().__init__(parent)
        self._themes = themes
        self.setObjectName("EmptyCard")
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 32, 28, 32)
        v.setSpacing(10)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Start with a drawing")
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QLabel(
            "Drop images, folders, image links or a project (.yaml) anywhere in this "
            "window, or pick them from your computer."
        )
        text.setObjectName("Muted")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setWordWrap(True)
        self.setMaximumWidth(460)
        self.button = QPushButton("Add images…")
        self.button.setProperty("primary", True)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.clicked.connect(self.addClicked)
        self.open_button = QPushButton("Open project…")
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_button.clicked.connect(self.openClicked)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(self.button)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        self.link_button = QPushButton("or add from a link…")
        self.link_button.setObjectName("LinkButton")
        self.link_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_button.clicked.connect(self.linkClicked)
        self.folder_button = QPushButton("or add a folder…")
        self.folder_button.setObjectName("LinkButton")
        self.folder_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_button.clicked.connect(self.folderClicked)
        links = QHBoxLayout()
        links.setSpacing(4)
        links.addStretch(1)
        links.addWidget(self.link_button)
        links.addWidget(self.folder_button)
        links.addStretch(1)
        # the projects opened or saved last: one click opens one
        self.recent_box = QWidget()
        rv = QVBoxLayout(self.recent_box)
        rv.setContentsMargins(0, 10, 0, 0)
        rv.setSpacing(4)
        head = QLabel("Recent projects")
        head.setObjectName("SubHeading")
        rv.addWidget(head)
        self.recent_list = QVBoxLayout()
        self.recent_list.setSpacing(2)
        rv.addLayout(self.recent_list)
        self.recent_box.hide()
        v.addWidget(self.icon)
        v.addWidget(title)
        v.addWidget(text)
        v.addSpacing(6)
        v.addLayout(buttons)
        v.addLayout(links)
        v.addWidget(self.recent_box)

    def set_recent(self, paths) -> None:
        """Show up to ``RECENT_SHOWN`` recent projects (newest first), or none: each its
        name and its folder, shortened in the middle to fit."""
        self._recent = list(paths)[: self.RECENT_SHOWN]
        while self.recent_list.count():
            w = self.recent_list.takeAt(0).widget()
            w.deleteLater()
        for p in self._recent:
            row = RecentProject(self._themes, p)
            row.clicked.connect(self.recentClicked)
            self.recent_list.addWidget(row)
        self.recent_box.setVisible(self.recent_list.count() > 0)
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        """Always its full width (its contents fit any width up to it: the text wraps and
        the recent projects' folders are shortened), so it never changes size while they
        are laid out; as tall as its contents are at that width."""
        w = self.maximumWidth()
        return QSize(
            w,
            self.layout().heightForWidth(w)
            if self.layout().hasHeightForWidth()
            else super().sizeHint().height(),
        )

    def refresh_icons(self):
        self.icon.setPixmap(self._themes.logo_pixmap(104))
        self.set_recent(getattr(self, "_recent", []))  # (in the new theme's colors)
