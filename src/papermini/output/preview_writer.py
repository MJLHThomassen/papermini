from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from ..support.font_library import FontLibrary
from .sheet_layout import (
    BAR_ABOVE_MM,
    BAR_MM,
    BAR_WIDTH_MM,
    INSTRUCTIONS_LINE_MM,
    TITLE,
    SheetLayout,
)


class PreviewWriter:
    """Writes the pages of a sheet as PNG pictures for a quick look, the pieces' text in
    their fonts from ``fonts``."""

    def __init__(self, fonts: FontLibrary):
        self._fonts = fonts

    def write(
        self, layout: SheetLayout, out: Path, dpi: int = 100, title: str = TITLE
    ) -> list[Path]:
        """Write one PNG per page: ``out``, then ``out-2.png`` and so on."""
        fonts = self._fonts
        out = Path(out)
        s = dpi / 25.4
        pw, ph = layout.paper
        margin_mm, hx = layout.margin_mm, layout.header_x
        paths = []
        for page in range(layout.pages):
            im = Image.new("RGB", (round(pw * s), round(ph * s)), "white")
            d = ImageDraw.Draw(im)
            for x, y, w, h in layout.mark_rects():
                d.rectangle([x * s, y * s, (x + w) * s, (y + h) * s], fill="black")
            d.text(
                (hx * s, (margin_mm) * s),
                title,
                fill="black",
                font=fonts.image_font(round(4 * s)),
            )
            for i, line in enumerate(layout.instructions()):
                d.text(
                    (hx * s, (margin_mm + 6 + INSTRUCTIONS_LINE_MM * i) * s),
                    line,
                    fill="black",
                    font=fonts.image_font(round(2.6 * s)),
                )
            cy = (margin_mm + layout.header_mm - BAR_ABOVE_MM) * s
            d.line(
                [(hx * s, cy), ((hx + BAR_MM) * s, cy)],
                fill="black",
                width=max(1, round(BAR_WIDTH_MM * s)),
            )
            for p in layout.placements:
                if p.page != page:
                    continue
                m = p.mini
                ox, oy = p.x * s, p.y * s
                art = m.art.resize(
                    (max(1, round(m.width_mm * s)), max(1, round(m.height_mm * s))),
                    Image.Resampling.LANCZOS,
                )
                im.paste(art, (round(ox), round(oy)), art)
                for x0, x1, y in m.folds:
                    d.line(
                        [(ox + x0 * s, oy + y * s), (ox + x1 * s, oy + y * s)],
                        fill=m.style.fold_color,
                    )
                for t in m.text_items(fonts):
                    if t.rot:  # (a quick look: upright text only)
                        continue
                    d.text(
                        (ox + t.cx * s, oy + t.cy * s),
                        t.text,
                        fill=t.color,
                        font=fonts.image_font(
                            max(6, round(t.size_mm * s)), m.style.font, t.bold
                        ),
                        anchor="mm",
                    )
                if not layout.machine and m.style.cut_line:
                    pts = [(ox + x * s, oy + y * s) for x, y in m.cut.flatten(6)]
                    d.line(
                        pts + pts[:1],
                        fill=m.style.cut_color,
                        width=max(1, round(m.style.cut_width_mm * s)),
                    )
            path = (
                out
                if page == 0
                else out.with_name(f"{out.stem}-{page + 1}{out.suffix}")
            )
            im.save(path)
            paths.append(path)
        return paths
