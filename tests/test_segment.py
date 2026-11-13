"""Segmentation backends without the real models: a fake onnxruntime session stands in
for the ONNX file, and no network access happens."""

import sys
import threading
import time
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from papermini import segment
from papermini.segment import ModelError, OnnxSegmenter


class FakeInput:
    def __init__(self, type_="tensor(float)"):
        self.name, self.shape, self.type = "input", [1, 3, "h", "w"], type_


class FakeSession:
    """Records the model input and returns a fixed output."""

    output = None
    seen = None
    input_type = "tensor(float)"

    def __init__(self, path, providers=None):
        pass

    def get_inputs(self):
        return [FakeInput(FakeSession.input_type)]

    def run(self, _names, feeds, run_options=None):
        FakeSession.seen = feeds["input"]
        if FakeSession.block is not None:  # a long run: wait until it is terminated
            FakeSession.block.set()
            while not run_options.terminate:
                time.sleep(0.01)
            raise RuntimeError("Exiting due to terminate flag being set to true.")
        return [FakeSession.output]

    block = None


class FakeRunOptions:
    terminate = False


@pytest.fixture
def fake_ort(monkeypatch):
    mod = types.SimpleNamespace(InferenceSession=FakeSession, RunOptions=FakeRunOptions)
    FakeSession.block = None
    monkeypatch.setitem(sys.modules, "onnxruntime", mod)
    FakeSession.input_type = "tensor(float)"
    return FakeSession


def grey(value=128, size=(40, 30)):
    return Image.new("RGB", size, (value, value, value))


def test_birefnet_uses_imagenet_normalisation_and_sigmoid(fake_ort, tmp_path):
    spec = segment.ONNX_MODELS["birefnet"]
    seg = OnnxSegmenter(tmp_path / "m.onnx", 8, spec["mean"], spec["std"], spec["post"])
    logits = np.full((1, 1, 8, 8), -6.0, np.float32)
    logits[..., 2:6, 2:6] = 6.0                                   # figure in the middle
    fake_ort.output = logits
    mask = seg(grey(128, (16, 16)))
    x = fake_ort.seen
    assert x.shape == (1, 3, 8, 8) and x.dtype == np.float32
    expected = (128 / 255 - np.array(spec["mean"])) / np.array(spec["std"])
    assert np.allclose(x[0, :, 0, 0], expected, atol=1e-5)       # per-channel mean/std
    assert mask.shape == (16, 16)
    assert mask[8, 8] > 250 and mask[0, 0] < 5                    # sigmoid, not min-max


def test_sigmoid_models_pass_probabilities_through(fake_ort, tmp_path):
    seg = OnnxSegmenter(tmp_path / "m.onnx", 8, 0.5, 1.0, "sigmoid")
    fake_ort.output = np.full((1, 1, 8, 8), 0.4, np.float32)    # already 0-1
    assert np.all(np.abs(seg(grey()).astype(int) - 102) <= 1)   # not stretched or squashed


def test_rmbg14_output_is_stretched(fake_ort, tmp_path):
    seg = OnnxSegmenter(tmp_path / "m.onnx", 8, 0.5, 1.0, "minmax")
    out = np.full((1, 1, 8, 8), 0.2, np.float32)
    out[..., :4] = 0.6
    fake_ort.output = out
    m = seg(grey(size=(8, 8)))
    assert m.min() == 0 and m.max() == 255
    assert np.allclose(fake_ort.seen[0, 0, 0, 0], 128 / 255 - 0.5, atol=1e-5)


def test_float16_models_get_float16_input(fake_ort, tmp_path):
    fake_ort.input_type = "tensor(float16)"
    seg = OnnxSegmenter(tmp_path / "m.onnx", 8)
    fake_ort.output = np.zeros((1, 1, 8, 8), np.float16)
    seg(grey())
    assert fake_ort.seen.dtype == np.float16


