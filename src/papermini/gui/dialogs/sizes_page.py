from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from ...project import sizes
from ...project.size_calculator import SizeCalculator
from ...project.size_row import SizeRow
from ...project.size_table import GRID_MM, MEDIUM_MM
from ..fields.double_spin_box import DoubleSpinBox
from ..preferences import Preferences
from ..theme_service import ThemeService
from .page_parts import PageParts

ui_log = logging.getLogger("papermini.ui")

COLUMNS = (
    ("height_mm", "Height"),
    ("base_mm", "Round base"),
    ("tab_width_mm", "Stand tab width"),
    ("tab_height_mm", "Stand tab height"),
)

PROJECT = "project"  # the entry of a project table that matches no preset
NOTES_ROLE = Qt.UserRole + 1  # a preset entry's notes: what it is used for, a line each


class _EntryDelegate(QStyledItemDelegate):
    """Paints a preset list entry: the name, and below it, smaller and muted, a line for
    each thing it is used for (``NOTES_ROLE``). Painted rather than a widget per entry:
    item widgets of a list that is filled again are deleted later, which can crash Qt
    when papermini quits."""

    PAD_X, PAD_Y = 8, 5

    def __init__(self, themes: ThemeService, parent=None):
        super().__init__(parent)
        self._themes = themes

    @staticmethod
    def _fonts(option) -> tuple[QFont, QFont]:
        notes = QFont(option.font)
        notes.setPointSizeF(8.5)  # (as #Hint)
        return QFont(option.font), notes

    @staticmethod
    def _lines(index) -> list[str]:
        return [n for n in (index.data(NOTES_ROLE) or "").split("\n") if n]

    def sizeHint(self, option, index) -> QSize:
        name, notes = self._fonts(option)
        lines = self._lines(index)
        h = QFontMetrics(name).height() + len(lines) * (
            QFontMetrics(notes).height() + 1
        )
        return QSize(200, h + 2 * self.PAD_Y)

    def paint(self, p, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""  # (the background and selection only)
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, p, opt.widget)
        name_font, notes_font = self._fonts(option)
        r = option.rect.adjusted(self.PAD_X, self.PAD_Y, -self.PAD_X, -self.PAD_Y)
        p.save()
        fm = QFontMetrics(name_font)
        p.setFont(name_font)
        p.setPen(QColor(self._themes.current.text))
        p.drawText(
            QRect(r.left(), r.top(), r.width(), fm.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            fm.elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight, r.width()),
        )
        y = r.top() + fm.height() + 1
        fn = QFontMetrics(notes_font)
        p.setFont(notes_font)
        p.setPen(QColor(self._themes.current.muted))
        for line in self._lines(index):
            p.drawText(
                QRect(r.left(), y, r.width(), fn.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                fn.elidedText(line, Qt.ElideRight, r.width()),
            )
            y += fn.height() + 1
        p.restore()


class SizesPage(QWidget):
    """Manage the size table presets, and pick the open project's table and the default
    for new projects. ``project_table()`` is the project's table after the changes."""

    def __init__(
        self,
        prefs: Preferences,
        size_calculator: SizeCalculator,
        themes: ThemeService,
        project_table: sizes.SizeTable,
        parent=None,
    ):
        super().__init__(parent)
        self._prefs = prefs
        self._size_calculator = size_calculator
        self._project = project_table
        self._user = prefs.user_presets()
        self._default = prefs.default_preset_name()
        if not self._find(self._default):
            self._default = sizes.BUILTIN_NAME
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(PageParts.title("Creature sizes"))
        intro = QLabel(
            "This page holds the size tables for D&D creature sizes: the table "
            "saved with this project, and presets you can use in any project. "
            "Select a table to see or change it. Click Calculate to fill it in "
            "from your grid square and Medium height, then change any value you "
            "need. Figures with a size are updated when you close this window."
        )
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
        self.list.setItemDelegate(_EntryDelegate(themes, self.list))
        self.list.currentItemChanged.connect(self._show_selected)
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
        self.b_delete.setToolTip(
            "Delete the selected preset. Projects that use it keep "
            "their own copy of the table."
        )
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
        self.status = PageParts.hint()
        right.addWidget(self.status)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Grid square"))
        self.grid = self._spin(GRID_MM, 5, 200)
        self.grid.setToolTip("The size of one square of your battle map's grid")
        self.grid.valueChanged.connect(self._sync_inch)
        top.addWidget(self.grid)
        self.inch = PageParts.hint()
        top.addWidget(self.inch)
        top.addSpacing(10)
        top.addWidget(QLabel("Medium height"))
        self.medium = self._spin(MEDIUM_MM, 5, 300)
        self.medium.setToolTip(
            "How tall a Medium figure is. The other sizes are calculated from it."
        )
        top.addWidget(self.medium)
        top.addStretch(1)
        self.calc = QPushButton("Calculate")
        self.calc.setToolTip(
            "Fill in every row from the grid square and Medium height. "
            "This replaces values you changed."
        )
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
            g.addWidget(QLabel(f"<b>{sizes.LABELS[s]}</b>"), r, 0)
            sq = sizes.SQUARES[s]
            squares = QLabel("½" if sq < 1 else f"{sq:g} × {sq:g}")
            squares.setObjectName("Muted")
            g.addWidget(squares, r, 1)
            for c, (key, text) in enumerate(COLUMNS, start=2):
                w = self._spin(1)
                w.setAccessibleName(f"{sizes.LABELS[s]} {text.lower()}")
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
        self.b_use.setToolTip(
            "Give the open project this table. Its figures with a size follow it."
        )
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
        for b in (
            self.b_new,
            self.b_copy,
            self.b_rename,
            self.b_delete,
            self.calc,
            self.b_use,
            self.b_default,
            self.b_save,
        ):
            b.setCursor(Qt.PointingHandCursor)
        self._loading = False
        self._rebuild(self._key_of_project())

    # -- state
    def project_table(self) -> sizes.SizeTable:
        return self._project

    def _all(self) -> list[sizes.SizeTable]:
        return [sizes.BUILTIN] + self._user

    def _find(self, name: str) -> sizes.SizeTable | None:
        return next((t for t in self._all() if t.name == name), None)

    def _project_preset(self) -> str:
        return self._prefs.preset_of(self._project, self._all())

    def _key_of_project(self) -> tuple[str, str]:
        name = self._project_preset()
        return ("preset", name) if name else (PROJECT, "")

    def _entries(self) -> list[tuple[str, str]]:
        keys = [("preset", t.name) for t in self._all()]
        return keys if self._project_preset() else keys + [(PROJECT, "")]

    def _key(self) -> tuple[str, str]:
        item = self.list.currentItem()
        return (
            item.data(Qt.UserRole)
            if item is not None
            else ("preset", sizes.BUILTIN_NAME)
        )

    def _table(self, key: tuple[str, str]) -> sizes.SizeTable:
        if key[0] == PROJECT:
            return self._project
        return self._find(key[1]) or sizes.BUILTIN

    def _notes(self, key: tuple[str, str]) -> str:
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

    def _rebuild(self, select: tuple[str, str]) -> None:
        """Fill the list again (after an entry was added, removed, renamed or marked)."""
        self.list.blockSignals(True)
        self.list.clear()
        current = None
        for key in self._entries():
            name = "This project's table" if key[0] == PROJECT else key[1]
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, key)
            item.setData(NOTES_ROLE, self._notes(key))
            item.setToolTip(name)
            self.list.addItem(item)
            if key == select:
                current = item
        self.list.setCurrentItem(current or self.list.item(0))
        self.list.blockSignals(False)
        self._show_selected()

    def _refresh_notes(self) -> None:
        if self._entries() != [
            self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
        ]:
            self._rebuild(self._key())
            return
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setData(NOTES_ROLE, self._notes(item.data(Qt.UserRole)))
        self.list.doItemsLayout()  # (an entry's height follows its notes)
        self._sync_buttons()

    def _show_selected(self, *_) -> None:
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
            if came and self._find(came):
                status = (
                    f"It came from the preset {came}, but the values are different "
                    "now. Save it as a preset to keep it, or use a preset instead."
                )
            elif came:
                status = (
                    f"It came from the preset {came}, which is not on this computer. "
                    "Save it as a preset to keep it."
                )
            else:
                status = "It is not saved as a preset. Save it as a preset to keep it."
        else:
            self.title.setText(key[1])
            status = (
                "The built-in table can't be changed. Copy it to make your own."
                if builtin
                else "Changes are saved at once."
            )
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
        rows = {
            s: SizeRow(*(round(self.spins[s, k].value(), 2) for k, _ in COLUMNS))
            for s in sizes.SIZES
        }
        return sizes.SizeTable(
            round(self.grid.value(), 2), round(self.medium.value(), 2), rows, name
        )

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
            self._prefs.save_user_presets(self._user)
            if follows:
                self._project = table
        self._refresh_notes()

    def calculate(self) -> None:
        """Every row of the selected table from the grid square and Medium height."""
        table = self._size_calculator.calculate(self.grid.value(), self.medium.value())
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
        if self._find(name):
            QMessageBox.warning(
                self, title, f"There is already a preset called {name}."
            )
            return ""
        return name

    def _add(self, table: sizes.SizeTable) -> None:
        self._user.append(table)
        self._prefs.save_user_presets(self._user)
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
        self._prefs.save_user_presets(self._user)
        if follows:
            self._project = replace(self._project, name=name)
        if self._default == old:
            self._default = name
            self._prefs.set_default_preset_name(name)
        ui_log.info("Renamed the creature size preset %s to %s", old, name)
        self._rebuild(("preset", name))

    def delete_preset(self) -> None:
        name = self._key()[1]
        if (
            QMessageBox.question(
                self,
                "Delete preset",
                f"Delete the preset {name}? Projects that use it keep their own copy of "
                "the table.",
            )
            != QMessageBox.Yes
        ):
            return
        self._user = [t for t in self._user if t.name != name]
        self._prefs.save_user_presets(self._user)
        if self._default == name:
            self._default = sizes.BUILTIN_NAME
            self._prefs.set_default_preset_name(self._default)
        ui_log.info("Deleted the creature size preset %s", name)
        self._rebuild(self._key_of_project())

    def use_in_project(self) -> None:
        self._project = self._table(self._key())
        self._rebuild(self._key())

    def make_default(self) -> None:
        self._default = self._key()[1]
        self._prefs.set_default_preset_name(self._default)
        ui_log.info("New projects use the creature size preset %s", self._default)
        self._refresh_notes()

    def save_as_preset(self) -> None:
        name = self._ask_name(
            "Save as preset",
            "Name for the preset:",
            self._unique(self._project.name or "My preset"),
        )
        if not name:
            return
        self._project = replace(self._project, name=name)
        self._add(self._project)

    @staticmethod
    def _spin(value: float, lo: float = 0.5, hi: float = 600.0) -> DoubleSpinBox:
        w = DoubleSpinBox()  # ("." as the decimal point, as in the settings)
        w.setRange(lo, hi)
        w.setDecimals(2)
        w.setSingleStep(0.5)
        w.setSuffix(" mm")
        w.setValue(value)
        return w
