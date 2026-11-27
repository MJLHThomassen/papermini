from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .figure_entry import FigureEntry
from .sheet_settings import SheetSettings
from .size_table import SizeTable
from .sizes import BUILTIN
from .style_preset import StylePreset
from .styles import BUILTIN_STYLES


@dataclass
class Project:
    path: Path | None = None  # the YAML file, if saved
    output: str = "minis"
    sheet: SheetSettings = field(default_factory=SheetSettings)
    figures: list[FigureEntry] = field(default_factory=list)
    debug: bool = False
    sizes: SizeTable = BUILTIN  # the project's creature size table
    # the style presets given to its figures or saved in it
    presets: list[StylePreset] = field(default_factory=list)

    def keep_preset(self, preset: StylePreset) -> bool:
        """Keep ``preset`` among the project's presets, in place of one with its name,
        and return whether it took the place of one with other settings. A built-in
        preset with papermini's settings is not kept, since every papermini has it."""
        builtin = next((p for p in BUILTIN_STYLES if p.name == preset.name), None)
        if builtin is not None and builtin.same_values(preset):
            self.presets = [p for p in self.presets if p.name != preset.name]
            return False
        at = next(
            (i for i, p in enumerate(self.presets) if p.name == preset.name), None
        )
        if at is None:
            self.presets = [*self.presets, preset]
            return False
        replaced = not self.presets[at].same_values(preset)
        self.presets = [*self.presets[:at], preset, *self.presets[at + 1 :]]
        return replaced

    @property
    def base(self) -> Path:
        return self.path.parent if self.path else Path.cwd()

    @property
    def output_dir(self) -> Path:
        return self.base / self.output

    @property
    def sheet_path(self) -> Path:
        return (
            self.base / self.sheet.output
            if self.sheet.output
            else self.output_dir / "sheet.pdf"
        )
