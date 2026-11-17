from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class Signals(QObject):
    """Signals the background jobs send to the main window."""

    update = Signal(
        str, object, str
    )  # update check: state, data, who asked (see check_updates)
    done = Signal(int, int, str, object)  # uid, gen, key, Mini
    failed = Signal(int, int, str, str)  # uid, gen, key, message
    cancelled = Signal(int, int, str)  # uid, gen, key: the user stopped the model
    stage = Signal(
        int, str, str, str, object
    )  # uid, key, mask_key, stage name, data (see make_mini)
    status = Signal(str)
    ask_download = Signal(str, object, object)  # model, answer dict, threading.Event
    link_done = Signal(
        str, object, str, object
    )  # link, downloaded path or None, error, settings
    fonts_found = Signal(object)  # the names of the fonts installed on this computer
