"""Where the desktop app keeps its preferences (theme, open sections, panel layout)."""

from PySide6.QtCore import QSettings


def store() -> QSettings:
    """The app's settings. Follows ``QSettings.setDefaultFormat`` / ``setPath``, so the
    tests can point it at a temporary folder instead of the user's real settings."""
    return QSettings(QSettings.defaultFormat(), QSettings.UserScope, "papermini", "papermini")
