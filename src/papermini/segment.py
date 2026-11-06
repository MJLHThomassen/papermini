"""Background removal: turn an RGB image into a greyscale foreground mask (0-255).

Backends ("models"):

* ``rmbg-1.4``      BRIA RMBG-1.4 ONNX export, run with onnxruntime (default).
                    Non-commercial licence, see README.
* ``rembg:<name>``  any model of the optional ``rembg`` package, e.g.
                    ``rembg:u2net``, ``rembg:isnet-general-use``,
                    ``rembg:birefnet-general``.
* ``alpha``         use the image's own alpha channel (already cut-out PNGs).
* ``<file>.onnx``   a custom ONNX model that takes RMBG-style input.
"""

from __future__ import annotations

import hashlib
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image

DEFAULT_MODEL = "rmbg-1.4"

ONNX_MODELS = {
    "rmbg-1.4": {
        "url": "https://huggingface.co/briaai/RMBG-1.4/resolve/main/onnx/model.onnx",
        "file": "rmbg-1.4.onnx",
        "size": 1024,
        "mean": 0.5,
        "std": 1.0,
    },
}

Box = Tuple[int, int, int, int]


class ModelError(RuntimeError):
    """The requested segmentation model cannot be used (unknown, missing, not installed)."""

# Optional callback(done_bytes, total_bytes_or_None, message) for model downloads (GUI).
PROGRESS_HOOK = None
# Set to abort a running model download or build (the GUI does this when it closes).
CANCEL = threading.Event()


def check_cancel() -> None:
    if CANCEL.is_set():
        raise ModelError("cancelled")


