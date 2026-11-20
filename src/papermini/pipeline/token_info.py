from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from ..support.font_library import FontLibrary
from .text_fitter import TextFitter
from .text_item import NUMBER_PLACEHOLDER, TEXT_BASELINE_DROP, TextItem


@dataclass
class TokenInfo:
    """Where a token's parts are on its piece (mm, origin top-left), for its text and for
    framing it in the app."""

    cx: float
    cy: float
    radius_mm: float  # the cut line
    inner_mm: float  # inside the ring
    text: str = "none"
    text_style: str = "nameplate"
    color: str = "#ffffff"  # the text's color
    size_mm: float = 0.0  # the text's height (nameplate: at most)
    plate: tuple[float, float, float, float] | None = (
        None  # the label's box (cx, cy, w, h)
    )
    badge: tuple[float, float, float] | None = None  # the number badge (cx, cy, r)
    # the square of the picture that fills the circle, as fractions of the image (what
    # token_area holds), and the figure's box on the piece (mm)
    area: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    figure_box: tuple[float, float, float, float] | None = None

    def text_items(
        self, label: str, number: int | None, font: str, fonts: FontLibrary
    ) -> list[TextItem]:
        """Return the token's label and copy number, as ``text`` says and where
        ``text_style`` puts them (the preview shows the number as #), in ``font`` from
        ``fonts``."""
        num = NUMBER_PLACEHOLDER if number is None else str(number)
        show_label = self.text in ("label", "label_number") and bool(label)
        show_number = self.text in ("number", "label_number")
        items: list[TextItem] = []
        if self.text_style == "curved":
            r = (self.radius_mm + self.inner_mm) / 2
            if show_label:
                items += self._arc(label, r, font, fonts, bottom=True)
            if show_number:
                items += self._arc(num, r, font, fonts, bottom=False, bold=True)
            return items
        if (
            show_label and self.plate is not None
        ):  # (centred: the letters' middle on the band's)
            cx, cy, w, _h = self.plate
            size = TextFitter.label_size(fonts, label, w, self.size_mm, font)
            items.append(
                TextItem(
                    "tokentext",
                    label,
                    cx,
                    cy - self._middle(label, font, fonts) * size,
                    0.0,
                    size,
                    self.color,
                )
            )
        if show_number and self.badge is not None:
            cx, cy, r = self.badge
            size = TextFitter.number_size(fonts, num, 1.25 * r, 1.1 * r, font)
            items.append(
                TextItem(
                    "tokentext",
                    num,
                    cx,
                    cy - self._middle(num, font, fonts, True) * size,
                    0.0,
                    size,
                    self.color,
                    True,
                )
            )
        return items

    def _arc(
        self,
        text: str,
        r: float,
        font: str,
        fonts: FontLibrary,
        bottom: bool,
        bold: bool = False,
    ) -> list[TextItem]:
        """Return ``text`` curved along a circle of radius ``r`` around the token's
        centre, one item per character: along the bottom read left to right with the
        tops towards the centre, along the top with the tops outwards. The letters
        (descenders included) are centred on the circle. Shrinks to fit in 150
        degrees."""
        size = self.size_mm
        widths = [fonts.text_width(ch, font, size, bold) for ch in text]
        track = 0.05 * size
        total = sum(widths) + track * max(0, len(text) - 1)
        most = math.radians(150) * r
        if total > most:
            k = most / total
            size, widths, track, total = (
                size * k,
                [w * k for w in widths],
                track * k,
                most,
            )
        # the items' centres, so the letters' middle lies on the circle ("down" in the
        # text is outwards along the bottom and inwards along the top)
        shift = self._middle(text, font, fonts, bold) * size
        r = r - shift if bottom else r + shift
        items, s = [], -total / 2
        for ch, w in zip(text, widths):
            a = (s + w / 2) / r  # angle from the middle of the text
            theta = math.pi / 2 - a if bottom else -math.pi / 2 + a
            rot = -math.degrees(a) if bottom else math.degrees(a)
            if ch.strip():
                items.append(
                    TextItem(
                        "tokentext",
                        ch,
                        self.cx + r * math.cos(theta),
                        self.cy + r * math.sin(theta),
                        rot,
                        size,
                        self.color,
                        bold,
                    )
                )
            s += w + track
        return items

    @staticmethod
    @lru_cache(maxsize=256)
    def _middle(text: str, font: str, fonts: FontLibrary, bold: bool = False) -> float:
        """Return where the middle of ``text``'s letters is (ascenders to descenders),
        below a text item's centre, as a share of the text size. A text item is drawn
        with its baseline ``TEXT_BASELINE_DROP`` times the size below its centre;
        letters with descenders sit lower."""
        try:
            _, top, _, bottom = fonts.image_font(100, font, bold).getbbox(
                text, anchor="ls"
            )
        except (
            OSError,
            TypeError,
            ValueError,
        ):  # (a font without metrics: caps-like letters)
            top, bottom = -66, 0
        return TEXT_BASELINE_DROP + (top + bottom) / 200.0
