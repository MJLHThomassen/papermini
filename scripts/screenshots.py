"""Regenerate the README screenshots of the desktop app from the dragons project.

    python scripts/screenshots.py            # writes docs/screenshots/*.png

Renders off-screen at 1.5x scale with an English locale and default preferences
(a temporary settings folder), so the result does not depend on your own setup.
It needs the rmbg-1.4, birefnet-lite and birefnet models (downloaded on first use);
background removal results are cached, so later runs are quick.

Besides the app screenshots it writes ``crop.png`` (cropping a stat block down to its
dragon), ``models.png`` (the three models on one image, with what a model left
behind circled: wherever it kept something that BiRefNet removed) and, for the
settings guide in docs/reference.md, ``settings/*.png``: the same piece side by side
with different values of a setting, and ``settings/machine.png``: a sheet cut by
machine next to its cut file.

    python scripts/screenshots.py --only settings   # just those
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAGONS = ROOT / "examples" / "dragons"
MODELS = [  # (model, caption under its name)
    ("rmbg-1.4", "keeps the ground at its feet"),
    ("birefnet-lite", "leaves background by the right wing"),
    ("birefnet", "a clean outline"),
]
HIGHLIGHT = "#0a84ff"
GROUPS = ["app", "crop", "models", "settings"]
GREEN = "#3b6e2a"  # a grass-green tab: shows what folds under


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "screenshots")
    ap.add_argument("--project", type=Path, default=DRAGONS / "dragons.yaml")
    ap.add_argument("--scale", default="1.5", help="Qt scale factor (default 1.5)")
    ap.add_argument("--only", nargs="+", choices=GROUPS, default=GROUPS,
                    help="make only these groups of images (default: all)")
    args = ap.parse_args()

    os.environ["QT_SCALE_FACTOR"] = args.scale
    from PySide6.QtCore import QLocale, QPointF, QRectF, QSettings, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import QApplication, QGraphicsScene

    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tempfile.mkdtemp("papermini"))

    sys.path.insert(0, str(ROOT / "src"))
    import numpy as np
    from PIL import Image

    import cv2

    from papermini import segment
    from papermini.gui import theme
    from papermini.gui.views import draw_mini
    from papermini.gui.window import MainWindow
    from papermini.settings import FigureSettings, build_mini

    args.out.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    ratio = float(args.scale)

    def settle(cond=lambda: True, timeout=600):
        end = time.time() + timeout
        while time.time() < end:
            app.processEvents()
            time.sleep(0.05)
            if cond():
                break
        for _ in range(10):
            app.processEvents()
            time.sleep(0.03)

    def window(mode: str, size=(1360, 820)) -> MainWindow:
        theme.apply(app, mode)
        w = MainWindow()
        w.setAttribute(Qt.WA_DontShowOnScreen)
        w.resize(*size)
        w.show()
        w.load(args.project)
        w.tabs.setCurrentIndex(w.SHEET)  # the sheet builds every figure
        settle(lambda: all(f.up_to_date for f in w.figures))
        return w

    def show(w: MainWindow, row: int, tab: int) -> None:
        w.list.setCurrentRow(row)
        w.tabs.setCurrentIndex(tab)
        settle(lambda: all(f.up_to_date for f in [w.current()] if f is not None))
        w._fit()
        settle()

    def change(w: MainWindow, **kw) -> None:
        fig = w.current()
        w.panel.set_settings(replace(fig.entry.settings, **kw), fig.entry.display_name,
                             fig.entry.image.stem)
        w._settings_changed(w.panel.settings())
        settle(lambda: fig.up_to_date)
        w._fit()
        settle()

    def close(w: MainWindow) -> None:
        w._modified = False
        w.close()

    def save(img, name: str) -> None:
        path = args.out / f"{name}.png"
        img.save(str(path))
        print(f"wrote {path}")

    def shot(mode: str, name: str, row: int, tab: int) -> None:
        w = window(mode)
        show(w, row, tab)
        save(w.grab(), name)
        close(w)

    def panels(items, mode: str):
        """Views side by side (centred in a row as high as the highest), each with a
        title and a caption above it."""
        t = theme.resolve(mode)
        pad, head = 16, 52
        sizes = [p.deviceIndependentSize() for p, *_ in items]
        ph = max(z.height() for z in sizes)
        total = pad + sum(max(z.width(), 260) + pad for z in sizes)
        out = QImage(int(total * ratio), int((head + ph + pad) * ratio), QImage.Format_ARGB32)
        out.setDevicePixelRatio(ratio)
        out.fill(QColor(t.bg))
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        bold, small = QFont(), QFont()
        bold.setPointSizeF(11.5)
        bold.setBold(True)
        small.setPointSizeF(9.5)
        x = pad
        for (pix, title, caption), size in zip(items, sizes):
            pw = max(size.width(), 260)  # room for the caption
            p.setPen(QColor(t.text))
            p.setFont(bold)
            p.drawText(QRectF(x, 6, pw, 24), Qt.AlignHCenter | Qt.AlignVCenter, title)
            p.setPen(QColor(t.muted))
            p.setFont(small)
            p.drawText(QRectF(x, 28, pw, 20), Qt.AlignHCenter | Qt.AlignVCenter, caption)
            p.drawPixmap(QPointF(x + (pw - size.width()) / 2,
                                 head + (ph - size.height()) / 2), pix)  # centred
            x += pw + pad
        p.end()
        return out

    def view_shot(view, scene_rect: QRectF, pad: int = 28, paint=None):
        """The part of a view around ``scene_rect`` (plus its shadow); ``paint(painter)``
        draws on top in view coordinates."""
        vp = view.viewport()
        r = view.mapFromScene(scene_rect).boundingRect().adjusted(-pad, -pad, pad, pad)
        r = r.intersected(vp.rect())
        pix = vp.grab(r)
        if paint is not None:
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            p.translate(-r.x(), -r.y())
            paint(p)
            p.end()
        return pix

    def picture(view) -> QRectF:
        return QRectF(0, 0, *view._img_size)

    def leftovers(mask, ref):
        """Larger areas that ``mask`` keeps and the reference mask removes."""
        extra = ((mask > 128) & (ref < 64)).astype(np.uint8)
        extra = cv2.morphologyEx(extra, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        n, labels, stats, _ = cv2.connectedComponentsWithStats(extra)
        keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > 0.002 * extra.size]
        return np.isin(labels, keep)

    def piece(m, rect: QRectF = None, mm: float = 3.6):
        """A miniature drawn as in the app, on white paper: all of it, or the part in
        ``rect`` (mm), at ``mm`` logical pixels per millimetre."""
        sc = QGraphicsScene()
        draw_mini(sc, m)
        r = rect or QRectF(0, 0, m.width_mm, m.height_mm)
        r = r.adjusted(-2.5, -2.5, 2.5, 2.5)
        img = QImage(int(r.width() * mm * ratio), int(r.height() * mm * ratio),
                     QImage.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        sc.render(p, QRectF(img.rect()), r)
        p.end()
        pix = QPixmap.fromImage(img)
        pix.setDevicePixelRatio(ratio)
        return pix

    def mini(image: str, bleed_mm: float = 0.0, **kw):
        """A miniature of one of the dragons, with BiRefNet unless ``kw`` says otherwise."""
        kw.setdefault("model", "birefnet")
        return build_mini(DRAGONS / image, FigureSettings(**kw), bleed_mm=bleed_mm,
                          log=lambda *_: None)

    def bottom(m, above: float = 14.0) -> QRectF:
        """The tab of a single-sided miniature and ``above`` mm of figure over its fold."""
        fold = m.folds[0][2]
        return QRectF(0, fold - above, m.width_mm, m.height_mm - fold + above)

    def compare(name: str, items, **kw) -> None:
        """``items``: (miniature, rect or None, title, caption) side by side."""
        save(panels([(piece(m, r, **kw), title, caption) for m, r, title, caption in items],
                    "light"), f"settings/{name}")

    def want(group: str) -> bool:
        return group in args.only

    # the app: the flying dragon is being edited; the sheet has all three figures
    if want("app"):
        shot("light", "app-miniature", 1, 1)
        shot("light", "app-source", 1, 0)
        shot("light", "app-sheet", 1, 2)
        shot("dark", "app-dark", 2, 1)

    # cropping: a box around the dragon; the stat block outside it is left out
    if want("crop"):
        w = window("light")
        show(w, 0, w.SOURCE)
        crop_box = view_shot(w.crop_view, picture(w.crop_view))
        w.tabs.setCurrentIndex(w.MINI)
        w._fit()
        settle()
        cropped = view_shot(w.mini_view, w.mini_view.scene().itemsBoundingRect(), pad=8)
        close(w)
        save(panels([(crop_box, "Drag a box around the dragon", "in step 1, Source"),
                     (cropped, "The miniature", "only what is inside the box")], "light"),
             "crop")

    # the models on one image; what one kept that BiRefNet removed is circled
    if want("models"):
        path = DRAGONS / "dragon.webp"
        im = Image.open(path)
        im.load()
        data = path.read_bytes()
        masks = {m: segment.compute_mask(im, m, image_bytes=data) for m, _ in MODELS}
        ref = masks["birefnet"]
        w = window("light", (1100, 760))
        w.crop_view.show_hint = lambda: False  # (no "drag a box" hint in a comparison)
        show(w, 2, w.SOURCE)
        items = []
        for model, caption in MODELS:
            change(w, model=model)
            extra = leftovers(masks[model], ref) if model != "birefnet" else None
            circle = None
            if extra is not None and extra.any():
                ys, xs = np.nonzero(extra)
                box = QRectF(QPointF(xs.min(), ys.min()), QPointF(xs.max(), ys.max()))
                circle = QRectF(w.crop_view.mapFromScene(box).boundingRect())
                circle.adjust(-14, -14, 14, 14)

            def ring(p, circle=circle):
                if circle is not None:
                    p.setPen(QPen(QColor(HIGHLIGHT), 3))
                    p.drawEllipse(circle)

            items.append((view_shot(w.crop_view, picture(w.crop_view), paint=ring), model,
                          caption))
        close(w)
        save(panels(items, "light"), "models")

    if want("settings"):
        settings_images(mini, piece, bottom, compare, QRectF)

        # cut by machine: the PDF (no cut lines, marks) and its cut file, side by side
        from PySide6.QtSvg import QSvgRenderer

        from papermini.gui.views import draw_sheet
        from papermini.settings import load_project
        from papermini.sheet import cut_file_svg, pack

        from papermini import sizes

        proj = load_project(args.project)
        sh = replace(proj.sheet, cut="machine")

        def smaller(s):  # one creature size down, so all three dragons fit on one page
            if s.size not in sizes.SIZES:
                return s
            down = sizes.SIZES[max(sizes.SIZES.index(s.size) - 1, 0)]
            return sizes.apply(s, down, proj.sizes)

        lay = pack([(build_mini(f.image, smaller(f.settings), bleed_mm=sh.figure_bleed,
                                log=lambda *_: None), 1) for f in proj.figures],
                   sh.paper, sh.margin_mm, sh.gap_mm, cut=sh.cut, marks=sh.marks)
        assert lay.pages == 1, "the machine sheet picture should fit on one page"
        k = 2.2 * ratio  # device pixels per mm
        pw, ph = lay.paper

        def page(render) -> QPixmap:
            img = QImage(int(pw * k), int(ph * k), QImage.Format_ARGB32)
            img.fill(QColor("white"))
            p = QPainter(img)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            render(p, QRectF(img.rect()))
            p.setPen(QPen(QColor("#c8c8cc"), 1))
            p.drawRect(img.rect().adjusted(0, 0, -1, -1))  # the paper's edge
            p.end()
            pix = QPixmap.fromImage(img)
            pix.setDevicePixelRatio(ratio)
            return pix

        sc = QGraphicsScene()
        draw_sheet(sc, lay, sh.title)
        svg = QSvgRenderer(bytearray(cut_file_svg(lay, 0, folds=True, title=sh.title), "utf-8"))
        save(panels([(page(lambda p, r: sc.render(p, r, QRectF(0, 0, pw, ph))), "The PDF",
                      "to print: no cut lines, with alignment marks"),
                     (page(svg.render), "The cut file (SVG)",
                      "cut lines (red), fold lines (blue) and the same marks")], "light"),
             "settings/machine")


def settings_images(mini, piece, bottom, compare, QRectF) -> None:
    """One image per setting in the settings guide: the same piece with different values."""
    from papermini import sizes

    red, fly = "dragon.webp", "dragon-flying.webp"
    one = dict(double_sided=False, label="")  # one side, no label: the setting stands out

    # step 2, Size: the creature size fills in the height and the base (a round tab shows it)
    def sized(size):
        return mini(red, size=size, tab_shape="round", tab_color=GREEN,
                    **sizes.BUILTIN.row(size).values(), **one)

    compare("creature-size", [
        (sized(s), None, sizes.label(s),
         f"{sizes.BUILTIN.row(s).height_mm:g} mm tall, {sizes.BUILTIN.row(s).base_mm:g} mm base")
        for s in ("small", "medium", "large")
    ], mm=3.4)

    # step 2, Back side
    compare("back", [
        (mini(red, label="Red dragon"), None, "Mirrored drawing", "the default"),
        (mini(red, label="Red dragon", back="blank"), None, "Blank", "to draw or write on"),
        (mini(red, label="Red dragon", back="text", back_text="Ember"), None, "Text",
         "a name or a note"),
    ], mm=3.4)

    # Outline and cut line
    cream = dict(one, no_tab=True, margin_color="#f3e6c8")
    compare("margin", [
        (mini(red, margin_mm=0.8, **cream), None, "Margin 0.8 mm", "close to the drawing"),
        (mini(red, **cream), None, "Margin 1.6 mm", "the default"),
        (mini(red, margin_mm=3.5, **cream), None, "Margin 3.5 mm", "easier to cut"),
    ])
    compare("margin-fill", [
        (mini(fly, height_mm=36, margin_color="#24477a", no_tab=True, **one), None,
         "Color", "any color, here blue"),
        (mini(fly, height_mm=36, margin_fill="image", no_tab=True, **one), None,
         "Original image", "the picture around the figure"),
    ])
    wing = QRectF(36, 0, 36, 22)  # the flying dragon's right wing
    compare("smoothing", [
        (mini(fly, height_mm=36, no_tab=True, **one), wing, "Smoothing 0.6 mm",
         "the default: follows the wing"),
        (mini(fly, height_mm=36, smooth_mm=2.5, no_tab=True, **one), wing,
         "Smoothing 2.5 mm", "fewer bends, but thin tips lose their margin"),
    ], mm=7)

    # step 3, Sheet: bleed (cut by machine); the red hairline shows where the machine cuts
    tip = QRectF(50, 2, 22, 14)
    dark = dict(height_mm=36, margin_color="#1d1d2b", no_tab=True, cut_color="#ff0000",
                cut_width_mm=0.1, **one)
    compare("bleed", [
        (mini(fly, **dark), tip, "No bleed", "a cut a little off leaves a white edge"),
        (mini(fly, bleed_mm=1.0, **dark), tip, "Bleed 1 mm",
         "the margin color goes on past the cut"),
    ], mm=11)

    # Tab
    m1 = mini(red, double_sided=False, label="Red dragon")
    m2 = mini(red, tab_shape="round", tab_color=GREEN, **one)
    compare("tab-shape", [
        (m1, bottom(m1), "Square", "slots into a stand, with the label"),
        (m2, bottom(m2), "Round", "folds out into a base, here green"),
    ], mm=6)
    ms = [mini(fly, height_mm=36, tab_overlap_mm=v, **one) for v in (0, 4)]
    compare("tab-overlap", [
        (ms[0], bottom(ms[0], 18), "Overlap 0 mm", "the tab hangs from the tail tip"),
        (ms[1], bottom(ms[1], 18), "Overlap 4 mm", "the tab holds the tail and the claws"),
    ], mm=6)
    ms = [mini(red, fold_mm=v, tab_color=GREEN, **one) for v in (0, 1.6, 4)]
    compare("fold", [
        (ms[0], bottom(ms[0]), "Fold 0 mm", "the feet float a margin above the ground"),
        (ms[1], bottom(ms[1]), "Fold 1.6 mm", "the feet stand on the fold"),
        (ms[2], bottom(ms[2]), "Fold 4 mm", "the claws fold under"),
    ], mm=6)

    # step 1, Image adjustments
    plain = dict(one, no_tab=True)
    compare("adjustments", [
        (mini(red, **plain), None, "As drawn", "all at 0"),
        (mini(red, greyscale=True, contrast=15, **plain), None, "Greyscale", "contrast +15"),
        (mini(red, hue=120, **plain), None, "Hue +120°", "a green dragon"),
    ])


if __name__ == "__main__":
    main()
