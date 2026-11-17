"""The sizes, colors and cursors of the crop box and its handles."""

from __future__ import annotations

from PySide6.QtCore import Qt

HANDLE_PX = 10  # handle size on screen
GRAB_PX = 8  # how close (on screen) the mouse must be to grab a handle or edge
DRAG_PX = 4  # a press that moves less than this (on screen) is a click: no change
CROP_COLOR = "#ffd400"  # the crop box and its handles
CROP_HINT = "Drag a box around the figure to crop"
WASH_ALPHA = 200  # how strongly the background outside the outline is faded

_HANDLE_CURSORS = {
    "tl": Qt.SizeFDiagCursor,
    "br": Qt.SizeFDiagCursor,
    "tr": Qt.SizeBDiagCursor,
    "bl": Qt.SizeBDiagCursor,
    "l": Qt.SizeHorCursor,
    "r": Qt.SizeHorCursor,
    "t": Qt.SizeVerCursor,
    "b": Qt.SizeVerCursor,
    "move": Qt.SizeAllCursor,
}
