from __future__ import annotations

from PySide6.QtWidgets import QLabel


class PageParts:
    """Makes the hint and title labels that the Preferences pages share."""

    @staticmethod
    def hint(text: str = "") -> QLabel:
        """Return a hint label that wraps its ``text``."""
        lab = QLabel(text)
        lab.setObjectName("Hint")
        lab.setWordWrap(True)
        return lab

    @staticmethod
    def title(text: str) -> QLabel:
        """Return the title label of a page."""
        lab = QLabel(text)
        lab.setObjectName("DialogTitle")
        return lab
