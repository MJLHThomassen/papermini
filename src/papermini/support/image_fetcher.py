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

from .cache_folder import CacheFolder
from .image_files import ImageFiles

_EXT_FOR = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "MPO": ".jpg",
    "WEBP": ".webp",
    "BMP": ".bmp",
    "TIFF": ".tif",
}


class ImageFetcher:
    """Downloads images from the web: a link (http/https URL) is downloaded once into
    the cache.

    Projects keep the link, not the cached file, so they stay portable; the image is
    fetched again only when the cache has been cleared.
    """

    # no illustration is this big; stops a wrong link filling the disk
    MAX_BYTES = 100 << 20

    @staticmethod
    def is_url(s: str | Path) -> bool:
        """True for an http(s) link."""
        return isinstance(s, str) and s.strip().lower().startswith(
            ("http://", "https://")
        )

    @staticmethod
    def folder() -> Path:
        """The folder in the cache that holds the downloaded images."""
        return CacheFolder.path() / "images"

    def cached_image(self, url: str) -> Path | None:
        """The downloaded copy of ``url``, or None if it is not in the cache."""
        d = self.folder() / self._key(url)
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if ImageFiles.is_image_file(p):
                    return p
        return None

    def cached_images(self) -> list:
        """The downloaded copies of every link in the cache."""
        d = self.folder()
        if not d.is_dir():
            return []
        return sorted(
            p
            for sub in d.iterdir()
            if sub.is_dir()
            for p in sub.iterdir()
            if ImageFiles.is_image_file(p)
        )

    def clear_images(self, keep=()) -> int:
        """Delete the downloaded images, except the files in ``keep`` (images that open
        figures use); returns how many were deleted. A link is downloaded again when a
        project that uses it opens."""
        d = self.folder()
        if not d.is_dir():
            return 0
        keep = {os.path.normcase(os.path.abspath(p)) for p in keep}
        gone = 0
        for sub in sorted(d.iterdir()):
            if not sub.is_dir() or any(
                os.path.normcase(os.path.abspath(p)) in keep for p in sub.iterdir()
            ):
                continue
            images = sum(ImageFiles.is_image_file(p) for p in sub.iterdir())
            shutil.rmtree(sub, ignore_errors=True)
            if not sub.exists():
                gone += images
        return gone

    def fetch_image(
        self, url: str, timeout: float = 30.0, cancel: threading.Event | None = None
    ) -> Path:
        """Download the image at ``url`` (once; later calls use the cache) and return its
        path.

        Raises ValueError with a readable message when the link fails or is not an image.
        """
        url = url.strip()
        hit = self.cached_image(url)
        if hit is not None:
            return hit
        data = self._download(url, timeout, cancel)
        try:
            with Image.open(io.BytesIO(data)) as im:
                fmt = im.format
        except Exception:  # noqa: BLE001 - any decode failure means "not an image"
            fmt = None
        ext = _EXT_FOR.get(fmt or "")
        if ext is None:
            if fmt:
                raise ValueError(
                    f"{url} is a {fmt} image; papermini reads {ImageFiles.READABLE}"
                )
            raise ValueError(
                f"{url} is not an image (a web page? use the link of the image itself)"
            )
        dest = self.folder() / self._key(url) / (self._name(url) + ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(
            dest.name + f".{os.getpid()}.{threading.get_ident()}.part"
        )
        part.write_bytes(data)
        os.replace(part, dest)
        return dest

    def _download(
        self, url: str, timeout: float, cancel: threading.Event | None
    ) -> bytes:
        """The bytes at ``url``, at most ``MAX_BYTES`` of them."""
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
                    if size > self.MAX_BYTES:
                        raise ValueError(
                            f"{url} is larger than {self.MAX_BYTES >> 20} MB, "
                            "too big for an image"
                        )
                    chunks.append(chunk)
        except urllib.error.HTTPError as e:
            raise ValueError(f"could not download {url}: {e.code} {e.reason}") from None
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise ValueError(f"could not download {url}: {reason}") from None
        return b"".join(chunks)

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _name(url: str) -> str:
        """A readable file name stem from the link (the figure's name in the app)."""
        last = urllib.parse.unquote(
            urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        )
        stem = Path(last).stem if ImageFiles.is_image_file(last) else last
        stem = re.sub(r"[^\w\- .()]+", "_", stem).strip(" ._")
        return stem[:80] or "image"
