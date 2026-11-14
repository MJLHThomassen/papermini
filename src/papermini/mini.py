"""One paper miniature: image -> mask -> layout -> cut path -> mm-unit result."""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps

from . import cache, fonts
from . import geometry as geo
from . import adjust as adj_mod
from .segment import DEFAULT_MODEL, check_cancel, compute_mask, has_alpha, parse_crop


@dataclass
class Style:
    cut_color: str = "#000000"
    cut_width_mm: float = 0.3
    fold_color: str = "#666666"
    fold_width_mm: float = 0.25
    label_color: str = "#2f5597"
    back_text_color: str = "#2f5597"
    label_size_mm: float = 3.4
    font: str = "Times"  # all of the piece's text (see fonts.py)


TAB_SHOWS = ("label", "number", "label_number")  # what a tab shows
NUMBER_PLACEHOLDER = "#"  # a figure's number where no copy number is known (the preview)


@dataclass
class TextItem:
    """One piece of text on a miniature, as every output draws it: centred on (cx, cy) mm,
    rotated ``rot`` degrees, ``size_mm`` high. ``kind``: "label", "number" or "backtext"."""

    kind: str
    text: str
    cx: float
    cy: float
    rot: float
    size_mm: float
    color: str
    bold: bool = False


def fit_number_size(text: str, max_w: float, max_h: float, font: str = fonts.DEFAULT) -> float:
    """The largest bold font size at which ``text`` fits ``max_w`` x ``max_h`` (mm)."""
    w = fonts.text_width(text, font, 1.0, bold=True)
    return max(0.0, min(max_h, max_w / w if w else max_h))


@dataclass
class Mini:
    """A finished miniature in millimetres (origin top-left, y down)."""

    name: str
    width_mm: float
    height_mm: float
    art: Image.Image                         # RGBA, covers 0..width_mm x 0..height_mm
    cut: geo.CutPath                          # in mm
    folds: List[Tuple[float, float, float]] = field(default_factory=list)   # x0, x1, y
    labels: List[Tuple[float, float, float]] = field(default_factory=list)  # cx, cy, rot
    label: str = ""
    label_size_mm: float = 3.4
    style: Style = field(default_factory=Style)
    # extra text lines: (text, cx, cy, rotation, size_mm) - e.g. the back of a double-sided mini
    texts: List[Tuple[str, float, float, float, float]] = field(default_factory=list)
    figure_height_mm: float = 0.0            # measured height of the drawing (one side)
    figure_width_mm: float = 0.0             # measured width of the drawing
    aspect: float = 1.0                      # width / height of the drawing in the image
    tab_overlap_used: bool = True            # False: the tab overlap changed nothing here
    tab_joint_mm: float = 0.0                # paper joining tab and figure (0: no tab)
    tab_width_mm: float = 0.0
    close_px: int = 0                        # closing radius used (the automatic one if unset)
    # the cut line and folds in pixels of the source image (front side), to show
    # on the original artwork what is kept and what is cut away
    source_cut: Optional[geo.CutPath] = None
    source_folds: List[Tuple[float, float, float]] = field(default_factory=list)
    source_top: float = 0.0  # above this row the piece is the double-sided back, not the image
    # what background removal found (outer edges and holes), in source image pixels
    source_outline: List[np.ndarray] = field(default_factory=list)
    # how the figure was found: "alpha" (the image's own transparency), "mask" (a mask
    # image file) or the model that ran; for model "auto", the one it picked
    method: str = ""
    # numbers: what each tab shows (one per entry of ``labels``: "label", "number" or
    # "label_number"), the room for text on a tab (w, h mm), where the back side's number
    # goes (cx, cy, w, h mm), and this copy's number (None: the placeholder)
    tab_shows: List[str] = field(default_factory=list)
    tab_room: Tuple[float, float] = (0.0, 0.0)
    number_box: Optional[Tuple[float, float, float, float]] = None
    number: Optional[int] = None
    # text read from an SVG file, drawn as it is (numbers already written into it)
    extra: List[TextItem] = field(default_factory=list)

    @property
    def numbered(self) -> bool:
        """Whether the miniature shows its copy number anywhere."""
        return self.number_box is not None or any(s != "label" for s in self.tab_shows)

    def text_items(self) -> List[TextItem]:
        """Every text on the miniature: the tab labels and numbers, the back text and the
        back side's number. On a tab showing both, the number goes above the label (on
        the fold's side), as large as fits."""
        st = self.style
        num = NUMBER_PLACEHOLDER if self.number is None else str(self.number)
        room_w, room_h = self.tab_room
        items: List[TextItem] = []
        shows = self.tab_shows or ["label"] * len(self.labels)
        for (cx, cy, rot), what in zip(self.labels, shows):
            label = self.label if what in ("label", "label_number") else ""
            number = what in ("number", "label_number")
            if label and not number:
                items.append(TextItem("label", label, cx, cy, rot, self.label_size_mm,
                                      st.label_color))
            elif number and not label:
                items.append(TextItem("number", num, cx, cy, rot,
                                      fit_number_size(num, room_w, room_h, st.font),
                                      st.label_color, True))
            elif number:
                ls, gap = self.label_size_mm, 0.15 * self.label_size_mm
                ns = max(ls, fit_number_size(num, room_w, room_h - ls - gap, st.font))
                block = ns + gap + ls
                up = -1.0 if rot == 0 else 1.0  # towards the fold (the back tab is upside down)
                items.append(TextItem("number", num, cx, cy + up * (block - ns) / 2, rot, ns,
                                      st.label_color, True))
                items.append(TextItem("label", label, cx, cy - up * (block - ls) / 2, rot, ls,
                                      st.label_color))
        items += [TextItem("backtext", text, cx, cy, rot, size, st.back_text_color)
                  for text, cx, cy, rot, size in self.texts]
        if self.number_box is not None:
            cx, cy, w, h = self.number_box
            items.append(TextItem("number", num, cx, cy, 180.0,
                                  fit_number_size(num, w, h, st.font), st.back_text_color, True))
        return items + list(self.extra)

    def png_bytes(self) -> bytes:
        buf = io.BytesIO()
        self.art.save(buf, "PNG", optimize=True)
        return buf.getvalue()


