"""The entry point of the command line, which creates the services its commands use."""

from __future__ import annotations

import sys

from .commands.command_line import CommandLine
from .output.output import Output
from .pipeline.pipeline import Pipeline
from .project.figure_builder import FigureBuilder
from .project.project_store import ProjectStore
from .project.size_calculator import SizeCalculator
from .support.font_library import FontLibrary
from .support.image_fetcher import ImageFetcher


def main(argv: list[str] | None = None) -> int:
    size_calculator = SizeCalculator()
    fonts = FontLibrary()
    images_from_web = ImageFetcher()
    command_line = CommandLine(
        ProjectStore(size_calculator, images_from_web),
        size_calculator,
        FigureBuilder(Pipeline(fonts)),
        Output(fonts),
        images_from_web,
    )
    return command_line.run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
