"""Tests of downloading the model files, without the network."""

import sys
import threading
import urllib.request
from pathlib import Path

import pytest

from papermini.pipeline.segmentation.cache_folder import CacheFolder
from papermini.pipeline.segmentation.downloader import Downloader
from papermini.pipeline.segmentation.model_error import ModelError


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
    monkeypatch.setattr(sys, "stderr", None)  # like the windowed app: no console
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, timeout: FakeResponse([b"a" * 10, b"b" * 10]),
    )
    seen = []
    dest = Downloader().download(
        "https://example.org/m.onnx",
        tmp_path / "m.onnx",
        progress=lambda d, t, _m: seen.append((d, t)),
    )
    assert dest.read_bytes() == b"a" * 10 + b"b" * 10 and seen == [(10, 20), (20, 20)]

    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ModelError, match="cancelled"):
        Downloader().download(
            "https://example.org/m.onnx", tmp_path / "n.onnx", cancel=cancel
        )
    assert not (tmp_path / "n.onnx").exists() and not list(tmp_path.glob("*.part"))


def test_tests_never_use_the_network_or_the_real_cache(tmp_path):
    """Regression: GUI tests built with the real default model, downloading it on CI;
    once the app asked before downloading, CI hung on the invisible dialog."""
    assert str(CacheFolder.path()) != str(Path.home() / ".cache" / "papermini")
    with pytest.raises(AssertionError, match="must not use the network"):
        Downloader().download("https://example.org/m.onnx", tmp_path / "m.onnx")