def load_image(path: Path) -> Tuple[Image.Image, bytes]:
    data = Path(path).read_bytes()
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    return im, data


def _load_for_pipeline(path: Path):
    """(PIL image, file bytes, pixels, has transparency) for the caches.

    Pixels are RGB, or for images with transparency premultiplied RGBA: never
    flattened onto white, so a cut-out's soft edge blends into the margin color
    instead of leaving a white fringe (and scales without bleeding).
    """
    im, data = load_image(path)
    im.load()
    transparent = has_alpha(im)
    if transparent:
        a = np.asarray(im.convert("RGBA")).astype(np.float32)
        a[..., :3] *= a[..., 3:4] / 255.0
        px = np.clip(a + 0.5, 0, 255).astype(np.uint8)
    else:
        px = np.asarray(im.convert("RGB"))
    return im, data, _frozen(px), transparent


def _frozen(a: np.ndarray) -> np.ndarray:
    """Read-only array, so a cached stage can never be modified by accident."""
    a = np.asarray(a)
    if a.flags.writeable:
        a = a.copy() if not a.flags.owndata else a
        a.setflags(write=False)
    return a


def fit_label_size(text: str, max_width_mm: float, size_mm: float,
                   font: str = fonts.DEFAULT) -> float:
    """Shrink the label font so the text fits ``max_width_mm``."""
    if not text:
        return size_mm
    w = fonts.text_width(text, font, size_mm)
    return size_mm if w <= max_width_mm else size_mm * max_width_mm / w


def fit_text_block(text: str, max_w: float, max_h: float, max_size: float,
                   max_lines: int = 4, font: str = fonts.DEFAULT) -> Tuple[float, List[str]]:
    """Largest font size (and line split) that fits ``text`` into max_w x max_h.

    Tries 1..max_lines lines; words are balanced over the lines. Line pitch is
    1.15 x the font size. Units are whatever max_w/max_h use (mm here).
    """
    words = text.split()
    if not words:
        return 0.0, []
    width = lambda t: fonts.text_width(t, font, 1.0)  # noqa: E731 - width at size 1
    best = (0.0, [text])
    for n in range(1, min(max_lines, len(words)) + 1):
        target = width(" ".join(words)) / n
        lines, cur = [], []
        for w in words:
            if cur and width(" ".join(cur + [w])) > target * 1.08 and len(lines) < n - 1:
                lines.append(" ".join(cur))
                cur = []
            cur.append(w)
        lines.append(" ".join(cur))
        size = min(max_size, max_h / (1.15 * len(lines)),
                   min(max_w / max(width(t), 1e-6) for t in lines))
        if size > best[0] * 1.15:  # prefer fewer lines unless clearly bigger
            best = (size, lines)
    return best


