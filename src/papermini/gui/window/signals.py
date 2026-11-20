from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class Signals(QObject):
    """Signals the background jobs send to the main window."""

    status = Signal(str)
    ask_download = Signal(str, object, object)  # model, answer dict, threading.Event
    link_done = Signal(
        str, object, str, object
    )  # link, downloaded path or None, error, settings
    fonts_found = Signal(object)  # the names of the fonts installed on this computer
