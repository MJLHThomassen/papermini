from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageSource:
    """An image given on the command line, ready to build."""

    image: Path  # for a link: the downloaded copy
    link: str | None = None  # the http(s) link it came from
    folder: Path | None = None  # the folder given on the command line it was found in
    name: str | None = None  # the figure's name, when the image's own name is taken
