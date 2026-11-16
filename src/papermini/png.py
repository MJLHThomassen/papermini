"""PNG output: a whole printed piece (a mini or a token) as a picture, transparent around
it, for a virtual tabletop or to share.

The scale is set in pixels per grid square, so a Medium mini and a Medium token come out
at the size a virtual tabletop expects for one square, whatever the paper size; or as a
resolution in dpi, for a picture at the size the piece prints.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw

from . import fonts
from .mini import Mini

PX_PER_SQUARE = 256  # the default scale: pixels per grid square...
DPI = 300  # ...or, sized as printed, this resolution
SUPERSAMPLE = 2  # drawn this many times larger, then shrunk (smooth lines and text)


def _font(name: str, size_px: int, bold: bool):
    from .sheet import _font as sheet_font

    return sheet_font(max(1, size_px), serif=True, path=fonts.file_for(name, bold))


def piece_image(m: Mini, px_per_mm: float) -> Image.Image:
    """The piece as printed (its art, fold lines, text and cut line), RGBA,
    ``px_per_mm`` pixels per millimetre."""
    s = px_per_mm * SUPERSAMPLE
    W, H = max(1, round(m.width_mm * s)), max(1, round(m.height_mm * s))
    im = m.art.convert("RGBA").resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    st = m.style
    fold_w = max(1, round(st.fold_width_mm * s))
    for x0, x1, y in m.folds:  # dashed: 1.2 mm on, 0.8 mm off
        x = x0
        while x < x1:
            d.line(
                [(x * s, y * s), (min(x + 1.2, x1) * s, y * s)],
                fill=st.fold_color,
                width=fold_w,
            )
            x += 2.0
    for t in m.text_items():
        size = t.size_mm * s
        font = _font(st.font, round(size), t.bold)
        box = font.getbbox(t.text)
        r = int(max(box[2] - box[0], size) * 1.5) + 4  # room to turn it in
        layer = Image.new("RGBA", (2 * r, 2 * r), (0, 0, 0, 0))
        # centred on (cx, cy), the baseline 0.35 x the size below it (as in the SVG)
        ImageDraw.Draw(layer).text(
            (r, r + 0.35 * size), t.text, font=font, fill=t.color, anchor="ms"
        )
        if t.rot:
            layer = layer.rotate(-t.rot, resample=Image.BICUBIC, center=(r, r))
        im.alpha_composite(layer, (round(t.cx * s) - r, round(t.cy * s) - r))
    if st.cut_line:
        pts = [(x * s, y * s) for x, y in m.cut.flatten(16)]
        d.line(
            pts + pts[:1],
            fill=st.cut_color,
            width=max(1, round(st.cut_width_mm * s)),
            joint="curve",
        )
    return im.resize(
        (max(1, round(W / SUPERSAMPLE)), max(1, round(H / SUPERSAMPLE))), Image.LANCZOS
    )


def write_png(m: Mini, path: Path, px_per_mm: float) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    piece_image(m, px_per_mm).save(path, optimize=True)
    return path


def write_pngs(m: Mini, path: Path, px_per_mm: float, copies: int = 1) -> list[Path]:
    """The PNG of a piece at ``path``; a numbered one gets a file per copy, each with its
    number: ``goblin-1.png`` to ``goblin-6.png``."""
    path = Path(path)
    if not m.numbered:
        return [write_png(m, path, px_per_mm)]
    return [
        write_png(
            replace(m, number=i),
            path.with_name(f"{path.stem}-{i}{path.suffix}"),
            px_per_mm,
        )
        for i in range(1, max(1, copies) + 1)
    ]


def px_per_mm(px_per_square: float, grid_mm: float) -> float:
    """The PNG scale for ``px_per_square`` pixels per grid square of ``grid_mm``."""
    return px_per_square / grid_mm
