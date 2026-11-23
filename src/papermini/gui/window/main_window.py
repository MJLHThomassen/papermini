from __future__ import annotations

import html
import itertools
import logging
import os
import re
import threading
from dataclasses import asdict, replace
from pathlib import Path
from typing import ClassVar

import yaml
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...output.output import Output
from ...pipeline.mini import Mini
from ...pipeline.pipeline import Pipeline
from ...pipeline.segmentation import segment
from ...pipeline.segmentation.download_hooks import DownloadHooks
from ...project import sizes
from ...project.figure_builder import FigureBuilder
from ...project.figure_entry import FigureEntry
from ...project.figure_settings import FigureSettings
from ...project.project import Project
from ...project.project_store import ProjectStore
from ...project.size_calculator import SizeCalculator
from ...support.font_library import FontLibrary
from ...support.image_fetcher import ImageFetcher
from ...support.image_files import ImageFiles
from ...support.log_session import LogSession
from ...support.update_service import UpdateService
from .. import errors, theme
from ..building.build_queue import BuildQueue
from ..dialogs.download_dialog import DownloadDialog
from ..dialogs.preferences_dialog import PreferencesDialog
from ..exporting.export_controller import ExportController
from ..exporting.export_dialogs import ExportDialogs
from ..panels.figure_fields import PER_IMAGE
from ..panels.figure_panel import FigurePanel
from ..panels.section import Section
from ..panels.sheet_panel import SheetPanel
from ..preferences import Preferences
from ..updating.update_controller import UpdateController
from ..views.crop_view import CropView
from ..views.drawing import draw_mini_page, draw_sheet
from ..views.images import adjusted_preview, load_qimage, pil_to_qimage
from ..views.mini_view import MiniView
from ..views.source_legend import SourceLegend
from ..views.zoom_view import ZoomView
from ..widgets.banner import Banner
from ..widgets.empty_state import EmptyState
from ..widgets.figure_delegate import COPIES_ROLE, SUBTITLE_ROLE, FigureDelegate
from ..widgets.overlay import overlay_wrap
from ..widgets.segmented import Segmented
from ..widgets.work_card import WorkCard
from ..widgets.zoom_bar import ZoomBar
from .figure import Figure
from .signals import Signals

