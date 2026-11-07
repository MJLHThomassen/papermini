"""Shared test setup: no test may use the real models, the network or the user's cache."""

import urllib.request

import pytest


@pytest.fixture(autouse=True)
def isolated_model_cache(monkeypatch, tmp_path_factory):
    """Every test gets an empty model and mask cache, and fetching a URL fails loudly.

    Tests that exercise downloads replace ``segment.download`` or ``urlopen`` with fakes.
    """
    from papermini import segment

    monkeypatch.setenv("PAPERMINI_CACHE", str(tmp_path_factory.mktemp("papermini-cache")))
    monkeypatch.setattr(segment, "_SEGMENTERS", {})  # no session left over from another test

    def no_network(req, *a, **k):
        url = getattr(req, "full_url", req)
        raise AssertionError(f"tests must not use the network (tried {url})")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
