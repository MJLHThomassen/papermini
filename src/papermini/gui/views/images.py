"""Converts and loads images for Qt, and makes the adjusted preview of the Source view."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader


def pil_to_qimage(im) -> QImage:
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    return QImage(
        data, im.width, im.height, 4 * im.width, QImage.Format_RGBA8888
    ).copy()


def load_qimage(path) -> QImage:
    """Load an image with EXIF orientation applied (matches PIL's exif_transpose)."""
    r = QImageReader(str(path))
    r.setAutoTransform(True)
    return r.read()


PREVIEW_PX = 1600  # longest side of the adjusted picture on the Source view


def adjusted_preview(img: QImage, adj) -> QImage:
    """``img`` with the color adjustments ``adj``, for the Source view: at most
    PREVIEW_PX on its longest side, so a slider stays smooth on a large photo (the
    view shows it at the original's size; the print uses the full image)."""
    from ...pipeline.adjust import apply

    if max(img.width(), img.height()) > PREVIEW_PX:
        img = img.scaled(
            PREVIEW_PX, PREVIEW_PX, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
    img = img.convertToFormat(
        QImage.Format_RGBA8888
    )  # straight (not premultiplied) alpha
    w, h = img.width(), img.height()
    a = np.frombuffer(img.constBits(), np.uint8).reshape(h, img.bytesPerLine())[
        :, : 4 * w
    ]
    out = np.ascontiguousarray(apply(a.reshape(h, w, 4), adj, premultiplied=False))
    return QImage(out.data, w, h, 4 * w, QImage.Format_RGBA8888).copy()
