"""Main window: figure list, live previews (miniature / source / sheet), settings."""

from __future__ import annotations

import html
import itertools
import traceback
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
                               QMenu, QMessageBox, QProgressDialog, QPushButton, QSplitter,
                               QTabWidget, QToolButton, QVBoxLayout, QWidget)

from .. import segment
from ..mini import Mini
from ..segment import ModelError
from ..settings import FigureEntry, FigureSettings, Project, build_mini, load_project, save_project
from ..sheet import pack, write_pdf
from ..svg import write_svg
from . import theme
from .panels import FigurePanel, Section, SheetPanel
from .views import (CropView, ZoomView, array_to_qimage, draw_mini_page, draw_sheet, load_qimage,
                    pil_to_qimage)
from .widgets import (SUBTITLE_ROLE, Banner, EmptyState, FigureDelegate, Segmented, ZoomBar,
                      overlay_wrap)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
PROJECT_FILTER = "papermini project (*.yaml *.yml)"
# settings that "apply to all" leaves alone
PER_IMAGE = {"label", "crop", "mask", "copies"}


@dataclass
class Figure:
    uid: int
    entry: FigureEntry
    mini: Optional[Mini] = None
    built_key: Optional[str] = None
    gen: int = 0
    error: Optional[str] = None
    pixmap: Optional[QPixmap] = None   # art of ``mini`` as a QPixmap (cached for the sheet)
    queued: Optional[tuple] = None     # (key, overlay) of the job waiting in the pool

    def key(self) -> str:
        d = asdict(self.entry.settings)
        d.pop("copies")  # only matters for the sheet, never a reason to rebuild
        return f"{self.entry.image}|{sorted(d.items())}"

    @property
    def up_to_date(self) -> bool:
        return self.mini is not None and self.built_key == self.key()


# --------------------------------------------------------------------------- worker

class Signals(QObject):
    done = Signal(int, int, str, object)   # uid, gen, key, Mini
    failed = Signal(int, int, str, str)     # uid, gen, key, message
    status = Signal(str)


