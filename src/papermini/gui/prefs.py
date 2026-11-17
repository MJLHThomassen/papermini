"""Where the desktop app keeps its preferences (theme, open sections, panel layout, the
recent projects, how a folder of images is added, the size of exported PNGs)."""

import os
from pathlib import Path

from PySide6.QtCore import QSettings

RECENT_KEY = "recent_projects"
RECENT_MAX = 10  # projects in Open recent
SUBFOLDERS_KEY = "add_subfolders"
PNG_PX_KEY = "png_px_per_square"
PNG_PX_RANGE = (16, 4096)  # the PNG size a user can set, pixels per grid square
PNG_MODE_KEY = "png_size"  # "square" (pixels per grid square) or "dpi"
PNG_DPI_KEY = "png_dpi"
PNG_DPI_RANGE = (50, 2400)


def store() -> QSettings:
    """The app's settings. Follows ``QSettings.setDefaultFormat`` / ``setPath``, so the
    tests can point it at a temporary folder instead of the user's real settings."""
    return QSettings(
        QSettings.defaultFormat(), QSettings.UserScope, "papermini", "papermini"
    )


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a)) == os.path.normcase(str(b))


def recent_projects() -> list[Path]:
    """The projects opened or saved last, newest first. A project whose file is gone is
    left out (and forgotten)."""
    stored = store().value(RECENT_KEY, [])
    paths = [stored] if isinstance(stored, str) else list(stored or [])
    found = [Path(p) for p in paths if p and Path(p).is_file()]
    if len(found) != len(paths):
        store().setValue(RECENT_KEY, [str(p) for p in found])
    return found[:RECENT_MAX]


def add_recent(path: Path) -> None:
    """Put the project at ``path`` at the top of the recent projects."""
    path = Path(path).resolve()
    rest = [p for p in recent_projects() if not _same(p, path)]
    store().setValue(RECENT_KEY, [str(p) for p in [path] + rest][:RECENT_MAX])


def clear_recent() -> None:
    store().setValue(RECENT_KEY, [])


def add_subfolders() -> bool:
    """Whether adding a folder also adds the images in its subfolders (on by default)."""
    v = store().value(SUBFOLDERS_KEY, True)
    return v if isinstance(v, bool) else str(v).lower() == "true"


def set_add_subfolders(on: bool) -> None:
    store().setValue(SUBFOLDERS_KEY, bool(on))


def png_px_per_square() -> int:
    """The size of exported PNGs: pixels per grid square (a preference, never saved in a
    project: it depends on the virtual tabletop)."""
    from ..output.png import PX_PER_SQUARE

    try:
        v = int(store().value(PNG_PX_KEY, PX_PER_SQUARE))
    except (TypeError, ValueError):
        v = PX_PER_SQUARE
    return v if PNG_PX_RANGE[0] <= v <= PNG_PX_RANGE[1] else PX_PER_SQUARE


def set_png_px_per_square(px: int) -> None:
    store().setValue(PNG_PX_KEY, int(px))


def png_size_mode() -> str:
    """How exported PNGs are sized: "square" (pixels per grid square, for a virtual
    tabletop) or "dpi" (a resolution, at the size it prints)."""
    v = str(store().value(PNG_MODE_KEY, "square"))
    return v if v in ("square", "dpi") else "square"


def set_png_size_mode(mode: str) -> None:
    store().setValue(PNG_MODE_KEY, mode)


def png_dpi() -> int:
    from ..output.png import DPI

    try:
        v = int(store().value(PNG_DPI_KEY, DPI))
    except (TypeError, ValueError):
        v = DPI
    return v if PNG_DPI_RANGE[0] <= v <= PNG_DPI_RANGE[1] else DPI


def set_png_dpi(dpi: int) -> None:
    store().setValue(PNG_DPI_KEY, int(dpi))


def png_px_per_mm(grid_mm: float) -> float:
    """The scale of exported PNGs (pixels per mm), as the preferences set it: from the
    pixels per square of a ``grid_mm`` grid, or from the dpi."""
    from ..output.png import px_per_mm

    if png_size_mode() == "dpi":
        return png_dpi() / 25.4
    return px_per_mm(png_px_per_square(), grid_mm)
