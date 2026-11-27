from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
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

from ...pipeline.segmentation.mask_store import MaskStore
from ...pipeline.segmentation.segmenter_registry import SegmenterRegistry
from ...project import sizes
from ...project.size_calculator import SizeCalculator
from ...support.image_fetcher import ImageFetcher
from ...support.log_session import LogSession
from ..fields.spin_box import SpinBox
from ..preferences import Preferences
from ..problem_reporter import ProblemReporter
from ..theme_service import ThemeService
from .cache_page import CachePage
from .page_parts import PageParts
from .sizes_page import SizesPage


class PreferencesDialog(QDialog):
    """The Preferences window, opened at ``page``. ``table`` is the open project's size
    table, ``in_use`` returns the images of the open project's figures, and
    ``segmenters`` and ``masks`` keep the models and masks it lists. The choices that the
    main window acts on come out as signals."""

    themeChanged = Signal(str)
    autoUpdatesChanged = Signal(bool)
    modelsChanged = Signal(str)  # the model downloaded or deleted

    PAGES = (
        ("sizes", "Creature sizes"),
        ("images", "Images"),
        ("undo", "Undo history"),
        ("appearance", "Appearance"),
        ("updates", "Updates"),
        ("logging", "Logging"),
        ("cache", "Models and cache"),
    )

    def __init__(
        self,
        prefs: Preferences,
        size_calculator: SizeCalculator,
        table: sizes.SizeTable,
        in_use: Callable[[], list[Path]],
        segmenters: SegmenterRegistry,
        masks: MaskStore,
        images_from_web: ImageFetcher,
        logs: LogSession,
        themes: ThemeService,
        problems: ProblemReporter,
        page: str = "sizes",
        parent=None,
    ):
        super().__init__(parent)
        self._prefs = prefs
        self._logs = logs
        self._problems = problems
        self.setWindowTitle("Preferences")
        self.setObjectName("PreferencesDialog")
        self.setSizeGripEnabled(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 18, 18, 16)
        v.setSpacing(12)
        h = QHBoxLayout()
        h.setSpacing(18)
        self.nav = QListWidget()
        self.nav.setObjectName("PrefNav")
        self.nav.setFixedWidth(150)
        self.stack = QStackedWidget()
        self.sizes = SizesPage(prefs, size_calculator, themes, table)
        self.cache = CachePage(segmenters, masks, images_from_web, in_use=in_use)
        self.cache.changed.connect(self.modelsChanged)
        pages = (
            self.sizes,
            self._images(),
            self._undo(),
            self._appearance(),
            self._updates(),
            self._logging(),
            self.cache,
        )
        for (key, text), w in zip(self.PAGES, pages):
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
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
        close.setCursor(Qt.CursorShape.PointingHandCursor)
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
        v.addWidget(PageParts.title(title))
        return w, v

    def _images(self) -> QWidget:
        w, v = self._page("Images")
        head = QLabel("Adding a folder")
        head.setObjectName("SubHeading")
        v.addWidget(head)
        self.subfolders = QCheckBox("Also add the images in subfolders")
        self.subfolders.setChecked(self._prefs.add_subfolders())
        self.subfolders.toggled.connect(self._prefs.set_add_subfolders)
        v.addWidget(self.subfolders)
        v.addWidget(
            PageParts.hint(
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
        self.png_px.setRange(*Preferences.PNG_PX_RANGE)
        self.png_px.setSingleStep(10)
        self.png_px.setValue(self._prefs.png_px_per_square())
        self.png_px.valueChanged.connect(self._prefs.set_png_px_per_square)
        self.png_dpi = SpinBox()
        self.png_dpi.setRange(*Preferences.PNG_DPI_RANGE)
        self.png_dpi.setSingleStep(50)
        self.png_dpi.setValue(self._prefs.png_dpi())
        self.png_dpi.valueChanged.connect(self._prefs.set_png_dpi)
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
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.png_mode.addButton(b)
            self.png_buttons[mode] = b
            box.setKeyboardTracking(False)
            box.setFixedWidth(90)
            grid.addWidget(b, row, 0)
            grid.addWidget(box, row, 1)
            grid.addWidget(QLabel(unit), row, 2)
        grid.setColumnStretch(3, 1)
        v.addLayout(grid)
        self.png_buttons[self._prefs.png_size_mode()].setChecked(True)
        for mode, b in self.png_buttons.items():
            b.toggled.connect(lambda on, m=mode: on and self._png_mode(m))
        self._png_mode(self._prefs.png_size_mode())
        v.addWidget(
            PageParts.hint(
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
        self._prefs.set_png_size_mode(mode)
        self.png_px.setEnabled(mode == "square")
        self.png_dpi.setEnabled(mode == "dpi")

    def _undo(self) -> QWidget:
        w, v = self._page("Undo history")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.undo_steps = SpinBox()
        self.undo_steps.setRange(*Preferences.UNDO_STEPS_RANGE)
        self.undo_steps.setSingleStep(10)
        self.undo_steps.setKeyboardTracking(False)
        self.undo_steps.setFixedWidth(90)
        self.undo_steps.setValue(self._prefs.undo_steps())
        self.undo_steps.valueChanged.connect(self._prefs.set_undo_steps)
        row.addWidget(QLabel("Keep the last"))
        row.addWidget(self.undo_steps)
        row.addWidget(QLabel("changes"))
        row.addStretch(1)
        v.addLayout(row)
        v.addWidget(
            PageParts.hint(
                f"How many changes Undo can take back. The default is "
                f"{Preferences.UNDO_STEPS}. A project's history starts empty when you "
                "open it or start a new one, and a new number takes effect then."
            )
        )
        v.addStretch(1)
        return w

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
            b.setChecked(mode == self._prefs.theme())
            b.toggled.connect(lambda on, mode=mode: on and self.themeChanged.emit(mode))
            self.theme_group.addButton(b)
            v.addWidget(b)
        v.addStretch(1)
        return w

    def _updates(self) -> QWidget:
        w, v = self._page("Updates")
        self.auto_updates = QCheckBox("Update automatically")
        self.auto_updates.setChecked(self._prefs.auto_updates())
        self.auto_updates.toggled.connect(self.autoUpdatesChanged)
        v.addWidget(self.auto_updates)
        v.addWidget(
            PageParts.hint(
                "Look for a new version once a day, download it in the "
                "background and install it when papermini closes. Check for "
                "updates in the menu looks right away."
            )
        )
        v.addStretch(1)
        return w

    def _logging(self) -> QWidget:
        w, v = self._page("Logging")
        on = self._logs.session() is not None
        self.detailed_log = QCheckBox("Detailed log")
        self.detailed_log.setChecked(self._logs.detailed())
        self.detailed_log.setEnabled(on)
        self.detailed_log.toggled.connect(self._logs.set_detailed)
        v.addWidget(self.detailed_log)
        v.addWidget(
            PageParts.hint(
                "Write more to the log, until papermini closes. Turn it on "
                "before you repeat a problem you want to report."
                if on
                else "There is no log in this session."
            )
        )
        folder = QPushButton("Open log folder")
        folder.setEnabled(on)
        folder.setCursor(Qt.CursorShape.PointingHandCursor)
        folder.clicked.connect(lambda: self._problems.open_log_folder())
        row = QHBoxLayout()
        row.addWidget(folder)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)
        return w
