"""The Preferences window: a page for the creature size presets, pages for the theme,
automatic updates and the log, and the models and cache page. Changes take effect at
once.

Size table presets are kept in the preferences: the built-in one (read-only) and the
user's own, one of them the default for new projects. A project keeps a copy of its table
with the name of the preset it came from; the page shows which preset that is, or the
project's own table when it matches none of them."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import List, Optional, Tuple

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QRadioButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import log, sizes
from . import errors, prefs
from .models import CachePage
from .panels import DoubleSpinBox

ui_log = logging.getLogger("papermini.ui")
PRESETS_KEY = "sizes/presets"
DEFAULT_KEY = "sizes/default_preset"
COLUMNS = (("height_mm", "Height"), ("base_mm", "Round base"),
           ("tab_width_mm", "Stand tab width"), ("tab_height_mm", "Stand tab height"))
PROJECT = "project"  # the entry of a project table that matches no preset


# ----------------------------------------------------------------- presets
def user_presets() -> List[sizes.SizeTable]:
    """The user's own size table presets (entries that cannot be read are left out)."""
    text = prefs.store().value(PRESETS_KEY, "", type=str)
    try:
        data = json.loads(text) if text else []
    except ValueError:
        return []
    out, seen = [], {sizes.BUILTIN_NAME}
    for d in data if isinstance(data, list) else []:
        try:
            t = sizes.SizeTable.from_dict(d)
        except (ValueError, TypeError, AttributeError):
            continue
        if t.name and t.name not in seen:
            seen.add(t.name)
            out.append(t)
    return out


def save_user_presets(tables: List[sizes.SizeTable]) -> None:
    prefs.store().setValue(PRESETS_KEY, json.dumps([t.to_dict() for t in tables]))


def presets() -> List[sizes.SizeTable]:
    """Every preset: the built-in one first, then the user's own."""
    return [sizes.BUILTIN] + user_presets()


def default_name() -> str:
    return prefs.store().value(DEFAULT_KEY, sizes.BUILTIN_NAME, type=str)


def set_default_name(name: str) -> None:
    prefs.store().setValue(DEFAULT_KEY, name)


def default_table() -> sizes.SizeTable:
    """The preset new projects start with (the built-in one when the default is gone)."""
    return find(presets(), default_name()) or sizes.BUILTIN


def find(tables: List[sizes.SizeTable], name: str) -> Optional[sizes.SizeTable]:
    return next((t for t in tables if t.name == name), None)


def preset_of(table: sizes.SizeTable, tables: Optional[List[sizes.SizeTable]] = None) -> str:
    """The name of the preset ``table`` is (same name and values), or ""."""
    p = find(tables if tables is not None else presets(), table.name)
    return p.name if p is not None and p.same_values(table) else ""


def table_label(table: sizes.SizeTable) -> str:
    """How the size hint names a project's table: its preset, or this project's own."""
    return preset_of(table) or "this project's table"


# ----------------------------------------------------------------- widgets
def _spin(value: float, lo: float = 0.5, hi: float = 600.0) -> DoubleSpinBox:
    w = DoubleSpinBox()  # ("." as the decimal point, as in the settings)
    w.setRange(lo, hi)
    w.setDecimals(2)
    w.setSingleStep(0.5)
    w.setSuffix(" mm")
    w.setValue(value)
    return w


def _hint(text: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("Hint")
    lab.setWordWrap(True)
    return lab


def _page_title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("DialogTitle")
    return lab


class _EntryLabel(QWidget):
    """A preset list entry: the name, and below it what it is used for."""

    def __init__(self, name: str, notes: str):
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 5, 8, 5)
        v.setSpacing(1)
        self.name = QLabel(name)
        self.name.setObjectName("EntryName")
        v.addWidget(self.name)
        self.notes = QLabel()
        self.notes.setObjectName("Hint")
        v.addWidget(self.notes)
        self.set_notes(notes)

    def set_notes(self, notes: str) -> None:
        self.notes.setText(notes)
        self.notes.setVisible(bool(notes))
        self.layout().activate()

    def height_hint(self) -> int:
        return self.layout().sizeHint().height()


