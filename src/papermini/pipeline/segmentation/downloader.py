from __future__ import annotations

import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from . import segment
from .model_error import ModelError


class Downloader:
    """Downloads model files."""

    def download(
        self,
        url: str,
        dest: Path,
        timeout: float = 30.0,
        progress=None,
        cancel: threading.Event | None = None,
    ) -> Path:
        """Download ``url`` to ``dest`` with progress (atomic via a .part file).

        Works without a console (``papermini-gui`` has no stderr), times out on a
        stalled connection, checks the size, and stops early when ``segment.CANCEL``
        or ``cancel`` is set. ``progress`` (default ``segment.PROGRESS_HOOK``) is
        called as ``progress(done_bytes, total_bytes_or_None, message)``.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(
            dest.suffix + f".{os.getpid()}.{threading.get_ident()}.part"
        )
        err = sys.stderr
        if err is not None:
            print(f"Downloading {url}\n  -> {dest}", file=err)
        progress = progress or segment.PROGRESS_HOOK
        req = urllib.request.Request(url, headers={"User-Agent": "papermini"})
        bar = None
        try:
            with (
                urllib.request.urlopen(req, timeout=timeout) as r,
                open(part, "wb") as f,
            ):
                total = int(r.headers.get("Content-Length") or 0) or None
                if err is not None:
                    from tqdm import tqdm

                    bar = tqdm(
                        total=total,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        file=err,
                    )
                done = 0
                while True:
                    if segment.CANCEL.is_set() or (
                        cancel is not None and cancel.is_set()
                    ):
                        raise ModelError("model download cancelled")
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if bar is not None:
                        bar.update(len(chunk))
                    if progress:
                        progress(done, total, f"Downloading model {dest.name}")
            if total and done != total:
                raise ModelError(
                    f"model download incomplete ({done} of {total} bytes); try again"
                )
            part.replace(dest)
        except (OSError, urllib.error.URLError) as e:
            raise ModelError(f"could not download the model from {url}: {e}") from e
        finally:
            if bar is not None:
                bar.close()
            part.unlink(missing_ok=True)
        return dest
