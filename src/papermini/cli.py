"""Command line interface: ``papermini make | sheet | batch | gui``."""

from __future__ import annotations

import argparse
import glob
import sys
from functools import partial
from pathlib import Path

from . import __version__
from .output.output import Output
from .output.png_writer import PX_PER_SQUARE, PngWriter
from .pipeline.pipeline import Pipeline
from .pipeline.segmentation.model_error import ModelError
from .project.figure_entry import safe_name
from .project.figure_settings import FIGURE_OPTIONS, FigureSettings
from .project.option_flags import OptionFlags
from .project.project import Project
from .project.project_store import ProjectStore
from .project.settings import build_mini
from .project.sheet_settings import SheetSettings
from .project.size_calculator import SizeCalculator
from .project.size_table import GRID_MM, SizeTable
from .project.sizes import BUILTIN
from .support.font_library import FontLibrary
from .support.image_fetcher import ImageFetcher
from .support.image_files import ImageFiles

DS = SheetSettings()
FORMATS = ("svg", "png", "both")  # what papermini make writes, the first by default
SHEET_PDF = "minis.pdf"  # the PDF papermini sheet writes by default


def add_figure_args(flags: OptionFlags) -> None:
    flags.add("copies", "kind", "size")
    flags.group_of("size").add_argument(
        "--grid-mm",
        type=float,
        help=flags.with_default(
            "grid square for --size: the bases and heights scale with it",
            GRID_MM,
            "mm",
        ),
    )
    flags.add(
        "height_mm",
        "width_mm",
        "margin_mm",
        "smooth_mm",
        "margin_fill",
        "margin_color",
        "tab_shape",
        "tab_color",
        "tab_width_mm",
        "tab_radius_mm",
        "tab_height_mm",
        "tab_overlap_mm",
        "fold_mm",
        "no_tab",
        "double_sided",
        "back",
        "back_text",
        "back_color",
        "back_text_color",
        "token_diameter_mm",
        "token_area",
        "token_fill",
        "token_fill_color",
        "token_border_mm",
        "token_border_color",
        "token_cut_line",
        "token_outline",
        "token_text",
        "token_text_style",
        "token_text_color",
        "token_text_mm",
        "greyscale",
        "brightness",
        "contrast",
        "saturation",
        "hue",
        "model",
        "mask",
        "crop",
        "strength",
        "fill_gaps",
        "keep_all",
        "min_area",
    )
    flags.group_of("model").add_argument(
        "--no-cache",
        action="store_true",
        help=flags.with_default("do not reuse cached model masks", False),
    )
    flags.add(
        "label",
        "tab_front",
        "tab_back",
        "dpi",
        "simplify_mm",
        "no_smooth",
        "cut_color",
        "cut_width_mm",
        "label_color",
        "label_size_mm",
    )
    flags.add_one(
        "font",
        ". A bundled font ("
        + ", ".join(FontLibrary.BUNDLED)
        + ") or a TrueType font installed on this computer",
    )
    flags.group_of("font").add_argument(
        "--debug",
        action="store_true",
        help=flags.with_default("write intermediate masks and a red overlay", False),
    )


# region commands


