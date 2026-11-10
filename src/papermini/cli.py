"""Command line interface: ``papermini make | sheet | batch | gui``."""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, remote
from .segment import ModelError
from .settings import (FIGURE_OPTIONS, FigureSettings, Project, SheetSettings, build_mini,
                       load_project, safe_name)
from .sheet import CUT_MODES, MARKS

D = FigureSettings()  # defaults shown in --help
DS = SheetSettings()


def add_figure_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("size and shape")
    g.add_argument("--height-mm", type=float,
                   help="height of the drawn figure, without margin and tab (42)")
    g.add_argument("--width-mm", type=float,
                   help="width of the drawn figure; alone it scales by width, with "
                        "--height-mm the figure is stretched to both")
    g.add_argument("--margin-mm", type=float, default=D.margin_mm, help="distance between the drawing and the cut line (1.6)")
    g.add_argument("--smooth-mm", type=float, default=D.smooth_mm, help="outline rounding, Gaussian sigma (0.6)")
    g.add_argument("--margin-fill", choices=["color", "image"], default=D.margin_fill,
                   help="what shows between drawing and cut line: --margin-color (default) "
                        "or the original image")
    g.add_argument("--margin-color", default=D.margin_color,
                   help="color of the margin around the drawing (#ffffff)")
    g.add_argument("--tab-shape", choices=["square", "round"], default=D.tab_shape,
                   help="square: slots into a stand; round: a half disc (--tab-radius-mm) "
                        "that folds out into a round base")
    g.add_argument("--tab-color", default=D.tab_color,
                   help="tab color behind the label, independent of the margin; "
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
    g.add_argument("--double-sided", action=argparse.BooleanOptionalAction, default=None,
                   help="front + back joined at a top fold, tabs at both ends; "
                        "--no-double-sided prints the front only (on)")
    g.add_argument("--back", choices=["mirror", "blank", "text"], default=D.back,
                   help="double-sided back: mirrored image (default), blank, or text")
    g.add_argument("--back-text", help="text on the back with --back text (default: the label)")
    g.add_argument("--back-color", default=D.back_color,
                   help="color of a blank or text back (#ffffff)")
    g.add_argument("--back-text-color", default=D.back_text_color,
                   help="color of the back text (#2f5597)")
    g = p.add_argument_group("picture (colors of what is printed; the mask is unaffected)")
    g.add_argument("--greyscale", action="store_true", help="print in black and white")
    g.add_argument("--brightness", type=int, default=D.brightness,
                   help="-100 (black) to 100 (white); white paper stays white (0)")
    g.add_argument("--contrast", type=int, default=D.contrast, help="-100 to 100 (0)")
    g.add_argument("--saturation", type=int, default=D.saturation,
                   help="-100 (grey) to 100 (twice as colorful) (0)")
    g.add_argument("--hue", type=int, default=D.hue,
                   help="turn the colors around the color wheel, -180 to 180 degrees (0)")
    g = p.add_argument_group("mask")
    g.add_argument("--model", default=D.model,
                   help="rmbg-1.4, birefnet, birefnet-lite, alpha, mask (with --mask) or a .onnx file; "
                        "'auto' uses the alpha channel of transparent PNGs, or --mask if given")
    g.add_argument("--mask", help="your own mask image (white = figure) instead of a model")
    g.add_argument("--crop", help="x0,y0,x1,y1 region (fractions or px) the model looks at")
    g.add_argument("--strength", type=int, default=D.strength,
                   help="background removal strength 0-254: lower keeps faint lines, "
                        "higher removes more background (40)")
    g.add_argument("--fill-gaps", type=int, default=None,
                   help="fill gaps and notches in the outline up to this many px; 0 = off "
                        "(default scales with the image: 9 px at 1400 px)")
    g.add_argument("--keep-all", action="store_true",
                   help="keep detached parts (>= --min-area) and bridge them to the figure")
    g.add_argument("--min-area", type=int, default=D.min_area, help="smallest part kept with --keep-all (px)")
    g.add_argument("--no-cache", action="store_true", help="do not reuse cached model masks")
    g = p.add_argument_group("output")
    g.add_argument("--label", help="text on the tab (default: file name; '' for none)")
    g.add_argument("--dpi", type=int, default=D.dpi, help="embedded image resolution (300)")
    g.add_argument("--simplify-mm", type=float, default=D.simplify_mm, help="cut line simplification (0.15)")
    g.add_argument("--no-smooth", action="store_true", help="straight-segment cut line, no Béziers")
    g.add_argument("--cut-color", default=D.cut_color,
                   help="cut line color, for cutting by hand (#000000)")
    g.add_argument("--cut-width-mm", type=float, default=D.cut_width_mm,
                   help="cut line width, for cutting by hand (0.3)")
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
    for src in images:
        img = remote.fetch_image(src) if remote.is_url(src) else remote.local_path(src)
        out_svg = Path(a.output) if a.output and a.output.lower().endswith(".svg") else None
        # next to the image, or for a link (its copy lives in the cache) here
        here = Path.cwd() if remote.is_url(src) else img.parent
        out_dir = out_svg.parent if out_svg else Path(a.output) if a.output else here
        m = build_mini(img, s, bleed_mm=a.bleed_mm, use_cache=not a.no_cache,
                       debug_dir=out_dir / "debug" if a.debug else None)
        out = write_svg(m, out_svg or out_dir / (safe_name(m.name) + ".svg"))
        print(f"  -> {out}")
    return 0


def cmd_sheet(a: argparse.Namespace) -> int:
    from .svg import read_svg

    minis = [(read_svg(Path(p)), a.copies) for p in _expand(a.svgs)]
    sh = SheetSettings(paper=a.paper, title=a.title, margin_mm=a.margin_mm, gap_mm=a.gap_mm,
                       cut=a.cut, marks=a.marks, cut_folds=a.cut_folds)
    return write_sheet(minis, Path(a.output), sh, a.preview)


def write_sheet(minis, output: Path, sh: SheetSettings, preview: bool = False) -> int:
    """The PDF sheet, its PNG previews, and cut by machine its cut files."""
    from .sheet import default_cut_file, pack, write_cut_files, write_pdf, write_previews

    lay = pack(minis, sh.paper, sh.margin_mm, sh.gap_mm, cut=sh.cut, marks=sh.marks)
    write_pdf(lay, output, sh.title)
    n = len(lay.placements)
    print(f"  -> {output} ({n} piece{'s' * (n != 1)}, {lay.pages} page{'s' * (lay.pages != 1)}, "
          f"{sh.paper.upper()})")
    if lay.machine:
        for p in write_cut_files(lay, default_cut_file(output), sh.cut_folds, sh.title):
            print(f"  -> {p} (cut file)")
    if preview:
        for p in write_previews(lay, output.with_suffix(".png"), title=sh.title):
            print(f"  -> {p}")
    return 0


def run_project(proj: Project, debug: bool = False, preview: bool = False,
                use_cache: bool = True) -> int:
    from .svg import write_svg

    if not proj.figures:
        raise SystemExit(f"{proj.path}: no 'figures' listed")
    out_dir = proj.output_dir
    minis = []
    sh = proj.sheet
    for f in proj.figures:
        m = build_mini(f.image, f.settings, bleed_mm=sh.figure_bleed, use_cache=use_cache,
                       debug_dir=out_dir / "debug" if debug or proj.debug else None)
        print(f"  -> {write_svg(m, out_dir / f.svg_name())}")
        minis.append((m, f.settings.copies))
    if sh.enabled:
        write_sheet(minis, proj.sheet_path, sh, preview or sh.preview)
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
    """Expand globs ourselves (Windows shells do not); links are passed through."""
    out: List[str] = []
    for p in patterns:
        if remote.is_url(p):
            out.append(p)
            continue
        p = str(remote.local_path(p))
        hits = sorted(glob.glob(p)) if any(ch in p for ch in "*?[") else [p]
        if not hits:
            raise SystemExit(f"no files match {p!r}")
        out += hits
    for p in out:
        if not remote.is_url(p) and not Path(p).exists():
            raise SystemExit(f"file not found: {p}")
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="papermini", description="Turn illustrations into print-ready paper miniatures.")
    p.add_argument("--version", action="version", version=f"papermini {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    mk = sub.add_parser("make", help="image(s) -> one SVG per figure")
    mk.add_argument("images", nargs="+", metavar="IMAGE",
                    help=f"image files ({remote.READABLE}) or http(s) links to images")
    mk.add_argument("-o", "--output", help="output .svg (single image) or directory "
                                           "(default: next to the image; for a link, here)")
    mk.add_argument("--bleed-mm", type=float, default=0.0,
                    help="print the edge colors this far beyond the cut line, for a sheet cut "
                         "by machine (papermini sheet --cut machine); 0 = none (0)")
    add_figure_args(mk)
    mk.set_defaults(func=cmd_make)

    sh = sub.add_parser("sheet", help="papermini SVGs -> printable PDF sheet")
    sh.add_argument("svgs", nargs="+")
    sh.add_argument("-o", "--output", default="minis.pdf")
    sh.add_argument("--copies", type=int, default=1, help="copies of each figure (1)")
    sh.add_argument("--paper", choices=["a4", "letter"], default="a4")
    sh.add_argument("--margin-mm", type=float, default=DS.margin_mm,
                    help="page margin; --cut machine: where the alignment marks are (12)")
    sh.add_argument("--gap-mm", type=float, default=7.0, help="gap between pieces (7)")
    sh.add_argument("--title", default=DS.title)
    sh.add_argument("--preview", action="store_true", help="also write a PNG preview per page")
    sh.add_argument("--cut", choices=CUT_MODES, default=DS.cut,
                    help="hand: cut lines on the sheet; machine: a sheet without cut lines but "
                         "with alignment marks, plus a cut file (NAME-cut.svg) per page (hand)")
    sh.add_argument("--marks", choices=MARKS, default=DS.marks,
                    help="--cut machine: alignment marks: corners, Silhouette Studio's "
                         "Type 1, or none (corners)")
    sh.add_argument("--cut-folds", action="store_true",
                    help="--cut machine: also put the fold lines in the cut file")
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
