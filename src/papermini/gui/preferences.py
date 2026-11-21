from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

from ..project import sizes


class Preferences:
    """The desktop app's preferences, with one accessor per stored key. A changed key
    string loses what users saved under it."""

    RECENT_MAX = 10  # projects in Open recent
    PNG_PX_RANGE = (16, 4096)  # the PNG size a user can set, pixels per grid square
    PNG_DPI_RANGE = (50, 2400)
    PNG_SIZE_MODES = ("square", "dpi")

    _THEME = "theme"
    _SPLITTER = "layout/splitter"
    _LEFT_WIDTH = "layout/left_width"
    _RIGHT_WIDTH = "layout/right_width"
    _SECTION = "sections/{}"
    _RECENT = "recent_projects"
    _SUBFOLDERS = "add_subfolders"
    _PNG_PX = "png_px_per_square"
    _PNG_MODE = "png_size"
    _PNG_DPI = "png_dpi"
    _SIZE_PRESETS = "sizes/presets"
    _DEFAULT_PRESET = "sizes/default_preset"
    _EXPORT_PDF = "export/pdf"
    _EXPORT_CUT = "export/cut"
    _LAST_UPDATE_CHECK = "updates/last_check"
    _AUTO_UPDATES = "updates/auto"

    # region store
    @staticmethod
    def _store() -> QSettings:
        """Open the store. It follows ``QSettings.setDefaultFormat`` and ``setPath``,
        so the tests can point it at a temporary folder."""
        return QSettings(
            QSettings.defaultFormat(),
            QSettings.Scope.UserScope,
            "papermini",
            "papermini",
        )

    def _bool(self, key: str, default: bool) -> bool:
        return bool(self._store().value(key, default, type=bool))

    def _int(self, key: str) -> int:
        stored = self._store().value(key, 0, type=int)
        return stored if isinstance(stored, int) else 0

    def _set(self, key: str, value) -> None:
        self._store().setValue(key, value)

    # endregion

    # region appearance
    def theme(self) -> str:
        """Return the theme: "system", "light" or "dark"."""
        return str(self._store().value(self._THEME, "system", type=str))

    def set_theme(self, mode: str) -> None:
        self._set(self._THEME, mode)

    def splitter_state(self) -> QByteArray | None:
        """Return the saved state of the main window's splitter, or None."""
        state = self._store().value(self._SPLITTER)
        return state if isinstance(state, QByteArray) and not state.isEmpty() else None

    def set_splitter_state(self, state: QByteArray) -> None:
        self._set(self._SPLITTER, state)

    def left_panel_width(self) -> int:
        """Return the width of the left side panel when open, or 0 when not saved."""
        return self._int(self._LEFT_WIDTH)

    def set_left_panel_width(self, width: int) -> None:
        self._set(self._LEFT_WIDTH, width)

    def right_panel_width(self) -> int:
        """Return the width of the right side panel when open, or 0 when not saved."""
        return self._int(self._RIGHT_WIDTH)

    def set_right_panel_width(self, width: int) -> None:
        self._set(self._RIGHT_WIDTH, width)

    def section_open(self, title: str) -> bool:
        """Tell whether the settings section called ``title`` is open (open by
        default)."""
        return self._bool(self._SECTION.format(title), True)

    def set_section_open(self, title: str, open_: bool) -> None:
        self._set(self._SECTION.format(title), open_)

    # endregion

    # region recent projects
    def recent_projects(self) -> list[Path]:
        """Return the projects opened or saved last, newest first. A project whose
        file is gone is left out, and forgotten."""
        stored = self._store().value(self._RECENT, [])
        if isinstance(stored, str):  # (QSettings reads back a list of one as a string)
            paths = [stored]
        else:
            paths = list(stored) if isinstance(stored, (list, tuple)) else []
        found = [Path(p) for p in paths if p and Path(p).is_file()]
        if len(found) != len(paths):
            self._set(self._RECENT, [str(p) for p in found])
        return found[: self.RECENT_MAX]

    def add_recent(self, path: Path) -> None:
        """Put the project at ``path`` at the top of the recent projects."""
        path = Path(path).resolve()
        rest = [p for p in self.recent_projects() if not self._same(p, path)]
        self._set(self._RECENT, [str(p) for p in [path, *rest]][: self.RECENT_MAX])

    def clear_recent(self) -> None:
        self._set(self._RECENT, [])

    @staticmethod
    def _same(a: Path, b: Path) -> bool:
        return os.path.normcase(str(a)) == os.path.normcase(str(b))

    # endregion

    # region images
    def add_subfolders(self) -> bool:
        """Tell whether adding a folder also adds the images in its subfolders (on by
        default)."""
        v = self._store().value(self._SUBFOLDERS, True)
        return v if isinstance(v, bool) else str(v).lower() == "true"

    def set_add_subfolders(self, on: bool) -> None:
        self._set(self._SUBFOLDERS, bool(on))

    def png_px_per_square(self) -> int:
        """Return the size of exported PNGs in pixels per grid square. It is never
        saved in a project, because it depends on the virtual tabletop."""
        from ..output.png_writer import PX_PER_SQUARE

        return self._int_in(self._PNG_PX, PX_PER_SQUARE, self.PNG_PX_RANGE)

    def set_png_px_per_square(self, px: int) -> None:
        self._set(self._PNG_PX, int(px))

    def png_size_mode(self) -> str:
        """Return how exported PNGs are sized: "square" (pixels per grid square, for a
        virtual tabletop) or "dpi" (a resolution, at the size it prints)."""
        v = str(self._store().value(self._PNG_MODE, "square"))
        return v if v in self.PNG_SIZE_MODES else "square"

    def set_png_size_mode(self, mode: str) -> None:
        self._set(self._PNG_MODE, mode)

    def png_dpi(self) -> int:
        """Return the resolution of exported PNGs in the "dpi" size mode."""
        from ..output.png_writer import DPI

        return self._int_in(self._PNG_DPI, DPI, self.PNG_DPI_RANGE)

    def set_png_dpi(self, dpi: int) -> None:
        self._set(self._PNG_DPI, int(dpi))

    def png_px_per_mm(self, grid_mm: float) -> float:
        """Return the scale of exported PNGs in pixels per mm: from the pixels per
        square of a ``grid_mm`` grid, or from the dpi, as the size mode says."""
        from ..output.png_writer import PngWriter

        if self.png_size_mode() == "dpi":
            return self.png_dpi() / 25.4
        return PngWriter.px_per_mm(self.png_px_per_square(), grid_mm)

    def _int_in(self, key: str, default: int, limits: tuple[int, int]) -> int:
        """Read a whole number, or ``default`` when it is unreadable or outside
        ``limits``."""
        stored = self._store().value(key, default)
        try:
            v = int(stored) if isinstance(stored, (int, float, str)) else default
        except ValueError:
            v = default
        return v if limits[0] <= v <= limits[1] else default

    # endregion

    # region creature size presets
    def user_presets(self) -> list[sizes.SizeTable]:
        """Return the user's own size table presets. Entries that cannot be read are
        left out, and so are entries with the built-in preset's name or a name used
        before."""
        text = str(self._store().value(self._SIZE_PRESETS, "", type=str))
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

    def save_user_presets(self, tables: list[sizes.SizeTable]) -> None:
        self._set(self._SIZE_PRESETS, json.dumps([t.to_dict() for t in tables]))

    def presets(self) -> list[sizes.SizeTable]:
        """Return every preset: the built-in one first, then the user's own."""
        return [sizes.BUILTIN, *self.user_presets()]

    def default_preset_name(self) -> str:
        """Return the name of the preset new projects start with."""
        return str(
            self._store().value(self._DEFAULT_PRESET, sizes.BUILTIN_NAME, type=str)
        )

    def set_default_preset_name(self, name: str) -> None:
        self._set(self._DEFAULT_PRESET, name)

    def default_table(self) -> sizes.SizeTable:
        """Return the preset new projects start with, or the built-in one when the
        default preset is gone."""
        return self._find(self.presets(), self.default_preset_name()) or sizes.BUILTIN

    def preset_of(
        self, table: sizes.SizeTable, tables: list[sizes.SizeTable] | None = None
    ) -> str:
        """Return the name of the preset among ``tables`` (by default every preset)
        that ``table`` is, with the same name and values, or ""."""
        p = self._find(tables if tables is not None else self.presets(), table.name)
        return p.name if p is not None and p.same_values(table) else ""

    def table_label(self, table: sizes.SizeTable) -> str:
        """Name a project's size table: by its preset, or as the project's own."""
        return self.preset_of(table) or "this project's table"

    @staticmethod
    def _find(tables: list[sizes.SizeTable], name: str) -> sizes.SizeTable | None:
        return next((t for t in tables if t.name == name), None)

    # endregion

    # region export
    def export_pdf(self) -> bool:
        """Tell whether exporting the sheet saves the sheet to print (on by default)."""
        return self._bool(self._EXPORT_PDF, True)

    def set_export_pdf(self, on: bool) -> None:
        self._set(self._EXPORT_PDF, on)

    def export_cut(self) -> bool:
        """Tell whether exporting a sheet cut by machine saves the cut file (on by
        default)."""
        return self._bool(self._EXPORT_CUT, True)

    def set_export_cut(self, on: bool) -> None:
        self._set(self._EXPORT_CUT, on)

    # endregion

    # region updates
    def last_update_check(self) -> float:
        """Return when papermini last heard back from an update check, in seconds since
        the epoch, or 0."""
        stored = self._store().value(self._LAST_UPDATE_CHECK, 0.0, type=float)
        return stored if isinstance(stored, float) else 0.0

    def set_last_update_check(self, when: float) -> None:
        self._set(self._LAST_UPDATE_CHECK, when)

    def auto_updates(self) -> bool:
        """Tell whether papermini looks for, downloads and installs updates by itself
        (on by default)."""
        return self._bool(self._AUTO_UPDATES, True)

    def set_auto_updates(self, on: bool) -> None:
        self._set(self._AUTO_UPDATES, bool(on))

    # endregion
