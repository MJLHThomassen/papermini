from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from ..project.figure_entry import FigureEntry
from ..project.project import Project
from ..project.project_store import ProjectStore
from .figure_flags import FigureFlags
from .image_arguments import ImageArguments
from .sheet_flags import SheetFlags

PROJECT_SUFFIXES = (".yaml", ".yml")  # the file names of a project file


class AddCommand:
    """``papermini add``: adds images to a project file, with their settings, and
    sets the project's sheet. Makes the file when it does not exist yet."""

    NAME = "add"

    def __init__(
        self,
        project_store: ProjectStore,
        images: ImageArguments,
        figure_flags: FigureFlags,
        sheet_flags: SheetFlags,
    ):
        self._project_store = project_store
        self._images = images
        self._figure_flags = figure_flags
        self._sheet_flags = sheet_flags

    def add_to(self, commands: argparse._SubParsersAction) -> None:
        """Add the command and its flags to ``commands``."""
        p = commands.add_parser(
            self.NAME,
            help="add images to a project file (YAML), without building them",
            description="Add images to a project file, with the settings the flags "
            "give, and set its sheet. The file is made when it does not exist. "
            "papermini build builds it.",
        )
        p.add_argument("project", help="the project file (YAML) to add to or make")
        self._images.add_to(p, nargs="*")
        self._figure_flags.add_to(p)
        self._sheet_flags.add_to(p)
        p.set_defaults(func=self.run)

    def run(self, args: argparse.Namespace) -> int:
        """Add the images and settings ``args`` gives to its project file."""
        path = Path(args.project)
        if path.suffix.lower() not in PROJECT_SUFFIXES:
            raise SystemExit(f"{path.name}: a project file ends in .yaml")
        project = (
            self._project_store.load(path)
            if path.exists()
            else Project(path=path.resolve())
        )
        project.sizes = self._figure_flags.table(args, project.sizes)
        settings = self._figure_flags.settings(args, project.sizes)
        sources = self._images.sources(args.images, not args.no_subfolders)
        for src in sources:
            project.figures.append(
                FigureEntry(src.image, replace(settings), src.name, src.link)
            )
            print(f"  + {src.link or src.image}")
        project.sheet = self._sheet_flags.apply(args, project.sheet)
        self._project_store.save(project, path)
        n = len(project.figures)
        print(f"  -> {path} ({n} figure{'s' * (n != 1)})")
        return 0
