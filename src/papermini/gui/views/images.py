"""Converts and loads images for Qt, and makes the adjusted preview of the Source view."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader

from ...pipeline.image_adjuster import ImageAdjuster

# Qt refuses to read an image whose decoded size is over its allocation limit, 256 MB
# by default: a large scan then shows nothing. This limit is the decoded size of the
# largest image PIL opens (it refuses one over twice MAX_IMAGE_PIXELS), with four
# 16-bit channels per pixel, the widest format Qt reads a PNG into. When PIL has no
# limit, neither has Qt (0).
READ_BYTES_PER_PIXEL = 8
READ_LIMIT_MB = (
    0
    if Image.MAX_IMAGE_PIXELS is None
    else math.ceil(2 * Image.MAX_IMAGE_PIXELS * READ_BYTES_PER_PIXEL / 2**20)
)


def pil_to_qimage(im) -> QImage:
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    return QImage(
        data, im.width, im.height, 4 * im.width, QImage.Format_RGBA8888
    ).copy()


def load_qimage(path) -> QImage:
    """Load an image with EXIF orientation applied (matches PIL's exif_transpose).
    It reads every image that PIL opens."""
    QImageReader.setAllocationLimit(READ_LIMIT_MB)
    r = QImageReader(str(path))
    r.setAutoTransform(True)
    return r.read()


PREVIEW_PX = 1600  # longest side of the adjusted picture on the Source view


def adjusted_preview(img: QImage, adj, adjuster: ImageAdjuster) -> QImage:
    """``img`` with the color adjustments ``adj`` applied by ``adjuster``, for the Source
    view: at most PREVIEW_PX on its longest side, so a slider stays smooth on a large
    photo (the view shows it at the original's size; the print uses the full image)."""

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
    out = np.ascontiguousarray(
        adjuster.apply(a.reshape(h, w, 4), adj, premultiplied=False)
    )
    return QImage(out.data, w, h, 4 * w, QImage.Format_RGBA8888).copy()