class SizesPage(QWidget):
    """Manage the size table presets, and pick the open project's table and the default
    for new projects. ``project_table()`` is the project's table after the changes."""

    def __init__(self, project_table: sizes.SizeTable, parent=None):
        super().__init__(parent)
        self._project = project_table
        self._user = user_presets()
        self._default = default_name()
        if not find(self._all(), self._default):
            self._default = sizes.BUILTIN_NAME
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(_page_title("Creature sizes"))
        intro = QLabel("Size table for D&D mini sizes, saved with this project. Click "
                       "Calculate to fill it in from your grid square and Medium height, "
                       "then change any value you need. Figures with a size are updated "
                       "when you close this window.")
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        v.addWidget(intro)

        body = QHBoxLayout()
        body.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(6)
        head = QLabel("Presets")
        head.setObjectName("SubHeading")
        left.addWidget(head)
        self.list = QListWidget()
        self.list.setObjectName("PresetList")
        self.list.setFixedWidth(230)
        self.list.currentItemChanged.connect(lambda *_: self._show_selected())
        left.addWidget(self.list, 1)
        tools = QGridLayout()
        tools.setSpacing(6)
        self.b_new = QPushButton("New")
        self.b_new.setToolTip("Add a preset with the built-in values")
        self.b_new.clicked.connect(self.new_preset)
        self.b_copy = QPushButton("Copy")
        self.b_copy.setToolTip("Add a copy of the selected table as a new preset")
        self.b_copy.clicked.connect(self.copy_preset)
        self.b_rename = QPushButton("Rename")
        self.b_rename.clicked.connect(self.rename_preset)
        self.b_delete = QPushButton("Delete")
        self.b_delete.setToolTip("Delete the selected preset. Projects that use it keep "
                                 "their own copy of the table.")
        self.b_delete.clicked.connect(self.delete_preset)
        for i, b in enumerate((self.b_new, self.b_copy, self.b_rename, self.b_delete)):
            tools.addWidget(b, i // 2, i % 2)
        left.addLayout(tools)
        body.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName("PageSection")
        right.addWidget(self.title)
        self.status = _hint()
        right.addWidget(self.status)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Grid square"))
        self.grid = _spin(sizes.GRID_MM, 5, 200)
        self.grid.setToolTip("The size of one square of your battle map's grid")
        self.grid.valueChanged.connect(self._sync_inch)
        top.addWidget(self.grid)
        self.inch = _hint()
        top.addWidget(self.inch)
        top.addSpacing(10)
        top.addWidget(QLabel("Medium height"))
        self.medium = _spin(sizes.MEDIUM_MM, 5, 300)
        self.medium.setToolTip("How tall a Medium figure is. The other sizes are "
                               "calculated from it.")
        top.addWidget(self.medium)
        top.addStretch(1)
        self.calc = QPushButton("Calculate")
        self.calc.setToolTip("Fill in every row from the grid square and Medium height. "
                             "This replaces values you changed.")
        self.calc.clicked.connect(self.calculate)
        top.addWidget(self.calc)
        right.addLayout(top)

        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        for c, text in enumerate(("Size", "Squares") + tuple(t for _, t in COLUMNS)):
            h = QLabel(text)
            h.setObjectName("SubHeading")
            g.addWidget(h, 0, c)
        self.spins = {}
        for r, s in enumerate(sizes.SIZES, start=1):
            g.addWidget(QLabel(f"<b>{sizes.label(s)}</b>"), r, 0)
            sq = sizes.SQUARES[s]
            squares = QLabel("½" if sq < 1 else f"{sq:g} × {sq:g}")
            squares.setObjectName("Muted")
            g.addWidget(squares, r, 1)
            for c, (key, text) in enumerate(COLUMNS, start=2):
                w = _spin(1)
                w.setAccessibleName(f"{sizes.label(s)} {text.lower()}")
                g.addWidget(w, r, c)
                self.spins[s, key] = w
        right.addLayout(g)
        right.addStretch(1)
        for w in (self.grid, self.medium, *self.spins.values()):
            w.valueChanged.connect(self._edited)
        body.addLayout(right, 1)
        v.addLayout(body, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.b_use = QPushButton("Use in this project")
        self.b_use.setToolTip("Give the open project this table. Its figures with a size "
                              "follow it.")
        self.b_use.clicked.connect(self.use_in_project)
        self.b_default = QPushButton("Make default for new projects")
        self.b_default.clicked.connect(self.make_default)
        self.b_save = QPushButton("Save as preset")
        self.b_save.setToolTip("Keep this project's table as a preset of your own")
        self.b_save.clicked.connect(self.save_as_preset)
        for b in (self.b_use, self.b_default, self.b_save):
            actions.addWidget(b)
        actions.addStretch(1)
        v.addLayout(actions)
        for b in (self.b_new, self.b_copy, self.b_rename, self.b_delete, self.calc,
                  self.b_use, self.b_default, self.b_save):
            b.setCursor(Qt.PointingHandCursor)
        self._loading = False
        self._rebuild(self._key_of_project())

    # -- state
    def project_table(self) -> sizes.SizeTable:
        return self._project

    def _all(self) -> List[sizes.SizeTable]:
        return [sizes.BUILTIN] + self._user

    def _project_preset(self) -> str:
        return preset_of(self._project, self._all())

    def _key_of_project(self) -> Tuple[str, str]:
        name = self._project_preset()
        return ("preset", name) if name else (PROJECT, "")

    def _entries(self) -> List[Tuple[str, str]]:
        keys = [("preset", t.name) for t in self._all()]
        return keys if self._project_preset() else keys + [(PROJECT, "")]

    def _key(self) -> Tuple[str, str]:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item is not None else ("preset", sizes.BUILTIN_NAME)

    def _table(self, key: Tuple[str, str]) -> sizes.SizeTable:
        if key[0] == PROJECT:
            return self._project
        return find(self._all(), key[1]) or sizes.BUILTIN

    def _notes(self, key: Tuple[str, str]) -> str:
        used = key == self._key_of_project()
        notes = []
        if key == ("preset", sizes.BUILTIN_NAME):
            notes.append("built-in")
        if key[0] == PROJECT:
            notes.append("not a preset")
        if used:
            notes.append("used in this project")
        if key[0] != PROJECT and key[1] == self._default:
            notes.append("default for new projects")
        return "\n".join(n[:1].upper() + n[1:] for n in notes)  # (a line each)

    def _rebuild(self, select: Tuple[str, str]) -> None:
        """Fill the list again (after an entry was added, removed, renamed or marked)."""
        self.list.blockSignals(True)
        self.list.clear()
        current = None
        for key in self._entries():
            item = QListWidgetItem()
            item.setData(Qt.UserRole, key)
            name = "This project's table" if key[0] == PROJECT else key[1]
            label = _EntryLabel(name, self._notes(key))
            item.setSizeHint(QSize(200, label.height_hint()))
            item.setToolTip(name)
            self.list.addItem(item)
            self.list.setItemWidget(item, label)
            if key == select:
                current = item
        self.list.setCurrentItem(current or self.list.item(0))
        self.list.blockSignals(False)
        self._show_selected()

    def _refresh_notes(self) -> None:
        if self._entries() != [self.list.item(i).data(Qt.UserRole)
                               for i in range(self.list.count())]:
            self._rebuild(self._key())
            return
        for i in range(self.list.count()):
            item = self.list.item(i)
            label = self.list.itemWidget(item)
            label.set_notes(self._notes(item.data(Qt.UserRole)))
            item.setSizeHint(QSize(200, label.height_hint()))
        self._sync_buttons()

    def _show_selected(self) -> None:
        key = self._key()
        table = self._table(key)
        builtin = key == ("preset", sizes.BUILTIN_NAME)
        self._loading = True
        self.grid.setValue(table.grid_mm)
        self.medium.setValue(table.medium_mm)
        for s in sizes.SIZES:
            row = table.row(s)
            for k, _ in COLUMNS:
                self.spins[s, k].setValue(getattr(row, k))
        self._loading = False
        for w in (self.grid, self.medium, self.calc, *self.spins.values()):
            w.setEnabled(not builtin)
        if key[0] == PROJECT:
            self.title.setText("This project's table")
            came = self._project.name
            if came and find(self._all(), came):
                status = (f"It came from the preset {came}, but the values are different "
                          "now. Save it as a preset to keep it, or use a preset instead.")
            elif came:
                status = (f"It came from the preset {came}, which is not on this computer. "
                          "Save it as a preset to keep it.")
            else:
                status = "It is not saved as a preset. Save it as a preset to keep it."
        else:
            self.title.setText(key[1])
            status = ("The built-in table can't be changed. Copy it to make your own."
                      if builtin else "Changes are saved at once.")
            if key == self._key_of_project() and not builtin:
                status += " The open project uses this preset, so it changes too."
        self.status.setText(status)
        self._sync_inch()
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        key = self._key()
        builtin = key == ("preset", sizes.BUILTIN_NAME)
        project = key[0] == PROJECT
        self.b_rename.setEnabled(not builtin and not project)
        self.b_delete.setEnabled(not builtin and not project)
        self.b_use.setEnabled(key != self._key_of_project())
        self.b_default.setEnabled(not project and key[1] != self._default)
        self.b_save.setVisible(project)

    def _sync_inch(self) -> None:
        self.inch.setText(f"({self.grid.value() / 25.4:.3g} in)")

    # -- editing
    def _shown(self, name: str) -> sizes.SizeTable:
        rows = {s: sizes.SizeRow(*(round(self.spins[s, k].value(), 2) for k, _ in COLUMNS))
                for s in sizes.SIZES}
        return sizes.SizeTable(round(self.grid.value(), 2), round(self.medium.value(), 2),
                               rows, name)

    def _edited(self, *_) -> None:
        if self._loading:
            return
        key = self._key()
        if key == ("preset", sizes.BUILTIN_NAME):
            return
        if key[0] == PROJECT:
            self._project = self._shown(self._project.name)
        else:
            follows = self._project_preset() == key[1]
            table = self._shown(key[1])
            self._user = [table if t.name == key[1] else t for t in self._user]
            save_user_presets(self._user)
            if follows:
                self._project = table
        self._refresh_notes()

    def calculate(self) -> None:
        """Every row of the selected table from the grid square and Medium height."""
        table = sizes.calculate(self.grid.value(), self.medium.value())
        self._loading = True
        for s in sizes.SIZES:
            for k, _ in COLUMNS:
                self.spins[s, k].setValue(getattr(table.row(s), k))
        self._loading = False
        self._edited()

    def _unique(self, base: str) -> str:
        names = {t.name for t in self._all()}
        if base not in names:
            return base
        n = 2
        while f"{base} {n}" in names:
            n += 1
        return f"{base} {n}"

    def _ask_name(self, title: str, text: str, current: str, old: str = "") -> str:
        """A preset name from the user ("" when cancelled or not usable)."""
        name, ok = QInputDialog.getText(self, title, text, text=current)
        name = name.strip() if ok else ""
        if not name or name == old:
            return ""
        if find(self._all(), name):
            QMessageBox.warning(self, title, f"There is already a preset called {name}.")
            return ""
        return name

    def _add(self, table: sizes.SizeTable) -> None:
        self._user.append(table)
        save_user_presets(self._user)
        ui_log.info("Added the creature size preset %s", table.name)
        self._rebuild(("preset", table.name))

    def new_preset(self) -> None:
        self._add(replace(sizes.BUILTIN, name=self._unique("New preset")))

    def copy_preset(self) -> None:
        key = self._key()
        base = "This project's table" if key[0] == PROJECT else key[1]
        self._add(replace(self._table(key), name=self._unique(f"{base} copy")))

    def rename_preset(self) -> None:
        old = self._key()[1]
        name = self._ask_name("Rename preset", "New name for the preset:", old, old)
        if not name:
            return
        follows = self._project_preset() == old
        self._user = [replace(t, name=name) if t.name == old else t for t in self._user]
        save_user_presets(self._user)
        if follows:
            self._project = replace(self._project, name=name)
        if self._default == old:
            self._default = name
            set_default_name(name)
        ui_log.info("Renamed the creature size preset %s to %s", old, name)
        self._rebuild(("preset", name))

    def delete_preset(self) -> None:
        name = self._key()[1]
        if QMessageBox.question(
                self, "Delete preset",
                f"Delete the preset {name}? Projects that use it keep their own copy of "
                "the table.") != QMessageBox.Yes:
            return
        self._user = [t for t in self._user if t.name != name]
        save_user_presets(self._user)
        if self._default == name:
            self._default = sizes.BUILTIN_NAME
            set_default_name(self._default)
        ui_log.info("Deleted the creature size preset %s", name)
        self._rebuild(self._key_of_project())

    def use_in_project(self) -> None:
        self._project = self._table(self._key())
        self._rebuild(self._key())

    def make_default(self) -> None:
        self._default = self._key()[1]
        set_default_name(self._default)
        ui_log.info("New projects use the creature size preset %s", self._default)
        self._refresh_notes()

    def save_as_preset(self) -> None:
        name = self._ask_name("Save as preset", "Name for the preset:",
                              self._unique(self._project.name or "My preset"))
        if not name:
            return
        self._project = replace(self._project, name=name)
        self._add(self._project)


# ----------------------------------------------------------------- the window
class PreferencesDialog(QDialog):
    """The Preferences window for ``window`` (the main window), opened at ``page``."""

    PAGES = (("sizes", "Creature sizes"), ("appearance", "Appearance"),
             ("updates", "Updates"), ("logging", "Logging"), ("cache", "Models and cache"))

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
        for (key, text), w in zip(self.PAGES, (self.sizes, self._appearance(),
                                               self._updates(), self._logging(),
                                               self.cache)):
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

    def _page(self, title: str) -> Tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(_page_title(title))
        return w, v

    def _appearance(self) -> QWidget:
        w, v = self._page("Appearance")
        head = QLabel("Theme")
        head.setObjectName("SubHeading")
        v.addWidget(head)
        self.theme_group = QButtonGroup(w)
        for mode, text in (("system", "Follow system"), ("light", "Light"), ("dark", "Dark")):
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
        v.addWidget(_hint("Look for a new version once a day, download it in the "
                          "background and install it when papermini closes. Check for "
                          "updates in the menu looks right away."))
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
        v.addWidget(_hint("Write more to the log, until papermini closes. Turn it on "
                          "before you repeat a problem you want to report."
                          if on else "There is no log in this session."))
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