IMAGE_FILTER = ImageFiles.FILTER
IMG_SRC = re.compile(r"""<img\b[^>]*?\ssrc\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
PROJECT_FILTER = "papermini project (*.yaml *.yml)"
ui_log = logging.getLogger("papermini.ui")  # what the user does


class MainWindow(QMainWindow):
    """The main window: the figure list, the live previews and the settings."""

    def __init__(
        self,
        prefs: Preferences,
        project_store: ProjectStore,
        size_calculator: SizeCalculator,
        pipeline: Pipeline,
        figure_builder: FigureBuilder,
        fonts: FontLibrary,
        output: Output,
        images_from_web: ImageFetcher,
        updates: UpdateService,
        logs: LogSession,
    ):
        super().__init__()
        self._prefs = prefs
        self._project_store = project_store
        self._size_calculator = size_calculator
        self._pipeline = pipeline
        self._fonts = fonts
        self._output = output
        self._images_from_web = images_from_web
        self._logs = logs
        self.resize(1440, 900)
        self.setAcceptDrops(True)
        self.project = self._fresh_project()
        self.figures: list[Figure] = []
        self._uids = itertools.count(1)
        self._modified = False
        self.sig = Signals()
        self.builds = BuildQueue(
            pipeline,
            figure_builder,
            DownloadHooks(self._confirm_download, self._download_progress),
            self._figure,
            self.current,
            self,
        )
        self.builds.built.connect(self._on_built)
        self.builds.failed.connect(self._on_failed)
        self.builds.cancelled.connect(self._on_cancelled)
        self.builds.outline.connect(self._on_outline)
        self.builds.run_started.connect(self._on_run_started)
        self.builds.run_ended.connect(self._on_run_ended)
        self.builds.building.connect(self._on_building)
        self.builds.ready.connect(self._show_mini)
        self.builds.held.connect(self._update_work)
        self.builds.status.connect(self._status)
        self._work_timer = QTimer(self, interval=500, timeout=self._update_work)
        self.sig.status.connect(self._status)
        self.sig.ask_download.connect(self._ask_download)
        self.sig.link_done.connect(self._on_link_done)
        self.exporter = ExportController(
            self, prefs, ExportDialogs(prefs, output.cut_files), fonts, output
        )
        self.exporter.status.connect(self._status)
        self.exporter.warning.connect(self._warn)
        self.exporter.build.connect(self.builds.queue)
        self.updater = UpdateController(self, prefs, updates, logs)
        self.updater.status.connect(self._status)
        self._closing = threading.Event()  # stops link downloads when the window closes
        self._declined = (
            set()
        )  # models the user did not want to download (until they change model)
        self._crop_undo = []  # (figure uid, crop before a change), newest last: Ctrl+Z
        self._undoing = False

        # settings changes go to the detailed log once they settle, as old -> new
        self._settings_log: dict[
            object, tuple
        ] = {}  # uid or "sheet" -> (name, old settings)
        self._settings_log_timer = QTimer(
            self, singleShot=True, interval=250, timeout=self._flush_settings_log
        )
        self._sheet_timer = QTimer(
            self, singleShot=True, interval=150, timeout=self._refresh_sheet
        )
        # the Source view's picture follows the color sliders, a moment after they move
        self._picture_timer = QTimer(
            self, singleShot=True, interval=60, timeout=self._refresh_picture
        )
        self._original = (
            None,
            None,
        )  # (image path, QImage): the shown image, loaded once

        self._theme_mode = prefs.theme()
        self._make_ui()
        self._make_actions()
        self._restore_layout()
        self._refresh_theme()
        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)
        self.tabs.currentChanged.connect(self.views.set_index)
        self.sheet_panel.set_settings(self.project.sheet)
        self._sync_size_label()
        self._update_title()
        self._show_current()
        QTimer.singleShot(2000, self.updater.start_up)  # (after the window is up)
        self.sig.fonts_found.connect(self.panel.set_installed_fonts)
        threading.Thread(target=self._find_fonts, daemon=True).start()

    # region ui
    # the workflow, one view per step; any step can be opened at any time
    VIEWS: ClassVar = [
        ("Source", "Step 1: the picture, and the figure found in it"),
        ("Miniature", "Step 2: the piece as it will print"),
        ("Print sheet", "Step 3: the pages to print"),
    ]
    SOURCE, MINI, SHEET = range(3)

    def _make_ui(self):
        self._tinted = []  # (widget, icon name, color token, size): re-tinted on theme change
        central = QWidget()
        central.setObjectName("Body")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.panel = FigurePanel(self._prefs, self._size_calculator, self._fonts)
        self.panel.changed.connect(self._settings_changed)
        self.panel.applyToAll.connect(self._apply_to_all)
        self.sheet_panel = SheetPanel(self._prefs)
        self.sheet_panel.changed.connect(self._sheet_changed)
        self.sheet_panel.printClicked.connect(self.print_sheet)
        self.sheet_panel.exportClicked.connect(self.export_pdf)
        self.panel.exportPiece.connect(self.export_current)
        canvas = self._make_canvas()
        root.addWidget(self._make_header())
        root.addWidget(self.updater.bar)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(1)
        self.splitter = split
        split.addWidget(self._make_figure_list())
        split.addWidget(canvas)
        right = QFrame()
        right.setObjectName("SideRight")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        # the selected figure's settings, or on the Print sheet step the sheet's own
        self.side = QStackedWidget()
        self.side.addWidget(self.panel)
        self.side.addWidget(self.sheet_panel)
        rv.addWidget(self.side)
        # usable width or dragged shut - never a sliver with clipped fields: as wide as
        # the widest step needs (measured with every group shown), not just the empty state
        right.setMinimumWidth(
            max(
                self.panel.minimumSizeHint().width(),
                self.sheet_panel.minimumSizeHint().width(),
            )
        )
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([290, 790, 380])
        # the side panels can be dragged shut (and back open); the canvas cannot
        split.setCollapsible(0, True)
        split.setCollapsible(1, False)
        split.setCollapsible(2, True)
        split.splitterMoved.connect(lambda *_: self._side_dragged())
        self._side_width = {0: 260, 2: 380}  # width to reopen a collapsed panel at
        root.addWidget(split, 1)
        self.setCentralWidget(central)

        self.info = QLabel()
        self.statusBar().addPermanentWidget(self.info)
        self.statusBar().setSizeGripEnabled(False)

    def _tool(self, icon: str, tip: str, slot, size: int = 18) -> QToolButton:
        b = QToolButton()
        b.setToolTip(tip)
        b.setAccessibleName(
            tip.split("  (")[0]
        )  # icon-only: name it for screen readers
        b.setIconSize(QSize(size, size))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        self._tinted.append((b, icon, "text", size))
        return b

    def _make_header(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Header")
        outer = QHBoxLayout(bar)
        outer.setContentsMargins(14, 8, 12, 8)
        outer.setSpacing(4)
        # the steps sit in the middle of the window: the parts left and right of them are
        # kept equally wide (see _balance_header)
        self._head_left, self._head_right = QWidget(), QWidget()
        h = QHBoxLayout(self._head_left)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self.logo = QLabel()
        self.logo.setPixmap(theme.logo_pixmap(30))
        name = QLabel("papermini")
        name.setObjectName("AppName")
        self.project_label = QLabel()
        self.project_label.setObjectName("ProjectName")
        h.addWidget(self.logo)
        h.addSpacing(4)
        h.addWidget(name)
        h.addSpacing(10)
        h.addWidget(self.project_label)
        h.addSpacing(14)
        h.addWidget(
            self._tool("open", "Open a project or images  (Ctrl+O)", self.open_dialog)
        )
        h.addWidget(self._tool("save", "Save project  (Ctrl+S)", self.save))
        h.addStretch(1)
        self.views = Segmented(self.VIEWS, steps=True)
        self.views.changed.connect(self.tabs.setCurrentIndex)
        outer.addWidget(self._head_left, 1)
        outer.addWidget(self.views)
        outer.addWidget(self._head_right, 1)
        h = QHBoxLayout(self._head_right)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch(1)
        # (Export SVG is on the Miniature step's panel, Print and Export on the sheet's)
        self._tinted += [
            (self.panel.export_piece, "export", "text", 16),
            (self.sheet_panel.print_btn, "printer", "text", 16),
            (self.sheet_panel.export_btn, "pdf", "accent_text", 16),
        ]
        for btn in (
            self.panel.export_piece,
            self.sheet_panel.print_btn,
            self.sheet_panel.export_btn,
        ):
            btn.setIconSize(QSize(16, 16))
        self.menu_btn = QToolButton()
        self.menu_btn.setToolTip("Menu")
        self.menu_btn.setAccessibleName("Menu")
        self.menu_btn.setIconSize(QSize(18, 18))
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self._tinted.append((self.menu_btn, "menu", "text", 18))
        h.addWidget(self.menu_btn)
        return bar

    def _balance_header(self):
        """Both sides of the steps as wide as the wider one, so the steps stay centred."""
        w = max(self._head_left.sizeHint().width(), self._head_right.sizeHint().width())
        for side in (self._head_left, self._head_right):
            side.setMinimumWidth(w)

    def _side_button(self, i: int):
        """A floating button on the canvas that hides / shows side panel ``i``."""
        card = QFrame()
        card.setObjectName("ZoomBar")  # same floating card as the zoom controls
        h = QHBoxLayout(card)
        h.setContentsMargins(4, 3, 4, 3)
        b = QToolButton()
        b.setIconSize(QSize(16, 16))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda: self.toggle_side(i))
        b.setFocusPolicy(
            Qt.TabFocus
        )  # keyboard focus ring, but no stuck ring after a click
        h.addWidget(b)
        return b, card

    def _make_figure_list(self) -> QFrame:
        left = QFrame()
        left.setObjectName("SideLeft")
        v = QVBoxLayout(left)
        v.setContentsMargins(10, 14, 10, 10)
        v.setSpacing(8)
        head = QHBoxLayout()
        head.setContentsMargins(8, 0, 0, 0)
        title = QLabel("Figures")
        title.setObjectName("PanelTitle")
        self.count_label = QLabel("0")
        self.count_label.setObjectName("Muted")
        head.addWidget(title)
        head.addSpacing(4)
        head.addWidget(self.count_label)
        head.addStretch(1)
        head.addWidget(
            self._tool("add", "Add images  (Ctrl+I)", self.add_images_dialog, 16)
        )
        head.addWidget(
            self._tool(
                "add_folder",
                "Add a folder of images  (Ctrl+Shift+I)",
                self.add_folder_dialog,
                16,
            )
        )
        self.btn_remove = self._tool(
            "trash", "Remove the selected figure  (Del)", self.remove_current, 16
        )
        head.addWidget(self.btn_remove)
        v.addLayout(head)
        v.addLayout(self._make_link_bar())
        self.list = QListWidget()
        self.list.setObjectName("Figures")
        delegate = FigureDelegate(self.list)
        delegate.copiesChanged.connect(self._copies_changed)
        self.list.setItemDelegate(delegate)
        self.list.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )  # (copies: see the delegate)
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setResizeMode(QListView.Adjust)  # cards follow the list's width
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.currentRowChanged.connect(lambda _: self._show_current())
        self.list.model().rowsMoved.connect(self._rows_moved)
        v.addWidget(self.list, 1)
        hint = QLabel(
            "Drop images, folders, image links or a project file anywhere in the window. "
            "Drag to reorder."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        hint.setContentsMargins(8, 0, 8, 0)
        v.addWidget(hint)
        return left

    def _make_link_bar(self) -> QHBoxLayout:
        """A field to paste image links into: Enter (or Add) downloads and adds them."""
        h = QHBoxLayout()
        h.setSpacing(6)
        self.link_edit = QLineEdit()
        self.link_edit.setObjectName("LinkEdit")
        self.link_edit.setPlaceholderText("Paste an image link")
        self.link_edit.setToolTip(
            "Paste the link of an image on the web and press Enter. "
            "In a browser: right-click the picture, Copy image address."
        )
        self.link_edit.setClearButtonEnabled(True)
        self._link_icon = self.link_edit.addAction(QIcon(), QLineEdit.LeadingPosition)
        self.link_edit.returnPressed.connect(self.add_from_link_bar)
        self.link_add = QPushButton("Add")
        self.link_add.setToolTip("Download the image and add it as a figure  (Enter)")
        self.link_add.setCursor(Qt.PointingHandCursor)
        self.link_add.setEnabled(False)
        self.link_add.clicked.connect(self.add_from_link_bar)
        self.link_edit.textChanged.connect(
            lambda t: self.link_add.setEnabled(bool(t.strip()))
        )
        h.addWidget(self.link_edit, 1)
        h.addWidget(self.link_add)
        return h

    def _make_canvas(self) -> QWidget:
        canvas = QWidget()
        grid = QGridLayout(canvas)
        grid.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        self.mini_view = MiniView()
        self.mini_view.areaChanged.connect(self.panel.set_token_area)
        self.crop_view = CropView()
        self.crop_view.cropChanged.connect(self.panel.set_crop)
        sheet_page = QWidget()
        sv = QGridLayout(sheet_page)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        self.sheet_view = ZoomView()
        sv.addWidget(self.sheet_view, 0, 0)
        self.sheet_banner = (
            Banner()
        )  # why the sheet is empty: a figure too big for the paper
        self.sheet_banner_box = overlay_wrap(self.sheet_banner)
        self.sheet_banner_box.hide()
        sv.addWidget(self.sheet_banner_box, 0, 0, Qt.AlignCenter)
        for view, (label, tip) in zip(
            (self.crop_view, self.mini_view, sheet_page), self.VIEWS
        ):
            self.tabs.addTab(view, label)
        self.tabs.currentChanged.connect(self._tab_changed)
        grid.addWidget(self.tabs, 0, 0)

        self.empty = EmptyState()
        self.empty.addClicked.connect(self.add_images_dialog)
        self.empty.openClicked.connect(self.open_dialog)
        self.empty.linkClicked.connect(self.focus_link_bar)
        self.empty.folderClicked.connect(self.add_folder_dialog)
        self.empty.recentClicked.connect(self._open_recent)
        self.empty.set_recent(self._prefs.recent_projects())
        grid.addWidget(self.empty, 0, 0, Qt.AlignCenter)
        self.banner = Banner()
        self.banner_box = overlay_wrap(self.banner)
        self.banner_box.hide()
        grid.addWidget(self.banner_box, 0, 0, Qt.AlignTop | Qt.AlignHCenter)
        self.busy = QLabel("Building preview…")
        self.busy.setObjectName("Busy")
        self.busy_box = overlay_wrap(self.busy)
        self.busy_box.hide()
        grid.addWidget(self.busy_box, 0, 0, Qt.AlignTop | Qt.AlignHCenter)
        # slow work (a model run) in the middle of the canvas, with Cancel
        self.work = WorkCard()
        self.work.clicked.connect(self._work_clicked)
        self.work_box = overlay_wrap(self.work)
        self.work_box.hide()
        grid.addWidget(self.work_box, 0, 0, Qt.AlignCenter)
        self.zoombar = ZoomBar()
        self.zoombar.zoomIn.connect(lambda: self._active_view().zoom_by(1.25))
        self.zoombar.zoomOut.connect(lambda: self._active_view().zoom_by(0.8))
        self.zoombar.fit.connect(self._fit)
        self.zoombar.actual.connect(self._actual)
        # side panel toggles in the bottom corners, next to the panel they control
        # (always shown, so a collapsed panel can be brought back)
        self.btn_left, left_card = self._side_button(0)
        grid.addWidget(overlay_wrap(left_card), 0, 0, Qt.AlignBottom | Qt.AlignLeft)
        # what the marks on the Source view mean (only there, with an image): above the
        # figure list toggle, clear of the banner at the top and the zoom bar. It lets
        # the mouse through, so a crop handle under it can still be dragged.
        self.legend = SourceLegend()
        self.legend_box = overlay_wrap(
            self.legend, (16, 16, 16, 16 + left_card.sizeHint().height() + 8)
        )
        for w in (self.legend, self.legend_box):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.legend_box.hide()
        grid.addWidget(self.legend_box, 0, 0, Qt.AlignBottom | Qt.AlignLeft)
        self.btn_right, right_card = self._side_button(2)
        self.zoom_box = QWidget()
        self.zoom_box.setAttribute(Qt.WA_TranslucentBackground)
        zb = QHBoxLayout(self.zoom_box)
        zb.setContentsMargins(16, 16, 16, 16)
        zb.setSpacing(8)
        # with a crop box on the Source view: take it away again in one click
        self.clear_crop_card = QFrame()
        self.clear_crop_card.setObjectName("ZoomBar")  # the same floating card
        cl = QHBoxLayout(self.clear_crop_card)
        cl.setContentsMargins(4, 3, 4, 3)
        self.btn_clear_crop = QToolButton()
        self.btn_clear_crop.setText("Clear crop")
        self.btn_clear_crop.setToolTip(
            "Remove the crop box, so background removal looks at "
            "the whole image (Delete). Ctrl+Z undoes a crop change."
        )
        self.btn_clear_crop.setCursor(Qt.PointingHandCursor)
        self.btn_clear_crop.clicked.connect(lambda: self.panel.set_crop(None))
        cl.addWidget(self.btn_clear_crop)
        self.clear_crop_card.hide()
        zb.addWidget(self.clear_crop_card, 0, Qt.AlignBottom)
        zb.addWidget(self.zoombar, 0, Qt.AlignBottom)
        zb.addWidget(right_card, 0, Qt.AlignBottom)
        grid.addWidget(self.zoom_box, 0, 0, Qt.AlignBottom | Qt.AlignRight)
        for v in (self.crop_view, self.mini_view, self.sheet_view):
            v.zoomChanged.connect(
                lambda z, v=v: v is self._active_view() and self.zoombar.set_zoom(z)
            )
        return canvas

    def _make_actions(self):
        def act(text, slot, key=None, tip=None):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if key:
                a.setShortcut(QKeySequence(key))
            if tip:
                a.setStatusTip(tip)
            self.addAction(a)  # shortcuts work without a menu bar
            return a

        self.a_new = act("New project", self.new_project, QKeySequence.New)
        self.a_open = act(
            "Open…",
            self.open_dialog,
            QKeySequence.Open,
            "Open a project (.yaml) or images",
        )
        self.a_add = act("Add images…", self.add_images_dialog, "Ctrl+I")
        self.a_add_folder = act(
            "Add folder…",
            self.add_folder_dialog,
            "Ctrl+Shift+I",
            "Add every image in a folder (and, as set in Preferences, its subfolders)",
        )
        self.a_add_link = act(
            "Add image from a link…",
            self.focus_link_bar,
            "Ctrl+L",
            "Download an image from the web by its link (URL)",
        )
        self.a_paste = act(
            "Paste images",
            self.paste,
            QKeySequence.Paste,
            "Add copied image files, or an image or its link copied in a browser",
        )
        self.a_save = act("Save project", self.save, QKeySequence.Save)
        self.a_save_as = act("Save project as…", self.save_as, QKeySequence.SaveAs)
        self.a_svg = act(
            "Export…",
            self.export_current,
            "Ctrl+E",
            "Save the selected figure as an SVG (to print or cut) or a PNG (for "
            "a virtual tabletop)",
        )
        self.a_svgs = act(
            "Export all…",
            self.export_all,
            "Ctrl+Shift+E",
            "Save every figure as an SVG, a PNG or both",
        )
        self.a_pdf = act(
            "Export sheet…",
            self.export_pdf,
            "Ctrl+P",
            "Save the sheet to print (PDF) and, cut by machine, the cut file",
        )
        self.a_print = act(
            "Print sheet…",
            self.print_sheet,
            "Ctrl+Shift+P",
            "Print the sheet at its real size",
        )
        self.a_undo_crop = act(
            "Undo crop change",
            self.undo_crop,
            QKeySequence.Undo,
            "Put the crop box back as it was before the last change",
        )
        self.a_remove = act("Remove figure", self.remove_current, QKeySequence.Delete)
        self.a_remove.setShortcutContext(Qt.WidgetShortcut)
        self.list.addAction(self.a_remove)
        self.a_quit = act("Quit", self.close, QKeySequence.Quit)
        self.a_fit = act("Fit to window", self._fit, "Ctrl+0")
        self.a_actual = act(
            "Actual size",
            self._actual,
            "Ctrl+1",
            "Show at real size (depends on your screen's reported DPI)",
        )
        self.a_left = act(
            "Figure list",
            lambda on: self.set_side_visible(0, on),
            "Ctrl+B",
            "Show or hide the figure list",
        )
        self.a_right = act(
            "Settings",
            lambda on: self.set_side_visible(2, on),
            "Ctrl+Alt+B",
            "Show or hide the settings panel",
        )
        for a in (self.a_left, self.a_right):
            a.setCheckable(True)
            a.setChecked(True)
        self.a_prefs = act(
            "Preferences…",
            lambda: self.show_preferences(),
            "Ctrl+,",
            "Creature size presets, the theme, automatic updates, the log, "
            "and the background-removal models and cache",
        )
        self.a_check_updates = act(
            "Check for updates…",
            self.show_about,
            None,
            "See whether there is a newer papermini, and update",
        )
        self.a_report = act(
            "Report a problem…",
            lambda: errors.report_problem(self._logs, self),
            None,
            "Open a new issue on GitHub with your papermini version and "
            "system filled in, and the log folder to attach the log from",
        )
        self.a_open_logs = act(
            "Open log folder",
            lambda: errors.open_log_folder(self._logs),
            None,
            "Show papermini's logs (they stay on your computer)",
        )
        self.a_open_logs.setEnabled(self._logs.session() is not None)

        m = self.menu = QMenu(self)
        self.recent_menu = QMenu("Open recent", self)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        m.aboutToShow.connect(self._sync_recent_menu)
        for a in (
            self.a_new,
            self.a_open,
            self.recent_menu.menuAction(),
            self.a_add,
            self.a_add_folder,
            self.a_add_link,
            None,
            self.a_undo_crop,
            None,
            self.a_save,
            self.a_save_as,
            None,
            self.a_svg,
            self.a_svgs,
            self.a_pdf,
            self.a_print,
            None,
        ):
            m.addSeparator() if a is None else m.addAction(a)
        vm = m.addMenu("View")
        for a in (self.a_left, self.a_right, None, self.a_fit, self.a_actual):
            vm.addSeparator() if a is None else vm.addAction(a)
        m.addSeparator()
        m.addAction(self.a_prefs)
        m.addSeparator()
        m.addAction(self.a_check_updates)
        m.addAction(self.a_report)
        m.addAction(self.a_open_logs)
        m.addAction("About papermini", self.show_about)
        m.addAction(self.a_quit)
        self.menu_btn.setMenu(m)
        self._sync_sides()

    # endregion

    # region side panels
    SIDE_NAMES: ClassVar = {0: "figure list", 2: "settings"}

    def side_visible(self, i: int) -> bool:
        return self.splitter.sizes()[i] > 0

    def toggle_side(self, i: int):
        self.set_side_visible(i, not self.side_visible(i))

    def set_side_visible(self, i: int, show: bool):
        """Collapse a side panel, or reopen it at the width it had."""
        sizes = self.splitter.sizes()
        if (sizes[i] > 0) != show:
            if show:
                w = max(
                    self._side_width[i],
                    self.splitter.widget(i).minimumSizeHint().width(),
                    self.splitter.widget(i).minimumWidth(),
                )
                sizes[i], sizes[1] = w, max(sizes[1] - w, 0)
            else:
                self._side_width[i] = sizes[i]
                sizes[1] += sizes[i]
                sizes[i] = 0
            self.splitter.setSizes(sizes)
        self._sync_sides()

    def _restore_layout(self):
        """Panel widths and which panels are collapsed, as they were last time."""
        state = self._prefs.splitter_state()
        if state is not None:
            self.splitter.restoreState(state)
            self.splitter.setCollapsible(1, False)  # (not part of the saved state)
        for i, w in (
            (0, self._prefs.left_panel_width()),
            (2, self._prefs.right_panel_width()),
        ):
            if w > 0:
                self._side_width[i] = w
        self._sync_sides()

    def _save_layout(self):
        sizes = self.splitter.sizes()
        for i in self._side_width:
            if sizes[i] > 0:
                self._side_width[i] = sizes[i]
        self._prefs.set_splitter_state(self.splitter.saveState())
        self._prefs.set_left_panel_width(self._side_width[0])
        self._prefs.set_right_panel_width(self._side_width[2])

    def _side_dragged(self):
        # remember open widths while dragging, so a panel dragged shut reopens at the
        # width it had just before
        for i, w in enumerate(self.splitter.sizes()):
            if i in self._side_width and w > 0:
                self._side_width[i] = w
        self._sync_sides()

    def _sync_sides(self):
        """Toggle buttons and menu checks follow the panels, however they were moved."""
        if not hasattr(self, "a_left"):
            return
        t = theme.current
        for i, btn, a in (
            (0, self.btn_left, self.a_left),
            (2, self.btn_right, self.a_right),
        ):
            on = self.side_visible(i)
            name = ("panel_left" if i == 0 else "panel_right") + ("_on" if on else "")
            btn.setIcon(theme.icon(name, t.text, 16))
            key = a.shortcut().toString(QKeySequence.NativeText)
            verb = "Hide" if on else "Show"
            btn.setToolTip(f"{verb} the {self.SIDE_NAMES[i]}  ({key})")
            btn.setAccessibleName(f"{verb} the {self.SIDE_NAMES[i]}")
            btn.setAccessibleDescription(f"Shortcut: {key}")
            a.blockSignals(True)
            a.setChecked(on)
            a.blockSignals(False)

    # endregion

    # region theme
    def set_theme(self, mode: str):
        self._theme_mode = mode
        self._prefs.set_theme(mode)
        app = QApplication.instance()
        if app is not None:
            theme.apply(app, mode)
        self._refresh_theme()

    def _system_scheme_changed(self, *_):
        if self._theme_mode == "system":
            self.set_theme("system")

    def _refresh_theme(self):
        t = theme.current
        self._link_icon.setIcon(theme.icon("link", theme.current.muted, 16))
        for w, name, token, size in self._tinted:
            if isinstance(w, QLabel):
                w.setPixmap(theme.pixmap(name, getattr(t, token), size))
            else:
                w.setIcon(theme.icon(name, getattr(t, token), size))
        self.zoombar.refresh_icons()
        self.legend.refresh_theme()
        self.empty.refresh_icons()
        self.panel.refresh_icons()
        self.crop_view.refresh_theme()
        self._sync_sides()
        for sec in self.panel.findChildren(Section):
            sec._toggle(sec.header.isChecked())
        for v in (self.mini_view, self.crop_view, self.sheet_view):
            v.viewport().update()
        self.list.viewport().update()
        fig = self.current()
        if fig is not None and fig.mini is not None:
            self._show_mini(fig)  # paper shadow color
        self._sheet_timer.start()

    # endregion

    # region figures
    def current(self) -> Figure | None:
        r = self.list.currentRow()
        return self.figures[r] if 0 <= r < len(self.figures) else None

    def _base_settings(self, settings: FigureSettings | None) -> FigureSettings | None:
        """New figures start from the selected figure's settings (or ``settings``)."""
        return (
            self.current().entry.settings
            if (settings is None and self.current())
            else settings
        )

    def _new_settings(self, base: FigureSettings | None) -> FigureSettings:
        if base is None:  # Medium, from the project's size table
            return self._size_calculator.apply(
                FigureSettings(), sizes.DEFAULT_SIZE, self.project.sizes
            )
        return replace(base, label=None, crop=None, mask=None)

    def _fresh_project(self) -> Project:
        """A new project, with the user's default creature size preset."""
        return Project(sizes=self._prefs.default_table())

    def add_images(self, paths, settings: FigureSettings | None = None, names=None):
        """Add image files; links among ``paths`` are downloaded first (in the background).
        ``names``: a figure name for each path (None: named after the file)."""
        base = self._base_settings(settings)
        links = [str(p).strip() for p in paths if ImageFetcher.is_url(p)]
        added = 0
        for p, name in zip(paths, names or [None] * len(paths)):
            if ImageFetcher.is_url(p):
                continue
            p = ImageFiles.local_path(p).resolve()
            if not ImageFiles.is_image_file(p):
                continue
            self._append(FigureEntry(p, self._new_settings(base), name))
            added += 1
        if added:
            names = [f.entry.image.name for f in self.figures[-added:]]
            ui_log.info(
                "Added %d image(s): %s",
                added,
                ", ".join(names[:10]) + (", …" if added > 10 else ""),
            )
            self.list.setCurrentRow(len(self.figures) - 1)
            self._set_modified()
        if links:
            self.add_links(links, base)
        return added

    def add_links(self, links, settings: FigureSettings | None = None):
        """Add images from links: downloaded once (in the background), then cached."""
        base = self._base_settings(settings)
        for url in links:
            url = url.strip()
            hit = self._images_from_web.cached_image(url)
            if hit is not None:
                self._on_link_done(url, hit, "", base)
                continue
            self._status(f"Downloading {url} …")
            threading.Thread(
                target=self._fetch_link, args=(url, base), daemon=True
            ).start()

    def _fetch_link(self, url: str, base):  # on a worker thread
        try:
            path, err = self._images_from_web.fetch_image(url, cancel=self._closing), ""
        except ValueError as e:
            path, err = None, str(e)
        if not self._closing.is_set():
            self.sig.link_done.emit(url, path, err, base)

    def _on_link_done(self, url: str, path, err: str, base):
        if self._closing.is_set():
            return
        if path is None:
            self._status("Could not add the image")
            self._warn(f"Could not add the image.\n\n{err}")
            return
        self._append(FigureEntry(Path(path), self._new_settings(base), source=url))
        ui_log.info("Added %s from %s", Path(path).name, LogSession.link_text(url))
        self.list.setCurrentRow(len(self.figures) - 1)
        self._set_modified()
        self._status(f"Added {Path(path).name}")

    def focus_link_bar(self):
        """Show the figure list and put the cursor in its link field, with a copied
        link already filled in."""
        self.set_side_visible(0, True)
        clip = QApplication.clipboard().text().strip()
        if not self.link_edit.text().strip() and ImageFetcher.is_url(clip):
            self.link_edit.setText(clip)
        self.link_edit.setFocus(Qt.ShortcutFocusReason)
        self.link_edit.selectAll()

    def add_from_link_bar(self):
        """Add the link(s) typed or pasted into the link field."""
        words = self.link_edit.text().split()
        if not words:
            return
        links = [w for w in words if ImageFetcher.is_url(w)]
        if len(links) != len(words):
            self._status("That is not a link: it should start with http:// or https://")
            self.link_edit.setFocus()
            self.link_edit.selectAll()
            return
        self.link_edit.clear()
        self.add_links(links)

    @staticmethod
    def _sources(mime):
        """(local files, web links) in dropped or pasted data. A picture dragged or copied
        from a browser carries its own address in the HTML; prefer that over the link
        around it, which is often a web page rather than the image."""
        files = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
        links = []
        if mime.hasHtml():
            found = IMG_SRC.findall(mime.html())
            links = [s for s in found if ImageFetcher.is_url(s)][:1]
        if not links:
            links = [
                u.toString() for u in mime.urls() if ImageFetcher.is_url(u.toString())
            ]
        if not links and not files and mime.hasText():
            links = [t for t in mime.text().split() if ImageFetcher.is_url(t)]
        return files, links

    def paste(self):
        """Ctrl+V outside a text field: add copied image files or image links."""
        files, links = self._sources(QApplication.clipboard().mimeData())
        if files or links:
            self.open_paths(files + links)
        else:
            self._status(
                "Nothing to paste: copy image files, or an image or its link in a browser"
            )

    def _append(self, entry: FigureEntry):
        fig = Figure(next(self._uids), entry, bleed_mm=self.project.sheet.figure_bleed)
        self.figures.append(fig)
        item = QListWidgetItem(entry.display_name)
        img = load_qimage(entry.image)
        if not img.isNull():
            item.setIcon(
                QIcon(
                    QPixmap.fromImage(
                        img.scaled(
                            112, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                    )
                )
            )
        item.setToolTip(entry.source or str(entry.image))
        item.setData(Qt.UserRole, fig.uid)
        item.setData(SUBTITLE_ROLE, "Building…")
        item.setData(COPIES_ROLE, entry.settings.copies)
        item.setFlags(item.flags() | Qt.ItemIsEditable)  # (the copies box)
        item.setSizeHint(QSize(0, FigureDelegate.H))
        self.list.addItem(item)
        self.count_label.setText(str(len(self.figures)))

    def _refresh_card(self, fig: Figure):
        """Figure list entry: name, a thumbnail of the finished piece, size and copies."""
        item = self._list_item(fig)
        if item is None:
            return
        item.setText(fig.entry.display_name)
        item.setData(COPIES_ROLE, fig.entry.settings.copies)
        if fig.error and not fig.up_to_date:
            item.setData(SUBTITLE_ROLE, "Needs attention")
        elif fig.stopped and not fig.up_to_date:
            item.setData(SUBTITLE_ROLE, "Cancelled")
        elif fig.mini is None:
            item.setData(SUBTITLE_ROLE, "Building…")
        else:
            m = fig.mini
            item.setData(
                SUBTITLE_ROLE,
                f"\u2300 {m.figure_height_mm:.0f} mm"
                if m.kind == "token"
                else f"{m.figure_height_mm:.0f} mm",
            )
            if fig.pixmap is not None:
                item.setIcon(
                    QIcon(
                        fig.pixmap.scaled(
                            112, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                    )
                )

    def remove_current(self):
        r = self.list.currentRow()
        if r < 0:
            return
        ui_log.info("Removed %s", self.figures[r].entry.image.name)
        self.figures.pop(r)
        self.list.takeItem(r)
        self.count_label.setText(str(len(self.figures)))
        self._set_modified()
        self._show_current()
        self._sheet_timer.start()

    def _rows_moved(self, *_):
        by_uid = {f.uid: f for f in self.figures}
        self.figures = [
            by_uid[self.list.item(i).data(Qt.UserRole)]
            for i in range(self.list.count())
        ]
        self._set_modified()

    def _figure(self, uid) -> Figure | None:
        return next((f for f in self.figures if f.uid == uid), None)

    def _list_item(self, fig: Figure) -> QListWidgetItem | None:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == fig.uid:
                return self.list.item(i)
        return None

    # endregion

    # region settings
    def _copies_changed(self, uid, n: int):
        """Copies set on a figure's card: only the sheet changes, nothing rebuilds."""
        fig = self._figure(uid)
        if fig is None or n == fig.entry.settings.copies:
            return
        self._note_settings(fig.uid, fig.entry.image.name, fig.entry.settings)
        fig.entry.settings = replace(fig.entry.settings, copies=n)
        self._refresh_card(fig)
        self._set_modified()
        self._sheet_timer.start()

    def _settings_changed(self, s: FigureSettings):
        fig = self.current()
        if fig is None:
            return
        old = fig.entry.settings
        s = replace(
            s, copies=old.copies
        )  # (the copies are set on the card, not the panel)
        matched = self._size_calculator.reconcile(old, s, self.project.sizes)
        if (
            matched != s
        ):  # a picked size filled in its values, or a hand edit made it custom
            s = matched
            self.panel.show_size(s)
        if s.adjustments() != old.adjustments():
            self._picture_timer.start()  # (the model is not involved: no rebuild of the mask)
        if s.crop != old.crop and not self._undoing:  # a crop change can be undone
            self._crop_undo.append((fig.uid, old.crop))
            del self._crop_undo[:-50]
        if s.model != old.model:
            self._declined.clear()  # a new model choice may ask again
            ui_log.info("%s: model %s → %s", fig.entry.image.name, old.model, s.model)
        old_mask = fig.mask_key()
        self._note_settings(fig.uid, fig.entry.image.name, old)
        fig.entry.settings = s
        self.builds.settings_changed(fig, old_mask)
        fig.invalidate()
        self._refresh_card(fig)
        self.crop_view.set_crop(s.crop)
        self._sync_legend()
        self._set_modified()
        self.builds.build_soon()
        self._sheet_timer.start()  # e.g. copies: no rebuild, but the sheet changes

    def _note_settings(self, key, name: str, old) -> None:
        """Remember a figure's (or the sheet's) settings before a change, for the line
        the detailed log gets once the changes settle."""
        if ui_log.isEnabledFor(logging.DEBUG):
            self._settings_log.setdefault(key, (name, old))
            self._settings_log_timer.start()

    def _flush_settings_log(self) -> None:
        """Write the settled settings changes to the detailed log, as old -> new."""
        pending, self._settings_log = self._settings_log, {}
        for key, (name, old) in pending.items():
            fig = None if key == "sheet" else self._figure(key)
            new = (
                self.project.sheet
                if key == "sheet"
                else (fig.entry.settings if fig else None)
            )
            diff = LogSession.settings_diff(old, new) if new is not None else ""
            if diff:
                ui_log.debug("%s: %s", name, diff)

    def _apply_to_all(self, names=None):
        """Copy the current figure's settings (``names``, default all but the per-image
        ones) to every other figure."""
        cur = self.current()
        if cur is None:
            return
        src = asdict(cur.entry.settings)
        names = set(src) - PER_IMAGE if names is None else set(names) - PER_IMAGE
        for f in self.figures:
            if f is cur:
                continue
            f.entry.settings = replace(f.entry.settings, **{k: src[k] for k in names})
            f.invalidate()
        self._set_modified()
        ui_log.info(
            "Applied %s of %s to %d other figure(s)",
            ", ".join(sorted(names)),
            cur.entry.image.name,
            len(self.figures) - 1,
        )
        self._status(f"Applied settings to {len(self.figures) - 1} other figure(s)")
        self._sheet_timer.start()

    def _sheet_changed(self, s):
        self._note_settings("sheet", "sheet", self.project.sheet)
        self.project.sheet = s
        if any(f.bleed_mm != s.figure_bleed for f in self.figures):
            for (
                f
            ) in self.figures:  # cut by machine (or not): every piece gets its bleed
                f.bleed_mm = s.figure_bleed
                f.invalidate()
            self.builds.build_soon()
        self._set_modified()
        self._sheet_timer.start()

    def too_big(self, lay) -> tuple[str, list[str], str]:
        """The figures too big for the paper: a line saying so, their names, and what to
        do about it."""
        sh = self.project.sheet
        one = len(lay.left_out) == 1
        what = "the figure" if one else "the figures"
        advice = f"Pick bigger paper, or make {what} smaller in step 2 (Miniature)."
        if sh.paper == "custom":
            advice = (
                f"Make the paper bigger, or make {what} smaller in step 2 (Miniature)."
            )
        else:
            other = "landscape" if sh.orientation == "portrait" else "portrait"
            turned = replace(sh, orientation=other).layout(
                self._output.packer, [(m, 1) for m in lay.left_out], leave_out=True
            )
            if not turned.left_out:
                advice = (
                    f"{'It fits' if one else 'They fit'} on {turned.paper_name}: set "
                    f"Orientation to {other.title()}. Or pick bigger paper, or make "
                    f"{what} smaller in step 2 (Miniature)."
                )
        intro = (
            "The following figure is too large to fit on the selected paper:"
            if one
            else "The following figures are too large to fit on the selected paper:"
        )
        return intro, lay.too_big_names(self._names()), advice

    @staticmethod
    def _too_big_list(names: list[str]) -> str:
        """The figures too big for the paper as a bulleted list (rich text)."""
        items = "".join(f"<li>{html.escape(n)}</li>" for n in names)
        return (
            "<ul style='margin-top:4px; margin-bottom:6px; margin-left:0px; "
            f"-qt-list-indent:1;'>{items}</ul>"
        )

    def _names(self) -> dict:
        """The figures' names, by ``id(mini.art)`` (as the sheet's minis share it)."""
        return {id(f.mini.art): f.entry.display_name for f in self.figures if f.mini}

    def _find_fonts(self):
        """Look for the fonts installed on this computer (a worker thread)."""
        try:
            names = list(self._fonts.installed())
        except Exception:  # noqa: BLE001 - without them, the bundled fonts still work
            ui_log.exception("Could not look for the installed fonts")
            names = []
        self.sig.fonts_found.emit(names)

    # endregion

    # region building
    def _on_building(self, fig: Figure):
        """The selected figure was queued to build."""
        self.info.setText("building…")
        self.busy_box.setVisible(fig.mini is None or not fig.up_to_date)
        self._update_work()  # (hides it again behind a work card)

    def _on_built(self, fig: Figure, mini: Mini):
        fig.pixmap = QPixmap.fromImage(pil_to_qimage(mini.art))
        self._refresh_card(fig)
        if fig is self.current():
            self._show_mini(fig)
        self._status("Ready")
        self.exporter.check()
        if self.tabs.currentIndex() == self.SHEET:
            self._sheet_timer.start()

    def _on_failed(self, fig: Figure, msg: str):
        self._refresh_card(fig)
        if fig is self.current():
            self._show_mini(fig)
        self.exporter.check()
        self._status(f"{fig.entry.image.name}: {msg.splitlines()[0]}")

    def _on_cancelled(self, fig: Figure):
        """The user cancelled the model run of ``fig``."""
        self._refresh_card(fig)
        self.exporter.check()
        self._status(f"{fig.entry.image.name}: background removal cancelled")
        if fig is self.current():
            self.busy_box.hide()
            self.info.setText("cancelled")
        self._update_work()

    def _on_outline(self, fig: Figure, data):
        """A build found the figure in its image, before the miniature is laid out."""
        if fig is self.current():
            contours, close_px = data
            self.crop_view.set_outline(contours)
            self.panel.set_auto_fill_gaps(close_px)

    def _on_run_started(self):
        self._work_timer.start()
        QTimer.singleShot(300, self._update_work)  # cached masks come back at once

    def _on_run_ended(self):
        self._work_timer.stop()
        self._update_work()

    def _update_work(self):
        """The work card and the dimmed Source image for the selected figure: a model
        running for it (with Cancel), a model running for another figure that it waits
        for (Cancel stops that one), or a cancelled one (Run again)."""
        fig = self.current()
        run = self.builds.run
        if run is not None and run.seconds() < 0.25:
            run = None  # (cached masks come back at once)
        mode = None
        if fig is not None and self.tabs.currentIndex() != self.SHEET:
            if run and run.uid == fig.uid and run.mask_key == fig.mask_key():
                mode = "working"
            elif fig.stopped and not fig.up_to_date:
                mode = "cancelled"
            elif run and run.uid != fig.uid and not fig.up_to_date and not fig.error:
                mode = "waiting"
        if run is not None and mode in ("working", "waiting"):
            secs = int(run.seconds())
            loaded = self._pipeline.segmenters.is_loaded(run.model)
            model = run.model if loaded else f"loading {run.model}"
            detail = f"{model} · {secs} s" if secs else model
            if mode == "working":
                self.work.show_working("Removing the background…", detail)
            else:
                other = self._figure(run.uid)
                name = other.entry.display_name if other else "another figure"
                self.work.show_working(
                    f"Waiting for {name}",
                    f"Removing its background: {detail}",
                    "Cancel it",
                )
        elif mode == "cancelled":
            self.work.show_stopped(
                "Background removal cancelled",
                "Change the crop or model, or run it again.",
                "Run again",
            )
        self.work_box.setVisible(mode is not None)
        self.crop_view.set_busy(mode == "working")
        if mode is not None:
            self.busy_box.hide()

    def _work_clicked(self):
        fig = self.current()
        if fig is None:
            return
        if fig.stopped and not fig.up_to_date:
            fig.cancelled = fig.error = fig.queued = None  # Run again
            self._refresh_card(fig)
            self._update_work()
            self.builds.build_current()
        else:
            self.builds.cancel()  # its own model run, or the one it waits for

    def _confirm_download(self, model: str) -> bool:
        """Build thread: ask (on the GUI thread) before a model is downloaded. The
        dialog downloads it, so the build continues with the file on disk."""
        if model in self._declined or segment.CANCEL.is_set():
            return False
        answer, done = {"ok": False}, threading.Event()
        self.sig.ask_download.emit(model, answer, done)
        while not done.wait(0.1):
            if segment.CANCEL.is_set():  # the window is closing
                answer["gone"] = True  # nobody waits for this question any more
                return False
        return answer["ok"]

    def _ask_download(self, model: str, answer: dict, done: threading.Event):
        try:
            if answer.get(
                "gone"
            ):  # the build stopped waiting (window closed): do not ask
                return
            segmenters = self._pipeline.segmenters
            if segmenters.path(
                model
            ).exists():  # downloaded meanwhile (Models and cache)
                answer["ok"] = True
                return
            ok = DownloadDialog(model, segmenters, self).exec() == QDialog.Accepted
            answer["ok"] = ok
            if not ok:
                self._declined.add(model)
        finally:
            done.set()

    def _models_changed(self, model: str):
        """Retry figures that failed, e.g. because a model was not downloaded."""
        self._declined.discard(model)
        for f in self.figures:
            if f.error and not f.up_to_date:
                f.error = None
                self._refresh_card(f)
        self.builds.build_current()
        if self.tabs.currentIndex() == self.SHEET:
            self._sheet_timer.start()

    def _download_progress(self, done, total, msg):
        t = f" / {total / 1e6:.0f}" if total else ""
        self.sig.status.emit(f"{msg}: {done / 1e6:.0f}{t} MB (first run only)")

    def _status(self, msg: str):
        self.statusBar().showMessage(
            msg, 0 if msg.endswith("…") or "MB" in msg else 6000
        )

    # endregion

    # region showing
    def _show_current(self):
        fig = self.current()
        has = fig is not None
        for w in (self.a_svg, self.panel.export_piece, self.btn_remove):
            w.setEnabled(has)
        for w in (self.sheet_panel.print_btn, self.sheet_panel.export_btn):
            w.setEnabled(bool(self.figures))
        self.empty.setVisible(not self.figures)
        self.zoombar.setVisible(bool(self.figures))
        self._sync_legend()
        if not has:
            self.panel.set_settings(FigureSettings())  # reset the hidden fields
            self.panel.set_empty(
                True,
                "Select a figure in the list to see its settings here."
                if self.figures
                else "Add images to see their settings here.",
            )
            self.mini_view.scene().clear()
            self.mini_view.set_token(None)
            self.crop_view.set_image(None)
            self.banner_box.hide()
            self.busy_box.hide()
            self.work_box.hide()
            self.info.setText("")
            return
        e = fig.entry
        self.panel.set_settings(e.settings, e.display_name, e.image.stem)
        self.panel.subtitle.setText(e.image.name)
        self.crop_view.set_image(*self._source_picture(fig))
        self.crop_view.set_crop(e.settings.crop)
        self.panel.set_aspect(fig.mini.aspect if fig.mini else None)
        self.mini_view.refit_on_next_show()
        self._show_mini(fig)
        self._update_work()
        if not fig.up_to_date:
            QTimer.singleShot(
                0, self.builds.build_current
            )  # (start(0) would kill the debounce)

    def _show_mini(self, fig: Figure):
        sc = self.mini_view.scene()
        self.panel.set_overlap_hint(None)
        # how "auto" found the figure: it depends only on the image and mask, so a stale
        # piece of this figure still tells
        self.panel.set_auto_method(fig.mini.method if fig.mini is not None else None)
        self.panel.set_figure_width(
            fig.mini.figure_width_mm if fig.mini is not None else None
        )
        if fig.error and not fig.up_to_date:
            sc.clear()
            self.mini_view.set_token(None)
            self.crop_view.set_outline(None)
            self.busy_box.hide()
            msg = html.escape(fig.error).replace("\n", "<br>")
            hint = (
                ""
                if "not downloaded" in fig.error
                else "<br><br>Try a lower strength, a crop, or another model."
            )
            self.banner.show_message("This miniature could not be built", msg + hint)
            self.banner_box.show()
            self.info.setText("error")
            return
        self.banner_box.hide()
        m = fig.mini
        # (the work card, when shown, already says what is going on)
        self.busy_box.setVisible(
            (m is None or not fig.up_to_date) and not self.work_box.isVisibleTo(self)
        )
        if m is None:
            sc.clear()
            self.mini_view.set_token(None)
            self.crop_view.set_outline(None)
            return
        first = sc.itemsBoundingRect().isEmpty() or self.mini_view._fit_pending
        draw_mini_page(sc, m, self._fonts)
        sc.setSceneRect(sc.itemsBoundingRect())
        # a token's framing handles (only on a piece built from the settings shown)
        if m.kind == "token" and fig.up_to_date:
            s = fig.entry.settings
            self.mini_view.set_token(
                m.token,
                *self._source_picture(fig),
                m.source_outline,
                (s.token_fill, s.token_fill_color),
            )
        else:
            self.mini_view.set_token(None)
        if first:
            self.mini_view.fit()
        if fig.up_to_date:  # (a stale piece's outline would hide the new one)
            self.crop_view.set_outline(m.source_outline)
            self.panel.set_aspect(m.aspect)
        self.panel.set_auto_fill_gaps(m.close_px)
        if not m.tab_overlap_used:
            self.panel.set_overlap_hint("unused")
        elif m.tab_width_mm and m.tab_joint_mm < min(10.0, 0.6 * m.tab_width_mm):
            self.panel.set_overlap_hint("narrow", m.tab_joint_mm)
        stale = "" if fig.up_to_date else "  (updating…)"
        if m.kind == "token":
            self.info.setText(
                f"token \u2300 {m.figure_height_mm:.1f} mm · ring "
                f"{m.token.radius_mm - m.token.inner_mm:.1f} mm{stale}"
            )
            return
        self.info.setText(
            f"figure {m.figure_width_mm:.1f} × {m.figure_height_mm:.1f} mm · "
            f"piece {m.width_mm:.1f} × "
            f"{m.height_mm:.1f} mm · {len(m.cut.points)} cut nodes{stale}"
        )

    def _tab_changed(self, i):
        self.panel.set_step(i)
        self.side.setCurrentWidget(self.sheet_panel if i == self.SHEET else self.panel)
        self._update_work()
        self._sync_legend()
        if i == self.SHEET:
            self._refresh_sheet()
        QTimer.singleShot(0, self._tab_zoom)

    def _source_picture(self, fig: Figure):
        """(picture, original size or None) for the Source view: the image itself, or
        with color adjustments a smaller adjusted preview of it."""
        path = fig.entry.image
        if self._original[0] != path:
            self._original = (path, load_qimage(path))
        img = self._original[1]
        adj = fig.entry.settings.adjustments()
        if adj.is_identity() or img.isNull():
            return img, None
        return adjusted_preview(img, adj, self._pipeline.adjuster), (
            img.width(),
            img.height(),
        )

    def _refresh_picture(self):
        fig = self.current()
        if fig is not None:
            self.crop_view.replace_picture(self._source_picture(fig)[0])

    def _sync_legend(self):
        """The Source legend, shown on the Source view while it shows an image, and the
        Clear crop button, while that image has a crop box."""
        fig = self.current()
        self.legend_box.setVisible(
            fig is not None and self.tabs.currentIndex() == self.SOURCE
        )
        cropped = fig is not None and bool(fig.entry.settings.crop)
        self.clear_crop_card.setVisible(
            cropped and self.tabs.currentIndex() == self.SOURCE
        )

    def undo_crop(self):
        """Ctrl+Z: the crop box as it was before its last change (also of another
        figure, which is then selected). Text fields keep their own Ctrl+Z."""
        while self._crop_undo:
            uid, crop = self._crop_undo.pop()
            fig = self._figure(uid)
            if fig is None:
                continue  # removed since
            if fig is not self.current():
                self.list.setCurrentItem(self._list_item(fig))
            self._undoing = True
            try:
                self.panel.set_crop(crop)
            finally:
                self._undoing = False
            self._status("Crop change undone")
            return
        self._status("No crop change to undo")

    def _refresh_sheet(self):
        if self.tabs.currentIndex() != self.SHEET:
            return
        missing = [f for f in self.figures if not f.up_to_date and f.error is None]
        failed = [f for f in self.figures if not f.up_to_date and f.error is not None]
        for f in missing:
            self.builds.queue(f)
        # stale pieces stay visible while they rebuild, but not when their settings fail
        ready = [f for f in self.figures if f.mini is not None and f not in failed]
        sh = self.project.sheet
        sc = self.sheet_view.scene()
        for w in (
            self.sheet_panel.print_btn,
            self.sheet_panel.export_btn,
            self.a_print,
        ):
            w.setEnabled(bool(self.figures))
        self.sheet_banner_box.hide()
        self.sheet_panel.set_fit_warning("")
        if not ready:
            sc.clear()
            self.sheet_panel.info.setText(
                "Building…" if missing else "No miniatures yet"
            )
            return
        try:
            lay = sh.layout(
                self._output.packer,
                [(f.mini, f.entry.settings.copies) for f in ready],
                leave_out=True,
            )
        except ValueError as e:
            sc.clear()
            self.sheet_panel.info.setText(str(e))
            return
        if lay.left_out:  # nothing on the sheet until every figure fits
            sc.clear()
            intro, names, advice = self.too_big(lay)
            body = self._too_big_list(names) + html.escape(advice)
            self.sheet_banner.show_message(html.escape(intro), body)
            self.sheet_banner_box.show()
            self.sheet_panel.set_fit_warning(f"{html.escape(intro)}{body}")
            self.sheet_panel.info.setText(
                "The sheet shows nothing until every figure fits."
            )
            return
        first = sc.itemsBoundingRect().isEmpty()
        draw_sheet(
            sc, lay, sh.title, self._fonts, {id(f.mini.art): f.pixmap for f in ready}
        )
        sc.setSceneRect(sc.itemsBoundingRect())
        if first:
            self.sheet_view.fit()
        n = len(lay.placements)
        pending = f" · {len(missing)} building…" if missing else ""
        if failed:
            pending += f" · {len(failed)} failed (select to see why)"
        self.sheet_panel.info.setText(
            f"{n} piece{'s' * (n != 1)} on {lay.pages} "
            f"page{'s' * (lay.pages != 1)}{pending}"
        )

    def _fit(self):
        self._active_view().fit()

    def _tab_zoom(self):
        self.zoombar.set_zoom(self._active_view().zoom())

    def _actual(self):
        self._active_view().actual_size()

    def _active_view(self) -> ZoomView:
        return [self.crop_view, self.mini_view, self.sheet_view][
            self.tabs.currentIndex()
        ]

    # endregion

    # region export
    def export_current(self):
        """Save the selected figure as an SVG or a PNG."""
        fig = self.current()
        if fig is not None:
            self.exporter.export_figure(fig)

    def export_all(self):
        """Save every figure as an SVG, a PNG or both."""
        self.exporter.export_all()

    def export_pdf(self):
        """Save the sheet to print (PDF) and, cut by machine, its cut files."""
        self.exporter.export_sheet()

    def print_sheet(self):
        """Print the sheet at its real size."""
        self.exporter.print_sheet()

    # endregion

    # region project
    def open_paths(self, paths):
        """Open a project and/or add images: files, ``file://`` URIs or web links."""
        links = [str(p).strip() for p in paths if ImageFetcher.is_url(p)]
        paths = [ImageFiles.local_path(p) for p in paths if not ImageFetcher.is_url(p)]
        projects = [p for p in paths if p.suffix.lower() in (".yaml", ".yml")]
        if projects:
            self.load(projects[0])
        self.add_images([p for p in paths if ImageFiles.is_image_file(p)] + links)
        for folder in (p for p in paths if p.is_dir()):
            self.add_folder(folder)

    # endregion

    # region recent projects
    def _remember(self, path: Path) -> None:
        """Put the project at the top of Open recent and the start screen's list."""
        self._prefs.add_recent(path)
        self.empty.set_recent(self._prefs.recent_projects())

    def _sync_recent_menu(self) -> None:
        self.recent_menu.menuAction().setEnabled(bool(self._prefs.recent_projects()))

    def _fill_recent_menu(self) -> None:
        """Open recent: each project's name and its folder (shortened in the middle),
        newest first, and Clear list."""
        m = self.recent_menu
        m.clear()
        fm = m.fontMetrics()
        for p in self._prefs.recent_projects():
            folder = fm.elidedText(str(p.parent), Qt.ElideMiddle, 320)
            a = m.addAction(f"{p.name}\t{folder}".replace("&", "&&"))
            a.setToolTip(str(p))
            a.setData(str(p))
            a.triggered.connect(self._open_recent_action)
        m.addSeparator()
        m.addAction("Clear list", self._clear_recent)

    def _open_recent_action(self) -> None:
        self._open_recent(self.sender().data())

    def _open_recent(self, path: str) -> None:
        if not Path(path).is_file():  # (gone since the list was shown)
            self._warn(f"{path} is no longer there.")
            self.empty.set_recent(self._prefs.recent_projects())
            return
        self.load(Path(path))

    def _clear_recent(self) -> None:
        self._prefs.clear_recent()
        self.empty.set_recent([])

    def load(self, path: Path):
        if not self._maybe_save():
            return
        try:
            # images from links may download
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                proj = self._project_store.load(path)
            finally:
                QApplication.restoreOverrideCursor()
        except (OSError, ValueError, yaml.YAMLError) as e:
            self._warn(f"Could not open {path}:\n{e}")
            return
        ui_log.info("Opened project %s (%d figure(s))", path, len(proj.figures))
        self._remember(path)
        self._reset(proj)
        missing = [f.image.name for f in proj.figures if not f.image.exists()]
        if missing:
            self._warn("Missing images:\n" + "\n".join(missing))

    def _reset(self, proj: Project):
        self.project = proj
        self.figures.clear()
        self.list.clear()
        self.count_label.setText("0")
        for e in proj.figures:
            if e.image.exists():
                self._append(e)
        self.sheet_panel.set_settings(proj.sheet)
        self._sync_size_label()
        self._modified = False
        if self.figures:
            self.list.setCurrentRow(0)
        self._show_current()
        self._update_title()
        self._sheet_timer.start()

    def new_project(self):
        if self._maybe_save():
            ui_log.info("New project")
            self._reset(self._fresh_project())

    def open_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Open project or images",
            str(self.out_dir()),
            f"{PROJECT_FILTER};;{IMAGE_FILTER};;All files (*)",
        )
        if files:
            self.open_paths(files)

    def add_images_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add images", str(self.out_dir()), IMAGE_FILTER
        )
        if files:
            self.add_images(files)

    def add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Add a folder of images", str(self.out_dir())
        )
        if folder:
            self.add_folder(Path(folder))

    def add_folder(self, folder: Path) -> int:
        """Add every image in ``folder`` (and its subfolders, as set in Preferences), in
        natural order; asks about images already in the project. Returns how many."""
        folder = Path(folder).resolve()
        images, skipped = ImageFiles.folder_images(folder, self._prefs.add_subfolders())
        if not images:
            QMessageBox.information(
                self,
                "papermini",
                f"{folder.name} has no images papermini can read ({ImageFiles.READABLE}).",
            )
            return 0
        names = ImageFiles.figure_names(images, folder)
        have = {os.path.normcase(str(f.entry.image)) for f in self.figures}
        dup = [
            i
            for i, p in enumerate(images)
            if os.path.normcase(str(p.resolve())) in have
        ]
        left = 0  # images already in the project, not added again
        if dup:
            one = len(dup) == 1
            again = (
                QMessageBox.question(
                    self,
                    "papermini",
                    f"{len(dup)} of the images in {folder.name} {'is' if one else 'are'} already "
                    f"in the project. Add {'it' if one else 'them'} again?",
                )
                == QMessageBox.Yes
            )
            if not again:
                left = len(dup)
                images = [p for i, p in enumerate(images) if i not in dup]
                names = [n for i, n in enumerate(names) if i not in dup]
        added = self.add_images(images, names=names) if images else 0
        notes = (
            [f"{skipped} other file{'s' * (skipped != 1)} skipped"] if skipped else []
        ) + ([f"{left} already in the project"] if left else [])
        done = (
            f"Added {added} image{'s' * (added != 1)} from {folder.name}"
            if added
            else f"No images added from {folder.name}"
        )
        self._status(done + (f" ({', '.join(notes)})" if notes else ""))
        return added

    def save(self) -> bool:
        if self.project.path is None:
            return self.save_as()
        self.project.figures = [f.entry for f in self.figures]
        try:
            self._project_store.save(self.project, self.project.path)
        except OSError as e:
            self._warn(str(e))
            return False
        self._modified = False
        self._update_title()
        self._remember(self.project.path)
        ui_log.info(
            "Saved project %s (%d figure(s))", self.project.path, len(self.figures)
        )
        self._status(f"Saved {self.project.path}")
        return True

    def save_as(self) -> bool:
        start = self.project.path or (self.out_dir() / "minis.yaml")
        f, _ = QFileDialog.getSaveFileName(
            self, "Save project", str(start), PROJECT_FILTER
        )
        if not f:
            return False
        self.project.path = Path(f)
        return self.save()

    def out_dir(self) -> Path:
        """The folder the file dialogs start in: the project's output folder, else the
        first image's folder, else the home folder."""
        return (
            self.project.output_dir
            if self.project.path
            else (self.figures[0].entry.image.parent if self.figures else Path.home())
        )

    def _maybe_save(self) -> bool:
        if not self._modified or not self.figures:
            return True
        r = QMessageBox.question(
            self,
            "papermini",
            "Save changes to the project?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def _set_modified(self):
        if not self._modified:
            self._modified = True
            self._update_title()

    def _update_title(self):
        name = self.project.path.name if self.project.path else "untitled"
        self.setWindowTitle(f"{name}{' *' if self._modified else ''} — papermini")
        self.project_label.setText(
            f"{name}{'  •  unsaved changes' if self._modified else ''}"
        )
        self._balance_header()

    def show_preferences(self, page: str = "sizes"):
        """Open the Preferences window at ``page``. When it closes, the project takes the
        size table picked or edited there; figures with a size follow it."""
        dlg = self.preferences_dialog(page)
        dlg.exec()
        table = dlg.sizes.project_table()
        if table != self.project.sizes:
            self.set_size_table(table)
        else:
            self._sync_size_label()  # (a preset may have been renamed or deleted)

    def preferences_dialog(self, page: str = "sizes") -> PreferencesDialog:
        """Build the Preferences window at ``page``, connected to this window."""
        dlg = PreferencesDialog(
            self._prefs,
            self._size_calculator,
            self.project.sizes,
            lambda: [f.entry.image for f in self.figures],
            self._pipeline.segmenters,
            self._pipeline.masks,
            self._images_from_web,
            self._logs,
            page,
            self,
        )
        dlg.themeChanged.connect(self.set_theme)
        dlg.autoUpdatesChanged.connect(self.updater.set_auto_updates)
        dlg.modelsChanged.connect(self._models_changed)
        return dlg

    def _sync_size_label(self) -> None:
        self.panel.set_size_table(
            self.project.sizes, self._prefs.table_label(self.project.sizes)
        )

    def set_size_table(self, table: sizes.SizeTable) -> None:
        """Use ``table`` for this project: every figure with a creature size takes its
        values from it."""
        self.project.sizes = table
        self._sync_size_label()
        changed = 0
        for f in self.figures:
            s = f.entry.settings
            if s.size == sizes.CUSTOM:
                continue
            new = self._size_calculator.apply(s, s.size, table)
            if new != s:
                f.entry.settings = new
                f.invalidate()
                self._refresh_card(f)
                changed += 1
        ui_log.info(
            "Changed the creature size table (%s, grid %g mm, Medium %g mm); %d "
            "figure(s) follow it",
            table.name or "no preset",
            table.grid_mm,
            table.medium_mm,
            changed,
        )
        self._set_modified()
        self._show_current()
        self.builds.build_soon()
        self._sheet_timer.start()

    def _warn(self, text: str) -> None:
        """Show a problem to the user, and write it to the log."""
        ui_log.warning("%s", text.replace("\n\n", ": ").replace("\n", "; "))
        QMessageBox.warning(self, "papermini", text)

    def show_about(self):
        """Open the About window, which checks for updates."""
        self.updater.show_about()

    # endregion

    # region events
    def dragEnterEvent(self, e):
        files, links = self._sources(e.mimeData())
        if files or links:
            e.acceptProposedAction()

    def dropEvent(self, e):
        files, links = self._sources(e.mimeData())
        self.open_paths(files + links)

    def closeEvent(self, e):
        if self._maybe_save():
            self._flush_settings_log()
            self._closing.set()  # link downloads stop and are not added
            for t in (self._sheet_timer, self._work_timer, self._picture_timer):
                t.stop()  # no build may start after closing
            self.builds.close()
            self._save_layout()
            self.updater.install_on_quit()
            e.accept()
        else:
            e.ignore()

    # endregion
