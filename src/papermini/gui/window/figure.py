from __future__ import annotations

from dataclasses import asdict, dataclass

from PySide6.QtGui import QPixmap

from ...pipeline.mini import Mini
from ...project.figure_entry import FigureEntry


@dataclass
class Figure:
    """One figure in the list: its settings and its latest build.

    A build is matched to its figure by ``key()``, which holds every setting the build
    depends on. A build job keeps the key it started with, and ``BuildQueue`` takes the
    finished build only while that key still equals the figure's ``key()``. A build
    for older settings is dropped, because the build for the new ones follows.
    ``built_key`` is the key of ``mini``, and ``queued`` the key of the job waiting in
    the pool.
    """

    uid: int
    entry: FigureEntry
    mini: Mini | None = None
    built_key: str | None = None
    error: str | None = None
    pixmap: QPixmap | None = None  # art of ``mini`` as a QPixmap (cached for the sheet)
    queued: str | None = None  # key of the job waiting in the pool
    cancelled: str | None = None  # mask_key whose background removal the user cancelled
    bleed_mm: float = 0.0  # from the sheet: only when it is cut by machine

    def invalidate(self) -> None:
        """Forget the error and the queued job of the old settings, so that the new
        settings get built."""
        self.error = self.queued = None

    def key(self) -> str:
        d = asdict(self.entry.settings)
        d.pop("copies")  # only matters for the sheet, never a reason to rebuild
        return f"{self.entry.image}|{sorted(d.items())}|bleed={self.bleed_mm}"

    def mask_key(self) -> str:
        """The image and the settings background removal depends on: a cancelled run
        stays cancelled until one of these changes (other settings do not start the
        model again)."""
        return f"{self.entry.image}|{self.entry.settings.mask_inputs()}"

    @property
    def up_to_date(self) -> bool:
        return self.mini is not None and self.built_key == self.key()

    @property
    def stopped(self) -> bool:
        """The user cancelled the background removal for the current image and crop."""
        return self.cancelled is not None and self.cancelled == self.mask_key()
