"""Figure: one figure in the list, with its settings and its latest build."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from PySide6.QtGui import QPixmap

from ...mini import Mini
from ...settings import FigureEntry


@dataclass
class Figure:
    uid: int
    entry: FigureEntry
    mini: Mini | None = None
    built_key: str | None = None
    gen: int = 0
    error: str | None = None
    pixmap: QPixmap | None = None  # art of ``mini`` as a QPixmap (cached for the sheet)
    queued: str | None = None  # key of the job waiting in the pool
    cancelled: str | None = None  # mask_key whose background removal the user cancelled
    bleed_mm: float = 0.0  # from the sheet: only when it is cut by machine

    def key(self) -> str:
        d = asdict(self.entry.settings)
        d.pop("copies")  # only matters for the sheet, never a reason to rebuild
        return f"{self.entry.image}|{sorted(d.items())}|bleed={self.bleed_mm}"

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
