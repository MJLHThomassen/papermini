from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from ..pipeline.mini import Mini
from ..pipeline.style import FOLD_DASH_MM, FOLD_GAP_MM
from ..pipeline.text_item import TEXT_BASELINE_DROP
from ..support.font_library import FontLibrary
from .svg_format import SvgFormat

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


class SvgWriter:
    """Writes a miniature as an SVG file in mm, its text in its font from ``fonts``."""

    def __init__(self, fonts: FontLibrary):
        self._fonts = fonts

    def svg(self, m: Mini) -> str:
        """The SVG file of the miniature, as text."""
        f = SvgFormat.number
        st = m.style
        b64 = base64.b64encode(m.png_bytes()).decode("ascii")
        W, H = f(m.width_mm), f(m.height_mm)
        out = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<svg xmlns="{SVG_NS}" xmlns:xlink="{XLINK_NS}" '
                f'width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">'
            ),
            f"<title>{escape(m.label or m.name)}</title>",
            f'<metadata id="papermini">{escape(m.name)}</metadata>',
            (
                f'<image id="art" x="0" y="0" width="{W}" height="{H}" preserveAspectRatio="none" '
                f'xlink:href="data:image/png;base64,{b64}"/>'
            ),
        ]
        for i, (x0, x1, y) in enumerate(m.folds):
            out.append(
                f'<line id="fold{i}" class="fold" x1="{f(x0)}" y1="{f(y)}" x2="{f(x1)}" y2="{f(y)}" '
                f'stroke="{st.fold_color}" stroke-width="{f(st.fold_width_mm)}" stroke-dasharray="{f(FOLD_DASH_MM)},{f(FOLD_GAP_MM)}"/>'
            )
        count: dict = {}
        # labels, numbers, the back text and a token's text
        for t in m.text_items(self._fonts):
            i = count[t.kind] = count.get(t.kind, -1) + 1
            ident = {
                "label": "label",
                "number": "number",
                "backtext": "text",
                "tokentext": "tokentext",
            }[t.kind]
            tr = f' transform="rotate({f(t.rot)},{f(t.cx)},{f(t.cy)})"' if t.rot else ""
            weight = ' font-weight="bold"' if t.bold else ""
            family = quoteattr(self._fonts.svg_family(st.font))
            out.append(
                f'<text id="{ident}{i}" class="{t.kind}" x="{f(t.cx)}" y="{f(t.cy + TEXT_BASELINE_DROP * t.size_mm)}" '
                f'font-family={family} font-size="{f(t.size_mm)}"{weight} '
                f'text-anchor="middle" fill="{t.color}"{tr}>{escape(t.text)}</text>'
            )
        out.append(
            f'<path id="cut" d="{SvgFormat.path_d(m.cut)}" fill="none" '
            f'stroke="{st.cut_color if st.cut_line else "none"}" '
            f'stroke-width="{f(st.cut_width_mm)}" stroke-linejoin="round"/>'
        )
        out.append("</svg>")
        return "\n".join(out) + "\n"

    def write(self, m: Mini, path: Path) -> Path:
        """Write the SVG file of the miniature at ``path``."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.svg(m), encoding="utf-8")
        return path

    def write_copies(self, m: Mini, path: Path, copies: int = 1) -> list[Path]:
        """Write the SVG file of a miniature at ``path``; a numbered one gets a file per
        copy, each with its number: ``goblin-1.svg`` to ``goblin-6.svg`` (one copy:
        ``goblin-1.svg``)."""
        path = Path(path)
        if not m.numbered:
            return [self.write(m, path)]
        return [
            self.write(
                replace(m, number=i), path.with_name(f"{path.stem}-{i}{path.suffix}")
            )
            for i in range(1, max(1, copies) + 1)
        ]
