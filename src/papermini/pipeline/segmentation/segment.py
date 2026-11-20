"""This module lists the segmentation models that remove an image's background, and
holds the hooks the desktop app sets for their downloads and builds.

Backends ("models"):

* ``rmbg-1.4``      BRIA RMBG-1.4 ONNX export, run with onnxruntime (default).
                    Licensed for non-commercial use only.
* ``birefnet``      BiRefNet general (MIT): sharper edges and fine detail, slower.
* ``birefnet-lite`` BiRefNet general with the small Swin-T backbone (MIT).
* ``alpha``         use the image's own alpha channel (already cut-out PNGs).
* ``<file>.onnx``   a custom ONNX model that takes RMBG-1.4-style input.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

DEFAULT_MODEL = "rmbg-1.4"

ONNX_MODELS = {
    "rmbg-1.4": {
        "title": "BRIA RMBG-1.4",
        "about": "Fast and good on most artwork (the default).",
        "licence": "non-commercial use only",
        "commercial": False,  # users accept that before it downloads
        # BRIA's licence page is gone and the repository has no licence file;
        # the model card states the licence
        "licence_url": "https://huggingface.co/briaai/RMBG-1.4",
        "mb": 176,
        "page": "https://huggingface.co/briaai/RMBG-1.4",
        "url": "https://huggingface.co/briaai/RMBG-1.4/resolve/main/onnx/model.onnx",
        "file": "rmbg-1.4.onnx",
        "size": 1024,
        "mean": 0.5,
        "std": 1.0,
        "post": "minmax",  # stretch the output to 0-1, as BRIA's own pipeline does
    },
}

_BIREFNET = "https://github.com/ZhengPeng7/BiRefNet/releases/download/v1/"


for _name, _title, _about, _mb, _file in (
    (
        "birefnet",
        "BiRefNet",
        "Sharpest edges and fine detail, but slow on a CPU.",
        928,
        "BiRefNet-general-epoch_244.onnx",
    ),
    (
        "birefnet-lite",
        "BiRefNet lite",
        "A smaller, faster BiRefNet.",
        214,
        "BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx",
    ),
):
    ONNX_MODELS[_name] = {
        "title": _title,
        "about": _about,
        "licence": "MIT",
        "commercial": True,
        "licence_url": "https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE",
        "mb": _mb,
        "page": "https://github.com/ZhengPeng7/BiRefNet",
        "url": _BIREFNET + _file,
        "file": _name + ".onnx",
        "size": 1024,
        "mean": (0.485, 0.456, 0.406),  # ImageNet normalisation
        "std": (0.229, 0.224, 0.225),
        "post": "sigmoid",  # the model outputs logits
    }


Box = tuple[int, int, int, int]

# Optional callback(done_bytes, total_bytes_or_None, message) for model downloads.
PROGRESS_HOOK = None

# Optional callback(model_name) -> bool, called before a built-in model is downloaded
# for a build. False refuses the download. The GUI asks the user here and downloads
# the model itself, with a progress dialog.
CONFIRM_DOWNLOAD: Callable[[str], bool] | None = None

# Set to abort a running model download or build (the GUI does this when it closes).
CANCEL = threading.Event()