def cmd_make(
    a: argparse.Namespace,
    size_calculator: SizeCalculator,
    pipeline: Pipeline,
    output: Output,
    images_from_web: ImageFetcher,
) -> int:
    images, folders = [], {}  # an image from a folder: the folder it came from
    for src in _expand(a.images):
        if not ImageFetcher.is_url(src) and Path(src).is_dir():
            found, skipped = ImageFiles.folder_images(src, not a.no_subfolders)
            print(
                f"  {src}: {len(found)} image{'s' * (len(found) != 1)}"
                + (
                    f" ({skipped} other file{'s' * (skipped != 1)} skipped)"
                    if skipped
                    else ""
                )
            )
            images += [str(p) for p in found]
            folders.update({str(p): Path(src) for p in found})
        else:
            images.append(src)
    if not images:
        raise SystemExit("no images to make")
    single = bool(a.output) and a.output.lower().endswith((".svg", ".png"))
    if single and len(images) > 1:
        raise SystemExit(
            f"-o NAME{Path(a.output).suffix} only works with a single image; use -o DIR"
        )
    if a.png_px is not None and a.png_dpi is not None:
        raise SystemExit("give --png-px or --png-dpi, not both")
    for flag, v in (("--png-px", a.png_px), ("--png-dpi", a.png_dpi)):
        if v is not None and v <= 0:
            raise SystemExit(f"{flag} must be above 0")
    if a.grid_mm is not None and a.grid_mm <= 0:
        raise SystemExit("--grid-mm must be above 0")
    table = size_calculator.for_grid(a.grid_mm) if a.grid_mm else BUILTIN
    s = size_calculator.settings_with_size(
        {k: v for k, v in vars(a).items() if k in FIGURE_OPTIONS and v is not None},
        table,
    )
    scale = (
        a.png_dpi / 25.4
        if a.png_dpi
        else PngWriter.px_per_mm(a.png_px or PX_PER_SQUARE, table.grid_mm)
    )
    for src in images:
        img = (
            images_from_web.fetch_image(src)
            if ImageFetcher.is_url(src)
            else ImageFiles.local_path(src)
        )
        out_file = Path(a.output) if single else None
        # next to the image, or for a link (its copy lives in the cache) here
        here = Path.cwd() if ImageFetcher.is_url(src) else img.parent
        out_dir = out_file.parent if out_file else Path(a.output) if a.output else here
        if (
            a.output and not out_file and src in folders
        ):  # (its subfolder, inside -o DIR)
            out_dir = out_dir / img.resolve().parent.relative_to(folders[src].resolve())
        m = build_mini(
            img,
            s,
            pipeline=pipeline,
            bleed_mm=a.bleed_mm,
            use_cache=not a.no_cache,
            debug_dir=out_dir / "debug" if a.debug else None,
        )
        stem = out_file.with_suffix("") if out_file else out_dir / safe_name(m.name)
        outs = []
        if a.format in ("svg", "both"):
            outs += output.svg.write_copies(m, stem.with_suffix(".svg"), a.copies)
        if a.format in ("png", "both"):
            outs += output.png.write_copies(
                m, stem.with_suffix(".png"), scale, a.copies
            )
        for out in outs:
            print(f"  -> {out}")
        _warn_width(img.name, s, m, table, size_calculator)
    return 0


def cmd_sheet(a: argparse.Namespace, output: Output) -> int:
    minis = [(output.svg_reader.read(Path(p)), a.copies) for p in _expand(a.svgs)]
    custom = {
        k: v
        for k, v in (
            ("paper_width_mm", a.paper_width_mm),
            ("paper_height_mm", a.paper_height_mm),
        )
        if v is not None
    }
    if custom and a.paper not in (None, "custom"):
        raise SystemExit(
            "--paper-width-mm and --paper-height-mm are a custom paper size: "
            f"leave out --paper {a.paper}"
        )
    try:
        sh = SheetSettings.from_dict(
            dict(
                custom,
                paper=a.paper or ("custom" if custom else DS.paper),
                orientation=a.orientation,
                title=a.title,
                margin_mm=a.margin_mm,
                gap_mm=a.gap_mm,
                cut=a.cut,
                marks=a.marks,
                cut_folds=a.cut_folds,
                mat=a.mat,
            )
        )
    except ValueError as e:
        raise SystemExit(str(e).replace("sheet ", "--").replace("_", "-")) from None
    return write_sheet(minis, Path(a.output), sh, output, a.preview)


def write_sheet(
    minis,
    pdf: Path,
    sh: SheetSettings,
    output: Output,
    preview: bool = False,
) -> int:
    """The PDF sheet, its PNG previews, and cut by machine its cut files."""
    lay = sh.layout(output.packer, minis)
    output.pdf.write(lay, pdf, sh.title)
    n = len(lay.placements)
    print(
        f"  -> {pdf} ({n} piece{'s' * (n != 1)}, {lay.pages} page{'s' * (lay.pages != 1)}, "
        f"{sh.paper_text()})"
    )
    if sh.mat_warning():
        print(f"  ! note: {sh.mat_warning()}")
    if lay.machine:
        cut_file = output.cut_files.default_path(pdf)
        for p in output.cut_files.write(lay, cut_file, sh.cut_folds, sh.title):
            print(f"  -> {p} (cut file)")
    if preview:
        previews = output.previews.write(lay, pdf.with_suffix(".png"), title=sh.title)
        for p in previews:
            print(f"  -> {p}")
    return 0


