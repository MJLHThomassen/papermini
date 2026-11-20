from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class JobSignals(QObject):
    """Signals the build jobs send from the worker thread to the build queue."""

    finished = Signal(object)  # BuildResult
    stage = Signal(
        int, str, str, str, object
    )  # uid, key, mask_key, stage name, data (see MiniBuilder.make)
    status = Signal(str)
