"""Where the desktop app keeps its preferences (theme, open sections, panel layout, the
recent projects, how a folder of images is added)."""

import os
from pathlib import Path
from typing import List

from PySide6.QtCore import QSettings

RECENT_KEY = "recent_projects"
RECENT_MAX = 10              # projects in Open recent
SUBFOLDERS_KEY = "add_subfolders"


def store() -> QSettings:
    """The app's settings. Follows ``QSettings.setDefaultFormat`` / ``setPath``, so the
    tests can point it at a temporary folder instead of the user's real settings."""
    return QSettings(QSettings.defaultFormat(), QSettings.UserScope, "papermini", "papermini")


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a)) == os.path.normcase(str(b))


def recent_projects() -> List[Path]:
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