class BuildJob(QRunnable):
    def __init__(self, sig: Signals, fig: Figure, overlay: bool, is_current):
        super().__init__()
        self.sig, self.uid, self.gen = sig, fig.uid, fig.gen
        self.image, self.settings, self.key = fig.entry.image, fig.entry.settings, fig.key()
        self.overlay, self.is_current = overlay, is_current

    def run(self):
        if not self.is_current(self.uid, self.key):
            return  # settings changed while queued
        self.sig.status.emit(f"Building {self.image.name}…")
        try:
            m = build_mini(self.image, self.settings, want_overlay=self.overlay, log=lambda *_: None)
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
        self.sig.status.connect(self._status)
        segment.PROGRESS_HOOK = self._download_progress
        segment.CANCEL.clear()

        self._build_timer = QTimer(self, singleShot=True, interval=250, timeout=self._build_current)
        self._sheet_timer = QTimer(self, singleShot=True, interval=150, timeout=self._refresh_sheet)

        self._theme_mode = QSettings("papermini", "papermini").value("theme", "system", type=str)
        self._make_ui()
        self._make_actions()
        self._refresh_theme()
        app = QApplication.instance()
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(self._system_scheme_changed)
        self.tabs.currentChanged.connect(self.views.set_index)
        self.sheet_panel.set_settings(self.project.sheet)
        self._update_title()
        self._show_current()

    # ----------------------------------------------------------------- ui
    VIEWS = [("Miniature", "The piece as it will print"),
             ("Cut-away", "Red = cut away, light blue = white margin, black = cut line"),
             ("Source", "The original image. Drag a box to limit what the model looks at; "
                        "drag its handles to resize, inside to move, Delete to clear"),
             ("Print sheet", "The PDF page layout")]

    def _make_ui(self):
        self._tinted = []  # (widget, icon name, colour token, size): re-tinted on theme change
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
        split.setChildrenCollapsible(False)
        split.addWidget(self._make_figure_list())
        split.addWidget(canvas)
        right = QFrame()
        right.setObjectName("SideRight")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.panel)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([260, 820, 380])
        root.addWidget(split, 1)
        self.setCentralWidget(central)

        self.info = QLabel()
        self.statusBar().addPermanentWidget(self.info)
        self.statusBar().setSizeGripEnabled(False)

    def _tool(self, icon: str, tip: str, slot, size: int = 18) -> QToolButton:
        b = QToolButton()
        b.setToolTip(tip)
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
        self._tinted.append((self.logo, "logo", "accent", 24))
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
        h.addWidget(self._tool("add", "Add images  (Ctrl+I)", self.add_images_dialog))
        h.addWidget(self._tool("save", "Save project  (Ctrl+S)", self.save))
        h.addStretch(1)
        self.views = Segmented(self.VIEWS)
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
        self.menu_btn.setIconSize(QSize(18, 18))
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self._tinted.append((self.menu_btn, "menu", "text", 18))
        h.addWidget(self.menu_btn)
        return bar

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
        head.addWidget(self._tool("plus", "Add images  (Ctrl+I)", self.add_images_dialog, 16))
        self.btn_remove = self._tool("trash", "Remove the selected figure  (Del)", self.remove_current, 16)
        head.addWidget(self.btn_remove)
        v.addLayout(head)
        self.list = QListWidget()
        self.list.setObjectName("Figures")
        self.list.setItemDelegate(FigureDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.currentRowChanged.connect(lambda _: self._show_current())
        self.list.model().rowsMoved.connect(self._rows_moved)
        v.addWidget(self.list, 1)
        hint = QLabel("Drop images or a project file anywhere in the window. Drag to reorder.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        hint.setContentsMargins(8, 0, 8, 0)
        v.addWidget(hint)
        return left

    def _make_canvas(self) -> QWidget:
        canvas = QWidget()
        grid = QGridLayout(canvas)
        grid.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        self.mini_view = ZoomView()
        self.overlay_view = ZoomView()
        self.crop_view = CropView()
        self.crop_view.cropChanged.connect(self.panel.set_crop)
        sheet_page = QWidget()
        sv = QVBoxLayout(sheet_page)
        sv.setContentsMargins(0, 0, 0, 0)
        sv.setSpacing(0)
        self.sheet_panel = SheetPanel()
        self.sheet_panel.changed.connect(self._sheet_changed)
        self.sheet_view = ZoomView()
        sv.addWidget(self.sheet_panel)
        sv.addWidget(self.sheet_view)
        for view, (label, tip) in zip((self.mini_view, self.overlay_view, self.crop_view, sheet_page),
                                      self.VIEWS):
            self.tabs.addTab(view, label)
        self.tabs.currentChanged.connect(self._tab_changed)
        grid.addWidget(self.tabs, 0, 0)

        self.empty = EmptyState()
        self.empty.addClicked.connect(self.add_images_dialog)
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
        self.zoombar = ZoomBar()
        self.zoombar.zoomIn.connect(lambda: self._active_view().zoom_by(1.25))
        self.zoombar.zoomOut.connect(lambda: self._active_view().zoom_by(0.8))
        self.zoombar.fit.connect(self._fit)
        self.zoombar.actual.connect(self._actual)
        self.zoom_box = overlay_wrap(self.zoombar)
        grid.addWidget(self.zoom_box, 0, 0, Qt.AlignBottom | Qt.AlignRight)
        for v in (self.mini_view, self.overlay_view, self.crop_view, self.sheet_view):
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
        self.a_save = act("Save project", self.save, QKeySequence.Save)
        self.a_save_as = act("Save project as…", self.save_as, QKeySequence.SaveAs)
        self.a_svg = act("Export SVG…", self.export_current_svg, "Ctrl+E",
                         "Save the selected miniature as SVG")
        self.a_svgs = act("Export all SVGs…", self.export_all_svgs, "Ctrl+Shift+E")
        self.a_pdf = act("Export PDF sheet…", self.export_pdf, "Ctrl+P")
        self.a_remove = act("Remove figure", self.remove_current, QKeySequence.Delete)
        self.a_remove.setShortcutContext(Qt.WidgetShortcut)
        self.list.addAction(self.a_remove)
        self.a_quit = act("Quit", self.close, QKeySequence.Quit)
        self.a_fit = act("Fit to window", self._fit, "Ctrl+0")
        self.a_actual = act("Actual size", self._actual, "Ctrl+1",
                            "Show at real size (depends on your screen's reported DPI)")

        m = self.menu = QMenu(self)
        for a in (self.a_new, self.a_open, self.a_add, None, self.a_save, self.a_save_as, None,
                  self.a_svg, self.a_svgs, self.a_pdf, None, self.a_fit, self.a_actual):
            m.addSeparator() if a is None else m.addAction(a)
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
        m.addSeparator()
        m.addAction("About papermini", self._about)
        m.addAction(self.a_quit)
        self.menu_btn.setMenu(m)

    # ----------------------------------------------------------------- theme
    def set_theme(self, mode: str):
        self._theme_mode = mode
        QSettings("papermini", "papermini").setValue("theme", mode)
        app = QApplication.instance()
        if app is not None:
            theme.apply(app, mode)
        self._refresh_theme()

    def _system_scheme_changed(self, *_):
        if self._theme_mode == "system":
            self.set_theme("system")

    def _refresh_theme(self):
        t = theme.current
        for w, name, token, size in self._tinted:
            if isinstance(w, QLabel):
                w.setPixmap(theme.pixmap(name, getattr(t, token), size))
            else:
                w.setIcon(theme.icon(name, getattr(t, token), size))
        self.zoombar.refresh_icons()
        self.empty.refresh_icons()
        for sec in self.panel.findChildren(Section):
            sec._toggle(sec.header.isChecked())
        for v in (self.mini_view, self.overlay_view, self.crop_view, self.sheet_view):
            v.viewport().update()
        self.list.viewport().update()
        fig = self.current()
        if fig is not None and fig.mini is not None:
            self._show_mini(fig)  # paper shadow colour
        self._sheet_timer.start()

    # ----------------------------------------------------------------- figures
    def current(self) -> Optional[Figure]:
        r = self.list.currentRow()
        return self.figures[r] if 0 <= r < len(self.figures) else None

    def add_images(self, paths, settings: Optional[FigureSettings] = None):
        base = self.current().entry.settings if (settings is None and self.current()) else settings
        added = 0
        for p in paths:
            p = Path(p).resolve()
            if p.suffix.lower() not in IMAGE_EXT:
                continue
            s = FigureSettings() if base is None else replace(
                base, label=None, crop=None, mask=None)
            self._append(FigureEntry(p, s))
            added += 1
        if added:
            self.list.setCurrentRow(len(self.figures) - 1)
            self._set_modified()
        return added

    def _append(self, entry: FigureEntry):
        fig = Figure(next(self._uids), entry)
        self.figures.append(fig)
        item = QListWidgetItem(entry.display_name)
        img = load_qimage(entry.image)
        if not img.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(img.scaled(
                112, 112, Qt.KeepAspectRatio, Qt.SmoothTransformation))))
        item.setToolTip(str(entry.image))
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
        fig.entry.settings = s
        fig.gen += 1
        fig.error = fig.queued = None
        self._refresh_card(fig)
        self.crop_view.set_crop(s.crop)
        self._set_modified()
        self._build_timer.start()
        self._sheet_timer.start()  # e.g. copies: no rebuild, but the sheet changes

    def _apply_to_all(self):
        cur = self.current()
        if cur is None:
            return
        src = asdict(cur.entry.settings)
        for f in self.figures:
            if f is cur:
                continue
            keep = {k: getattr(f.entry.settings, k) for k in PER_IMAGE}
            f.entry.settings = FigureSettings(**{**src, **keep})
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
        """A build is wanted iff it is for the figure's current settings."""
        f = self._figure(uid)
        return f is not None and f.key() == key

    def _queue(self, fig: Figure, overlay: bool):
        job = (fig.key(), overlay)
        if fig.queued == job or (fig.queued == (job[0], True) and not overlay):
            return  # an equivalent (or better) build is already waiting
        fig.queued = job
        # the selected figure jumps ahead of background (sheet) builds
        priority = 10 if fig is self.current() else 0
        self.pool.start(BuildJob(self.sig, fig, overlay, self._is_current), priority)

    def _build_current(self):
        fig = self.current()
        if fig is None:
            return
        if not fig.up_to_date or fig.mini.overlay is None:
            self._queue(fig, overlay=True)
            self.info.setText("building…")
            self.busy_box.setVisible(fig.mini is None or not fig.up_to_date)
        else:
            self._show_mini(fig)  # settings went back to what is already built

    def _on_done(self, uid, gen, key, mini: Mini):
        fig = self._figure(uid)
        if fig is None or fig.key() != key:
            return  # settings changed meanwhile (a newer build is queued)
        if fig.queued and fig.queued[0] == key and (mini.overlay is not None or not fig.queued[1]):
            fig.queued = None
        if mini.overlay is None and fig.mini is not None and fig.built_key == key:
            mini.overlay = fig.mini.overlay
        fig.mini, fig.built_key, fig.error = mini, key, None
        fig.pixmap = QPixmap.fromImage(pil_to_qimage(mini.art))
        self._refresh_card(fig)
        if fig is self.current():
            self._show_mini(fig)
        self._status("Ready")
        self._check_export()
        if self.tabs.currentIndex() == 3:
            self._sheet_timer.start()

    def _on_failed(self, uid, gen, key, msg):
        fig = self._figure(uid)
        if fig is None or fig.key() != key:
            return
        fig.error, fig.queued = msg, None
        self._refresh_card(fig)
        if fig is self.current():
            self._show_mini(fig)
        self._check_export()
        self._status(f"{fig.entry.image.name}: {msg.splitlines()[0]}")

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
        self.zoom_box.setVisible(bool(self.figures))
        if not has:
            self.panel.set_settings(FigureSettings(), "No figure selected")
            self.panel.subtitle.setText("Add an image to see its settings here")
            self.panel.setEnabled(False)
            self.panel.set_empty(True)
            self.mini_view.scene().clear()
            self.overlay_view.scene().clear()
            self.crop_view.set_image(None)
            self.banner_box.hide()
            self.busy_box.hide()
            self.info.setText("")
            return
        e = fig.entry
        self.panel.set_settings(e.settings, e.display_name, e.image.stem)
        self.panel.subtitle.setText(e.image.name)
        self.crop_view.set_image(load_qimage(e.image))
        self.crop_view.set_crop(e.settings.crop)
        self.mini_view.refit_on_next_show()
        self.overlay_view.refit_on_next_show()
        self._show_mini(fig)
        if not fig.up_to_date or fig.mini.overlay is None:
            QTimer.singleShot(0, self._build_current)  # (start(0) would kill the debounce)

    def _show_mini(self, fig: Figure):
        sc = self.mini_view.scene()
        self.panel.set_overlap_hint(None)
        if fig.error and not fig.up_to_date:
            sc.clear()
            self.overlay_view.scene().clear()
            self.busy_box.hide()
            msg = html.escape(fig.error).replace("\n", "<br>")
            self.banner.show_message("This miniature could not be built",
                                     f"{msg}<br><br>Try a lower threshold, a crop, or another model.")
            self.banner_box.show()
            self.info.setText("error")
            return
        self.banner_box.hide()
        m = fig.mini
        self.busy_box.setVisible(m is None or not fig.up_to_date)
        if m is None:
            sc.clear()
            return
        first = sc.itemsBoundingRect().isEmpty() or self.mini_view._fit_pending
        draw_mini_page(sc, m)
        sc.setSceneRect(sc.itemsBoundingRect())
        if first:
            self.mini_view.fit()
        if m.overlay is not None:
            osc = self.overlay_view.scene()
            osc.clear()
            item = osc.addPixmap(QPixmap.fromImage(array_to_qimage(m.overlay)))
            item.setTransformationMode(Qt.SmoothTransformation)
            osc.setSceneRect(item.boundingRect())
            if self.overlay_view._fit_pending:
                self.overlay_view.fit()
        if not m.tab_overlap_used:
            self.panel.set_overlap_hint("unused")
        elif m.tab_width_mm and m.tab_joint_mm < min(10.0, 0.6 * m.tab_width_mm):
            self.panel.set_overlap_hint("narrow", m.tab_joint_mm)
        stale = "" if fig.up_to_date else "  (updating…)"
        self.info.setText(f"figure {m.figure_height_mm:.1f} mm · piece {m.width_mm:.1f} × "
                          f"{m.height_mm:.1f} mm · {len(m.cut.points)} cut nodes{stale}")

    def _tab_changed(self, i):
        if i == 3:
            self._refresh_sheet()
        QTimer.singleShot(0, self._tab_zoom)

    def _refresh_sheet(self):
        if self.tabs.currentIndex() != 3:
            return
        missing = [f for f in self.figures if not f.up_to_date and f.error is None]
        failed = [f for f in self.figures if not f.up_to_date and f.error is not None]
        for f in missing:
            self._queue(f, overlay=False)
        # stale pieces stay visible while they rebuild, but not when their settings fail
        ready = [f for f in self.figures if f.mini is not None and f not in failed]
        sh = self.project.sheet
        sc = self.sheet_view.scene()
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
        return [self.mini_view, self.overlay_view, self.crop_view, self.sheet_view][
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
            f.error = None  # retry figures that failed before
            self._queue(f, overlay=f is self.current())
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

    # ----------------------------------------------------------------- project
    def open_paths(self, paths):
        paths = [Path(p) for p in paths]
        projects = [p for p in paths if p.suffix.lower() in (".yaml", ".yml")]
        if projects:
            self.load(projects[0])
        self.add_images([p for p in paths if p.suffix.lower() in IMAGE_EXT])

    def load(self, path: Path):
        if not self._maybe_save():
            return
        try:
            proj = load_project(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "papermini", f"Could not open {path}:\n{e}")
            return
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
            "<b>papermini</b> turns illustrations into print-ready paper miniatures.<br><br>"
            "The default background-removal model, BRIA RMBG-1.4, is licensed for "
            "<b>non-commercial use only</b>.<br><br>"
            "Projects are saved as batch YAML files, so you can also run them from the "
            "command line: <code>papermini batch project.yaml</code>")

    # ----------------------------------------------------------------- events
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.open_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def closeEvent(self, e):
        if self._maybe_save():
            self.pool.clear()               # drop queued builds
            segment.CANCEL.set()            # abort a model download in progress
            segment.PROGRESS_HOOK = None
            self.pool.waitForDone(15000)    # builds stop at the next checkpoint
            segment.CANCEL.clear()
            e.accept()
        else:
            e.ignore()
