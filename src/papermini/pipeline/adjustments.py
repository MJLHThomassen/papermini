from __future__ import annotations

from dataclasses import astuple, dataclass


@dataclass(frozen=True)
class Adjustments:
    brightness: int = 0  # -100 (black) .. 100 (white); white paper stays white
    contrast: int = 0  # -100 (flat grey) .. 100 (hard)
    saturation: int = 0  # -100 (grey) .. 100 (twice as colorful)
    hue: int = 0  # degrees around the color wheel
    greyscale: bool = False  # black and white (saturation and hue then do nothing)

    def is_identity(self) -> bool:
        return not any(astuple(self))
