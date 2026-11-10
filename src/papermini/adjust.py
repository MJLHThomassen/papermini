"""Color adjustments of the printed picture: greyscale, hue, saturation, brightness
and contrast.

They change what is printed (the drawing, a margin filled with the image, the
mirrored back), never what background removal sees: moving a slider never runs the
model again, and the outline stays where it was.
"""

from __future__ import annotations

from dataclasses import astuple, dataclass

import numpy as np

# setting -> (lowest, highest); 0 leaves the picture as it is
RANGES = {"brightness": (-100, 100), "contrast": (-100, 100),
          "saturation": (-100, 100), "hue": (-180, 180)}

# RGB <-> YIQ: rotating I and Q turns the hue while keeping the brightness (Y)
_YIQ = np.array([[0.299, 0.587, 0.114],
                 [0.596, -0.274, -0.322],
                 [0.211, -0.523, 0.312]], np.float32)
_RGB = np.linalg.inv(_YIQ).astype(np.float32)
_LUMA = np.array([0.299, 0.587, 0.114], np.float32)
_ROWS = 256  # rows per chunk, so a large image never needs a full float copy


@dataclass(frozen=True)
class Adjustments:
    brightness: int = 0      # -100 (black) .. 100 (white); white paper stays white
    contrast: int = 0        # -100 (flat grey) .. 100 (hard)
    saturation: int = 0      # -100 (grey) .. 100 (twice as colorful)
    hue: int = 0             # degrees around the color wheel
    greyscale: bool = False  # black and white (saturation and hue then do nothing)

    def is_identity(self) -> bool:
        return not any(astuple(self))


def _matrix(adj: Adjustments) -> np.ndarray:
    """Hue, then saturation, as one 3x3 matrix, for pixels as rows (``c @ M``)."""
    m = np.eye(3, dtype=np.float32)  # on column vectors while composing
    if adj.hue and not adj.greyscale:
        a = -np.deg2rad(adj.hue)  # (positive: red -> yellow -> green, as in other editors)
        rot = np.array([[1, 0, 0],
                        [0, np.cos(a), -np.sin(a)],
                        [0, np.sin(a), np.cos(a)]], np.float32)
        m = _RGB @ rot @ _YIQ
    s = 0.0 if adj.greyscale else 1.0 + adj.saturation / 100.0
    if s != 1.0:
        grey = np.repeat(_LUMA[None, :], 3, axis=0)    # every channel = the luma
        m = (s * np.eye(3, dtype=np.float32) + (1 - s) * grey) @ m
    return m.T.astype(np.float32)


def _tone(c: np.ndarray, adj: Adjustments) -> np.ndarray:
    b = adj.brightness / 100.0
    if b > 0:
        c = c + (1.0 - c) * b      # towards white: white stays white
    elif b < 0:
        c = c * (1.0 + b)          # towards black: black stays black
    if adj.contrast:
        k = np.tan((min(adj.contrast, 99) / 100.0 + 1.0) * np.pi / 4)
        c = (c - 0.5) * k + 0.5
    return c


def apply(px: np.ndarray, adj: Adjustments, premultiplied: bool = True) -> np.ndarray:
    """``px`` (uint8 RGB, or RGBA: premultiplied as the pipeline keeps it, or straight
    with ``premultiplied=False``) with ``adj`` applied; alpha is unchanged."""
    if adj.is_identity():
        return px
    m = _matrix(adj)
    out = np.array(px, dtype=np.uint8, copy=True)
    rgba = out.shape[-1] == 4
    for y in range(0, out.shape[0], _ROWS):
        part = out[y:y + _ROWS]
        c = part[..., :3].astype(np.float32) / 255.0
        a = part[..., 3:4].astype(np.float32) / 255.0 if rgba else None
        if rgba and premultiplied:  # adjust the colors, not color times coverage
            c = np.where(a > 0, c / np.maximum(a, 1e-6), 0.0)
        c = _tone(c @ m, adj)
        c = np.clip(c, 0.0, 1.0)
        if rgba and premultiplied:
            c = c * a
        part[..., :3] = (c * 255.0 + 0.5).astype(np.uint8)
    return out