def cache_dir() -> Path:
    """User cache directory (``$PAPERMINI_CACHE`` or ``~/.cache/papermini``)."""
    d = Path(os.environ.get("PAPERMINI_CACHE", Path.home() / ".cache" / "papermini"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def download(url: str, dest: Path, timeout: float = 30.0) -> Path:
    """Download ``url`` to ``dest`` with progress (atomic via a .part file).

    Works without a console (``papermini-gui`` has no stderr), times out on a
    stalled connection, checks the size, and stops early when ``CANCEL`` is set.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + f".{os.getpid()}.{threading.get_ident()}.part")
    err = sys.stderr
    if err is not None:
        print(f"Downloading {url}\n  -> {dest}", file=err)
    req = urllib.request.Request(url, headers={"User-Agent": "papermini"})
    bar = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0) or None
            if err is not None:
                from tqdm import tqdm

                bar = tqdm(total=total, unit="B", unit_scale=True, unit_divisor=1024, file=err)
            done = 0
            while True:
                if CANCEL.is_set():
                    raise ModelError("model download cancelled")
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if bar is not None:
                    bar.update(len(chunk))
                if PROGRESS_HOOK:
                    PROGRESS_HOOK(done, total, f"Downloading model {dest.name}")
        if total and done != total:
            raise ModelError(f"model download incomplete ({done} of {total} bytes); try again")
        part.replace(dest)
    except (OSError, urllib.error.URLError) as e:
        raise ModelError(f"could not download the model from {url}: {e}") from e
    finally:
        if bar is not None:
            bar.close()
        part.unlink(missing_ok=True)
    return dest


def parse_crop(spec, width: int, height: int) -> Optional[Box]:
    """Parse ``x0,y0,x1,y1`` (fractions 0-1 or pixels) into a pixel box.

    ``spec`` may be a string or a sequence of four numbers. If every value is
    <= 1 the values are fractions of the image size, otherwise pixels.
    """
    if spec is None or spec == "":
        return None
    if isinstance(spec, str):
        vals = [float(v) for v in spec.replace(" ", "").split(",")]
    else:
        vals = [float(v) for v in spec]
    if len(vals) != 4:
        raise ValueError(f"crop needs 4 values x0,y0,x1,y1, got {spec!r}")
    if all(v <= 1.0 for v in vals):
        vals = [vals[0] * width, vals[1] * height, vals[2] * width, vals[3] * height]
    x0, y0, x1, y1 = (int(round(v)) for v in vals)
    x0, x1 = max(0, min(x0, x1)), min(width, max(x0, x1))
    y0, y1 = max(0, min(y0, y1)), min(height, max(y0, y1))
    if x1 - x0 < 8 or y1 - y0 < 8:
        raise ValueError(f"crop {spec!r} is empty for a {width}x{height} image")
    return x0, y0, x1, y1


class OnnxSegmenter:
    """RMBG-style ONNX model: RGB resized to size x size, (x/255 - mean)/std, CHW."""

    def __init__(self, path: Path, size: int = 1024, mean: float = 0.5, std: float = 1.0):
        import onnxruntime as ort

        self.sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        inp = self.sess.get_inputs()[0]
        self.input_name = inp.name
        shape = inp.shape
        if len(shape) == 4 and isinstance(shape[2], int) and isinstance(shape[3], int):
            self.size = (shape[3], shape[2])
        else:
            self.size = (size, size)
        self.mean, self.std = mean, std

    def __call__(self, im: Image.Image) -> np.ndarray:
        x = np.asarray(im.convert("RGB").resize(self.size, Image.BILINEAR), np.float32) / 255.0
        x = (x - self.mean) / self.std
        x = x.transpose(2, 0, 1)[None]
        out = self.sess.run(None, {self.input_name: x})[0]
        out = np.squeeze(out).astype(np.float32)
        if out.ndim != 2:
            out = out.reshape(out.shape[-2:])
        out = (out - out.min()) / (out.max() - out.min() + 1e-8)
        m = Image.fromarray((out * 255).astype(np.uint8)).resize(im.size, Image.BILINEAR)
        return np.asarray(m)


class RembgSegmenter:
    def __init__(self, name: str):
        try:
            from rembg import new_session
        except ImportError as e:  # pragma: no cover - optional dependency
            raise ModelError(
                "the rembg models need the optional dependency: pip install 'papermini[rembg]'"
            ) from e
        self.session = new_session(name)

    def __call__(self, im: Image.Image) -> np.ndarray:
        from rembg import remove

        m = remove(im.convert("RGB"), session=self.session, only_mask=True)
        return np.asarray(m.convert("L"))


def rembg_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("rembg") is not None


def get_segmenter(model: str):
    if model.startswith("rembg:"):
        return RembgSegmenter(model.split(":", 1)[1])
    if model in ONNX_MODELS:
        spec = ONNX_MODELS[model]
        path = cache_dir() / spec["file"]
        if not path.exists():
            download(spec["url"], path)
        return OnnxSegmenter(path, spec["size"], spec["mean"], spec["std"])
    if model.lower().endswith(".onnx"):
        path = Path(model).expanduser()
        if not path.exists():
            raise ModelError(f"model file not found: {path}")
        return OnnxSegmenter(path)
    known = ", ".join(list(ONNX_MODELS) + ["alpha", "rembg:<name>", "<file>.onnx"])
    raise ModelError(f"unknown model {model!r} (known: {known})")


_SEGMENTERS: dict = {}
_SEGMENTER_LOCK = threading.Lock()


def get_cached_segmenter(model: str):
    """One segmenter per model, created (and downloaded) only once, thread-safely."""
    with _SEGMENTER_LOCK:
        if model not in _SEGMENTERS:
            _SEGMENTERS[model] = get_segmenter(model)
        return _SEGMENTERS[model]


def has_alpha(im: Image.Image) -> bool:
    if im.mode not in ("RGBA", "LA", "PA") and not (im.mode == "P" and "transparency" in im.info):
        return False
    return im.convert("RGBA").getchannel("A").getextrema()[0] < 255


def compute_mask(
    im: Image.Image,
    model: str = DEFAULT_MODEL,
    crop: Optional[Box] = None,
    use_cache: bool = True,
    image_bytes: Optional[bytes] = None,
) -> np.ndarray:
    """Return a full-size greyscale mask (uint8 0-255) for ``im``.

    With ``crop`` the model only sees that region and the result is pasted into
    an otherwise empty mask - this is what makes busy backgrounds work.
    Results are cached by image content, model and crop.
    """
    W, H = im.size
    if model == "alpha":
        if not has_alpha(im):
            raise ModelError("model 'alpha' needs an image with transparency; "
                             "this one has none - pick another model")
        full = np.asarray(im.convert("RGBA").getchannel("A")).copy()
        if crop:
            keep = np.zeros_like(full)
            x0, y0, x1, y1 = crop
            keep[y0:y1, x0:x1] = full[y0:y1, x0:x1]
            full = keep
        return full

    cache_file = None
    if use_cache and image_bytes is not None:
        tag = model
        if model.lower().endswith(".onnx") and Path(model).exists():
            st = Path(model).stat()  # a replaced model file must not reuse old masks
            tag += f"@{st.st_size}-{st.st_mtime_ns}"
        key = hashlib.sha256(image_bytes + f"|{tag}|{crop}".encode()).hexdigest()[:24]
        cache_file = cache_dir() / "masks" / f"{key}.png"
        if cache_file.exists():
            try:
                cached = np.asarray(Image.open(cache_file).convert("L"))
                if cached.shape == (H, W):
                    return cached
            except OSError:
                pass  # damaged cache file: recompute and overwrite it

    seg = get_cached_segmenter(model)
    rgb = im.convert("RGB")
    if has_alpha(im):  # the model sees a cut-out on white, not its hidden pixel colours
        rgb = Image.alpha_composite(Image.new("RGBA", im.size, (255, 255, 255, 255)),
                                    im.convert("RGBA")).convert("RGB")
    if crop:
        x0, y0, x1, y1 = crop
        full = np.zeros((H, W), np.uint8)
        full[y0:y1, x0:x1] = seg(rgb.crop(crop))
    else:
        full = seg(rgb)

    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        Image.fromarray(full).save(tmp, format="PNG")
        os.replace(tmp, cache_file)  # atomic: readers never see a half-written file
    return full
