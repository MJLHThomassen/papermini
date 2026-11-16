"""Images from the web: a link (http/https URL) is downloaded once into the cache.

Projects keep the link, not the cached file, so they stay portable; the image is
fetched again only when the cache has been cleared.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

# image types papermini reads (Pillow and Qt both handle these)
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
IMAGE_FILTER = "Images (" + " ".join("*" + e for e in IMAGE_EXT) + ")"
READABLE = "PNG, JPG, WebP, BMP and TIFF"
_EXT_FOR = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "MPO": ".jpg",
    "WEBP": ".webp",
    "BMP": ".bmp",
    "TIFF": ".tif",
}
MAX_BYTES = (
    100 << 20
)  # no illustration is this big; stops a wrong link filling the disk


def is_url(s: str | Path) -> bool:
    """True for an http(s) link."""
    return isinstance(s, str) and s.strip().lower().startswith(("http://", "https://"))


def is_image_file(p: str | Path) -> bool:
    return Path(p).suffix.lower() in IMAGE_EXT


def natural_key(name: str) -> list:
    """Sort key that counts numbers as numbers: "goblin 2" before "goblin 10"."""
    return [
        (0, int(s), "") if s.isdigit() else (1, 0, s)
        for s in re.split(r"(\d+)", name.lower())
        if s
    ]


def folder_images(
    folder: str | Path, subfolders: bool = True
) -> tuple[list[Path], int]:
    """The images papermini reads in ``folder``, in natural order: the folder's own first,
    then (with ``subfolders``) each subfolder's the same way. Also how many other files
    were skipped. Hidden files and folders (a name starting with ".") are left out."""
    folder = Path(folder)
    images: list[Path] = []
    skipped = 0
    entries = sorted(
        (e for e in folder.iterdir() if not e.name.startswith(".")),
        key=lambda e: natural_key(e.name),
    )
    for e in entries:
        if e.is_file():
            if is_image_file(e):
                images.append(e)
            else:
                skipped += 1
    if subfolders:
        for e in entries:
            if e.is_dir():
                more, other = folder_images(e, True)
                images += more
                skipped += other
    return images, skipped


def figure_names(images: list[Path], folder: str | Path) -> list[str | None]:
    """Names for figures from a folder's ``images``: None (named after the file, as
    usual), but for files that share a name, the subfolder in front, e.g. goblins-leader
    and orcs-leader (an image directly in ``folder`` keeps its own name)."""
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


def local_path(s: str | Path) -> Path:
    """A path, also from a ``file://`` URI (what browsers and file managers hand over)."""
    if isinstance(s, str) and s.lower().startswith("file:"):
        u = urllib.parse.urlparse(s)
        p = urllib.request.url2pathname(u.path)
        if u.netloc and u.netloc != "localhost":  # a network share: \\server\share\...
            p = "//" + u.netloc + p
        return Path(p)
    return Path(s)


def _cache_dir() -> Path:
    from .segment import cache_dir

    return cache_dir() / "images"


def cached_image(url: str) -> Path | None:
    """The downloaded copy of ``url``, or None if it is not in the cache."""
    d = _cache_dir() / _key(url)
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if is_image_file(p):
                return p
    return None


def cached_images() -> list:
    """The downloaded copies of every link in the cache."""
    d = _cache_dir()
    if not d.is_dir():
        return []
    return sorted(
        p
        for sub in d.iterdir()
        if sub.is_dir()
        for p in sub.iterdir()
        if is_image_file(p)
    )


def clear_images(keep=()) -> int:
    """Delete the downloaded images, except the files in ``keep`` (images that open
    figures use); returns how many were deleted. A link is downloaded again when a
    project that uses it opens."""
    d = _cache_dir()
    if not d.is_dir():
        return 0
    keep = {os.path.normcase(os.path.abspath(p)) for p in keep}
    gone = 0
    for sub in sorted(d.iterdir()):
        if not sub.is_dir() or any(
            os.path.normcase(os.path.abspath(p)) in keep for p in sub.iterdir()
        ):
            continue
        images = sum(is_image_file(p) for p in sub.iterdir())
        shutil.rmtree(sub, ignore_errors=True)
        if not sub.exists():
            gone += images
    return gone


def _key(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:20]


def _name(url: str) -> str:
    """A readable file name stem from the link (the figure's name in the app)."""
    last = urllib.parse.unquote(
        urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    )
    stem = Path(last).stem if is_image_file(last) else last
    stem = re.sub(r"[^\w\- .()]+", "_", stem).strip(" ._")
    return stem[:80] or "image"


def fetch_image(
    url: str, timeout: float = 30.0, cancel: threading.Event | None = None
) -> Path:
    """Download the image at ``url`` (once; later calls use the cache) and return its path.

    Raises ValueError with a readable message when the link fails or is not an image.
    """
    url = url.strip()
    hit = cached_image(url)
    if hit is not None:
        return hit
    req = urllib.request.Request(url, headers={"User-Agent": "papermini"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            chunks, size = [], 0
            while True:
                if cancel is not None and cancel.is_set():
                    raise ValueError("download cancelled")
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError(
                        f"{url} is larger than {MAX_BYTES >> 20} MB, "
                        "too big for an image"
                    )
                chunks.append(chunk)
    except urllib.error.HTTPError as e:
        raise ValueError(f"could not download {url}: {e.code} {e.reason}") from None
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise ValueError(f"could not download {url}: {reason}") from None
    data = b"".join(chunks)
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = im.format
    except Exception:  # noqa: BLE001 - any decode failure means "not an image"
        fmt = None
    ext = _EXT_FOR.get(fmt or "")
    if ext is None:
        if fmt:
            raise ValueError(f"{url} is a {fmt} image; papermini reads {READABLE}")
        raise ValueError(
            f"{url} is not an image (a web page? use the link of the image itself)"
        )
    dest = _cache_dir() / _key(url) / (_name(url) + ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + f".{os.getpid()}.{threading.get_ident()}.part")
    part.write_bytes(data)
    os.replace(part, dest)
    return dest
