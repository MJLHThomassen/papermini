from __future__ import annotations

import re
import urllib.parse
import urllib.request
from pathlib import Path


class ImageFiles:
    """The image files papermini reads: which files are images, the images in a folder
    and the names of the figures made from them."""

    # image types papermini reads (Pillow and Qt both handle these)
    EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
    FILTER = "Images (" + " ".join("*" + e for e in EXTENSIONS) + ")"
    READABLE = "PNG, JPG, WebP, BMP and TIFF"

    @staticmethod
    def is_image_file(p: str | Path) -> bool:
        """Whether ``p`` names a file of an image type papermini reads."""
        return Path(p).suffix.lower() in ImageFiles.EXTENSIONS

    @staticmethod
    def natural_key(name: str) -> list:
        """Sort key that counts numbers as numbers: "goblin 2" before "goblin 10"."""
        return [
            (0, int(s), "") if s.isdigit() else (1, 0, s)
            for s in re.split(r"(\d+)", name.lower())
            if s
        ]

    @staticmethod
    def folder_images(
        folder: str | Path, subfolders: bool = True
    ) -> tuple[list[Path], int]:
        """The images papermini reads in ``folder``, in natural order: the folder's own
        first, then (with ``subfolders``) each subfolder's the same way. Also how many
        other files were skipped. Hidden files and folders (a name starting with ".")
        are left out."""
        folder = Path(folder)
        images: list[Path] = []
        skipped = 0
        entries = sorted(
            (e for e in folder.iterdir() if not e.name.startswith(".")),
            key=lambda e: ImageFiles.natural_key(e.name),
        )
        for e in entries:
            if e.is_file():
                if ImageFiles.is_image_file(e):
                    images.append(e)
                else:
                    skipped += 1
        if subfolders:
            for e in entries:
                if e.is_dir():
                    more, other = ImageFiles.folder_images(e, True)
                    images += more
                    skipped += other
        return images, skipped

    @staticmethod
    def figure_names(images: list[Path], folder: str | Path) -> list[str | None]:
        """Names for figures from a folder's ``images``: None (named after the file, as
        usual), but for files that share a name, the subfolder in front, e.g.
        goblins-leader and orcs-leader (an image directly in ``folder`` keeps its own
        name)."""
        stems: dict = {}
        for p in images:
            stems.setdefault(p.stem.lower(), []).append(p)
        out: list[str | None] = []
        for p in images:
            rel = p.parent.relative_to(folder).parts
            out.append(
                "-".join(rel + (p.stem,))
                if len(stems[p.stem.lower()]) > 1 and rel
                else None
            )
        return out

    @staticmethod
    def local_path(s: str | Path) -> Path:
        """A path, also from a ``file://`` URI (what browsers and file managers hand
        over)."""
        if isinstance(s, str) and s.lower().startswith("file:"):
            u = urllib.parse.urlparse(s)
            p = urllib.request.url2pathname(u.path)
            if u.netloc and u.netloc != "localhost":  # a network share: \\server\share
                p = "//" + u.netloc + p
            return Path(p)
        return Path(s)