def test_birefnet_downloads_from_github_without_a_token(monkeypatch, tmp_path, fake_ort):
    monkeypatch.setenv("PAPERMINI_CACHE", str(tmp_path / "cache"))
    got = []

    def fake_download(url, dest, **_):
        got.append((url, dest.name))
        dest.write_bytes(b"x")
        return dest

    monkeypatch.setattr(segment, "download", fake_download)
    for name in ("birefnet", "birefnet-lite"):
        seg = segment.get_segmenter(name)
        assert seg.post == "sigmoid"
        assert np.allclose(seg.mean, (0.485, 0.456, 0.406))
    assert [d for _, d in got] == ["birefnet.onnx", "birefnet-lite.onnx"]
    assert all(u.startswith("https://github.com/ZhengPeng7/BiRefNet/releases/download/")
               for u, _ in got)
    segment.get_segmenter("birefnet")                             # cached: no second download
    assert len(got) == 2


def test_rmbg2_is_gone():
    assert not hasattr(segment, "hf_token")
    with pytest.raises(ModelError, match="unknown model"):
        segment.get_segmenter("rmbg-2.0")


def test_rembg_is_gone():
    assert not hasattr(segment, "RembgSegmenter")
    with pytest.raises(ModelError, match="unknown model"):
        segment.get_segmenter("rembg:u2net")


def fake_downloads(monkeypatch, tmp_path):
    """Point the cache at tmp_path and record downloads instead of doing them."""
    monkeypatch.setenv("PAPERMINI_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(segment, "CONFIRM_DOWNLOAD", None)
    got = []

    def fake_download(url, dest, **_):
        got.append(dest.name)
        dest.write_bytes(b"new")
        return dest

    monkeypatch.setattr(segment, "download", fake_download)
    return got


def test_refused_download_explains_and_downloads_nothing(monkeypatch, tmp_path, fake_ort):
    got = fake_downloads(monkeypatch, tmp_path)
    asked = []
    monkeypatch.setattr(segment, "CONFIRM_DOWNLOAD", lambda m: asked.append(m) or False)
    with pytest.raises(ModelError, match="not downloaded.*Models and cache"):
        segment.get_segmenter("rmbg-1.4")
    assert asked == ["rmbg-1.4"] and got == []
    # an approved download goes ahead; a model that is already there is never asked about
    monkeypatch.setattr(segment, "CONFIRM_DOWNLOAD", lambda m: asked.append(m) or True)
    segment.get_segmenter("rmbg-1.4")
    segment.get_segmenter("rmbg-1.4")
    assert asked == ["rmbg-1.4", "rmbg-1.4"] and got == ["rmbg-1.4.onnx"]


def test_a_running_model_can_be_cancelled(fake_ort, tmp_path):
    """cancel_runs() stops a model run in progress (the GUI's Cancel button)."""
    seg = OnnxSegmenter(tmp_path / "m.onnx", 8)
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
    assert fake_ort.block.wait(5)            # the model is running
    assert segment.cancel_runs() == 1
    t.join(5)
    assert isinstance(result.get("error"), segment.Cancelled)
    assert segment.cancel_runs() == 0        # nothing left running


def test_a_build_can_be_cancelled_while_the_model_loads(monkeypatch):
    """Loading a model can take longer than running it (BiRefNet-lite: ~10 s): Cancel
    then stops the build as soon as the model is loaded, before it runs. The next
    build is not affected."""
    loading, loaded = threading.Event(), threading.Event()
    runs = []

    def slow_load(model):
        loading.set()
        assert loaded.wait(5)
        return lambda im: runs.append(1) or np.zeros(im.size[::-1], np.uint8)

    monkeypatch.setattr(segment, "get_cached_segmenter", slow_load)
    result = {}

    def build():
        try:
            with segment.cancellable():
                segment.compute_mask(grey(), "rmbg-1.4", use_cache=False)
        except Exception as e:  # noqa: BLE001
            result["error"] = e

    t = threading.Thread(target=build)
    t.start()
    assert loading.wait(5)                   # no model run yet, only the build
    assert segment.cancel_runs() == 1
    loaded.set()
    t.join(5)
    assert isinstance(result.get("error"), segment.Cancelled) and runs == []

    with segment.cancellable():               # a new build runs normally
        segment.compute_mask(grey(), "rmbg-1.4", use_cache=False)
    assert runs == [1] and segment.cancel_runs() == 0


def test_fetch_and_delete_model(monkeypatch, tmp_path, fake_ort):
    got = fake_downloads(monkeypatch, tmp_path)
    path = segment.fetch_model("birefnet-lite")
    assert path == tmp_path / "cache" / "birefnet-lite.onnx" and path.exists()
    segment.fetch_model("birefnet-lite")                 # already there: nothing to do
    assert got == ["birefnet-lite.onnx"]
    segment.get_cached_segmenter("birefnet-lite")
    path.write_bytes(b"damaged")
    segment.fetch_model("birefnet-lite", force=True)     # download again replaces the file
    assert got == ["birefnet-lite.onnx"] * 2 and path.read_bytes() == b"new"
    assert "birefnet-lite" not in segment._SEGMENTERS   # the old session is dropped
    segment.get_cached_segmenter("birefnet-lite")
    segment.delete_model("birefnet-lite")
    assert not path.exists() and "birefnet-lite" not in segment._SEGMENTERS
    segment.delete_model("birefnet-lite")                # deleting twice is fine


class FakeResponse:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.headers = {"Content-Length": str(sum(len(c) for c in self.chunks))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, _n):
        return self.chunks.pop(0) if self.chunks else b""


def test_download_reports_progress_and_can_be_cancelled(monkeypatch, tmp_path):
    import threading

    monkeypatch.setattr(sys, "stderr", None)  # like the windowed app: no console
    monkeypatch.setattr(segment.urllib.request, "urlopen",
                        lambda req, timeout: FakeResponse([b"a" * 10, b"b" * 10]))
    seen = []
    dest = segment.download("https://example.org/m.onnx", tmp_path / "m.onnx",
                            progress=lambda d, t, _m: seen.append((d, t)))
    assert dest.read_bytes() == b"a" * 10 + b"b" * 10 and seen == [(10, 20), (20, 20)]

    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ModelError, match="cancelled"):
        segment.download("https://example.org/m.onnx", tmp_path / "n.onnx", cancel=cancel)
    assert not (tmp_path / "n.onnx").exists() and not list(tmp_path.glob("*.part"))


