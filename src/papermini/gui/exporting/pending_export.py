from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtWidgets import QProgressDialog

from ..window.figure import Figure


@dataclass
class PendingExport:
    """An export or print that waits for its figures to build."""

    figures: list[Figure]
    then: Callable[[], None]  # runs once every figure is built
    progress: QProgressDialog
    count: int  # how many figures needed a build when it started
