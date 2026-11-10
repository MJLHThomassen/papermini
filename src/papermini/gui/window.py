"""Main window: figure list, live previews (miniature / source / sheet), settings."""

from __future__ import annotations

import html
import itertools
import re
import threading
import time
import traceback
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QByteArray, QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QDialog, QLineEdit, QMenu, QMessageBox, QProgressDialog,
                               QPushButton, QSplitter, QTabWidget, QToolButton, QVBoxLayout,
                               QWidget)

from .. import __version__, remote, segment
from ..mini import Mini
from ..segment import Cancelled, ModelError
from ..settings import FigureEntry, FigureSettings, Project, build_mini, load_project, save_project
from ..sheet import pack, write_pdf
from ..svg import write_svg
from . import prefs, theme
from .models import DownloadDialog, ModelsDialog
from .panels import PER_IMAGE, FigurePanel, Section, SheetPanel
from .views import (CropView, SourceLegend, ZoomView, adjusted_preview, draw_mini_page,
                    draw_sheet, load_qimage, print_sheet, pil_to_qimage)
from .widgets import (SUBTITLE_ROLE, Banner, EmptyState, FigureDelegate, Segmented, WorkCard,
                      ZoomBar,
                      overlay_wrap)

IMAGE_FILTER = remote.IMAGE_FILTER
IMG_SRC = re.compile(r"""<img\b[^>]*?\ssrc\s*=\s*["']([^"']+)["']""", re.I)
PROJECT_FILTER = "papermini project (*.yaml *.yml)"
# settings that "apply to all" leaves alone


@dataclass
class Figure:
    uid: int
    entry: FigureEntry
    mini: Optional[Mini] = None
    built_key: Optional[str] = None
    gen: int = 0
    error: Optional[str] = None
    pixmap: Optional[QPixmap] = None   # art of ``mini`` as a QPixmap (cached for the sheet)
    queued: Optional[str] = None       # key of the job waiting in the pool
    cancelled: Optional[str] = None    # mask_key whose background removal the user cancelled

    def key(self) -> str:
        d = asdict(self.entry.settings)
        d.pop("copies")  # only matters for the sheet, never a reason to rebuild
        return f"{self.entry.image}|{sorted(d.items())}"

    def mask_key(self) -> str:
        """What the background removal depends on: a cancelled run stays cancelled
        until one of these changes (other settings do not start the model again)."""
        s = self.entry.settings
        return f"{self.entry.image}|{s.model}|{s.mask}|{s.crop}"

    @property
    def up_to_date(self) -> bool:
        return self.mini is not None and self.built_key == self.key()

    @property
    def stopped(self) -> bool:
        """The user cancelled the background removal for the current image and crop."""
        return self.cancelled is not None and self.cancelled == self.mask_key()


# --------------------------------------------------------------------------- worker

class Signals(QObject):
    done = Signal(int, int, str, object)   # uid, gen, key, Mini
    failed = Signal(int, int, str, str)     # uid, gen, key, message
    cancelled = Signal(int, int, str)       # uid, gen, key: the user stopped the model
    stage = Signal(int, str, str, str, object)  # uid, key, mask_key, stage name, data (see make_mini)
    status = Signal(str)
    ask_download = Signal(str, object, object)  # model, answer dict, threading.Event
    link_done = Signal(str, object, str, object)  # link, downloaded path or None, error, settings


class BuildJob(QRunnable):
    def __init__(self, sig: Signals, fig: Figure, is_current):
        super().__init__()
        self.sig, self.uid, self.gen = sig, fig.uid, fig.gen
        self.image, self.settings, self.key = fig.entry.image, fig.entry.settings, fig.key()
        self.mask_key = fig.mask_key()
        self.is_current = is_current

    def run(self):
        if not self.is_current(self.uid, self.key):
            return  # settings changed while queued, or the user cancelled it
        self.sig.status.emit(f"Building {self.image.name}…")
        try:
            with segment.cancellable():  # Cancel also stops it while the model loads
                m = build_mini(self.image, self.settings, log=lambda *_: None,
                               on_stage=lambda name, data: self.sig.stage.emit(
                                   self.uid, self.key, self.mask_key, name, data))
        except Cancelled:
            self.sig.cancelled.emit(self.uid, self.gen, self.key)
        except (Exception, SystemExit) as e:  # noqa: BLE001 - always report back, never die silently
            expected = (ValueError, FileNotFoundError, ModelError, SystemExit)
            msg = str(e) if isinstance(e, expected) else \
                f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
            self.sig.failed.emit(self.uid, self.gen, self.key, msg)
        else:
            self.sig.done.emit(self.uid, self.gen, self.key, m)


