from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout

from ...pipeline.segmentation import segment
from ...pipeline.segmentation.segmenter_registry import SegmenterRegistry
from .model_info import MB, _host, _label, licence_link

if TYPE_CHECKING:
    from .cache_page import CachePage


class ModelCard(QFrame):
    """One built-in model on the Models and cache page: what it is, where it is,
    actions."""

    def __init__(self, model: str, dialog: CachePage):
        super().__init__()
        self.setObjectName("ModelCard")
        self.model, self.dialog = model, dialog
        spec = segment.ONNX_MODELS[model]
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 14, 12)
        h.setSpacing(14)
        v = QVBoxLayout()
        v.setSpacing(3)
        v.addWidget(
            _label(
                f"<b>{html.escape(spec['title'])}</b>"
                f"&nbsp;&nbsp;<span style='font-weight:400'>{model}</span>"
            )
        )
        v.addWidget(_label(html.escape(spec["about"]), "Muted"))
        restricted = SegmenterRegistry.non_commercial(model)
        self.licence = _label(
            licence_link(model), "LicenceNote" if restricted else "Muted"
        )
        self.licence.setTextInteractionFlags(Qt.TextBrowserInteraction)
        if restricted:
            self.licence.setToolTip(SegmenterRegistry.licence_notice(model))
        v.addWidget(self.licence)
        self.state = _label("", "Hint")
        self.state.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.state)
        h.addLayout(v, 1)
        self.btn_get = QPushButton()
        self.btn_get.clicked.connect(lambda: dialog.download(model))
        self.btn_del = QPushButton("Delete")
        self.btn_del.clicked.connect(lambda: dialog.delete(model))
        for b in (self.btn_get, self.btn_del):
            h.addWidget(b, 0, Qt.AlignVCenter)
        self.refresh()

    def refresh(self):
        spec = segment.ONNX_MODELS[self.model]
        path = SegmenterRegistry.path(self.model)
        have = path.exists()
        if have:
            size = path.stat().st_size / MB
            self.state.setText(f"Downloaded · {size:.0f} MB · {html.escape(path.name)}")
        else:
            self.state.setText(
                f"Not downloaded · about {spec['mb']} MB from "
                f"{html.escape(_host(self.model))}"
            )
        self.btn_get.setText("Download again" if have else "Download")
        self.btn_get.setAccessibleName(f"{self.btn_get.text()} {spec['title']}")
        self.btn_del.setEnabled(have)
        self.btn_del.setAccessibleName(f"Delete {spec['title']}")