def make_mini(
    image_path: Path,
    prm: geo.Params,
    *,
    label: Optional[str] = None,
    back_text: Optional[str] = None,
    tab_front: str = "label",
    tab_back: str = "label",
    threshold: int = 40,
    close_px: Optional[int] = None,
    min_area: int = 1000,
    crop=None,
    model: str = "auto",
    mask_path: Optional[Path] = None,
    dpi: int = 300,
    simplify_mm: float = 0.15,
    smooth_path: bool = True,
    bleed_mm: float = 0.0,
    adjust: Optional[adj_mod.Adjustments] = None,
    use_cache: bool = True,
    style: Optional[Style] = None,
    debug_dir: Optional[Path] = None,
    log=print,
    on_stage=None,
) -> Mini:
    """Build one miniature. ``on_stage(name, data)``, if given, hears about progress:
    ``("segment", model)`` just before a model runs (it may take a while) and
    ``("outline", (contours, close_px))`` once the figure is found, before the layout."""
    image_path = Path(image_path)
    stage = on_stage or (lambda *_: None)
    style = style or Style()
    if not fonts.resolve(style.font)[1]:
        log(f"  {image_path.name}: note: the font {style.font} is not on this computer: "
            f"printing in {fonts.DEFAULT}")
        style = replace(style, font=fonts.DEFAULT)
    fkey = cache.file_key(image_path)
    im, data, rgb, transparent = cache.images.get_or_make(fkey, lambda: _load_for_pipeline(image_path))
    W, H = im.size
    box = parse_crop(crop, W, H)

    # 1. raw mask - cached per image, mask source and crop (the AI model also on disk)
    if mask_path is not None:
        source: tuple = ("mask",) + cache.file_key(mask_path)
        method = "mask"
    else:
        if model == "auto":
            model = "alpha" if transparent else DEFAULT_MODEL
            if model == "alpha":
                log(f"  {image_path.name}: has transparency, using its alpha channel as mask")
        source = ("model", model)
        method = model
        if model.lower().endswith(".onnx") and Path(model).exists():
            source += cache.file_key(model)
    raw_key = (fkey, source, box)
    raw = cache.raw_masks.get(raw_key) if use_cache else None
    if raw is None:
        if mask_path is not None:
            raw = np.asarray(Image.open(mask_path).convert("L").resize((W, H), Image.BILINEAR))
            if box:
                x0, y0, x1, y1 = box
                keep = np.zeros_like(raw)
                keep[y0:y1, x0:x1] = raw[y0:y1, x0:x1]
                raw = keep
        else:
            if model != "alpha":
                stage("segment", model)
            raw = compute_mask(im, model, box, use_cache=use_cache, image_bytes=data)
        raw = cache.raw_masks.put(raw_key, _frozen(raw))

    check_cancel()

    # 2. clean-up
    clean_key = (raw_key, threshold, close_px, prm.keep_all, min_area if prm.keep_all else None)
    if debug_dir:
        stages: Optional[Dict[str, np.ndarray]] = {"0_raw": raw}
        clean = geo.clean_mask(raw, threshold, close_px, prm.keep_all, min_area, stages)
    else:
        stages = None
        clean = cache.clean_masks.get_or_make(clean_key, lambda: _frozen(
            geo.clean_mask(raw, threshold, close_px, prm.keep_all, min_area)))

    close_used = geo.default_close_px(raw.shape[1], raw.shape[0]) if close_px is None else close_px
    contours = geo.outline(clean)
    stage("outline", (contours, close_used))

    # 2b. size (by height, by width, or both: stretched sideways), then a bounded
    # working resolution for that size
    bx0, by0, bx1, by1 = geo.bbox(clean)
    bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
    height_mm, stretch = geo.figure_size(bw, bh, prm.height_mm, prm.width_mm)
    prm = replace(prm, height_mm=height_mm, width_mm=None)

    def _work():
        c, r = (clean, rgb) if stretch == 1 else geo.stretch_x(clean, rgb, stretch)
        return tuple(_frozen(a) for a in geo.limit_resolution(c, r, height_mm, prm.max_px_per_mm))

    work_key = (clean_key, height_mm, stretch, prm.max_px_per_mm)
    clean, rgb = _work() if debug_dir else cache.working.get_or_make(work_key, _work)

    # 2c. color adjustments of the picture, at the working size (cheap there); the mask
    # and outline above never see them, so a slider never runs the model again
    adj = adjust or adj_mod.Adjustments()
    if not adj.is_identity():
        rgb = (_frozen(adj_mod.apply(rgb, adj)) if debug_dir else cache.adjusted.get_or_make(
            (work_key, adj), lambda: _frozen(adj_mod.apply(rgb, adj))))

    # 3+4. margin, tab and vector cut line - cached, so cosmetic changes (label,
    # colors, line width, dpi) only redo the cheap finishing below
    def _layout():
        lay = geo.build_layout(clean, rgb, prm)
        return lay, geo.trace_cut(lay.cut, lay.px_per_mm, simplify_mm, smooth_path,
                                  lay.tab_circles)

    layout_key = (work_key, adj, tuple(sorted(asdict(prm).items())), simplify_mm, smooth_path)
    lay, path_px = _layout() if debug_dir else cache.layouts.get_or_make(layout_key, _layout)
    pxmm = lay.px_per_mm
    check_cancel()

    # the artwork alpha is the rasterised path, so picture and cut line match exactly
    alpha = geo.rasterize(path_px, lay.cut.shape)

    # room around the cut line: half the stroke, or the bleed (the canvas keeps 6 mm)
    bleed_mm = min(max(0.0, bleed_mm), 5.0)
    pad = max(style.cut_width_mm / 2 + 0.3, bleed_mm + 0.2 if bleed_mm else 0.0)
    ex0, ey0, ex1, ey1 = path_px.extent()
    X0 = max(0, int(np.floor(ex0 - pad * pxmm)))
    Y0 = max(0, int(np.floor(ey0 - pad * pxmm)))
    X1 = int(np.ceil(ex1 + pad * pxmm))
    Y1 = int(np.ceil(ey1 + pad * pxmm))
    rgb_c, alpha_c = lay.rgb[Y0:Y1, X0:X1], alpha[Y0:Y1, X0:X1]
    if bleed_mm:
        rgb_c, alpha_c = geo.add_bleed(rgb_c, alpha_c, bleed_mm * pxmm)
    art = np.dstack([rgb_c, alpha_c])
    w_mm, h_mm = (X1 - X0) / pxmm, (Y1 - Y0) / pxmm
    size = (max(1, round(w_mm / 25.4 * dpi)), max(1, round(h_mm / 25.4 * dpi)))
    art_im = Image.fromarray(art, "RGBA").resize(size, Image.LANCZOS)

    s = 1.0 / pxmm
    label = image_path.stem if label is None else label
    max_w = lay.label_max_w_px * s if prm.tab else w_mm
    mini = Mini(
        name=image_path.stem,
        width_mm=w_mm,
        height_mm=h_mm,
        art=art_im,
        cut=path_px.transformed(s, X0, Y0),
        folds=[((a - X0) * s, (b - X0) * s, (y - Y0) * s) for a, b, y in lay.folds],
        labels=[((x - X0) * s, (y - Y0) * s, r) for x, y, r in lay.labels] if prm.tab else [],
        label=label,
        label_size_mm=fit_label_size(label, max_w, min(style.label_size_mm,
                                                        lay.label_max_h_px * s or style.label_size_mm),
                                     style.font),
        style=style,
        figure_height_mm=lay.figure_height_px * s,
        figure_width_mm=height_mm * bw * stretch / bh,
        aspect=bw / bh,
        source_outline=contours,
        method=method,
        tab_overlap_used=lay.tab_overlap_used or not prm.tab or prm.tab_overlap_mm == 0,
        tab_joint_mm=lay.tab_joint_px * s if prm.tab else 0.0,
        tab_width_mm=lay.tab_width_px * s if prm.tab else 0.0,
        close_px=close_used,
        # (the front tab's label is upright, the back tab's upside down)
        tab_shows=[tab_front if r == 0 else tab_back for _, _, r in lay.labels] if prm.tab else [],
        tab_room=(max_w, lay.label_max_h_px * s) if prm.tab else (0.0, 0.0),
    )
    if lay.back_box is not None:
        bcx, bcy, bw, bh = lay.back_box
        bcx, bcy, bw, bh = (bcx - X0) * s, (bcy - Y0) * s, bw * s, bh * s
        if prm.back in ("number", "text_number"):
            # the number above the text: the back half is upside down on the sheet, so its
            # top is further down the sheet
            nh = bh if prm.back == "number" else 0.45 * bh
            mini.number_box = (bcx, bcy + (bh - nh) / 2, bw, nh)
            bcy, bh = bcy - nh / 2, bh - nh
        if prm.back in ("text", "text_number"):
            text = back_text if back_text else (label or image_path.stem)
            size, lines = fit_text_block(text, bw, bh, max_size=10.0, font=style.font)
            pitch = 1.15 * size
            for i, line in enumerate(lines):
                # the back half is upside down on the sheet: rotate 180 and reverse line order
                off = ((len(lines) - 1) / 2 - i) * pitch
                mini.texts.append((line, bcx, bcy + off, 180.0, size))

    if prm.tab and not lay.tab_overlap_used and prm.tab_overlap_mm != geo.Params().tab_overlap_mm:
        log(f"  {image_path.name}: note: the tab overlap has no effect here - the figure's "
            "bottom is wider than the tab (it only matters for narrow feet or tails)")
    log(f"  {image_path.name}: figure {lay.figure_height_px * s:.1f} mm high, "
        f"piece {w_mm:.1f} x {h_mm:.1f} mm, cut line {len(path_px.points)} nodes")

    # canvas -> working image (lay.src) -> source image (the working downscale)
    sx, sy, dx, dy = lay.src
    k = np.array([sx * W / rgb.shape[1], sy * H / rgb.shape[0]])
    d = np.array([dx, dy])
    mini.source_cut = geo.CutPath((path_px.points - d) * k, None if path_px.controls is None
                                  else (path_px.controls - d) * k)
    mini.source_folds = [((a - dx) * k[0], (b - dx) * k[0], (y - dy) * k[1])
                         for a, b, y in lay.folds]
    if prm.double_sided:
        mini.source_top = max(0.0, (lay.front_top - dy) * k[1])
    if debug_dir is not None:
        write_debug(Path(debug_dir), image_path.stem, stages, lay, path_px)
    return mini


