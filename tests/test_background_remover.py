"""Tests of turning a picture into a mask, with a stand-in model."""

import threading

import numpy as np
from PIL import Image

from papermini.pipeline.pipeline import Pipeline
from papermini.pipeline.segmentation.cancelled import Cancelled
from papermini.pipeline.segmentation.segmenter_registry import SegmenterRegistry


def test_a_build_can_be_cancelled_while_the_model_loads():
    """Loading a model can take longer than running it (BiRefNet-lite: ~10 s): Cancel
    then stops the build as soon as the model is loaded, before it runs. The next
    build is not affected."""
    loading, loaded = threading.Event(), threading.Event()
    runs = []

    def slow_load(path, *a, **k):
        loading.set()
        assert loaded.wait(5)
        return lambda im: runs.append(1) or np.zeros(im.size[::-1], np.uint8)

    SegmenterRegistry.path("rmbg-1.4").write_bytes(b"not a real model")
    pipeline = Pipeline(make_segmenter=slow_load)
    cancellation = pipeline.cancellation
    grey = Image.new("RGB", (40, 30), (128, 128, 128))
    result = {}

    def build():
        try:
            with cancellation.cancellable():
                pipeline.remover.mask(grey, "rmbg-1.4", use_cache=False)
        except Exception as e:  # noqa: BLE001
            result["error"] = e

    t = threading.Thread(target=build)
    t.start()
    assert loading.wait(5)  # no model run yet, only the build
    assert cancellation.cancel_runs() == 1
    loaded.set()
    t.join(5)
    assert isinstance(result.get("error"), Cancelled) and runs == []

    with cancellation.cancellable():  # a new build runs normally
        pipeline.remover.mask(grey, "rmbg-1.4", use_cache=False)
    assert runs == [1] and cancellation.cancel_runs() == 0