def test_tests_never_use_the_network_or_the_real_cache(tmp_path):
    """Regression: GUI tests built with the real default model, downloading it on CI;
    once the app asked before downloading, CI hung on the invisible dialog."""
    assert str(segment.cache_dir()) != str(Path.home() / ".cache" / "papermini")
    with pytest.raises(AssertionError, match="must not use the network"):
        segment.download("https://example.org/m.onnx", tmp_path / "m.onnx")


def test_clear_masks_keeps_the_folder_and_other_files():
    """Clearing the masks deletes them (and leftovers of interrupted writes) but keeps
    the folder, so a build saving a mask meanwhile still can, and the models."""
    d = segment.masks_dir()
    d.mkdir(parents=True)
    for name in ("a.png", "b.png", "c.123.456.tmp"):
        (d / name).write_bytes(b"x")
    model = segment.model_path(segment.DEFAULT_MODEL)
    model.write_bytes(b"model")
    assert [p.name for p in segment.cached_masks()] == ["a.png", "b.png"]
    assert segment.clear_masks() == 2
    assert d.is_dir() and not any(d.iterdir()) and segment.cached_masks() == []
    assert model.exists()
    assert segment.clear_masks() == 0


@pytest.mark.parametrize("model, noted", [("rmbg-1.4", True), ("birefnet-lite", False)])
def test_the_command_line_names_the_licence_when_it_downloads_a_model(monkeypatch, capsys,
                                                                     model, noted):
    monkeypatch.setattr(segment, "CONFIRM_DOWNLOAD", None)  # (the command line)
    monkeypatch.setattr(segment, "fetch_model", lambda m, **k: segment.model_path(m))
    monkeypatch.setattr(segment, "OnnxSegmenter", lambda *a, **k: object())
    segment.get_segmenter(model)
    err = capsys.readouterr().err
    assert ("non-commercial use only" in err) == noted
    if noted:
        assert "You are responsible for not using it commercially" in err
        assert "BiRefNet or BiRefNet lite (MIT licence)" in err


def test_only_rmbg_is_non_commercial():
    assert [m for m in segment.ONNX_MODELS if segment.non_commercial(m)] == ["rmbg-1.4"]
    assert not segment.non_commercial("alpha") and not segment.non_commercial("x.onnx")
