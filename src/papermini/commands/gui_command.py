from __future__ import annotations

import argparse


class GuiCommand:
    """``papermini gui``: opens the desktop app, with the files given."""

    NAME = "gui"

    def add_to(self, commands: argparse._SubParsersAction) -> None:
        """Add the command and its arguments to ``commands``."""
        p = commands.add_parser(
            self.NAME,
            help="open the desktop app (also what papermini does without a command)",
        )
        p.add_argument("files", nargs="*", help="images or a project .yaml to open")
        p.set_defaults(func=self.run)

    def run(self, args: argparse.Namespace) -> int:
        """Open the desktop app with the files ``args`` gives, and wait until it
        closes."""
        try:
            from ..gui.app import run
        except ImportError as e:
            raise SystemExit(
                f"The desktop app needs PySide6 ({e}). Start it from the source "
                "folder with: uv run --all-extras papermini-gui"
            ) from None
        return run(args.files)
