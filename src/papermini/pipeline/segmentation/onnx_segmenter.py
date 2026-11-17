from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .cancelled import Cancelled
from .model_error import ModelError


class OnnxSegmenter:
    """ONNX segmentation model: RGB resized to size x size, (x/255 - mean)/std per
    channel, NCHW; the first output is the foreground mask.

    ``post`` turns the raw output into 0-1: ``"minmax"`` stretches it (RMBG-1.4),
    ``"sigmoid"`` applies a sigmoid when the output is logits rather than
    probabilities (BiRefNet).
    """

    def __init__(
        self, path: Path, size: int = 1024, mean=0.5, std=1.0, post: str = "minmax"
    ):
        import onnxruntime as ort

        try:
            self.sess = ort.InferenceSession(
                str(path), providers=["CPUExecutionProvider"]
            )
        except Exception as e:
            raise ModelError(f"cannot load the model {path.name}: {e}") from e
        inp = self.sess.get_inputs()[0]
        self.input_name = inp.name
        self.dtype = np.float16 if "float16" in inp.type else np.float32
        shape = inp.shape
        if len(shape) == 4 and isinstance(shape[2], int) and isinstance(shape[3], int):
            self.size = (shape[3], shape[2])
        else:
            self.size = (size, size)
        self.mean = np.asarray(mean, np.float32)
        self.std = np.asarray(std, np.float32)
        self.post = post

    def __call__(self, im: Image.Image) -> np.ndarray:
        x = (
            np.asarray(im.convert("RGB").resize(self.size, Image.BILINEAR), np.float32)
            / 255.0
        )
        x = (x - self.mean) / self.std
        x = x.transpose(2, 0, 1)[None].astype(self.dtype)
        out = self._run(x)
        out = np.squeeze(out).astype(np.float32)
        if out.ndim != 2:
            out = out.reshape(out.shape[-2:])
        if self.post == "sigmoid":
            if out.min() < 0.0 or out.max() > 1.0:  # logits
                out = 1.0 / (1.0 + np.exp(-np.clip(out, -60.0, 60.0)))
        else:
            out = (out - out.min()) / (out.max() - out.min() + 1e-8)
        m = Image.fromarray((np.clip(out, 0.0, 1.0) * 255).round().astype(np.uint8))
        return np.asarray(m.resize(im.size, Image.BILINEAR))

    def _run(self, x: np.ndarray) -> np.ndarray:
        """One model run that ``cancel_runs`` (or closing the window) can stop."""
        import onnxruntime as ort

        from .segment import _RUNS, _RUNS_LOCK, check_cancel

        ro = ort.RunOptions()
        with _RUNS_LOCK:
            _RUNS.add(ro)
        try:
            check_cancel()
            return self.sess.run(None, {self.input_name: x}, ro)[0]
        except Exception:
            if ro.terminate:
                raise Cancelled("cancelled") from None
            raise
        finally:
            with _RUNS_LOCK:
                _RUNS.discard(ro)
