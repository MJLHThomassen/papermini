from __future__ import annotations

import html
import logging
import urllib.parse

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ...pipeline.segmentation import segment

ui_log = logging.getLogger("papermini.ui")
MB = 1024 * 1024


class ModelInfo:
    """Makes the labels and texts that the model dialogs share."""

    @staticmethod
    def host(model: str) -> str:
        """Return the name of the host that ``model`` downloads from."""
        return (
            urllib.parse.urlsplit(segment.ONNX_MODELS[model].url).hostname
            or "the internet"
        )

    @staticmethod
    def label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
        """Return a rich-text label whose links open in the browser, with the object
        name ``name``."""
        lab = QLabel(text)
        if name:
            lab.setObjectName(name)
        lab.setWordWrap(wrap)
        lab.setTextFormat(Qt.TextFormat.RichText)
        lab.setOpenExternalLinks(True)
        return lab

    @staticmethod
    def licence_link(model: str) -> str:
        """Return the licence of ``model`` as rich text, its name linked to the
        licence."""
        spec = segment.ONNX_MODELS[model]
        return (
            f'Licence: <a href="{html.escape(spec.licence_url)}">'
            f"{html.escape(spec.licence)}</a>"
        )
