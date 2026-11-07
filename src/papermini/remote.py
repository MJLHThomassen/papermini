"""Images from the web: a link (http/https URL) is downloaded once into the cache.

Projects keep the link, not the cached file, so they stay portable; the image is
fetched again only when the cache has been cleared.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Union

from PIL import Image

# image types papermini reads (Pillow and Qt both handle these)
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
IMAGE_FILTER = "Images (" + " ".join("*" + e for e in IMAGE_EXT) + ")"
READABLE = "PNG, JPG, WebP, BMP and TIFF"
_EXT_FOR = {"PNG": ".png", "JPEG": ".jpg", "MPO": ".jpg", "WEBP": ".webp", "BMP": ".bmp",
            "TIFF": ".tif"}
MAX_BYTES = 100 << 20  # no illustration is this big; stops a wrong link filling the disk


def is_url(s: Union[str, Path]) -> bool:
    """True for an http(s) link."""
    return isinstance(s, str) and s.strip().lower().startswith(("http://", "https://"))


def is_image_file(p: Union[str, Path]) -> bool:
    return Path(p).suffix.lower() in IMAGE_EXT


def local_path(s: Union[str, Path]) -> Path:
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


def cached_image(url: str) -> Optional[Path]:
    """The downloaded copy of ``url``, or None if it is not in the cache."""
    d = _cache_dir() / _key(url)
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if is_image_file(p):
                return p
    return None


def _key(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:20]


def _name(url: str) -> str:
    """A readable file name stem from the link (the figure's name in the app)."""
    last = urllib.parse.unquote(urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1])
    stem = Path(last).stem if is_image_file(last) else last
    stem = re.sub(r"[^\w\- .()]+", "_", stem).strip(" ._")
    return stem[:80] or "image"


def fetch_image(url: str, timeout: float = 30.0,
                cancel: Optional[threading.Event] = None) -> Path:
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
                    raise ValueError(f"{url} is larger than {MAX_BYTES >> 20} MB, "
                                     "too big for an image")
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
        raise ValueError(f"{url} is not an image (a web page? use the link of the image itself)")
    dest = _cache_dir() / _key(url) / (_name(url) + ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + f".{os.getpid()}.{threading.get_ident()}.part")
    part.write_bytes(data)
    os.replace(part, dest)
    return dest
