"""Command line interface: ``papermini make | sheet | batch | gui``."""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .segment import ModelError
from .settings import (FIGURE_OPTIONS, FigureSettings, Project, build_mini, load_project,
                       safe_name)

D = FigureSettings()  # defaults shown in --help


def add_figure_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("size and shape")
    g.add_argument("--height-mm", type=float, default=D.height_mm, help="figure height without tab (42)")
    g.add_argument("--margin-mm", type=float, default=D.margin_mm, help="white border around the drawing (1.6)")
    g.add_argument("--smooth-mm", type=float, default=D.smooth_mm, help="outline rounding, Gaussian sigma (0.6)")
    g.add_argument("--margin-fill", choices=["color", "image"], default=D.margin_fill,
                   help="what shows between drawing and cut line: --margin-color (default) "
                        "or the original image")
    g.add_argument("--margin-color", default=D.margin_color,
                   help="colour of the margin around the drawing (#ffffff)")
    g.add_argument("--tab-shape", choices=["square", "round"], default=D.tab_shape,
                   help="square: slots into a stand; round: a half disc (--tab-radius-mm) "
                        "that folds out into a round base")
    g.add_argument("--tab-color", default=D.tab_color,
                   help="tab colour behind the label, independent of the margin; "
                        "use --label '' for a plain tab (#ffffff)")
    g.add_argument("--tab-width-mm", type=float, default=D.tab_width_mm,
                   help="square tab width (22)")
    g.add_argument("--tab-radius-mm", type=float, default=D.tab_radius_mm,
                   help="round tab radius; 12.5 makes a 25 mm base (12.5)")
    g.add_argument("--tab-height-mm", type=float, default=D.tab_height_mm,
                   help="square tab height below the fold (12)")
    g.add_argument("--tab-overlap-mm", type=float, default=D.tab_overlap_mm, help="tab reach above the fold, adds paper beside narrow feet (0)")
    g.add_argument("--fold-mm", type=float, default=D.fold_mm, help="fold line above the lowest point of the outline (0)")
    g.add_argument("--no-tab", action="store_true", help="no fold tab")
    g.add_argument("--double-sided", action="store_true",
                   help="front + back joined at a top fold, tabs at both ends")
    g.add_argument("--back", choices=["mirror", "blank", "text"], default=D.back,
                   help="double-sided back: mirrored image (default), blank, or text")
    g.add_argument("--back-text", help="text on the back with --back text (default: the label)")
    g.add_argument("--back-color", default=D.back_color,
                   help="colour of a blank or text back (#ffffff)")
    g.add_argument("--back-text-color", default=D.back_text_color,
                   help="colour of the back text (#2f5597)")
    g = p.add_argument_group("mask")
    g.add_argument("--model", default=D.model,
                   help="rmbg-1.4, birefnet, birefnet-lite, alpha, mask (with --mask) or a .onnx file; "
                        "'auto' uses the alpha channel of transparent PNGs, or --mask if given")
    g.add_argument("--mask", help="your own mask image (white = figure) instead of a model")
    g.add_argument("--crop", help="x0,y0,x1,y1 region (fractions or px) the model looks at")
    g.add_argument("--threshold", type=int, default=D.threshold, help="mask threshold 0-255 (40)")
    g.add_argument("--close", type=int, default=None,
                   help="closing radius in px (default scales with image: 9 px at 1400 px)")
    g.add_argument("--keep-all", action="store_true",
                   help="keep detached parts (>= --min-area) and bridge them to the figure")
    g.add_argument("--min-area", type=int, default=D.min_area, help="smallest part kept with --keep-all (px)")
    g.add_argument("--no-cache", action="store_true", help="do not reuse cached model masks")
    g = p.add_argument_group("output")
    g.add_argument("--label", help="text on the tab (default: file name; '' for none)")
    g.add_argument("--dpi", type=int, default=D.dpi, help="embedded image resolution (300)")
    g.add_argument("--simplify-mm", type=float, default=D.simplify_mm, help="cut line simplification (0.15)")
    g.add_argument("--no-smooth", action="store_true", help="straight-segment cut line, no Béziers")
    g.add_argument("--cut-color", default=D.cut_color, help="cut line colour (#000000)")
    g.add_argument("--cut-width-mm", type=float, default=D.cut_width_mm, help="cut line width (0.3)")
    g.add_argument("--cutter", action="store_true",
                   help="cutting-machine style: red 0.1 mm cut line, with a --bleed-mm bleed")
    g.add_argument("--bleed-mm", type=float, default=D.bleed_mm,
                   help="with --cutter: print the background this far beyond the cut line, "
                        "so a slightly misaligned cut shows no white edge (1)")
    g.add_argument("--label-color", default=D.label_color)
    g.add_argument("--label-size-mm", type=float, default=D.label_size_mm)
    g.add_argument("--debug", action="store_true", help="write intermediate masks and a red overlay")


# --------------------------------------------------------------------------- commands

