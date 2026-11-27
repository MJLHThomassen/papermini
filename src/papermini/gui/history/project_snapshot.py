from __future__ import annotations

from dataclasses import dataclass, field, fields

from ...project.figure_settings import FigureSettings
from ...project.sheet_settings import SheetSettings
from ...project.size_table import SizeTable
from ...project.style_preset import StylePreset
from ..window.figure import Figure
from .merge_key import MergeKey


@dataclass(frozen=True)
class ProjectSnapshot:
    """The state of a project that undo puts back: the uids of its figures in
    order, each figure's settings by uid, the sheet settings, the creature size
    table and the project's style presets.

    ``kept`` holds each figure by its uid, so that a figure brought back keeps its
    latest build. Two snapshots are equal when all else is.
    """

    order: tuple[int, ...]
    settings: dict[int, FigureSettings] = field(hash=False)
    sheet: SheetSettings
    sizes: SizeTable
    presets: tuple[StylePreset, ...] = field(default=(), hash=False)
    kept: dict[int, Figure] = field(default_factory=dict, compare=False, hash=False)

    @classmethod
    def of(
        cls,
        figures: list[Figure],
        sheet: SheetSettings,
        sizes: SizeTable,
        presets: list[StylePreset],
    ) -> ProjectSnapshot:
        """Take a snapshot of ``figures`` and the project's sheet, sizes and style
        presets."""
        return cls(
            tuple(f.uid for f in figures),
            {f.uid: f.entry.settings for f in figures},
            sheet,
            sizes,
            tuple(presets),
            {f.uid: f for f in figures},
        )

    def changed_figures(self, other: ProjectSnapshot) -> list[int]:
        """Return the uids of the figures here that ``other`` lacks or holds with
        other settings, in their order here."""
        return [
            uid for uid in self.order if other.settings.get(uid) != self.settings[uid]
        ]

    def changed_names(self, other: ProjectSnapshot, uid: int) -> set[str]:
        """Return the names of the settings of the figure ``uid`` that differ between
        here and ``other``. A figure only one of them holds has no changed names."""
        mine, theirs = self.settings.get(uid), other.settings.get(uid)
        if mine is None or theirs is None:
            return set()
        return self._differing(mine, theirs)

    def changed_sheet_names(self, other: ProjectSnapshot) -> set[str]:
        """Return the names of the sheet settings that differ between here and
        ``other``."""
        return self._differing(self.sheet, other.sheet)

    def merge_key(self, before: ProjectSnapshot) -> MergeKey | None:
        """Return what the change from ``before`` to here edits, when it edits one
        figure's settings or the sheet's and nothing else, or None for any other
        change."""
        if (
            self.order != before.order
            or self.sizes != before.sizes
            or self.presets != before.presets
        ):
            return None
        changed = self.changed_figures(before)
        sheet = self.changed_sheet_names(before)
        if len(changed) == 1 and not sheet:
            names = self.changed_names(before, changed[0])
            return MergeKey(changed[0], frozenset(names))
        if sheet and not changed:
            return MergeKey(None, frozenset(sheet))
        return None

    @staticmethod
    def _differing(a, b) -> set[str]:
        return {f.name for f in fields(a) if getattr(a, f.name) != getattr(b, f.name)}