# --------------------------------------------------------------------------- window

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1440, 900)
        self.setAcceptDrops(True)
        self.project = Project()
        self.figures: List[Figure] = []
        self._uids = itertools.count(1)
        self._export = None  # (figures, callback, progress dialog, count) while exporting
        self._modified = False
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)  # one model run at a time
        self.sig = Signals()
        self.sig.done.connect(self._on_done)
        self.sig.failed.connect(self._on_failed)
        self.sig.cancelled.connect(self._on_cancelled)
        self.sig.stage.connect(self._on_stage)
        self._segmenting = None  # (uid, mask_key, model, start time) while a model runs
        self._work_timer = QTimer(self, interval=500, timeout=self._update_work)
        self.sig.status.connect(self._status)
        self.sig.ask_download.connect(self._ask_download)
        self.sig.link_done.connect(self._on_link_done)
        self._closing = threading.Event()  # stops link downloads when the window closes
        self._declined = set()  # models the user did not want to download (until they change model)
        self._crop_undo = []    # (figure uid, crop before a change), newest last: Ctrl+Z
        self._undoing = False
        segment.PROGRESS_HOOK = self._download_progress
        segment.CONFIRM_DOWNLOAD = self._confirm_download
        segment.CANCEL.clear()

        self._build_timer = QTimer(self, singleShot=True, interval=250, timeout=self._build_current)
        self._sheet_timer = QTimer(self, singleShot=True, interval=150, timeout=self._refresh_sheet)
        # the Source view's picture follows the color sliders, a moment after they move
        self._picture_timer = QTimer(self, singleShot=True, interval=60,
                                     timeout=self._refresh_picture)
        self._original = (None, None)  # (image path, QImage): the shown image, loaded once

        self._theme_mode = prefs.store().value("theme", "system", type=str)
        self._make_ui()
        self._make_actions()
        self._restore_layout()
        self._refresh_theme()
        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)
        self.tabs.currentChanged.connect(self.views.set_index)
        self.sheet_panel.set_settings(self.project.sheet)
        self._update_title()
        self._show_current()

    # ----------------------------------------------------------------- ui
    # the workflow, one view per step; any step can be opened at any time
    VIEWS = [("Source", "Step 1: crop the picture and remove the background. Drag a box on "
                        "the image to limit what the model looks at; drag its handles to "
                        "resize, inside to move, Delete to clear"),
             ("Miniature", "Step 2: the paper piece as it will print: margin, cut line, "
                           "tab and back"),
             ("Print sheet", "Step 3: size and copies of each figure, and the PDF pages")]
    SOURCE, MINI, SHEET = range(3)

    def _make_ui(self):
        self._tinted = []  # (widget, icon name, color token, size): re-tinted on theme change
        central = QWidget()
        central.setObjectName("Body")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.panel = FigurePanel()
        self.panel.changed.connect(self._settings_changed)
        self.panel.applyToAll.connect(self._apply_to_all)
        canvas = self._make_canvas()
        root.addWidget(self._make_header())

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(1)
        self.splitter = split
        split.addWidget(self._make_figure_list())
        split.addWidget(canvas)
        right = QFrame()
        right.setObjectName("SideRight")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.panel)
        # usable width or dragged shut - never a sliver with clipped fields: as wide as
        # the widest step needs (measured with every group shown), not just the empty state
        right.setMinimumWidth(self.panel.minimumSizeHint().width())
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([260, 820, 380])
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
        b.setAccessibleName(tip.split("  (")[0])  # icon-only: name it for screen readers
        b.setIconSize(QSize(size, size))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        self._tinted.append((b, icon, "text", size))
        return b

    def _make_header(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Header")
        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 8, 12, 8)
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
        h.addWidget(self._tool("open", "Open a project or images  (Ctrl+O)", self.open_dialog))
        h.addWidget(self._tool("save", "Save project  (Ctrl+S)", self.save))
        h.addStretch(1)
        self.views = Segmented(self.VIEWS, steps=True)
        self.views.changed.connect(self.tabs.setCurrentIndex)
        h.addWidget(self.views)
        h.addStretch(1)
        self.btn_svg = QPushButton("Export SVG")
        self.btn_svg.setToolTip("Save the selected miniature as SVG  (Ctrl+E)")
        self.btn_svg.clicked.connect(self.export_current_svg)
        self._tinted.append((self.btn_svg, "export", "text", 16))
        self.btn_pdf = QPushButton("Export PDF")
        self.btn_pdf.setProperty("primary", True)
        self.btn_pdf.setToolTip("Save the print sheet as PDF  (Ctrl+P)")
        self.btn_pdf.clicked.connect(self.export_pdf)
        self._tinted.append((self.btn_pdf, "pdf", "accent_text", 16))
        for btn in (self.btn_svg, self.btn_pdf):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIconSize(QSize(16, 16))
            h.addWidget(btn)
        h.addSpacing(4)
        self.menu_btn = QToolButton()
        self.menu_btn.setToolTip("Menu")
        self.menu_btn.setAccessibleName("Menu")
        self.menu_btn.setIconSize(QSize(18, 18))
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self._tinted.append((self.menu_btn, "menu", "text", 18))
        h.addWidget(self.menu_btn)
        return bar

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
        b.setFocusPolicy(Qt.TabFocus)  # keyboard focus ring, but no stuck ring after a click
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
        head.addWidget(self._tool("add", "Add images  (Ctrl+I)", self.add_images_dialog, 16))
        self.btn_remove = self._tool("trash", "Remove the selected figure  (Del)", self.remove_current, 16)
        head.addWidget(self.btn_remove)
        v.addLayout(head)
        v.addLayout(self._make_link_bar())
        self.list = QListWidget()
        self.list.setObjectName("Figures")
        self.list.setItemDelegate(FigureDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.currentRowChanged.connect(lambda _: self._show_current())
        self.list.model().rowsMoved.connect(self._rows_moved)
        v.addWidget(self.list, 1)
        hint = QLabel("Drop images, image links or a project file anywhere in the window. "
                      "Drag to reorder.")
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
        self.link_edit.setToolTip("Paste the link of an image on the web and press Enter. "
                                  "In a browser: right-click the picture, Copy image address.")
        self.link_edit.setClearButtonEnabled(True)
        self._link_icon = self.link_edit.addAction(QIcon(), QLineEdit.LeadingPosition)
        self.link_edit.returnPressed.connect(self.add_from_link_bar)
        self.link_add = QPushButton("Add")
        self.link_add.setToolTip("Download the image and add it as a figure  (Enter)")
        self.link_add.setCursor(Qt.PointingHandCursor)
        self.link_add.setEnabled(False)
        self.link_add.clicked.connect(self.add_from_link_bar)
        self.link_edit.textChanged.connect(lambda t: self.link_add.setEnabled(bool(t.strip())))
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
        self.mini_view = ZoomView()
        self.crop_view = CropView()
        self.crop_view.cropChanged.connect(self.panel.set_crop)
        sheet_page = QWidget()
        sv = QVBoxLayout(sheet_page)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        self.sheet_panel = SheetPanel()
        self.sheet_panel.changed.connect(self._sheet_changed)
        self.sheet_panel.printClicked.connect(self.print_sheet)
        self._tinted.append((self.sheet_panel.print_btn, "printer", "text", 16))
        self.sheet_view = ZoomView()
        sv.addWidget(self.sheet_panel)
        sv.addWidget(self.sheet_view)
        for view, (label, tip) in zip((self.crop_view, self.mini_view, sheet_page),
                                      self.VIEWS):
            self.tabs.addTab(view, label)
        self.tabs.currentChanged.connect(self._tab_changed)
        grid.addWidget(self.tabs, 0, 0)

        self.empty = EmptyState()
        self.empty.addClicked.connect(self.add_images_dialog)
        self.empty.openClicked.connect(self.open_dialog)
        self.empty.linkClicked.connect(self.focus_link_bar)
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
            self.legend, (16, 16, 16, 16 + left_card.sizeHint().height() + 8))
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
        self.btn_clear_crop.setToolTip("Remove the crop box, so background removal looks at "
                                       "the whole image (Delete). Ctrl+Z undoes a crop change.")
        self.btn_clear_crop.setCursor(Qt.PointingHandCursor)
        self.btn_clear_crop.clicked.connect(lambda: self.panel.set_crop(None))
        cl.addWidget(self.btn_clear_crop)
        self.clear_crop_card.hide()
        zb.addWidget(self.clear_crop_card, 0, Qt.AlignBottom)
        zb.addWidget(self.zoombar, 0, Qt.AlignBottom)
        zb.addWidget(right_card, 0, Qt.AlignBottom)
        grid.addWidget(self.zoom_box, 0, 0, Qt.AlignBottom | Qt.AlignRight)
        for v in (self.crop_view, self.mini_view, self.sheet_view):
            v.zoomChanged.connect(lambda z, v=v: v is self._active_view() and self.zoombar.set_zoom(z))
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
        self.a_open = act("Open…", self.open_dialog, QKeySequence.Open,
                          "Open a project (.yaml) or images")
        self.a_add = act("Add images…", self.add_images_dialog, "Ctrl+I")
        self.a_add_link = act("Add image from a link…", self.focus_link_bar, "Ctrl+L",
                              "Download an image from the web by its link (URL)")
        self.a_paste = act("Paste images", self.paste, QKeySequence.Paste,
                           "Add copied image files, or an image or its link copied in a browser")
        self.a_save = act("Save project", self.save, QKeySequence.Save)
        self.a_save_as = act("Save project as…", self.save_as, QKeySequence.SaveAs)
        self.a_svg = act("Export SVG…", self.export_current_svg, "Ctrl+E",
                         "Save the selected miniature as SVG")
        self.a_svgs = act("Export all SVGs…", self.export_all_svgs, "Ctrl+Shift+E")
        self.a_pdf = act("Export PDF sheet…", self.export_pdf, "Ctrl+P")
        self.a_print = act("Print sheet…", self.print_sheet, "Ctrl+Shift+P",
                           "Print the sheet at its real size")
        self.a_undo_crop = act("Undo crop change", self.undo_crop, QKeySequence.Undo,
                               "Put the crop box back as it was before the last change")
        self.a_remove = act("Remove figure", self.remove_current, QKeySequence.Delete)
        self.a_remove.setShortcutContext(Qt.WidgetShortcut)
        self.list.addAction(self.a_remove)
        self.a_quit = act("Quit", self.close, QKeySequence.Quit)
        self.a_fit = act("Fit to window", self._fit, "Ctrl+0")
        self.a_actual = act("Actual size", self._actual, "Ctrl+1",
                            "Show at real size (depends on your screen's reported DPI)")
        self.a_left = act("Figure list", lambda on: self.set_side_visible(0, on), "Ctrl+B",
                          "Show or hide the figure list")
        self.a_right = act("Settings", lambda on: self.set_side_visible(2, on), "Ctrl+Alt+B",
                           "Show or hide the settings panel")
        for a in (self.a_left, self.a_right):
            a.setCheckable(True)
            a.setChecked(True)
        self.a_models = act("Models…", self.show_models, None,
                            "See, download or delete the background-removal models")

        m = self.menu = QMenu(self)
        for a in (self.a_new, self.a_open, self.a_add, self.a_add_link, None,
                  self.a_undo_crop, None, self.a_save,
                  self.a_save_as, None,
                  self.a_svg, self.a_svgs, self.a_pdf, self.a_print, None):
            m.addSeparator() if a is None else m.addAction(a)
        vm = m.addMenu("View")
        for a in (self.a_left, self.a_right, None, self.a_fit, self.a_actual):
            vm.addSeparator() if a is None else vm.addAction(a)
        tm = m.addMenu("Theme")
        group = QActionGroup(self)
        self.theme_actions = {}
        for mode, text in (("system", "Follow system"), ("light", "Light"), ("dark", "Dark")):
            a = tm.addAction(text)
            a.setCheckable(True)
            a.setChecked(mode == self._theme_mode)
            a.triggered.connect(lambda _=False, mode=mode: self.set_theme(mode))
            group.addAction(a)
            self.theme_actions[mode] = a
        m.addAction(self.a_models)
        m.addSeparator()
        m.addAction("About papermini", self._about)
        m.addAction(self.a_quit)
        self.menu_btn.setMenu(m)
        self._sync_sides()

    # ----------------------------------------------------------------- side panels
    SIDE_NAMES = {0: "figure list", 2: "settings"}

    def side_visible(self, i: int) -> bool:
        return self.splitter.sizes()[i] > 0

    def toggle_side(self, i: int):
        self.set_side_visible(i, not self.side_visible(i))

    def set_side_visible(self, i: int, show: bool):
        """Collapse a side panel, or reopen it at the width it had."""
        sizes = self.splitter.sizes()
        if (sizes[i] > 0) != show:
            if show:
                w = max(self._side_width[i], self.splitter.widget(i).minimumSizeHint().width(),
                        self.splitter.widget(i).minimumWidth())
                sizes[i], sizes[1] = w, max(sizes[1] - w, 0)
            else:
                self._side_width[i] = sizes[i]
                sizes[1] += sizes[i]
                sizes[i] = 0
            self.splitter.setSizes(sizes)
        self._sync_sides()

    def _restore_layout(self):
        """Panel widths and which panels are collapsed, as they were last time."""
        st = prefs.store()
        state = st.value("layout/splitter")
        if isinstance(state, QByteArray) and not state.isEmpty():
            self.splitter.restoreState(state)
            self.splitter.setCollapsible(1, False)  # (not part of the saved state)
        for i, key in ((0, "layout/left_width"), (2, "layout/right_width")):
            w = st.value(key, 0, type=int)
            if w > 0:
                self._side_width[i] = w
        self._sync_sides()

    def _save_layout(self):
        sizes = self.splitter.sizes()
        for i in self._side_width:
            if sizes[i] > 0:
                self._side_width[i] = sizes[i]
        st = prefs.store()
        st.setValue("layout/splitter", self.splitter.saveState())
        st.setValue("layout/left_width", self._side_width[0])
        st.setValue("layout/right_width", self._side_width[2])

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
        for i, btn, a in ((0, self.btn_left, self.a_left), (2, self.btn_right, self.a_right)):
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

    # ----------------------------------------------------------------- theme
    def set_theme(self, mode: str):
        self._theme_mode = mode
        prefs.store().setValue("theme", mode)
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

    # ----------------------------------------------------------------- figures
    def current(self) -> Optional[Figure]:
        r = self.list.currentRow()
        return self.figures[r] if 0 <= r < len(self.figures) else None

    def _base_settings(self, settings: Optional[FigureSettings]) -> Optional[FigureSettings]:
        """New figures start from the selected figure's settings (or ``settings``)."""
        return self.current().entry.settings if (settings is None and self.current()) else settings

    @staticmethod
    def _new_settings(base: Optional[FigureSettings]) -> FigureSettings:
        return FigureSettings() if base is None else replace(base, label=None, crop=None, mask=None)

    def add_images(self, paths, settings: Optional[FigureSettings] = None):
        """Add image files; links among ``paths`` are downloaded first (in the background)."""
        base = self._base_settings(settings)
        links = [str(p).strip() for p in paths if remote.is_url(p)]
        added = 0
        for p in paths:
            if remote.is_url(p):
                continue
            p = remote.local_path(p).resolve()
            if not remote.is_image_file(p):
                continue
            self._append(FigureEntry(p, self._new_settings(base)))
            added += 1
        if added:
            self.list.setCurrentRow(len(self.figures) - 1)
            self._set_modified()
        if links:
            self.add_links(links, base)
        return added

    def add_links(self, links, settings: Optional[FigureSettings] = None):
        """Add images from links: downloaded once (in the background), then cached."""
        base = self._base_settings(settings)
        for url in links:
            url = url.strip()
            hit = remote.cached_image(url)
            if hit is not None:
                self._on_link_done(url, hit, "", base)
                continue
            self._status(f"Downloading {url} …")
            threading.Thread(target=self._fetch_link, args=(url, base), daemon=True).start()

    def _fetch_link(self, url: str, base):  # on a worker thread
        try:
            path, err = remote.fetch_image(url, cancel=self._closing), ""
        except ValueError as e:
            path, err = None, str(e)
        if not self._closing.is_set():
            self.sig.link_done.emit(url, path, err, base)

    def _on_link_done(self, url: str, path, err: str, base):
        if self._closing.is_set():
            return
        if path is None:
            self._status("Could not add the image")
            QMessageBox.warning(self, "papermini", f"Could not add the image.\n\n{err}")
            return
        self._append(FigureEntry(Path(path), self._new_settings(base), source=url))
        self.list.setCurrentRow(len(self.figures) - 1)
        self._set_modified()
        self._status(f"Added {Path(path).name}")

    def focus_link_bar(self):
        """Show the figure list and put the cursor in its link field, with a copied
        link already filled in."""
        self.set_side_visible(0, True)
        clip = QApplication.clipboard().text().strip()
        if not self.link_edit.text().strip() and remote.is_url(clip):
            self.link_edit.setText(clip)
        self.link_edit.setFocus(Qt.ShortcutFocusReason)
        self.link_edit.selectAll()

    def add_from_link_bar(self):
        """Add the link(s) typed or pasted into the link field."""
        words = self.link_edit.text().split()
        if not words:
            return
        links = [w for w in words if remote.is_url(w)]
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
            links = [s for s in IMG_SRC.findall(mime.html()) if remote.is_url(s)][:1]
        if not links:
            links = [u.toString() for u in mime.urls() if remote.is_url(u.toString())]
        if not links and not files and mime.hasText():
            links = [t for t in mime.text().split() if remote.is_url(t)]
        return files, links

    def paste(self):
        """Ctrl+V outside a text field: add copied image files or image links."""
        files, links = self._sources(QApplication.clipboard().mimeData())
        if files or links:
            self.open_paths(files + links)
        else:
            self._status("Nothing to paste: copy image files, or an image or its link in a browser")

    def _append(self, entry: FigureEntry):
        fig = Figure(next(self._uids), entry)
        self.figures.append(fig)
        item = QListWidgetItem(entry.display_name)
        img = load_qimage(entry.image)
        if not img.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(img.scaled(
                112, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation))))
        item.setToolTip(entry.source or str(entry.image))
        item.setData(Qt.UserRole, fig.uid)
        item.setData(SUBTITLE_ROLE, "Building…")
        item.setSizeHint(QSize(0, FigureDelegate.H))
        self.list.addItem(item)
        self.count_label.setText(str(len(self.figures)))

    def _refresh_card(self, fig: Figure):
        """Figure list entry: name, a thumbnail of the finished piece, size and copies."""
        item = self._list_item(fig)
        if item is None:
            return
        item.setText(fig.entry.display_name)
        n = fig.entry.settings.copies
        copies = f"{n} cop{'y' if n == 1 else 'ies'}"
        if fig.error and not fig.up_to_date:
            item.setData(SUBTITLE_ROLE, "Needs attention · " + copies)
        elif fig.stopped and not fig.up_to_date:
            item.setData(SUBTITLE_ROLE, "Cancelled · " + copies)
        elif fig.mini is None:
            item.setData(SUBTITLE_ROLE, "Building…")
        else:
            item.setData(SUBTITLE_ROLE, f"{fig.mini.figure_height_mm:.0f} mm · {copies}")
            if fig.pixmap is not None:
                item.setIcon(QIcon(fig.pixmap.scaled(112, 112, Qt.KeepAspectRatio,
                                                     Qt.SmoothTransformation)))

    def remove_current(self):
        r = self.list.currentRow()
        if r < 0:
            return
        self.figures.pop(r)
        self.list.takeItem(r)
        self.count_label.setText(str(len(self.figures)))
        self._set_modified()
        self._show_current()
        self._sheet_timer.start()

    def _rows_moved(self, *_):
        by_uid = {f.uid: f for f in self.figures}
        self.figures = [by_uid[self.list.item(i).data(Qt.UserRole)] for i in range(self.list.count())]
        self._set_modified()

    def _figure(self, uid) -> Optional[Figure]:
        return next((f for f in self.figures if f.uid == uid), None)

    def _list_item(self, fig: Figure) -> Optional[QListWidgetItem]:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == fig.uid:
                return self.list.item(i)
        return None

    # ----------------------------------------------------------------- settings
    def _settings_changed(self, s: FigureSettings):
        fig = self.current()
        if fig is None:
            return
        old = fig.entry.settings
        if s.adjustments() != old.adjustments():
            self._picture_timer.start()  # (the model is not involved: no rebuild of the mask)
        if s.crop != old.crop and not self._undoing:  # a crop change can be undone
            self._crop_undo.append((fig.uid, old.crop))
            del self._crop_undo[:-50]
        if s.model != old.model:
            self._declined.clear()  # a new model choice may ask again
        seg = self._segmenting
        old_mask = fig.mask_key()
        fig.entry.settings = s
        if seg and seg[0] == fig.uid and seg[1] == old_mask != fig.mask_key():
            segment.cancel_runs()  # its mask is no longer wanted: start the new one now
        if not fig.stopped:
            fig.cancelled = None  # a new image, crop or model: build it
        fig.gen += 1
        fig.error = fig.queued = None
        self._refresh_card(fig)
        self.crop_view.set_crop(s.crop)
        self._sync_legend()
        self._set_modified()
        self._build_timer.start()
        self._sheet_timer.start()  # e.g. copies: no rebuild, but the sheet changes

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
            f.gen += 1
            f.error = f.queued = None
        self._set_modified()
        self._status(f"Applied settings to {len(self.figures) - 1} other figure(s)")
        self._sheet_timer.start()

    def _sheet_changed(self, s):
        self.project.sheet = s
        self._set_modified()
        self._sheet_timer.start()

    # ----------------------------------------------------------------- building
    def _is_current(self, uid, key) -> bool:
        """A build is wanted iff it is for the figure's current settings, and the user
        did not cancel its background removal."""
        f = self._figure(uid)
        return f is not None and f.key() == key and not f.stopped

    def _queue(self, fig: Figure):
        key = fig.key()
        if fig.queued == key or fig.stopped or self._closing.is_set():
            return  # already waiting, stopped by the user (see _work_clicked), or closed
        fig.queued = key
        # the selected figure jumps ahead of background (sheet) builds
        priority = 10 if fig is self.current() else 0
        self.pool.start(BuildJob(self.sig, fig, self._is_current), priority)

    def _build_current(self):
        fig = self.current()
        if fig is None:
            return
        if fig.stopped and not fig.up_to_date:
            self._update_work()  # stopped by the user: wait for Run again
        elif not fig.up_to_date:
            self._queue(fig)
            self.info.setText("building…")
            self.busy_box.setVisible(fig.mini is None or not fig.up_to_date)
            self._update_work()  # (hides it again behind a work card)
        else:
            self._show_mini(fig)  # settings went back to what is already built

    def _on_done(self, uid, gen, key, mini: Mini):
        fig = self._figure(uid)
        if fig is None or fig.key() != key:
            return  # settings changed meanwhile (a newer build is queued)
        if fig.queued == key:
            fig.queued = None
        fig.mini, fig.built_key, fig.error = mini, key, None
        fig.cancelled = None  # (finished just before a Cancel could stop it)
        self._end_segmenting(uid)
        fig.pixmap = QPixmap.fromImage(pil_to_qimage(mini.art))
        self._refresh_card(fig)
        if fig is self.current():
            self._show_mini(fig)
        self._status("Ready")
        self._check_export()
        if self.tabs.currentIndex() == self.SHEET:
            self._sheet_timer.start()

    def _on_failed(self, uid, gen, key, msg):
        self._end_segmenting(uid)
        fig = self._figure(uid)
        if fig is None or fig.key() != key:
            return
        fig.error, fig.queued = msg, None
        self._refresh_card(fig)
        if fig is self.current():
            self._show_mini(fig)
        self._check_export()
        self._status(f"{fig.entry.image.name}: {msg.splitlines()[0]}")

    def _on_cancelled(self, uid, gen, key):
        """A build stopped: by Cancel (``_cancel_run`` already marked the figure), or
        because a new crop or model made it useless (that one is built next)."""
        self._end_segmenting(uid)
        fig = self._figure(uid)
        if fig is not None and fig.queued == key:
            fig.queued = None

    def _cancel_run(self):
        """Cancel: stop the running model. Its figure is marked cancelled at once, even
        when the build only notices later (a model still loading finishes that first)."""
        seg = self._segmenting
        segment.cancel_runs()
        if seg is None:
            return
        self._end_segmenting(seg[0])
        fig = self._figure(seg[0])
        if fig is None or fig.mask_key() != seg[1]:
            return
        fig.cancelled, fig.queued = seg[1], None  # (a build still waiting is skipped)
        self._refresh_card(fig)
        self._check_export()
        self._status(f"{fig.entry.image.name}: background removal cancelled")
        if fig is self.current():
            self.busy_box.hide()
            self.info.setText("cancelled")
        self._update_work()

    def _on_stage(self, uid, key, mask_key, name, data):
        """Progress of a build: a model starts ("segment"), or the figure was found
        ("outline", before the miniature is laid out)."""
        if name == "segment":
            self._segmenting = (uid, mask_key, data, time.monotonic())
            self._work_timer.start()
            QTimer.singleShot(300, self._update_work)  # cached masks come back at once
            return
        if name == "outline":
            self._end_segmenting(uid)
            fig = self.current()
            if fig is not None and fig.uid == uid and fig.key() == key:
                contours, close_px = data
                self.crop_view.set_outline(contours)
                self.panel.set_auto_fill_gaps(close_px)

    def _end_segmenting(self, uid):
        if self._segmenting and self._segmenting[0] == uid:
            self._segmenting = None
            self._work_timer.stop()
            self._update_work()

    def _update_work(self):
        """The work card and the dimmed Source image for the selected figure: a model
        running for it (with Cancel), a model running for another figure that it waits
        for (Cancel stops that one), or a cancelled one (Run again)."""
        fig = self.current()
        seg = self._segmenting
        mode = None
        if fig is not None and self.tabs.currentIndex() != self.SHEET:
            running = seg is not None and time.monotonic() - seg[3] >= 0.25
            if running and seg[0] == fig.uid and seg[1] == fig.mask_key():
                mode = "working"
            elif fig.stopped and not fig.up_to_date:
                mode = "cancelled"
            elif running and seg[0] != fig.uid and not fig.up_to_date and not fig.error:
                mode = "waiting"
        if mode in ("working", "waiting"):
            secs = int(time.monotonic() - seg[3])
            model = seg[2] if segment.is_loaded(seg[2]) else f"loading {seg[2]}"
            detail = f"{model} · {secs} s" if secs else model
            if mode == "working":
                self.work.show_working("Removing the background…", detail)
            else:
                other = self._figure(seg[0])
                name = other.entry.display_name if other else "another figure"
                self.work.show_working(f"Waiting for {name}",
                                       f"Removing its background: {detail}", "Cancel it")
        elif mode == "cancelled":
            self.work.show_stopped("Background removal cancelled",
                                   "Change the crop or model, or run it again.", "Run again")
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
            self._build_current()
        else:
            self._cancel_run()  # its own model run, or the one it waits for

    def _confirm_download(self, model: str) -> bool:
        """Build thread: ask (on the GUI thread) before a model is downloaded. The
        dialog downloads it, so the build continues with the file on disk."""
        if model in self._declined or segment.CANCEL.is_set():
            return False
        answer, done = {"ok": False}, threading.Event()
        self.sig.ask_download.emit(model, answer, done)
        while not done.wait(0.1):
            if segment.CANCEL.is_set():  # the window is closing
                answer["gone"] = True    # nobody waits for this question any more
                return False
        return answer["ok"]

    def _ask_download(self, model: str, answer: dict, done: threading.Event):
        try:
            if answer.get("gone"):  # the build stopped waiting (window closed): do not ask
                return
            if segment.model_path(model).exists():  # downloaded meanwhile (Models window)
                answer["ok"] = True
                return
            ok = DownloadDialog(model, self).exec() == QDialog.Accepted
            answer["ok"] = ok
            if not ok:
                self._declined.add(model)
        finally:
            done.set()

    def show_models(self):
        dlg = ModelsDialog(self)
        dlg.changed.connect(self._models_changed)
        dlg.exec()

    def _models_changed(self, model: str):
        """Retry figures that failed, e.g. because a model was not downloaded."""
        self._declined.discard(model)
        for f in self.figures:
            if f.error and not f.up_to_date:
                f.error = None
                f.gen += 1
                self._refresh_card(f)
        self._build_current()
        if self.tabs.currentIndex() == self.SHEET:
            self._sheet_timer.start()

    def _download_progress(self, done, total, msg):
        t = f" / {total / 1e6:.0f}" if total else ""
        self.sig.status.emit(f"{msg}: {done / 1e6:.0f}{t} MB (first run only)")

    def _status(self, msg: str):
        self.statusBar().showMessage(msg, 0 if msg.endswith("…") or "MB" in msg else 6000)

    # ----------------------------------------------------------------- showing
    def _show_current(self):
        fig = self.current()
        has = fig is not None
        for w in (self.a_svg, self.btn_svg, self.btn_remove):
            w.setEnabled(has)
        self.btn_pdf.setEnabled(bool(self.figures))
        self.empty.setVisible(not self.figures)
        self.zoombar.setVisible(bool(self.figures))
        self._sync_legend()
        if not has:
            self.panel.set_settings(FigureSettings())  # reset the hidden fields
            self.panel.set_empty(True, "Select a figure in the list to see its settings here."
                                 if self.figures else "Add images to see their settings here.")
            self.mini_view.scene().clear()
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
            QTimer.singleShot(0, self._build_current)  # (start(0) would kill the debounce)

    def _show_mini(self, fig: Figure):
        sc = self.mini_view.scene()
        self.panel.set_overlap_hint(None)
        if fig.error and not fig.up_to_date:
            sc.clear()
            self.crop_view.set_outline(None)
            self.busy_box.hide()
            msg = html.escape(fig.error).replace("\n", "<br>")
            hint = "" if "not downloaded" in fig.error else \
                "<br><br>Try a lower strength, a crop, or another model."
            self.banner.show_message("This miniature could not be built", msg + hint)
            self.banner_box.show()
            self.info.setText("error")
            return
        self.banner_box.hide()
        m = fig.mini
        # (the work card, when shown, already says what is going on)
        self.busy_box.setVisible((m is None or not fig.up_to_date)
                                 and not self.work_box.isVisibleTo(self))
        if m is None:
            sc.clear()
            self.crop_view.set_outline(None)
            return
        first = sc.itemsBoundingRect().isEmpty() or self.mini_view._fit_pending
        draw_mini_page(sc, m)
        sc.setSceneRect(sc.itemsBoundingRect())
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
        self.info.setText(f"figure {m.figure_width_mm:.1f} × {m.figure_height_mm:.1f} mm · "
                          f"piece {m.width_mm:.1f} × "
                          f"{m.height_mm:.1f} mm · {len(m.cut.points)} cut nodes{stale}")

    def _tab_changed(self, i):
        self.panel.set_step(i)
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
        return adjusted_preview(img, adj), (img.width(), img.height())

    def _refresh_picture(self):
        fig = self.current()
        if fig is not None:
            self.crop_view.replace_picture(self._source_picture(fig)[0])

    def _sync_legend(self):
        """The Source legend, shown on the Source view while it shows an image, and the
        Clear crop button, while that image has a crop box."""
        fig = self.current()
        self.legend_box.setVisible(fig is not None and self.tabs.currentIndex() == self.SOURCE)
        cropped = fig is not None and bool(fig.entry.settings.crop)
        self.clear_crop_card.setVisible(cropped and self.tabs.currentIndex() == self.SOURCE)

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
            self._queue(f)
        # stale pieces stay visible while they rebuild, but not when their settings fail
        ready = [f for f in self.figures if f.mini is not None and f not in failed]
        sh = self.project.sheet
        sc = self.sheet_view.scene()
        self.sheet_panel.print_btn.setEnabled(bool(self.figures))
        self.a_print.setEnabled(bool(self.figures))
        if not ready:
            sc.clear()
            self.sheet_panel.info.setText("Building…" if missing else "No miniatures yet")
            return
        try:
            lay = pack([(f.mini, f.entry.settings.copies) for f in ready], sh.paper,
                       sh.margin_mm, sh.gap_mm)
        except ValueError as e:
            sc.clear()
            self.sheet_panel.info.setText(str(e))
            return
        first = sc.itemsBoundingRect().isEmpty()
        draw_sheet(sc, lay, sh.title, sh.margin_mm, {id(f.mini): f.pixmap for f in ready})
        sc.setSceneRect(sc.itemsBoundingRect())
        if first:
            self.sheet_view.fit()
        n = len(lay.placements)
        pending = f" · {len(missing)} building…" if missing else ""
        if failed:
            pending += f" · {len(failed)} failed (select to see why)"
        self.sheet_panel.info.setText(f"{n} piece{'s' * (n != 1)} on {lay.pages} "
                                      f"page{'s' * (lay.pages != 1)}{pending}")

    def _fit(self):
        self._active_view().fit()

    def _tab_zoom(self):
        self.zoombar.set_zoom(self._active_view().zoom())

    def _actual(self):
        self._active_view().actual_size()

    def _active_view(self) -> ZoomView:
        return [self.crop_view, self.mini_view, self.sheet_view][
            self.tabs.currentIndex()]

    # ----------------------------------------------------------------- export
    def _when_built(self, figs: List[Figure], then) -> None:
        """Build stale figures in the background (UI stays responsive), then ``then()``."""
        todo = [f for f in figs if not f.up_to_date]
        if not todo:
            then()
            return
        dlg = QProgressDialog("Building miniatures…", "Cancel", 0, len(todo), self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.canceled.connect(lambda: setattr(self, "_export", None))
        self._export = (figs, then, dlg, len(todo))
        for f in todo:
            f.error = f.cancelled = None  # retry figures that failed or were stopped
            self._queue(f)
        self._check_export()

    def _check_export(self):
        if self._export is None:
            return
        figs, then, dlg, n = self._export
        figs = [f for f in figs if f in self.figures]
        failed = [f for f in figs if not f.up_to_date and f.error is not None]
        left = [f for f in figs if not f.up_to_date]
        if failed:
            self._export = None
            dlg.close()
            f = failed[0]
            QMessageBox.warning(self, "papermini", f"{f.entry.image.name}: {f.error.splitlines()[0]}")
        elif not left:
            self._export = None
            dlg.close()
            then()
        else:
            dlg.setValue(n - len(left))
            dlg.setLabelText(f"Building {left[0].entry.image.name}…")

    def _out_dir(self) -> Path:
        return self.project.output_dir if self.project.path else (
            self.figures[0].entry.image.parent if self.figures else Path.home())

    def export_current_svg(self):
        fig = self.current()
        if fig is not None:
            self._when_built([fig], lambda: self._save_svg(fig))

    def _save_svg(self, fig: Figure):
        f, _ = QFileDialog.getSaveFileName(self, "Export SVG",
                                           str(self._out_dir() / fig.entry.svg_name()),
                                           "SVG (*.svg)")
        if f:
            write_svg(fig.mini, Path(f))
            self._status(f"Saved {f}")

    def export_all_svgs(self):
        if self.figures:
            self._when_built(list(self.figures), self._save_all_svgs)

    def _save_all_svgs(self):
        d = QFileDialog.getExistingDirectory(self, "Export all SVGs to", str(self._out_dir()))
        if d:
            for f in self.figures:
                write_svg(f.mini, Path(d) / f.entry.svg_name())
            self._status(f"Saved {len(self.figures)} SVG(s) to {d}")

    def export_pdf(self):
        if self.figures:
            self._when_built(list(self.figures), self._save_pdf)

    def _save_pdf(self):
        sh = self.project.sheet
        default = self.project.sheet_path if self.project.path else self._out_dir() / "minis.pdf"
        f, _ = QFileDialog.getSaveFileName(self, "Export PDF sheet", str(default), "PDF (*.pdf)")
        if not f:
            return
        try:
            lay = pack([(x.mini, x.entry.settings.copies) for x in self.figures], sh.paper,
                       sh.margin_mm, sh.gap_mm)
            write_pdf(lay, Path(f), sh.margin_mm, sh.title)
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "papermini", str(e))
            return
        self._status(f"Saved {f} ({len(lay.placements)} pieces, {lay.pages} page(s))")

    def print_sheet(self):
        if self.figures:
            self._when_built(list(self.figures), self._print)

    def _print(self):
        from PySide6.QtGui import QPageLayout, QPageSize
        from PySide6.QtPrintSupport import QPrinter

        sh = self.project.sheet
        try:
            lay = pack([(x.mini, x.entry.settings.copies) for x in self.figures], sh.paper,
                       sh.margin_mm, sh.gap_mm)
        except ValueError as e:
            QMessageBox.warning(self, "papermini", str(e))
            return
        printer = QPrinter(QPrinter.HighResolution)
        size = QPageSize.A4 if sh.paper == "a4" else QPageSize.Letter
        printer.setPageSize(QPageSize(size))
        printer.setPageOrientation(QPageLayout.Portrait)
        printer.setFullPage(True)  # true size: no scaling to the printable area
        printer.setDocName(self.project.path.stem if self.project.path else "papermini sheet")
        printer.setFromTo(0, 0)
        if not self._print_dialog(printer, lay.pages):
            return
        chosen = printer.pageLayout().pageSize().id()
        if chosen != size and QMessageBox.question(
                self, "papermini",
                f"The sheet is laid out for {sh.paper.upper()} paper, but the printer is set to "
                f"{printer.pageLayout().pageSize().name()}. The minis still print at their real "
                "size, but parts of the sheet may be cut off.\n\nPrint anyway?") \
                != QMessageBox.Yes:
            return
        n = print_sheet(printer, lay, sh.title, sh.margin_mm)
        if n:
            self._status(f"Sent {n} page(s) to {printer.printerName() or 'the printer'}")
        else:
            QMessageBox.warning(self, "papermini", "Could not print: the printer did not start.")

    def _print_dialog(self, printer, pages: int) -> bool:
        from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog

        dlg = QPrintDialog(printer, self)
        dlg.setWindowTitle("Print sheet")
        dlg.setMinMax(1, pages)
        dlg.setOption(QAbstractPrintDialog.PrintPageRange, pages > 1)
        return dlg.exec() == QDialog.Accepted

    # ----------------------------------------------------------------- project
    def open_paths(self, paths):
        """Open a project and/or add images: files, ``file://`` URIs or web links."""
        links = [str(p).strip() for p in paths if remote.is_url(p)]
        paths = [remote.local_path(p) for p in paths if not remote.is_url(p)]
        projects = [p for p in paths if p.suffix.lower() in (".yaml", ".yml")]
        if projects:
            self.load(projects[0])
        self.add_images([p for p in paths if remote.is_image_file(p)] + links)

    def load(self, path: Path):
        if not self._maybe_save():
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)  # images from links may download
        try:
            proj = load_project(path)
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "papermini", f"Could not open {path}:\n{e}")
            return
        QApplication.restoreOverrideCursor()
        self._reset(proj)
        missing = [f.image.name for f in proj.figures if not f.image.exists()]
        if missing:
            QMessageBox.warning(self, "papermini", "Missing images:\n" + "\n".join(missing))

    def _reset(self, proj: Project):
        self.project = proj
        self.figures.clear()
        self.list.clear()
        self.count_label.setText("0")
        for e in proj.figures:
            if e.image.exists():
                self._append(e)
        self.sheet_panel.set_settings(proj.sheet)
        self._modified = False
        if self.figures:
            self.list.setCurrentRow(0)
        self._show_current()
        self._update_title()
        self._sheet_timer.start()

    def new_project(self):
        if self._maybe_save():
            self._reset(Project())

    def open_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Open project or images", str(self._out_dir()),
            f"{PROJECT_FILTER};;{IMAGE_FILTER};;All files (*)")
        if files:
            self.open_paths(files)

    def add_images_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add images", str(self._out_dir()), IMAGE_FILTER)
        if files:
            self.add_images(files)

    def save(self) -> bool:
        if self.project.path is None:
            return self.save_as()
        self.project.figures = [f.entry for f in self.figures]
        try:
            save_project(self.project, self.project.path)
        except OSError as e:
            QMessageBox.warning(self, "papermini", str(e))
            return False
        self._modified = False
        self._update_title()
        self._status(f"Saved {self.project.path}")
        return True

    def save_as(self) -> bool:
        start = self.project.path or (self._out_dir() / "minis.yaml")
        f, _ = QFileDialog.getSaveFileName(self, "Save project", str(start), PROJECT_FILTER)
        if not f:
            return False
        self.project.path = Path(f)
        return self.save()

    def _maybe_save(self) -> bool:
        if not self._modified or not self.figures:
            return True
        r = QMessageBox.question(self, "papermini", "Save changes to the project?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
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
        self.project_label.setText(f"{name}{'  •  unsaved changes' if self._modified else ''}")

    def _about(self):
        QMessageBox.about(
            self, "About papermini",
            f"<b>papermini {__version__}</b><br><br>"
            "Turns illustrations into print-ready paper miniatures.<br><br>"
            "The default background-removal model, BRIA RMBG-1.4, is licensed for "
            "<b>non-commercial use only</b>. The BiRefNet models are MIT-licensed."
            "<br><br>"
            "Projects are saved as batch YAML files, so you can also run them from the "
            "command line: <code>papermini batch project.yaml</code>")

    # ----------------------------------------------------------------- events
    def dragEnterEvent(self, e):
        files, links = self._sources(e.mimeData())
        if files or links:
            e.acceptProposedAction()

    def dropEvent(self, e):
        files, links = self._sources(e.mimeData())
        self.open_paths(files + links)

    def closeEvent(self, e):
        if self._maybe_save():
            self._closing.set()             # link downloads stop and are not added
            for t in (self._build_timer, self._sheet_timer, self._work_timer,
                      self._picture_timer):
                t.stop()                    # no build may start after closing
            self.pool.clear()               # drop queued builds
            segment.CANCEL.set()            # abort a model download in progress
            segment.cancel_runs()           # and a model run
            segment.PROGRESS_HOOK = segment.CONFIRM_DOWNLOAD = None
            self.pool.waitForDone(15000)    # builds stop at the next checkpoint
            segment.CANCEL.clear()
            self._save_layout()
            e.accept()
        else:
            e.ignore()
