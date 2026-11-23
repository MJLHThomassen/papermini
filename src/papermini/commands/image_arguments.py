from __future__ import annotations

import argparse
import glob
from collections.abc import Callable
from pathlib import Path

from ..support.image_fetcher import ImageFetcher
from ..support.image_files import ImageFiles
from .image_source import ImageSource


class ImageArguments:
    """Reads the images given on the command line: files, glob patterns, folders and
    http(s) links, downloaded with ``images_from_web``."""

    def __init__(self, images_from_web: ImageFetcher):
        self._images_from_web = images_from_web

    def add_to(self, parser: argparse.ArgumentParser, nargs: str = "+") -> None:
        """Add the images and the folder flag to ``parser``."""
        parser.add_argument(
            "images",
            nargs=nargs,
            metavar="IMAGE",
            help=f"image files ({ImageFiles.READABLE}), folders of them, or http(s) "
            "links to images",
        )
        self.add_folder_flag(parser)

    def add_folder_flag(self, parser: argparse.ArgumentParser) -> None:
        """Add the flag that leaves out a folder's subfolders to ``parser``."""
        parser.add_argument(
            "--no-subfolders",
            action="store_true",
            help="a folder: only its own images, not those in its subfolders "
            "(default: off)",
        )

    def sources(
        self,
        given: list[str],
        subfolders: bool = True,
        log: Callable[[str], None] = print,
    ) -> list[ImageSource]:
        """The images ``given`` names, in order. A folder gives its images, and those
        of its subfolders with ``subfolders``; ``log`` hears how many it has."""
        out: list[ImageSource] = []
        for src in self._expand(given):
            if ImageFetcher.is_url(src):
                out.append(ImageSource(self._images_from_web.fetch_image(src), src))
            elif Path(src).is_dir():
                found, skipped = ImageFiles.folder_images(src, subfolders)
                log(
                    f"  {src}: {len(found)} image{'s' * (len(found) != 1)}"
                    + (
                        f" ({skipped} other file{'s' * (skipped != 1)} skipped)"
                        if skipped
                        else ""
                    )
                )
                names = ImageFiles.figure_names(found, src)
                out += [
                    ImageSource(p, folder=Path(src), name=name)
                    for p, name in zip(found, names)
                ]
            else:
                out.append(ImageSource(ImageFiles.local_path(src)))
        return out

    def _expand(self, patterns: list[str]) -> list[str]:
        """Expand globs here, since Windows shells do not; links are passed through."""
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
