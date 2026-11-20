from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from ..pipeline.mini import Mini
from ..pipeline.style import Style
from ..pipeline.text_item import TEXT_BASELINE_DROP, TextItem
from ..support.font_library import FontLibrary
from .svg_format import NUMBER, SvgFormat
from .svg_writer import SVG_NS, XLINK_NS


class SvgReader:
    """Reads the SVG files of miniatures that ``SvgWriter`` writes, to put them on a
    sheet."""

    def read(self, path: Path) -> Mini:
        """Load a papermini SVG."""
        path = Path(path)
        root = ET.parse(path).getroot()
        ns = {"s": SVG_NS}
        W, H = self._mm(root.get("width")), self._mm(root.get("height"))
        vb = [
            float(v)
            for v in re.split(r"[\s,]+", root.get("viewBox", f"0 0 {W} {H}").strip())
        ]
        sx, sy = W / vb[2], H / vb[3]  # viewBox units -> mm (1 for papermini files)
        if abs(sx - sy) > 1e-6:
            raise ValueError(
                f"{path.name}: non-uniform viewBox scaling is not supported"
            )

        def el(tag, id_=None, cls=None):
            for e in root.iter(f"{{{SVG_NS}}}{tag}"):
                if (
                    id_
                    and e.get("id") == id_
                    or cls
                    and cls in (e.get("class") or "").split()
                ):
                    yield e

        img = next(el("image", id_="art"), None)
        if img is None:
            img = root.find("s:image", ns)
        cut = next(el("path", id_="cut"), None)
        if img is None or cut is None:
            raise ValueError(
                f"{path.name} is not a papermini SVG (needs image#art and path#cut)"
            )
        href = img.get(f"{{{XLINK_NS}}}href") or img.get("href") or ""
        if not href.startswith("data:image"):
            raise ValueError(f"{path.name}: artwork must be an embedded data: URI")
        art = Image.open(io.BytesIO(base64.b64decode(href.split(",", 1)[1]))).convert(
            "RGBA"
        )

        style = Style()
        stroke = cut.get("stroke", style.cut_color)
        if stroke == "none":  # (a piece printed without its cut line)
            style.cut_line = False
        else:
            style.cut_color = stroke
        style.cut_width_mm = float(cut.get("stroke-width", style.cut_width_mm)) * sx
        folds = []
        for ln in el("line", cls="fold"):
            style.fold_color = ln.get("stroke", style.fold_color)
            style.fold_width_mm = (
                float(ln.get("stroke-width", style.fold_width_mm)) * sx
            )
            folds.append(
                (
                    float(ln.get("x1")) * sx,
                    float(ln.get("x2")) * sx,
                    float(ln.get("y1")) * sx,
                )
            )
        first = next(iter(root.iter(f"{{{SVG_NS}}}text")), None)
        if first is not None:  # (one font for all of a piece's text)
            style.font = FontLibrary.from_svg_family(first.get("font-family", ""))
        labels, text, size = [], "", style.label_size_mm
        for t in el("text", cls="label"):
            text = "".join(t.itertext())
            size = float(t.get("font-size", size)) * sx
            style.label_color = t.get("fill", style.label_color)
            rot = 0.0
            m = re.match(rf"\s*rotate\(\s*({NUMBER})", t.get("transform") or "")
            if m:
                rot = float(m.group(1))
            cx = float(t.get("x")) * sx
            cy = float(t.get("y")) * sx - TEXT_BASELINE_DROP * size
            labels.append((cx, cy, rot))
        texts = []
        for t in el("text", cls="backtext"):
            size_t = float(t.get("font-size", 3.4)) * sx
            style.back_text_color = t.get("fill", style.back_text_color)
            m = re.match(rf"\s*rotate\(\s*({NUMBER})", t.get("transform") or "")
            texts.append(
                TextItem(
                    "backtext",
                    "".join(t.itertext()),
                    float(t.get("x")) * sx,
                    float(t.get("y")) * sx - TEXT_BASELINE_DROP * size_t,
                    float(m.group(1)) if m else 0.0,
                    size_t,
                    style.back_text_color,
                )
            )
        numbers = []  # (written into the file: kept as they are, also a token's text)
        for t in [*el("text", cls="number"), *el("text", cls="tokentext")]:
            size_t = float(t.get("font-size", 3.4)) * sx
            m = re.match(rf"\s*rotate\(\s*({NUMBER})", t.get("transform") or "")
            numbers.append(
                TextItem(
                    t.get("class"),
                    "".join(t.itertext()),
                    float(t.get("x")) * sx,
                    float(t.get("y")) * sx - TEXT_BASELINE_DROP * size_t,
                    float(m.group(1)) if m else 0.0,
                    size_t,
                    t.get("fill", style.label_color),
                    t.get("font-weight") == "bold",
                )
            )
        return Mini(
            name=path.stem,
            width_mm=W,
            height_mm=H,
            art=art,
            texts=texts,
            extra=numbers,
            cut=SvgFormat.parse_path_d(cut.get("d")).transformed(sx),
            folds=folds,
            labels=labels,
            label=text,
            label_size_mm=size,
            style=style,
        )

    @staticmethod
    def _mm(v: str | None) -> float:
        """A length in an SVG file, in mm. A length without a unit is in pixels."""
        m = re.fullmatch(rf"\s*({NUMBER})\s*(mm|cm|in|px|pt)?\s*", v or "")
        if not m:
            raise ValueError(f"cannot read length {v!r}")
        n, unit = float(m.group(1)), m.group(2) or "px"
        return (
            n * {"mm": 1, "cm": 10, "in": 25.4, "pt": 25.4 / 72, "px": 25.4 / 96}[unit]
        )
