from __future__ import annotations

from ..support.font_library import FontLibrary


class TextFitter:
    """Works out how large a piece's text can be to fit the room it has. Each method
    measures the text in the fonts of a ``FontLibrary``."""

    @staticmethod
    def label_size(
        fonts: FontLibrary,
        text: str,
        max_width_mm: float,
        size_mm: float,
        font: str = FontLibrary.DEFAULT,
    ) -> float:
        """Shrink the label font so the text fits ``max_width_mm``."""
        if not text:
            return size_mm
        w = fonts.text_width(text, font, size_mm)
        return size_mm if w <= max_width_mm else size_mm * max_width_mm / w

    @staticmethod
    def number_size(
        fonts: FontLibrary,
        text: str,
        max_w: float,
        max_h: float,
        font: str = FontLibrary.DEFAULT,
    ) -> float:
        """Return the largest bold font size at which ``text`` fits ``max_w`` x
        ``max_h`` (mm)."""
        w = fonts.text_width(text, font, 1.0, bold=True)
        return max(0.0, min(max_h, max_w / w if w else max_h))

    @staticmethod
    def text_block(
        fonts: FontLibrary,
        text: str,
        max_w: float,
        max_h: float,
        max_size: float,
        max_lines: int = 4,
        font: str = FontLibrary.DEFAULT,
    ) -> tuple[float, list[str]]:
        """Return the largest font size (and line split) that fits ``text`` into
        max_w x max_h.

        Tries 1..max_lines lines; words are balanced over the lines. Line pitch is
        1.15 x the font size. Units are whatever max_w/max_h use (mm here).
        """
        words = text.split()
        if not words:
            return 0.0, []
        width = lambda t: fonts.text_width(t, font, 1.0)
        best = (0.0, [text])
        for n in range(1, min(max_lines, len(words)) + 1):
            target = width(" ".join(words)) / n
            lines, cur = [], []
            for w in words:
                if (
                    cur
                    and width(" ".join(cur + [w])) > target * 1.08
                    and len(lines) < n - 1
                ):
                    lines.append(" ".join(cur))
                    cur = []
                cur.append(w)
            lines.append(" ".join(cur))
            size = min(
                max_size,
                max_h / (1.15 * len(lines)),
                min(max_w / max(width(t), 1e-6) for t in lines),
            )
            if size > best[0] * 1.15:  # prefer fewer lines unless clearly bigger
                best = (size, lines)
        return best
