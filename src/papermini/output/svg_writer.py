from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path

import svg as svgpy

from ..pipeline.mini import Mini
from ..pipeline.style import FOLD_DASH_MM, FOLD_GAP_MM
from ..pipeline.text_item import TEXT_BASELINE_DROP
from ..support.font_library import FontLibrary
from .svg_format import SvgFormat

XLINK_NS = "http://www.w3.org/1999/xlink"
# the id of each kind of text, before its number
TEXT_IDS = {
    "label": "label",
    "number": "number",
    "backtext": "text",
    "tokentext": "tokentext",
}


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
        elements: list[svgpy.Element] = [
            svgpy.Title(text=svgpy.escape(m.label or m.name)),
            svgpy.Metadata(id="papermini", text=svgpy.escape(m.name)),
            svgpy.Image(
                id="art",
                x=0,
                y=0,
                width=W,
                height=H,
                preserveAspectRatio=svgpy.PreserveAspectRatio("none"),
                extra={"xlink:href": f"data:image/png;base64,{b64}"},
            ),
        ]
        elements += [
            svgpy.Line(
                id=f"fold{i}",
                class_=["fold"],
                x1=f(x0),
                y1=f(y),
                x2=f(x1),
                y2=f(y),
                stroke=st.fold_color,
                stroke_width=f(st.fold_width_mm),
                stroke_dasharray=[f(FOLD_DASH_MM), f(FOLD_GAP_MM)],
            )
            for i, (x0, x1, y) in enumerate(m.folds)
        ]
        elements += self._texts(m)
        elements.append(
            svgpy.Path(
                id="cut",
                d=SvgFormat.path_d(m.cut),
                fill="none",
                stroke=st.cut_color if st.cut_line else "none",
                stroke_width=f(st.cut_width_mm),
                stroke_linejoin="round",
            )
        )
        root = svgpy.SVG(
            width=svgpy.mm(W),
            height=svgpy.mm(H),
            viewBox=svgpy.ViewBoxSpec(0, 0, W, H),
            elements=elements,
            extra={"xmlns:xlink": XLINK_NS},
        )
        return SvgFormat.document(root)

    def _texts(self, m: Mini) -> list[svgpy.Element]:
        """The labels, numbers, back text and token text of the miniature."""
        f = SvgFormat.number
        family = SvgFormat.attribute(self._fonts.svg_family(m.style.font))
        count: dict[str, int] = {}
        texts: list[svgpy.Element] = []
        for t in m.text_items(self._fonts):
            i = count[t.kind] = count.get(t.kind, -1) + 1
            texts.append(
                svgpy.Text(
                    id=f"{TEXT_IDS[t.kind]}{i}",
                    class_=[t.kind],
                    x=f(t.cx),
                    y=f(t.cy + TEXT_BASELINE_DROP * t.size_mm),
                    font_family=family,
                    font_size=f(t.size_mm),
                    font_weight="bold" if t.bold else None,
                    text_anchor="middle",
                    fill=t.color,
                    transform=[svgpy.Rotate(f(t.rot), f(t.cx), f(t.cy))]
                    if t.rot
                    else None,
                    text=svgpy.escape(t.text),
                )
            )
        return texts

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
