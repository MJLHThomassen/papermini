from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ... import log
from .. import errors, prefs
from ..fields.spin_box import SpinBox
from .cache_page import CachePage
from .page_parts import _hint, _page_title
from .sizes_page import SizesPage


# ----------------------------------------------------------------- the window
class PreferencesDialog(QDialog):
    """The Preferences window for ``window`` (the main window), opened at ``page``."""

    PAGES = (
        ("sizes", "Creature sizes"),
        ("images", "Images"),
        ("appearance", "Appearance"),
        ("updates", "Updates"),
        ("logging", "Logging"),
        ("cache", "Models and cache"),
    )

    def __init__(self, window, page: str = "sizes"):
        super().__init__(window)
        self.setWindowTitle("Preferences")
        self.setObjectName("PreferencesDialog")
        self.setSizeGripEnabled(True)
        self.window_ = window
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 18, 18, 16)
        v.setSpacing(12)
        h = QHBoxLayout()
        h.setSpacing(18)
        self.nav = QListWidget()
        self.nav.setObjectName("PrefNav")
        self.nav.setFixedWidth(150)
        self.stack = QStackedWidget()
        self.sizes = SizesPage(window.project.sizes)
        self.cache = CachePage(in_use=lambda: [f.entry.image for f in window.figures])
        self.cache.changed.connect(window._models_changed)
        pages = (
            self.sizes,
            self._images(),
            self._appearance(),
            self._updates(),
            self._logging(),
            self.cache,
        )
        for (key, text), w in zip(self.PAGES, pages):
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, key)
            item.setSizeHint(QSize(0, 32))
            self.nav.addItem(item)
            self.stack.addWidget(w)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        h.addWidget(self.nav)
        h.addWidget(self.stack, 1)
        v.addLayout(h, 1)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close = QPushButton("Close")
        close.setProperty("primary", True)
        close.setDefault(True)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        v.addLayout(bottom)
        self.show_page(page)
        self.resize(980, 560)

    def show_page(self, key: str) -> None:
        keys = [k for k, _ in self.PAGES]
        self.nav.setCurrentRow(keys.index(key) if key in keys else 0)

    def _page(self, title: str) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(_page_title(title))
        return w, v

    def _images(self) -> QWidget:
        w, v = self._page("Images")
        head = QLabel("Adding a folder")
        head.setObjectName("SubHeading")
        v.addWidget(head)
        self.subfolders = QCheckBox("Also add the images in subfolders")
        self.subfolders.setChecked(prefs.add_subfolders())
        self.subfolders.toggled.connect(prefs.set_add_subfolders)
        v.addWidget(self.subfolders)
        v.addWidget(
            _hint(
                "When you add a folder (Add folder\u2026 in the menu, or by dropping "
                "it on the window), also add the images in its subfolders. The "
                "command line always does, unless you give --no-subfolders."
            )
        )
        v.addSpacing(14)
        head = QLabel("PNG size")
        head.setObjectName("SubHeading")
        v.addWidget(head)
        self.png_mode = QButtonGroup(w)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.png_px = SpinBox()
        self.png_px.setRange(*prefs.PNG_PX_RANGE)
        self.png_px.setSingleStep(10)
        self.png_px.setValue(prefs.png_px_per_square())
        self.png_px.valueChanged.connect(prefs.set_png_px_per_square)
        self.png_dpi = SpinBox()
        self.png_dpi.setRange(*prefs.PNG_DPI_RANGE)
        self.png_dpi.setSingleStep(50)
        self.png_dpi.setValue(prefs.png_dpi())
        self.png_dpi.valueChanged.connect(prefs.set_png_dpi)
        self.png_buttons = {}
        for row, (mode, text, box, unit) in enumerate(
            (
                (
                    "square",
                    "For a virtual tabletop",
                    self.png_px,
                    "pixels per grid square",
                ),
                ("dpi", "At the size it prints", self.png_dpi, "dpi"),
            )
        ):
            b = QRadioButton(text)
            b.setCursor(Qt.PointingHandCursor)
            self.png_mode.addButton(b)
            self.png_buttons[mode] = b
            box.setKeyboardTracking(False)
            box.setFixedWidth(90)
            grid.addWidget(b, row, 0)
            grid.addWidget(box, row, 1)
            grid.addWidget(QLabel(unit), row, 2)
        grid.setColumnStretch(3, 1)
        v.addLayout(grid)
        self.png_buttons[prefs.png_size_mode()].setChecked(True)
        for mode, b in self.png_buttons.items():
            b.toggled.connect(lambda on, m=mode: on and self._png_mode(m))
        self._png_mode(prefs.png_size_mode())
        v.addWidget(
            _hint(
                "How big an exported PNG is. For a virtual tabletop: this many pixels "
                "for each grid square, so a Medium figure covers one square and a "
                "Large one two; set it to your tabletop's grid size (for example 100 "
                "in Foundry or 70 in Roll20). At the size it prints: a picture of the "
                "piece at this resolution, as on the print sheet. The command line "
                "takes --png-px or --png-dpi."
            )
        )
        v.addStretch(1)
        return w

    def _png_mode(self, mode: str) -> None:
        prefs.set_png_size_mode(mode)
        self.png_px.setEnabled(mode == "square")
        self.png_dpi.setEnabled(mode == "dpi")

    def _appearance(self) -> QWidget:
        w, v = self._page("Appearance")
        head = QLabel("Theme")
        head.setObjectName("SubHeading")
        v.addWidget(head)
        self.theme_group = QButtonGroup(w)
        for mode, text in (
            ("system", "Follow system"),
            ("light", "Light"),
            ("dark", "Dark"),
        ):
            b = QRadioButton(text)
            b.setChecked(mode == self.window_._theme_mode)
            b.toggled.connect(lambda on, mode=mode: on and self.window_.set_theme(mode))
            self.theme_group.addButton(b)
            v.addWidget(b)
        v.addStretch(1)
        return w

    def _updates(self) -> QWidget:
        w, v = self._page("Updates")
        self.auto_updates = QCheckBox("Update automatically")
        self.auto_updates.setChecked(self.window_.auto_updates())
        self.auto_updates.toggled.connect(self.window_.set_auto_updates)
        v.addWidget(self.auto_updates)
        v.addWidget(
            _hint(
                "Look for a new version once a day, download it in the "
                "background and install it when papermini closes. Check for "
                "updates in the menu looks right away."
            )
        )
        v.addStretch(1)
        return w

    def _logging(self) -> QWidget:
        w, v = self._page("Logging")
        on = log.session() is not None
        self.detailed_log = QCheckBox("Detailed log")
        self.detailed_log.setChecked(log.detailed())
        self.detailed_log.setEnabled(on)
        self.detailed_log.toggled.connect(log.set_detailed)
        v.addWidget(self.detailed_log)
        v.addWidget(
            _hint(
                "Write more to the log, until papermini closes. Turn it on "
                "before you repeat a problem you want to report."
                if on
                else "There is no log in this session."
            )
        )
        folder = QPushButton("Open log folder")
        folder.setEnabled(on)
        folder.setCursor(Qt.PointingHandCursor)
        folder.clicked.connect(errors.open_log_folder)
        row = QHBoxLayout()
        row.addWidget(folder)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)
        return w