def write_debug(out: Path, stem: str, stages, lay: geo.Layout, path_px: geo.CutPath) -> None:
    """Intermediate masks plus a red-overlay preview (what gets cut away is red)."""
    out.mkdir(parents=True, exist_ok=True)
    for name, m in (stages or {}).items():
        cv2.imwrite(str(out / f"{stem}_{name}.png"), m)
    cv2.imwrite(str(out / f"{stem}_5_cut.png"), lay.cut)
    over = overlay_image(lay, path_px)
    cv2.imwrite(str(out / f"{stem}_overlay.png"), cv2.cvtColor(over, cv2.COLOR_RGB2BGR))


def overlay_image(lay: geo.Layout, path_px: geo.CutPath) -> np.ndarray:
    """RGB preview: red = cut away, light blue = white margin, black = cut line."""
    rgb = lay.rgb
    outside = (lay.cut == 0)[..., None]
    margin = ((lay.cut > 0) & (lay.figure == 0))[..., None]
    red = cv2.addWeighted(rgb, 0.45, np.full_like(rgb, (255, 60, 60)), 0.55, 0)
    blue = cv2.addWeighted(rgb, 0.8, np.full_like(rgb, (120, 200, 255)), 0.2, 0)
    over = np.where(outside, red, np.where(margin, blue, rgb))
    pts = np.round(path_px.flatten() - 0.5).astype(np.int32)
    t = max(1, int(round(0.3 * lay.px_per_mm)))
    cv2.polylines(over, [pts], True, (0, 0, 0), t, cv2.LINE_AA)
    for x0, x1, y in lay.folds:
        cv2.line(over, (int(x0), int(y)), (int(x1), int(y)), (60, 160, 60), t, cv2.LINE_AA)
    x0, y0, x1, y1 = geo.bbox(lay.cut)
    b = int(5 * lay.px_per_mm)
    return np.ascontiguousarray(over[max(0, y0 - b):y1 + b, max(0, x0 - b):x1 + b])
