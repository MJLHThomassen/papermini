from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SheetFiles:
    """The files an export of a sheet wrote."""

    pdf: Path | None = None
    cut_files: list[Path] = field(default_factory=list)
    previews: list[Path] = field(default_factory=list)

    @property
    def paths(self) -> list[Path]:
        """Every file, the PDF first."""
        return ([self.pdf] if self.pdf else []) + self.cut_files + self.previews
