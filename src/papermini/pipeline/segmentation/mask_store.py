from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from ...support.cache_folder import CacheFolder


class MaskStore:
    """Keeps the raw masks the models made on disk, one PNG per image, model and
    crop."""

    def folder(self) -> Path:
        """Return where the masks are kept."""
        return CacheFolder.path() / "masks"

    def files(self) -> list:
        """Return the kept mask files."""
        d = self.folder()
        return sorted(d.glob("*.png")) if d.is_dir() else []

    def clear(self) -> int:
        """Delete the kept masks (and files left from interrupted writes); returns how
        many masks were deleted. A file another program holds open is skipped. The
        folder stays, so a build that is saving a mask meanwhile still can."""
        d = self.folder()
        gone = 0
        for f in sorted(d.iterdir()) if d.is_dir() else []:
            if f.is_file():
                try:
                    f.unlink()
                except OSError:
                    continue
                gone += f.suffix == ".png"
        return gone

    def file(self, image_bytes: bytes, model: str, crop) -> Path:
        """Return the file that keeps the mask of an image, model and crop."""
        tag = model
        if model.lower().endswith(".onnx") and Path(model).exists():
            st = Path(model).stat()  # a replaced model file must not reuse old masks
            tag += f"@{st.st_size}-{st.st_mtime_ns}"
        key = hashlib.sha256(image_bytes + f"|{tag}|{crop}".encode()).hexdigest()[:24]
        return self.folder() / f"{key}.png"

    def read(self, path: Path, shape: tuple[int, int]) -> np.ndarray | None:
        """Return the mask kept in ``path`` if it is there and has ``shape``."""
        if not path.exists():
            return None
        try:
            cached = np.asarray(Image.open(path).convert("L"))
        except OSError:
            return None  # damaged file: recompute and overwrite it
        return cached if cached.shape == shape else None

    def write(self, path: Path, mask: np.ndarray) -> None:
        """Save ``mask`` in ``path``, atomically: readers never see a half-written
        file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        Image.fromarray(mask).save(tmp, format="PNG")
        os.replace(tmp, path)
