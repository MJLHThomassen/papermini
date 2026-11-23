"""Command line interface: ``papermini add | build | gui``."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .commands.add_command import AddCommand
from .commands.build_command import BuildCommand
from .commands.figure_flags import FigureFlags
from .commands.image_arguments import ImageArguments
from .commands.sheet_flags import SheetFlags
from .output.output import Output
from .pipeline.pipeline import Pipeline
from .pipeline.segmentation.model_error import ModelError
from .project.project_store import ProjectStore
from .project.size_calculator import SizeCalculator
from .support.font_library import FontLibrary
from .support.image_fetcher import ImageFetcher

# region commands


def cmd_gui(a: argparse.Namespace) -> int:
    try:
        from .gui.app import run
    except ImportError as e:
        raise SystemExit(
            f"The GUI needs PySide6: pip install 'papermini[gui]'  ({e})"
        ) from None
    return run(a.files)


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
    images = ImageArguments(images_from_web)
    figure_flags = FigureFlags(size_calculator)
    sheet_flags = SheetFlags()
    AddCommand(project_store, images, figure_flags, sheet_flags).add_to(sub)
    BuildCommand(
        project_store,
        size_calculator,
        pipeline,
        output,
        images,
        figure_flags,
        sheet_flags,
    ).add_to(sub)
    gu = sub.add_parser(
        "gui", help="open the desktop app (also what papermini does without a command)"
    )
    gu.add_argument("files", nargs="*", help="images or a project .yaml to open")
    gu.set_defaults(func=cmd_gui)
    return p


COMMANDS = ("add", "build", "gui")


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
