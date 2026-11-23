from __future__ import annotations

import argparse
import sys

from .. import __version__
from ..output.figure_too_large_error import FigureTooLargeError
from ..output.output import Output
from ..pipeline.nothing_found_error import NothingFoundError
from ..pipeline.segmentation.model_error import ModelError
from ..pipeline.too_many_parts_error import TooManyPartsError
from ..project.figure_builder import FigureBuilder
from ..project.project_store import ProjectStore
from ..project.size_calculator import SizeCalculator
from ..support.image_fetcher import ImageFetcher
from .add_command import AddCommand
from .build_command import BuildCommand
from .figure_flags import FigureFlags
from .gui_command import GuiCommand
from .image_arguments import ImageArguments
from .sheet_flags import SheetFlags

MAC_PROCESS_ID = "-psn_"  # older macOS adds an argument with the process id

# what the user can do about an error of each type, in terms of the flags
ADVICE: dict[type[Exception], str] = {
    NothingFoundError: "try a lower --strength, a --crop or another --model",
    TooManyPartsError: "raise --min-area or --strength, or leave out --keep-all",
    FigureTooLargeError: "make it smaller with --height-mm, or with "
    "--token-diameter-mm for a token",
}


class CommandLine:
    """The command line: its commands, made with the services they use, and the
    parser of the program's arguments."""

    def __init__(
        self,
        project_store: ProjectStore,
        size_calculator: SizeCalculator,
        figure_builder: FigureBuilder,
        output: Output,
        images_from_web: ImageFetcher,
    ):
        images = ImageArguments(images_from_web)
        figure_flags = FigureFlags(size_calculator)
        sheet_flags = SheetFlags()
        self._commands = (
            AddCommand(project_store, images, figure_flags, sheet_flags),
            BuildCommand(
                project_store,
                size_calculator,
                figure_builder,
                output,
                images,
                figure_flags,
                sheet_flags,
            ),
            GuiCommand(),
        )
        self.parser = self._parser()

    def run(self, argv: list[str]) -> int:
        """Run the command that the program's arguments ``argv`` give (see ``route``)
        and return its exit code. An error in what it was given is printed, with what
        to do about it when ``ADVICE`` knows, and exit code 2."""
        args = self.parser.parse_args(self.route(argv))
        try:
            return args.func(args)
        except (ValueError, FileNotFoundError, ModelError) as e:
            print(f"papermini: error: {e}{self._advice(e)}", file=sys.stderr)
            return 2

    def route(self, argv: list[str]) -> list[str]:
        """Turn the program's arguments into a command: a command or an option runs the
        command line as given; no arguments, or only files (an image dropped on the
        program, or opened with it), open the desktop app with those files."""
        args = [a for a in argv if not a.startswith(MAC_PROCESS_ID)]
        if not args:
            return [GuiCommand.NAME]
        if args[0] in {c.NAME for c in self._commands} or args[0].startswith("-"):
            return args
        return [GuiCommand.NAME, *args]

    def _advice(self, error: Exception) -> str:
        """Return what the user can do about ``error``, in brackets after a space, or
        an empty string when ``ADVICE`` has nothing for its type."""
        for kind, advice in ADVICE.items():
            if isinstance(error, kind):
                return f" ({advice})"
        return ""

    def _parser(self) -> argparse.ArgumentParser:
        """The parser of the program's arguments, with a subcommand for each
        command."""
        p = argparse.ArgumentParser(
            prog="papermini",
            description="Turn illustrations into print-ready paper miniatures. "
            "Without a command, papermini opens the desktop app.",
        )
        p.add_argument(
            "--version", action="version", version=f"papermini {__version__}"
        )
        sub = p.add_subparsers(dest="cmd", required=True)
        for command in self._commands:
            command.add_to(sub)
        return p
