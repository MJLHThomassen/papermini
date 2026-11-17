"""Wrapping a canvas overlay so it keeps a margin from the canvas edge."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget


def overlay_wrap(w: QWidget, margins=(16, 16, 16, 16)) -> QWidget:
    """Wrap an overlay so it keeps a margin from the canvas edge."""
    box = QWidget()
    box.setAttribute(Qt.WA_TranslucentBackground)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(*margins)
    lay.addWidget(w)
    return box
