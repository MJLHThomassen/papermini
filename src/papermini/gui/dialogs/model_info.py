"""What the model dialogs say about a model: its size, host, labels and licence link."""

from __future__ import annotations

import html
import logging
import urllib.parse

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ...pipeline.segmentation import segment

ui_log = logging.getLogger("papermini.ui")


MB = 1024 * 1024


def _host(model: str) -> str:
    return (
        urllib.parse.urlsplit(segment.ONNX_MODELS[model]["url"]).hostname
        or "the internet"
    )


def _label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    lab.setTextFormat(Qt.RichText)
    lab.setOpenExternalLinks(True)  # links open in the browser
    return lab


def licence_link(model: str) -> str:
    """ "Licence: <name>" with the name linking to the licence (rich text)."""
    spec = segment.ONNX_MODELS[model]
    return (
        f'Licence: <a href="{html.escape(spec["licence_url"])}">'
        f"{html.escape(spec['licence'])}</a>"
    )
