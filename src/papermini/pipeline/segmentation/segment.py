"""This module lists the built-in segmentation models that remove an image's
background, in ``ONNX_MODELS``, and holds the event that stops their downloads and
builds.

Besides these, a model can be ``alpha``, which uses the image's own transparency, or
the path of a custom ONNX model that takes RMBG-1.4-style input.
"""

from __future__ import annotations

import threading

from .builtin_model import BuiltinModel

DEFAULT_MODEL = "rmbg-1.4"

ONNX_MODELS: dict[str, BuiltinModel] = {
    "rmbg-1.4": BuiltinModel(
        title="BRIA RMBG-1.4",
        about="Fast and good on most artwork (the default).",
        licence="non-commercial use only",
        commercial=False,
        # BRIA's licence page is gone and the repository has no licence file;
        # the model card states the licence
        licence_url="https://huggingface.co/briaai/RMBG-1.4",
        mb=176,
        page="https://huggingface.co/briaai/RMBG-1.4",
        url="https://huggingface.co/briaai/RMBG-1.4/resolve/main/onnx/model.onnx",
        file="rmbg-1.4.onnx",
        size=1024,
        mean=0.5,
        std=1.0,
        post="minmax",  # stretch the output to 0-1, as BRIA's own pipeline does
    ),
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
    ONNX_MODELS[_name] = BuiltinModel(
        title=_title,
        about=_about,
        licence="MIT",
        commercial=True,
        licence_url="https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE",
        mb=_mb,
        page="https://github.com/ZhengPeng7/BiRefNet",
        url=_BIREFNET + _file,
        file=_name + ".onnx",
        size=1024,
        mean=(0.485, 0.456, 0.406),  # ImageNet normalisation
        std=(0.229, 0.224, 0.225),
        post="sigmoid",  # the model outputs logits
    )


Box = tuple[int, int, int, int]

# Set to abort a running model download or build (the GUI does this when it closes).
CANCEL = threading.Event()
