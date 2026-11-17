from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import sizes
from .figure_entry import FigureEntry
from .sheet_settings import SheetSettings


@dataclass
class Project:
    path: Path | None = None  # the YAML file, if saved
    output: str = "minis"
    sheet: SheetSettings = field(default_factory=SheetSettings)
    figures: list[FigureEntry] = field(default_factory=list)
    debug: bool = False
    sizes: sizes.SizeTable = sizes.BUILTIN  # the project's creature size table

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
