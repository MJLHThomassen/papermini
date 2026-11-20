from __future__ import annotations


class HexColor:
    """Reads colors written as hex strings."""

    @staticmethod
    def to_rgb(c: str) -> tuple[int, int, int]:
        """Turn '#rrggbb' (or '#rgb') into (r, g, b)."""
        h = c.strip().lstrip("#")
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        if len(h) != 6:
            raise ValueError(f"not a color: {c!r} (use #rrggbb)")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
