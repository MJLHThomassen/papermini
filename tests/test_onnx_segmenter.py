"""Tests of the ONNX segmenter without the real models: a fake onnxruntime session
stands in for the ONNX file."""

import threading

import numpy as np
from PIL import Image

from papermini.pipeline.segmentation import segment
from papermini.pipeline.segmentation.cancellation import Cancellation
from papermini.pipeline.segmentation.cancelled import Cancelled
from papermini.pipeline.segmentation.onnx_segmenter import OnnxSegmenter


def grey(value=128, size=(40, 30)):
    return Image.new("RGB", size, (value, value, value))


def test_birefnet_uses_imagenet_normalisation_and_sigmoid(fake_ort, tmp_path):
    spec = segment.ONNX_MODELS["birefnet"]
    seg = OnnxSegmenter(
        tmp_path / "m.onnx",
        8,
        spec["mean"],
        spec["std"],
        spec["post"],
        cancellation=Cancellation(),
    )
    logits = np.full((1, 1, 8, 8), -6.0, np.float32)
    logits[..., 2:6, 2:6] = 6.0  # figure in the middle
    fake_ort.output = logits
    mask = seg(grey(128, (16, 16)))
    x = fake_ort.seen
    assert x.shape == (1, 3, 8, 8) and x.dtype == np.float32
    expected = (128 / 255 - np.array(spec["mean"])) / np.array(spec["std"])
    assert np.allclose(x[0, :, 0, 0], expected, atol=1e-5)  # per-channel mean/std
    assert mask.shape == (16, 16)
    assert mask[8, 8] > 250 and mask[0, 0] < 5  # sigmoid, not min-max


def test_sigmoid_models_pass_probabilities_through(fake_ort, tmp_path):
    seg = OnnxSegmenter(
        tmp_path / "m.onnx", 8, 0.5, 1.0, "sigmoid", cancellation=Cancellation()
    )
    fake_ort.output = np.full((1, 1, 8, 8), 0.4, np.float32)  # already 0-1
    assert np.all(
        np.abs(seg(grey()).astype(int) - 102) <= 1
    )  # not stretched or squashed


def test_rmbg14_output_is_stretched(fake_ort, tmp_path):
    seg = OnnxSegmenter(
        tmp_path / "m.onnx", 8, 0.5, 1.0, "minmax", cancellation=Cancellation()
    )
    out = np.full((1, 1, 8, 8), 0.2, np.float32)
    out[..., :4] = 0.6
    fake_ort.output = out
    m = seg(grey(size=(8, 8)))
    assert m.min() == 0 and m.max() == 255
    assert np.allclose(fake_ort.seen[0, 0, 0, 0], 128 / 255 - 0.5, atol=1e-5)


def test_float16_models_get_float16_input(fake_ort, tmp_path):
    fake_ort.input_type = "tensor(float16)"
    seg = OnnxSegmenter(tmp_path / "m.onnx", 8, cancellation=Cancellation())
    fake_ort.output = np.zeros((1, 1, 8, 8), np.float16)
    seg(grey())
    assert fake_ort.seen.dtype == np.float16


def test_a_running_model_can_be_cancelled(fake_ort, tmp_path):
    """cancel_runs() stops a model run in progress (the GUI's Cancel button)."""
    cancellation = Cancellation()
    seg = OnnxSegmenter(tmp_path / "m.onnx", 8, cancellation=cancellation)
    fake_ort.output = np.zeros((1, 1, 8, 8), np.float32)
    fake_ort.block = threading.Event()
    result = {}

    def run():
        try:
            seg(grey())
        except Exception as e:  # noqa: BLE001
            result["error"] = e

    t = threading.Thread(target=run)
    t.start()
    assert fake_ort.block.wait(5)  # the model is running
    assert cancellation.cancel_runs() == 1
    t.join(5)
    assert isinstance(result.get("error"), Cancelled)
    assert cancellation.cancel_runs() == 0  # nothing left running