def _warn_width(
    name: str, s: FigureSettings, m, table: SizeTable, size_calculator: SizeCalculator
) -> None:
    """Say so when a mini is wider than its creature size's squares."""
    warning = (
        ""
        if s.kind == "token"
        else size_calculator.width_warning(s.size, m.figure_width_mm, table)
    )
    if warning:
        print(f"  ! {name}: {warning}", file=sys.stderr)


def run_project(
    proj: Project,
    size_calculator: SizeCalculator,
    pipeline: Pipeline,
    output: Output,
    debug: bool = False,
    preview: bool = False,
    use_cache: bool = True,
) -> int:
    if not proj.figures:
        raise SystemExit(f"{proj.path}: no 'figures' listed")
    out_dir = proj.output_dir
    minis = []
    sh = proj.sheet
    for f in proj.figures:
        m = build_mini(
            f.image,
            f.settings,
            pipeline=pipeline,
            bleed_mm=sh.figure_bleed,
            use_cache=use_cache,
            debug_dir=out_dir / "debug" if debug or proj.debug else None,
        )
        svgs = output.svg.write_copies(m, out_dir / f.svg_name(), f.settings.copies)
        for out in svgs:
            print(f"  -> {out}")
        _warn_width(f.image.name, f.settings, m, proj.sizes, size_calculator)
        minis.append((m, f.settings.copies))
    if sh.enabled:
        write_sheet(minis, proj.sheet_path, sh, output, preview or sh.preview)
    return 0


def cmd_batch(
    a: argparse.Namespace,
    project_store: ProjectStore,
    size_calculator: SizeCalculator,
    pipeline: Pipeline,
    output: Output,
) -> int:
    return run_project(
        project_store.load(Path(a.config)),
        size_calculator,
        pipeline,
        output,
        a.debug,
        a.preview,
        not a.no_cache,
    )


def cmd_gui(a: argparse.Namespace) -> int:
    try:
        from .gui.app import run
    except ImportError as e:
        raise SystemExit(
            f"The GUI needs PySide6: pip install 'papermini[gui]'  ({e})"
        ) from None
    return run(a.files)


def _expand(patterns: list[str]) -> list[str]:
    """Expand globs ourselves (Windows shells do not); links are passed through."""
    out: list[str] = []
    for p in patterns:
        if ImageFetcher.is_url(p):
            out.append(p)
            continue
        p = str(ImageFiles.local_path(p))
        hits = sorted(glob.glob(p)) if any(ch in p for ch in "*?[") else [p]
        if not hits:
            raise SystemExit(f"no files match {p!r}")
        out += hits
    for p in out:
        if not ImageFetcher.is_url(p) and not Path(p).exists():
            raise SystemExit(f"file not found: {p}")
    return out


