from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """The colors of a theme."""

    name: str
    bg: str  # window
    surface: str  # panels, cards
    surface2: str  # inputs, hover
    canvas: str  # behind the paper
    dots: str  # canvas dot grid
    border: str
    text: str
    muted: str
    accent: str
    accent_text: str
    accent_soft: str  # selection background
    danger: str
    shadow: str


DRAGON_RED = "#fd3c1b"  # the logo's red: the accent in both themes

LIGHT = Theme(
    "light",
    bg="#f4f4f6",
    surface="#ffffff",
    surface2="#f7f7f9",
    canvas="#e9e9ee",
    dots="#d4d4dc",
    border="#e2e2e8",
    text="#1d1d22",
    muted="#6e6e7a",
    accent=DRAGON_RED,
    accent_text="#ffffff",
    accent_soft="#ffe9e4",
    danger="#d64545",
    shadow="#00000028",
)

DARK = Theme(
    "dark",
    bg="#161618",
    surface="#1e1e21",
    surface2="#26262a",
    canvas="#111113",
    dots="#26262b",
    border="#2f2f34",
    text="#ececf0",
    muted="#9a9aa6",
    accent=DRAGON_RED,
    accent_text="#ffffff",
    accent_soft="#45231f",
    danger="#f07070",
    shadow="#00000070",
)
