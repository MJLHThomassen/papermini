"""The hint and title labels the Preferences pages share."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel


def _hint(text: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("Hint")
    lab.setWordWrap(True)
    return lab


def _page_title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("DialogTitle")
    return lab
