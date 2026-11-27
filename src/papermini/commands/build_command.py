from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from ..output.output import Output
from ..output.png_writer import PX_PER_SQUARE, PngWriter
from ..pipeline.mini import Mini
from ..project.figure_builder import FigureBuilder
from ..project.figure_entry import FigureEntry
from ..project.project import Project
from ..project.project_store import ProjectStore
from ..project.sheet_settings import SheetSettings
from ..project.size_calculator import SizeCalculator
from .add_command import PROJECT_SUFFIXES
from .figure_flags import FigureFlags
from .image_arguments import ImageArguments
from .image_source import ImageSource
from .sheet_flags import SheetFlags

SHEET_PDF = "minis.pdf"  # the sheet of images built without a project file
PIECE_SUFFIXES = (".svg", ".png")  # the file names -o can give one image's piece


class BuildCommand:
    """``papermini build``: builds a project file, or images without one, and writes
    the outputs asked for: the pieces as SVG or PNG files, and the sheet."""

    NAME = "build"

    def __init__(
        self,
        project_store: ProjectStore,
        size_calculator: SizeCalculator,
        figure_builder: FigureBuilder,
        output: Output,
        images: ImageArguments,
        figure_flags: FigureFlags,
        sheet_flags: SheetFlags,
    ):
        self._project_store = project_store
        self._size_calculator = size_calculator
        self._figure_builder = figure_builder
        self._output = output
        self._images = images
        self._figure_flags = figure_flags
        self._sheet_flags = sheet_flags

    def add_to(self, commands: argparse._SubParsersAction) -> None:
        """Add the command and its flags to ``commands``."""
        p = commands.add_parser(
            self.NAME,
            help="build a project file, or images, into pieces and a sheet",
            description="Build a project file (YAML), or images without one, and "
            "write the outputs the flags ask for. Without any, a project writes each "
            "figure as an SVG and the sheet, when the project makes one; images "
            "write an SVG each. The figure flags are for images; a project file "
            "holds its figures' settings (see papermini add).",
        )
        p.add_argument(
            "target",
            nargs="+",
            metavar="PROJECT_OR_IMAGE",
            help="a project file (YAML), or images: image files, folders of them, "
            "or http(s) links",
        )
        self._images.add_folder_flag(p)
        p.add_argument(
            "-o",
            "--output",
            help="the folder to write everything in, or for a single image the "
            "piece's file (NAME.svg or NAME.png) (default: the project's folders; "
            "for images, next to each image)",
        )
        out = p.add_argument_group("outputs")
        out.add_argument(
            "--svg",
            action="store_true",
            help="each figure as an SVG: the piece with its cut line, for printing "
            "and cutting machines",
        )
        out.add_argument(
            "--png",
            action="store_true",
            help="each figure as a PNG: a picture of the whole piece, transparent "
            "around it, for a virtual tabletop",
        )
        out.add_argument(
            "--sheet",
            action="store_true",
            help="the sheet to print (PDF) and, cut by machine, its cut files (SVG)",
        )
        out.add_argument(
            "--preview",
            action="store_true",
            help="a PNG preview of each page of the sheet, written with the sheet "
            "and the other outputs",
        )
        out.add_argument(
            "--png-px",
            type=float,
            help="PNG size: pixels per grid square, so a Medium figure fits one "
            f"square of a virtual tabletop (default: {PX_PER_SQUARE})",
        )
        out.add_argument(
            "--png-dpi",
            type=float,
            help="PNG size as a resolution instead: the piece at the size it "
            "prints, this many pixels per inch (default: none, --png-px sets the "
            "size)",
        )
        p.add_argument(
            "--debug",
            action="store_true",
            help="write intermediate masks and a red overlay of each figure "
            "(default: off)",
        )
        p.add_argument(
            "--no-cache",
            action="store_true",
            help="do not reuse cached model masks (default: off)",
        )
        self._figure_flags.add_to(p)
        self._sheet_flags.add_to(p)
        p.set_defaults(func=self.run)

    def run(self, args: argparse.Namespace) -> int:
        """Build what ``args`` names and write the outputs it asks for."""
        self._check_png_size(args)
        is_project = len(args.target) == 1 and args.target[0].lower().endswith(
            PROJECT_SUFFIXES
        )
        if is_project:
            project, piece_dirs = self._project(args)
        else:
            project, piece_dirs = self._images_project(args)
        if not project.figures:
            raise SystemExit(f"{project.path}: no 'figures' listed")
        sheet = self._sheet_flags.apply(args, project.sheet)
        formats = [f for f in ("svg", "png") if getattr(args, f)]
        write_sheet = args.sheet
        if not (formats or write_sheet):
            formats = ["svg"]
            write_sheet = is_project and sheet.enabled
        write_sheet = write_sheet or args.preview
        previews = args.preview or (is_project and sheet.preview)
        single = self._single_file(args)
        scale = (
            args.png_dpi / 25.4
            if args.png_dpi
            else PngWriter.px_per_mm(
                args.png_px or PX_PER_SQUARE, project.sizes.grid_mm
            )
        )
        minis: list[tuple[Mini, int]] = []
        for entry, folder in zip(project.figures, piece_dirs):
            m = self._figure_builder.build(
                entry.image,
                entry.settings,
                bleed_mm=sheet.figure_bleed,
                use_cache=not args.no_cache,
                debug_dir=folder / "debug" if args.debug or project.debug else None,
            )
            path = single or folder / entry.svg_name()
            copies = entry.settings.copies
            for out in self._output.exporter.pieces(m, path, formats, copies, scale):
                print(f"  -> {out}")
            self._warn_width(entry, m, project)
            minis.append((m, copies))
        if write_sheet:
            self._write_sheet(args, project, sheet, minis, previews, is_project)
        return 0

    def _project(self, args: argparse.Namespace) -> tuple[Project, list[Path]]:
        """The project file ``args`` names, and the folder of each figure's piece."""
        if (
            self._figure_flags.given(args)
            or args.grid_mm is not None
            or args.preset is not None
        ):
            raise SystemExit(
                "the figure flags are for images: a project file holds its figures' "
                "settings (change them with papermini add, in the file or in the app)"
            )
        project = self._project_store.load(Path(args.target[0]))
        folder = Path(args.output) if args.output else project.output_dir
        return project, [folder] * len(project.figures)

    def _images_project(self, args: argparse.Namespace) -> tuple[Project, list[Path]]:
        """The images ``args`` names as a project without a file, with the settings
        its flags give, and the folder of each figure's piece."""
        sources = self._images.sources(args.target, not args.no_subfolders)
        if not sources:
            raise SystemExit("no images to build")
        if self._single_file(args) and len(sources) > 1:
            raise SystemExit(
                f"-o NAME{Path(args.output).suffix} only works with a single image; "
                "use -o DIR"
            )
        table = self._figure_flags.table(args, Project().sizes)
        preset = self._figure_flags.preset(args)
        settings = self._figure_flags.settings(args, table, preset)
        project = Project(
            sizes=table,
            figures=[
                FigureEntry(src.image, replace(settings), source=src.link)
                for src in sources
            ],
        )
        return project, [self._piece_dir(args, src) for src in sources]

    def _piece_dir(self, args: argparse.Namespace, src: ImageSource) -> Path:
        """The folder an image's piece goes in: next to the image (a link's: here), or
        in the folder -o gives, an image from a folder in its subfolder there."""
        single = self._single_file(args)
        if single:
            return single.parent
        if not args.output:
            return Path.cwd() if src.link else src.image.parent
        folder = Path(args.output)
        if src.folder is not None:
            folder /= src.image.resolve().parent.relative_to(src.folder.resolve())
        return folder

    def _single_file(self, args: argparse.Namespace) -> Path | None:
        """The piece file -o gives a single image, or None."""
        if args.output and args.output.lower().endswith(PIECE_SUFFIXES):
            return Path(args.output)
        return None

    def _write_sheet(
        self,
        args: argparse.Namespace,
        project: Project,
        sheet: SheetSettings,
        minis: list[tuple[Mini, int]],
        previews: bool,
        is_project: bool,
    ) -> None:
        """Lay out ``minis`` on ``sheet`` and write its files."""
        if is_project:
            pdf = project.sheet_path
            if args.output:
                pdf = Path(args.output) / pdf.name
        else:
            single = self._single_file(args)
            folder = (
                single.parent
                if single
                else Path(args.output)
                if args.output
                else Path.cwd()
            )
            pdf = folder / SHEET_PDF
        lay = sheet.layout(self._output.packer, minis)
        files = self._output.exporter.sheet(
            lay, pdf, sheet.title, sheet.cut_folds, write_previews=previews
        )
        n = len(lay.placements)
        print(
            f"  -> {pdf} ({n} piece{'s' * (n != 1)}, {lay.pages} "
            f"page{'s' * (lay.pages != 1)}, {sheet.paper_text()})"
        )
        if sheet.mat_warning():
            print(f"  ! note: {sheet.mat_warning()}")
        for p in files.cut_files:
            print(f"  -> {p} (cut file)")
        for p in files.previews:
            print(f"  -> {p}")

    def _warn_width(self, entry: FigureEntry, m: Mini, project: Project) -> None:
        """Say so when a mini is wider than its creature size's squares."""
        s = entry.settings
        warning = (
            ""
            if s.kind == "token"
            else self._size_calculator.width_warning(
                s.size, m.figure_width_mm, project.sizes
            )
        )
        if warning:
            print(f"  ! {entry.image.name}: {warning}", file=sys.stderr)

    @staticmethod
    def _check_png_size(args: argparse.Namespace) -> None:
        """Refuse PNG sizes that cannot be used."""
        if args.png_px is not None and args.png_dpi is not None:
            raise SystemExit("give --png-px or --png-dpi, not both")
        for flag, v in (("--png-px", args.png_px), ("--png-dpi", args.png_dpi)):
            if v is not None and v <= 0:
                raise SystemExit(f"{flag} must be above 0")