def build_parser(
    size_calculator: SizeCalculator,
    project_store: ProjectStore,
    pipeline: Pipeline,
    output: Output,
    images_from_web: ImageFetcher,
) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="papermini",
        description="Turn illustrations into print-ready paper miniatures. "
        "Without a command, papermini opens the desktop app.",
    )
    p.add_argument("--version", action="version", version=f"papermini {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    mk = sub.add_parser("make", help="image(s) -> one SVG per figure")
    flags = OptionFlags(mk, FigureSettings, given_only={"size"})
    mk.add_argument(
        "images",
        nargs="+",
        metavar="IMAGE",
        help=f"image files ({ImageFiles.READABLE}), folders of them, or http(s) "
        "links to images",
    )
    mk.add_argument(
        "--no-subfolders",
        action="store_true",
        help=flags.with_default(
            "a folder: only its own images, not those in its subfolders", False
        ),
    )
    mk.add_argument(
        "-o",
        "--output",
        help=flags.with_default(
            "output .svg or .png (single image) or directory",
            None,
            none_means="next to the image; for a link, here",
        ),
    )
    mk.add_argument(
        "--format",
        choices=FORMATS,
        default=FORMATS[0],
        help=flags.with_default(
            "svg: the piece with its cut line, for printing and cutting machines; "
            "png: a picture of the whole piece, transparent around it, for a virtual "
            "tabletop; both",
            FORMATS[0],
        ),
    )
    mk.add_argument(
        "--png-px",
        type=float,
        help=flags.with_default(
            "PNG size: pixels per grid square (--grid-mm), so a Medium figure fits "
            "one square of a virtual tabletop",
            PX_PER_SQUARE,
        ),
    )
    mk.add_argument(
        "--png-dpi",
        type=float,
        help=flags.with_default(
            "PNG size as a resolution instead: the piece at the size it prints, "
            "this many pixels per inch",
            None,
            none_means="none, --png-px sets the size",
        ),
    )
    mk.add_argument(
        "--bleed-mm",
        type=float,
        default=0.0,
        help=flags.with_default(
            "print the edge colors this far beyond the cut line, for a sheet cut "
            "by machine (papermini sheet --cut machine); 0 = none",
            0.0,
            "mm",
        ),
    )
    add_figure_args(flags)
    mk.set_defaults(
        func=partial(
            cmd_make,
            size_calculator=size_calculator,
            pipeline=pipeline,
            output=output,
            images_from_web=images_from_web,
        )
    )

    sh = sub.add_parser("sheet", help="papermini SVGs -> printable PDF sheet")
    flags = OptionFlags(sh, SheetSettings, given_only={"paper"})
    sh.add_argument("svgs", nargs="+", help="SVGs written by papermini make")
    sh.add_argument(
        "-o",
        "--output",
        default=SHEET_PDF,
        help=flags.with_default("the PDF to write", SHEET_PDF),
    )
    flags.add(
        "copies",
        "paper",
        "paper_width_mm",
        "paper_height_mm",
        "orientation",
        "margin_mm",
        "gap_mm",
        "title",
        "preview",
        "cut",
        "marks",
        "cut_folds",
        "mat",
    )
    sh.set_defaults(func=partial(cmd_sheet, output=output))

    bt = sub.add_parser(
        "batch", help="YAML config: images + per-image options -> SVGs + sheet"
    )
    flags = OptionFlags(bt, SheetSettings)
    bt.add_argument("config", help="the project file (YAML) to build")
    bt.add_argument(
        "--debug",
        action="store_true",
        help=flags.with_default(
            "write intermediate masks and a red overlay of each figure", False
        ),
    )
    flags.add("preview")
    bt.add_argument(
        "--no-cache",
        action="store_true",
        help=flags.with_default("do not reuse cached model masks", False),
    )
    bt.set_defaults(
        func=partial(
            cmd_batch,
            project_store=project_store,
            size_calculator=size_calculator,
            pipeline=pipeline,
            output=output,
        )
    )

    gu = sub.add_parser(
        "gui", help="open the desktop app (also what papermini does without a command)"
    )
    gu.add_argument("files", nargs="*", help="images or a project .yaml to open")
    gu.set_defaults(func=cmd_gui)
    return p


COMMANDS = ("make", "sheet", "batch", "gui")


def route(argv: list[str]) -> list[str]:
    """Turn the program's arguments into a command: a command or an option runs the
    command line as given; no arguments, or only files (an image dropped on the program,
    or opened with it), open the desktop app with those files."""
    args = [
        a for a in argv if not a.startswith("-psn_")
    ]  # (older macOS adds a process id)
    if not args:
        return ["gui"]
    if args[0] in COMMANDS or args[0].startswith("-"):
        return args
    return ["gui", *args]


def main(argv: list[str] | None = None) -> int:
    size_calculator = SizeCalculator()
    fonts = FontLibrary()
    images_from_web = ImageFetcher()
    parser = build_parser(
        size_calculator,
        ProjectStore(size_calculator, images_from_web),
        Pipeline(fonts),
        Output(fonts),
        images_from_web,
    )
    a = parser.parse_args(route(sys.argv[1:] if argv is None else argv))
    try:
        return a.func(a)
    except (ValueError, FileNotFoundError, ModelError) as e:
        print(f"papermini: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
# endregion
