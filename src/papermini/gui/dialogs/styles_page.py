from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...project.figure_settings import FigureSettings
from ...project.style_preset import StylePreset
from ...project.style_preset_file import StylePresetFile
from ...project.styles import BUILTIN_STYLES
from ...support.font_library import FontLibrary
from ..preferences import Preferences
from ..style_library import StyleLibrary
from ..theme_service import ThemeService
from ..views.qt_fonts import QtFonts
from .page_parts import PageParts
from .preset_entry_delegate import (
    LIST_MAX_WIDTH,
    LIST_MIN_WIDTH,
    NOTES_ROLE,
    PresetEntryDelegate,
)
from .style_editor import StyleEditor
from .style_name_prompt import StyleNamePrompt

ui_log = logging.getLogger("papermini.ui")


class StylesPage(QWidget):
    """Manage and edit the style presets: the built-in ones, the user's own and the
    open project's. ``project_presets()`` returns the project's presets after the
    changes. ``fonts`` and ``qt_fonts`` list the fonts a preset can have."""

    def __init__(
        self,
        prefs: Preferences,
        styles: StyleLibrary,
        preset_files: StylePresetFile,
        themes: ThemeService,
        fonts: FontLibrary,
        qt_fonts: QtFonts,
        project: list[StylePreset],
        folder: Path,
        parent=None,
    ):
        super().__init__(parent)
        self._prefs = prefs
        self._styles = styles
        self._preset_files = preset_files
        self._themes = themes
        self._project = list(project)
        self._folder = folder
        self._names = StyleNamePrompt(styles)
        self._editing: StylePreset | None = None  # the preset in the editor
        self._pending: StylePreset | None = None  # its changes, until saved
        self.editor = StyleEditor(fonts, qt_fonts, themes)
        self.editor.changed.connect(self._edited)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        v.addWidget(PageParts.title("Style presets"))
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addLayout(self._build_list(), 0)
        body.addLayout(self._build_details(), 1)
        v.addLayout(body, 1)
        v.addLayout(self._build_default())
        self._rebuild(self._styles.default_style().name)

    # region building
    def _build_list(self) -> QVBoxLayout:
        left = QVBoxLayout()
        left.setSpacing(6)
        head = QLabel("Presets")
        head.setObjectName("SubHeading")
        left.addWidget(head)
        self.list = QListWidget()
        self.list.setObjectName("PresetList")
        self.list.setMinimumWidth(LIST_MIN_WIDTH)
        self.list.setMaximumWidth(LIST_MAX_WIDTH)
        self.list.setHorizontalScrollBarPolicy(  # (its entries are elided)
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        # (it scrolls: its height follows the window, not its entries)
        self.list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored
        )
        self.list.setMinimumHeight(120)
        self.list.setItemDelegate(PresetEntryDelegate(self._themes, self.list))
        self.list.currentItemChanged.connect(self._show_selected)
        left.addWidget(self.list, 1)
        tools = QGridLayout()
        tools.setSpacing(6)
        self.b_copy = self._button(
            "Copy", self.copy_preset, "Add a copy of the selected preset to your own"
        )
        self.b_rename = self._button("Rename", self.rename_preset)
        self.b_delete = self._button(
            "Delete",
            self.delete_preset,
            "Delete the selected preset of your own. Projects that use it keep "
            "their own copy.",
        )
        self.b_import = self._button(
            "Import…", self.import_presets, "Add the presets in a preset file"
        )
        self.b_export = self._button(
            "Export…",
            self.export_preset,
            "Save the selected preset to a file, to share it or use it with the "
            "command line's --preset",
        )
        for i, b in enumerate(
            (self.b_copy, self.b_rename, self.b_delete, self.b_import, self.b_export)
        ):
            tools.addWidget(b, i // 2, i % 2)
        left.addLayout(tools)
        return left

    def _build_details(self) -> QVBoxLayout:
        right = QVBoxLayout()
        right.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName("PageSection")
        right.addWidget(self.title)
        self.status = PageParts.hint()
        right.addWidget(self.status)
        self.edit_hint = PageParts.hint(
            "Click Save to keep your changes. Figures that already have this style "
            "keep their settings."
        )
        right.addWidget(self.edit_hint)
        holder = QWidget()
        h = QVBoxLayout(holder)
        h.setContentsMargins(0, 0, 12, 0)
        h.addWidget(self.editor)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setWidget(holder)
        # (it scrolls: its height follows the window, not the fields)
        self._scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored
        )
        self._scroll.setMinimumHeight(160)
        # as wide as the fields need, so a narrower window narrows the list first
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setMinimumWidth(
            holder.minimumSizeHint().width()
            + self._scroll.verticalScrollBar().sizeHint().width()
        )
        right.addWidget(self._scroll, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.b_save = self._button(
            "Save as your own",
            self.save_as_users,
            "Keep this project's version of the preset among your own presets",
        )
        self.b_remove = self._button(
            "Remove from this project",
            self.remove_from_project,
            "Take the preset out of this project. Its figures keep their settings.",
        )
        self.b_cancel_changes = self._button(
            "Cancel", self.cancel_changes, "Undo the changes since the last save"
        )
        self.b_save_changes = self._button(
            "Save", self.save_changes, "Keep the changes in this preset"
        )
        self.b_save_changes.setProperty("primary", True)
        actions.addWidget(self.b_save)
        actions.addWidget(self.b_remove)
        actions.addStretch(1)
        actions.addWidget(self.b_cancel_changes)
        actions.addWidget(self.b_save_changes)
        right.addLayout(actions)
        return right

    def _build_default(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("Default style"))
        self.default_box = QComboBox()
        self.default_box.setMinimumWidth(220)
        self.default_box.setToolTip(
            "The style of a figure you add while no figure is selected. With a "
            "figure selected, new figures copy its style."
        )
        self.default_box.activated.connect(self._default_picked)
        row.addWidget(self.default_box)
        row.addStretch(1)
        return row

    def _button(self, text: str, slot, tip: str = "") -> QPushButton:
        b = QPushButton(text)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    # endregion

    # region state
    def project_presets(self) -> list[StylePreset]:
        return list(self._project)

    def _selected(self) -> StylePreset | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return self._styles.find(item.data(Qt.ItemDataRole.UserRole), self._project)

    def _rebuild(self, select: str = "") -> None:
        """Fill the list again, with the preset called ``select`` selected."""
        self.list.blockSignals(True)
        try:
            self.list.clear()
            for p in self._styles.offered(self._project):
                item = QListWidgetItem(p.name)
                item.setData(Qt.ItemDataRole.UserRole, p.name)
                item.setData(NOTES_ROLE, self._styles.note(p, self._project))
                self.list.addItem(item)
                if p.name == select:
                    self.list.setCurrentItem(item)
            if self.list.currentItem() is None and self.list.count():
                self.list.setCurrentRow(0)
        finally:
            self.list.blockSignals(False)
        self._fill_default()
        self._show_selected()

    def _fill_default(self) -> None:
        box = self.default_box
        box.blockSignals(True)
        try:
            box.clear()
            for p in (*BUILTIN_STYLES, *self._prefs.user_styles()):
                box.addItem(p.name)
            box.setCurrentText(self._styles.default_style().name)
        finally:
            box.blockSignals(False)

    def _show_selected(self, current=None, previous=None) -> None:
        """Show the selected preset. Changes to the one shown before are saved or
        dropped first, as the user says, or else it stays selected."""
        if previous is not None and not self.resolve_pending():
            self.list.blockSignals(True)
            self.list.setCurrentItem(previous)
            self.list.blockSignals(False)
            return
        p = self._selected()
        if p is None:
            return
        self._show_details(p)
        self._show_state(p)

    def _show_state(self, p: StylePreset) -> None:
        """Say where ``p`` comes from, and enable the buttons that act on it."""
        builtin = self._styles.is_builtin(p.name)
        users = self._styles.is_users(p.name)
        in_project = p in self._project
        self.title.setText(p.name)
        self.status.setText(self._status(p, builtin, users, in_project))
        self.edit_hint.setVisible(self._editable(p))
        self.b_rename.setEnabled(users and not self._styles.differs(p))
        self.b_delete.setEnabled(users)
        self.b_save.setVisible(in_project)
        self.b_save.setEnabled(in_project and not builtin)
        self.b_remove.setVisible(in_project)
        self._sync_edit_buttons()

    def _sync_edit_buttons(self) -> None:
        editable = self._editing is not None
        changed = self._pending is not None
        self.b_save_changes.setVisible(editable)
        self.b_cancel_changes.setVisible(editable)
        self.b_save_changes.setEnabled(changed)
        self.b_cancel_changes.setEnabled(changed)

    def _status(
        self, p: StylePreset, builtin: bool, users: bool, in_project: bool
    ) -> str:
        if not in_project:
            if builtin:
                return (
                    "This preset comes with papermini and cannot be changed. Copy it "
                    "to make one of your own that you can change."
                )
            return "This preset is one of your own."
        if builtin:
            return (
                "This project has its own version of a preset that comes with "
                "papermini, with other settings. In this project, this version is used."
            )
        if not users:
            return (
                "This preset is saved with this project only. Save it as your own to "
                "use it in other projects."
            )
        if not self._styles.differs(p):
            return "This preset is one of your own, and it is saved with this project."
        return (
            "This project has its own version of one of your presets, with other "
            "settings. In this project, this version is used. Save it as your own to "
            "replace yours."
        )

    def _show_details(self, p: StylePreset) -> None:
        """Show the settings of ``p`` in the editor, which edits only presets that do
        not come with papermini."""
        self._scroll.verticalScrollBar().setValue(0)
        self._editing = p if self._editable(p) else None
        self._pending = None
        self.editor.set_settings(p.applied_to(FigureSettings()))
        self.editor.setEnabled(self._editing is not None)

    def _editable(self, p: StylePreset) -> bool:
        return p in self._project or not self._styles.is_builtin(p.name)

    def set_installed_fonts(self, names) -> None:
        """List the fonts installed on this computer in the editor."""
        self.editor.set_installed_fonts(names)

    # endregion

    # region actions
    def _edited(self, settings: FigureSettings) -> None:
        """Hold the edited settings until they are saved."""
        p = self._editing
        if p is None:
            return
        new = StylePreset.of(p.name, settings)
        self._pending = None if new.same_values(p) else new
        self._sync_edit_buttons()

    def save_changes(self) -> None:
        """Keep the changes in the preset being edited: the project's, and the user's
        own when the project's copy had the same settings, or else the user's."""
        p, new = self._editing, self._pending
        if p is None or new is None:
            return
        in_project = p in self._project
        if self._styles.is_users(p.name) and not (
            in_project and self._styles.differs(p)
        ):
            self._styles.save_users(new)
        if in_project:
            self._project = [new if q == p else q for q in self._project]
        self._editing, self._pending = new, None
        ui_log.info("Changed the style preset %s", p.name)
        self._sync_notes()
        self._show_state(new)

    def cancel_changes(self) -> None:
        """Show the preset being edited as it was last saved."""
        self._pending = None
        if self._editing is not None:
            self.editor.set_settings(self._editing.applied_to(FigureSettings()))
        self._sync_edit_buttons()

    def resolve_pending(self) -> bool:
        """Ask whether to save the unsaved changes, if there are any, and save or drop
        them. Return False when the user cancels."""
        if self._pending is None or self._editing is None:
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            f"Save the changes to the style preset {self._editing.name}?",
            buttons.Save | buttons.Discard | buttons.Cancel,
            buttons.Save,
        )
        if answer == buttons.Cancel:
            return False
        if answer == buttons.Save:
            self.save_changes()
        else:
            self.cancel_changes()
        return True

    def _sync_notes(self) -> None:
        """Say again where each listed preset comes from."""
        for row in range(self.list.count()):
            item = self.list.item(row)
            p = self._styles.find(item.data(Qt.ItemDataRole.UserRole), self._project)
            if p is not None:
                item.setData(NOTES_ROLE, self._styles.note(p, self._project))

    def copy_preset(self) -> None:
        if not self.resolve_pending():
            return
        p = self._selected()
        if p is None:
            return
        name = self._names.ask(self, "Copy style preset", self._unique(p.name))
        if name:
            self._styles.save_users(replace(p, name=name))
            ui_log.info("Copied the style preset %s as %s", p.name, name)
            self._rebuild(name)

    def rename_preset(self) -> None:
        """Rename the selected preset of the user's own, and this project's copy of
        it."""
        if not self.resolve_pending():
            return
        p = self._selected()
        if p is None or not self._styles.is_users(p.name):
            return
        name = self._names.ask(self, "Rename style preset", p.name, p.name)
        if not name or name == p.name:
            return
        mine = [
            replace(q, name=name) if q.name == p.name else q
            for q in self._prefs.user_styles()
            if q.name != name
        ]
        self._prefs.save_user_styles(mine)
        self._project = [
            replace(q, name=name) if q == p else q
            for q in self._project
            if q.name != name
        ]
        if self._prefs.default_style_name() == p.name:
            self._prefs.set_default_style_name(name)
        ui_log.info("Renamed the style preset %s to %s", p.name, name)
        self._rebuild(name)

    def delete_preset(self) -> None:
        if not self.resolve_pending():
            return
        p = self._selected()
        if p is None or not self._styles.is_users(p.name):
            return
        answer = QMessageBox.question(
            self, "Delete style preset", f"Delete your style preset {p.name}?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._prefs.save_user_styles(
            [q for q in self._prefs.user_styles() if q.name != p.name]
        )
        ui_log.info("Deleted the style preset %s", p.name)
        self._rebuild(p.name)

    def save_as_users(self) -> None:
        if not self.resolve_pending():
            return
        p = self._selected()
        if p is None or p not in self._project:
            return
        if self._styles.is_users(p.name):
            answer = QMessageBox.question(
                self,
                "Save style preset",
                f"Replace your style preset {p.name} with this project's version?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._styles.save_users(p)
        ui_log.info("Saved this project's style preset %s as your own", p.name)
        self._rebuild(p.name)

    def remove_from_project(self) -> None:
        if not self.resolve_pending():
            return
        p = self._selected()
        if p is None or p not in self._project:
            return
        self._project = [q for q in self._project if q.name != p.name]
        ui_log.info("Removed the style preset %s from the project", p.name)
        self._rebuild(p.name)

    def import_presets(self) -> None:
        if not self.resolve_pending():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import style presets",
            str(self._folder),
            "Style presets (*.yaml *.yml)",
        )
        if not path:
            return
        try:
            presets = self._preset_files.load(Path(path))
        except (OSError, ValueError, yaml.YAMLError) as e:
            QMessageBox.warning(self, "Import style presets", f"Could not import:\n{e}")
            return
        added, skipped = [], []
        for p in presets:
            if self._styles.is_builtin(p.name):
                skipped.append(p.name)
                continue
            if self._styles.is_users(p.name) and not self._replace(p.name):
                skipped.append(p.name)
                continue
            self._styles.save_users(p)
            added.append(p.name)
        ui_log.info("Imported the style presets %s from %s", ", ".join(added), path)
        if skipped:
            QMessageBox.information(
                self,
                "Import style presets",
                "Not imported, because a preset of that name is already here: "
                + ", ".join(skipped)
                + ".",
            )
        self._rebuild(added[0] if added else "")

    def _replace(self, name: str) -> bool:
        answer = QMessageBox.question(
            self,
            "Import style presets",
            f"You already have a style preset called {name}. Replace it?",
        )
        return answer == QMessageBox.StandardButton.Yes

    def export_preset(self) -> None:
        if not self.resolve_pending():
            return
        p = self._selected()
        if p is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export style preset",
            str(self._folder / f"{p.name}.yaml"),
            "Style presets (*.yaml)",
        )
        if not path:
            return
        try:
            self._preset_files.save([p], Path(path))
        except OSError as e:
            QMessageBox.warning(self, "Export style preset", f"Could not save:\n{e}")
            return
        ui_log.info("Exported the style preset %s to %s", p.name, path)

    def _default_picked(self, *_) -> None:
        self._prefs.set_default_style_name(self.default_box.currentText())

    def _unique(self, base: str) -> str:
        taken = {p.name for p in self._styles.offered(self._project)}
        name, n = f"{base} copy", 2
        while name in taken:
            name, n = f"{base} copy {n}", n + 1
        return name

    # endregion