def cmd_make(a: argparse.Namespace) -> int:
    from .svg import write_svg

    images = _expand(a.images)
    if a.output and len(images) > 1 and a.output.lower().endswith(".svg"):
        raise SystemExit("-o NAME.svg only works with a single image; use -o DIR")
    s = FigureSettings.from_dict(
        {k: v for k, v in vars(a).items() if k in FIGURE_OPTIONS and v is not None})
    for img in map(Path, images):
        out_svg = Path(a.output) if a.output and a.output.lower().endswith(".svg") else None
        out_dir = out_svg.parent if out_svg else Path(a.output) if a.output else img.parent
        m = build_mini(img, s, use_cache=not a.no_cache,
                       debug_dir=out_dir / "debug" if a.debug else None)
        out = write_svg(m, out_svg or out_dir / (safe_name(m.name) + ".svg"))
        print(f"  -> {out}")
    return 0


def cmd_sheet(a: argparse.Namespace) -> int:
    from .svg import read_svg

    minis = [(read_svg(Path(p)), a.copies) for p in _expand(a.svgs)]
    return write_sheet(minis, Path(a.output), a.paper, a.preview, a.title, a.margin_mm, a.gap_mm)


def write_sheet(minis, output: Path, paper: str, preview: bool, title: str,
                margin_mm: float = 12.0, gap_mm: float = 7.0) -> int:
    from .sheet import pack, write_pdf, write_previews

    lay = pack(minis, paper, margin_mm, gap_mm)
    write_pdf(lay, output, margin_mm, title)
    n = len(lay.placements)
    print(f"  -> {output} ({n} piece{'s' * (n != 1)}, {lay.pages} page{'s' * (lay.pages != 1)}, "
          f"{paper.upper()})")
    if preview:
        for p in write_previews(lay, output.with_suffix(".png"), margin_mm=margin_mm, title=title):
            print(f"  -> {p}")
    return 0


def run_project(proj: Project, debug: bool = False, preview: bool = False,
                use_cache: bool = True) -> int:
    from .svg import write_svg

    if not proj.figures:
        raise SystemExit(f"{proj.path}: no 'figures' listed")
    out_dir = proj.output_dir
    minis = []
    for f in proj.figures:
        m = build_mini(f.image, f.settings, use_cache=use_cache,
                       debug_dir=out_dir / "debug" if debug or proj.debug else None)
        print(f"  -> {write_svg(m, out_dir / f.svg_name())}")
        minis.append((m, f.settings.copies))
    sh = proj.sheet
    if sh.enabled:
        write_sheet(minis, proj.sheet_path, sh.paper, preview or sh.preview, sh.title,
                    sh.margin_mm, sh.gap_mm)
    return 0


def cmd_batch(a: argparse.Namespace) -> int:
    return run_project(load_project(Path(a.config)), a.debug, a.preview, not a.no_cache)


def cmd_gui(a: argparse.Namespace) -> int:
    try:
        from .gui import run
    except ImportError as e:
        raise SystemExit(f"The GUI needs PySide6: pip install 'papermini[gui]'  ({e})") from None
    return run(a.files)


def _expand(patterns: List[str]) -> List[str]:
    """Expand globs ourselves (Windows shells do not)."""
    out: List[str] = []
    for p in patterns:
        hits = sorted(glob.glob(p)) if any(ch in p for ch in "*?[") else [p]
        if not hits:
            raise SystemExit(f"no files match {p!r}")
        out += hits
    for p in out:
        if not Path(p).exists():
            raise SystemExit(f"file not found: {p}")
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="papermini", description="Turn illustrations into print-ready paper miniatures.")
    p.add_argument("--version", action="version", version=f"papermini {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    mk = sub.add_parser("make", help="image(s) -> one SVG per figure")
    mk.add_argument("images", nargs="+")
    mk.add_argument("-o", "--output", help="output .svg (single image) or directory (default: next to image)")
    add_figure_args(mk)
    mk.set_defaults(func=cmd_make)

    sh = sub.add_parser("sheet", help="papermini SVGs -> printable PDF sheet")
    sh.add_argument("svgs", nargs="+")
    sh.add_argument("-o", "--output", default="minis.pdf")
    sh.add_argument("--copies", type=int, default=1, help="copies of each figure (1)")
    sh.add_argument("--paper", choices=["a4", "letter"], default="a4")
    sh.add_argument("--margin-mm", type=float, default=12.0, help="page margin (12)")
    sh.add_argument("--gap-mm", type=float, default=7.0, help="gap between pieces (7)")
    sh.add_argument("--title", default="Paper miniatures")
    sh.add_argument("--preview", action="store_true", help="also write a PNG preview per page")
    sh.set_defaults(func=cmd_sheet)

    bt = sub.add_parser("batch", help="YAML config: images + per-image options -> SVGs + sheet")
    bt.add_argument("config")
    bt.add_argument("--debug", action="store_true")
    bt.add_argument("--preview", action="store_true")
    bt.add_argument("--no-cache", action="store_true")
    bt.set_defaults(func=cmd_batch)

    gu = sub.add_parser("gui", help="open the desktop app (needs papermini[gui])")
    gu.add_argument("files", nargs="*", help="images or a project .yaml to open")
    gu.set_defaults(func=cmd_gui)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.func(a)
    except (ValueError, FileNotFoundError, ModelError) as e:
        print(f"papermini: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
