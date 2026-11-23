"""Tests of keeping the segmentation models, without the real models: a fake
onnxruntime session stands in for the ONNX file, and downloads are faked."""

import numpy as np
import pytest

from papermini.pipeline.segmentation import segment
from papermini.pipeline.segmentation.cancellation import Cancellation
from papermini.pipeline.segmentation.download_hooks import DownloadHooks
from papermini.pipeline.segmentation.model_error import ModelError
from papermini.pipeline.segmentation.model_not_downloaded_error import (
    ModelNotDownloadedError,
)
from papermini.pipeline.segmentation.segmenter_registry import SegmenterRegistry


@pytest.fixture
def registry(monkeypatch, tmp_path, fake_downloader):
    """Returns a registry with its cache in tmp_path and the fake downloads, as on the
    command line (nothing asks before a download)."""
    monkeypatch.setenv("PAPERMINI_CACHE", str(tmp_path / "cache"))
    return SegmenterRegistry(fake_downloader, Cancellation())


def test_birefnet_downloads_from_github_without_a_token(
    registry, fake_downloader, fake_ort
):
    for name in ("birefnet", "birefnet-lite"):
        seg = registry.get(name)
        assert seg.post == "sigmoid"
        assert np.allclose(seg.mean, (0.485, 0.456, 0.406))
    assert fake_downloader.got == ["birefnet.onnx", "birefnet-lite.onnx"]
    assert all(
        u.startswith("https://github.com/ZhengPeng7/BiRefNet/releases/download/")
        for u in fake_downloader.urls
    )
    # downloaded: a new registry loads it without a second download
    SegmenterRegistry(fake_downloader, Cancellation()).get("birefnet")
    assert len(fake_downloader.got) == 2


def test_rmbg2_is_gone(registry):
    assert not hasattr(segment, "hf_token")
    with pytest.raises(ModelError, match="unknown model"):
        registry.get("rmbg-2.0")


def test_rembg_is_gone(registry):
    assert not hasattr(segment, "RembgSegmenter")
    with pytest.raises(ModelError, match="unknown model"):
        registry.get("rembg:u2net")


def test_refused_download_explains_and_downloads_nothing(
    registry, fake_downloader, fake_ort
):
    asked, seen = [], []
    refuse = DownloadHooks(confirm=lambda m: asked.append(m) or False)
    with pytest.raises(
        ModelNotDownloadedError, match="rmbg-1.4 model is not downloaded"
    ):
        registry.get("rmbg-1.4", refuse)
    assert asked == ["rmbg-1.4"] and fake_downloader.got == []
    # an approved download goes ahead with progress; a model that is already there is
    # never asked about
    allow = DownloadHooks(
        confirm=lambda m: asked.append(m) or True,
        progress=lambda done, total, _msg: seen.append((done, total)),
    )
    registry.get("rmbg-1.4", allow)
    SegmenterRegistry(fake_downloader, Cancellation()).get("rmbg-1.4", allow)
    assert asked == ["rmbg-1.4", "rmbg-1.4"]
    assert fake_downloader.got == ["rmbg-1.4.onnx"] and seen[-1] == (30, 30)


def test_fetch_and_delete_model(registry, fake_downloader, tmp_path, fake_ort):
    fake_downloader.content = b"new"
    path = registry.fetch("birefnet-lite")
    assert path == tmp_path / "cache" / "birefnet-lite.onnx" and path.exists()
    registry.fetch("birefnet-lite")  # already there: nothing to do
    assert fake_downloader.got == ["birefnet-lite.onnx"]
    registry.get("birefnet-lite")
    assert registry.is_loaded("birefnet-lite")
    path.write_bytes(b"damaged")
    registry.fetch("birefnet-lite", force=True)  # download again replaces the file
    assert fake_downloader.got == ["birefnet-lite.onnx"] * 2
    assert path.read_bytes() == b"new"
    assert not registry.is_loaded("birefnet-lite")  # the old session is dropped
    registry.get("birefnet-lite")
    registry.delete("birefnet-lite")
    assert not path.exists() and not registry.is_loaded("birefnet-lite")
    registry.delete("birefnet-lite")  # deleting twice is fine


@pytest.mark.parametrize("model, noted", [("rmbg-1.4", True), ("birefnet-lite", False)])
def test_the_command_line_names_the_licence_when_it_downloads_a_model(
    capsys, fake_downloader, model, noted
):
    registry = SegmenterRegistry(
        fake_downloader, Cancellation(), lambda *a, **k: object()
    )
    registry.get(model)
    err = capsys.readouterr().err
    assert ("non-commercial use only" in err) == noted
    if noted:
        assert "You are responsible for not using it commercially" in err
        assert "BiRefNet or BiRefNet lite (MIT licence)" in err


def test_only_rmbg_is_non_commercial():
    non_commercial = SegmenterRegistry.non_commercial
    assert [m for m in segment.ONNX_MODELS if non_commercial(m)] == ["rmbg-1.4"]
    assert not non_commercial("alpha") and not non_commercial("x.onnx")
    assert SegmenterRegistry.free_models() == ["birefnet", "birefnet-lite"]
