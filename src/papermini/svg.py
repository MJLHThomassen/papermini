"""SVG output (mm units) and reading papermini SVGs back for the print sheet."""

from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List
from xml.sax.saxutils import escape, quoteattr

import numpy as np
from PIL import Image

from .geometry import CutPath
from .mini import Mini, Style

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


def _f(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def path_d(p: CutPath) -> str:
    pts = p.points
    parts = [f"M{_f(pts[0, 0])},{_f(pts[0, 1])}"]
    n = len(pts)
    for i in range(n):
        q = pts[(i + 1) % n]
        if p.controls is None:
            if i < n - 1:
                parts.append(f"L{_f(q[0])},{_f(q[1])}")
        else:
            c1, c2 = p.controls[i]
            parts.append(f"C{_f(c1[0])},{_f(c1[1])} {_f(c2[0])},{_f(c2[1])} {_f(q[0])},{_f(q[1])}")
    return " ".join(parts) + " Z"


def to_svg(m: Mini) -> str:
    st = m.style
    b64 = base64.b64encode(m.png_bytes()).decode("ascii")
    W, H = _f(m.width_mm), _f(m.height_mm)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="{SVG_NS}" xmlns:xlink="{XLINK_NS}" '
        f'width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
        f"<title>{escape(m.label or m.name)}</title>",
        f'<metadata id="papermini">{escape(m.name)}</metadata>',
        f'<image id="art" x="0" y="0" width="{W}" height="{H}" preserveAspectRatio="none" '
        f'xlink:href="data:image/png;base64,{b64}"/>',
    ]
    for i, (x0, x1, y) in enumerate(m.folds):
        out.append(
            f'<line id="fold{i}" class="fold" x1="{_f(x0)}" y1="{_f(y)}" x2="{_f(x1)}" y2="{_f(y)}" '
            f'stroke="{st.fold_color}" stroke-width="{_f(st.fold_width_mm)}" stroke-dasharray="1.2,0.8"/>'
        )
    if m.label:
        for i, (cx, cy, rot) in enumerate(m.labels):
            tr = f' transform="rotate({_f(rot)},{_f(cx)},{_f(cy)})"' if rot else ""
            out.append(
                f'<text id="label{i}" class="label" x="{_f(cx)}" y="{_f(cy + 0.35 * m.label_size_mm)}" '
                f'font-family={quoteattr(st.font_family)} font-size="{_f(m.label_size_mm)}" '
                f'text-anchor="middle" fill="{st.label_color}"{tr}>{escape(m.label)}</text>'
            )
    for i, (text, cx, cy, rot, size) in enumerate(m.texts):
        tr = f' transform="rotate({_f(rot)},{_f(cx)},{_f(cy)})"' if rot else ""
        out.append(
            f'<text id="text{i}" class="backtext" x="{_f(cx)}" y="{_f(cy + 0.35 * size)}" '
            f'font-family={quoteattr(st.font_family)} font-size="{_f(size)}" '
            f'text-anchor="middle" fill="{st.back_text_color}"{tr}>{escape(text)}</text>'
        )
    out.append(
        f'<path id="cut" d="{path_d(m.cut)}" fill="none" stroke="{st.cut_color}" '
        f'stroke-width="{_f(st.cut_width_mm)}" stroke-linejoin="round"/>'
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def write_svg(m: Mini, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_svg(m), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- reading

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"


def parse_path_d(d: str) -> CutPath:
    """Parse the absolute M/L/C/Z paths written by :func:`path_d`."""
    tokens = re.findall(rf"[MLCZmlcz]|{_NUM}", d)
    pts: List[List[float]] = []
    ctrls: List[List[List[float]]] = []
    has_curve = False
    i, cmd = 0, None
    while i < len(tokens):
        t = tokens[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                break
            continue
        if cmd in ("m", "l", "c"):
            raise ValueError("relative path commands are not supported; use a papermini SVG")
        if cmd in ("M", "L"):
            p = [float(tokens[i]), float(tokens[i + 1])]
            if pts:
                ctrls.append([pts[-1], p])  # straight: handles on the endpoints
            pts.append(p)
            i += 2
        elif cmd == "C":
            v = [float(x) for x in tokens[i:i + 6]]
            ctrls.append([v[0:2], v[2:4]])
            pts.append(v[4:6])
            has_curve = True
            i += 6
        else:
            raise ValueError(f"unexpected path data near {t!r}")
    P = np.array(pts, float)
    if len(P) > 1 and np.allclose(P[0], P[-1]):
        P = P[:-1]  # closing segment came back to the start
    elif ctrls:
        ctrls.append([pts[-1], pts[0]])  # implicit closing line
    if not has_curve:
        return CutPath(P)
    return CutPath(P, np.array(ctrls[: len(P)], float))


def _mm(v: str) -> float:
    m = re.fullmatch(rf"\s*({_NUM})\s*(mm|cm|in|px|pt)?\s*", v or "")
    if not m:
        raise ValueError(f"cannot read length {v!r}")
    n, unit = float(m.group(1)), m.group(2) or "px"
    return n * {"mm": 1, "cm": 10, "in": 25.4, "pt": 25.4 / 72, "px": 25.4 / 96}[unit]


def read_svg(path: Path) -> Mini:
    """Load a papermini SVG (as written by :func:`write_svg`)."""
    path = Path(path)
    root = ET.parse(path).getroot()
    ns = {"s": SVG_NS}
    W, H = _mm(root.get("width")), _mm(root.get("height"))
    vb = [float(v) for v in re.split(r"[\s,]+", root.get("viewBox", f"0 0 {W} {H}").strip())]
    sx, sy = W / vb[2], H / vb[3]  # viewBox units -> mm (1 for papermini files)
    if abs(sx - sy) > 1e-6:
        raise ValueError(f"{path.name}: non-uniform viewBox scaling is not supported")

    def el(tag, id_=None, cls=None):
        for e in root.iter(f"{{{SVG_NS}}}{tag}"):
            if id_ and e.get("id") == id_:
                yield e
            elif cls and cls in (e.get("class") or "").split():
                yield e

    img = next(el("image", id_="art"), None)
    if img is None:
        img = root.find("s:image", ns)
    cut = next(el("path", id_="cut"), None)
    if img is None or cut is None:
        raise ValueError(f"{path.name} is not a papermini SVG (needs image#art and path#cut)")
    href = img.get(f"{{{XLINK_NS}}}href") or img.get("href") or ""
    if not href.startswith("data:image"):
        raise ValueError(f"{path.name}: artwork must be an embedded data: URI")
    art = Image.open(io.BytesIO(base64.b64decode(href.split(",", 1)[1]))).convert("RGBA")

    style = Style()
    style.cut_color = cut.get("stroke", style.cut_color)
    style.cut_width_mm = float(cut.get("stroke-width", style.cut_width_mm)) * sx
    folds = []
    for ln in el("line", cls="fold"):
        style.fold_color = ln.get("stroke", style.fold_color)
        style.fold_width_mm = float(ln.get("stroke-width", style.fold_width_mm)) * sx
        folds.append((float(ln.get("x1")) * sx, float(ln.get("x2")) * sx, float(ln.get("y1")) * sx))
    labels, text, size = [], "", style.label_size_mm
    for t in el("text", cls="label"):
        text = "".join(t.itertext())
        size = float(t.get("font-size", size)) * sx
        style.label_color = t.get("fill", style.label_color)
        rot = 0.0
        m = re.match(rf"\s*rotate\(\s*({_NUM})", t.get("transform") or "")
        if m:
            rot = float(m.group(1))
        cx = float(t.get("x")) * sx
        cy = float(t.get("y")) * sx - 0.35 * size
        labels.append((cx, cy, rot))
    texts = []
    for t in el("text", cls="backtext"):
        size_t = float(t.get("font-size", 3.4)) * sx
        style.back_text_color = t.get("fill", style.back_text_color)
        m = re.match(rf"\s*rotate\(\s*({_NUM})", t.get("transform") or "")
        texts.append(("".join(t.itertext()), float(t.get("x")) * sx,
                      float(t.get("y")) * sx - 0.35 * size_t, float(m.group(1)) if m else 0.0, size_t))
    return Mini(
        name=path.stem, width_mm=W, height_mm=H, art=art, texts=texts,
        cut=parse_path_d(cut.get("d")).transformed(sx),
        folds=folds, labels=labels, label=text, label_size_mm=size, style=style,
    )
