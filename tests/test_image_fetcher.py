"""Tests of images from links. No real network."""

import urllib.error
from pathlib import Path

import pytest

from papermini.support.image_fetcher import ImageFetcher


def test_link_is_downloaded_once_and_named_after_the_link(
    images_from_web, fake_web, figure_bytes
):
    url = "https://example.com/art/Red%20Goblin.webp?size=large"
    fake_web[url] = figure_bytes("WEBP")
    p = images_from_web.fetch_image(url)
    assert p.name == "Red Goblin.webp" and p.read_bytes() == fake_web[url]
    assert fake_web.asked == [(url, "papermini")]
    assert images_from_web.fetch_image(url) == p and len(fake_web.asked) == 1
    assert images_from_web.cached_image(url) == p


def test_link_without_extension_gets_one_from_the_content(
    images_from_web, fake_web, figure_bytes
):
    fake_web["https://example.com/image?id=7"] = figure_bytes("JPEG")
    got = images_from_web.fetch_image("https://example.com/image?id=7")
    assert got.name == "image.jpg"


def test_bad_links_give_readable_errors(images_from_web, fake_web, monkeypatch):
    with pytest.raises(ValueError, match="404 Not Found"):
        images_from_web.fetch_image("https://example.com/missing.png")
    fake_web["https://example.com/page"] = b"<html><body>a web page</body></html>"
    with pytest.raises(ValueError, match="not an image"):
        images_from_web.fetch_image("https://example.com/page")
    fake_web["https://down.example/x.png"] = urllib.error.URLError("no route to host")
    with pytest.raises(ValueError, match="no route to host"):
        images_from_web.fetch_image("https://down.example/x.png")
    monkeypatch.setattr(images_from_web, "MAX_BYTES", 1000)
    fake_web["https://example.com/huge.png"] = b"\0" * 5000
    with pytest.raises(ValueError, match="larger than"):
        images_from_web.fetch_image("https://example.com/huge.png")
    assert not list(images_from_web.folder().rglob("*.png"))  # nothing half-written


def test_links_are_http_or_https():
    assert ImageFetcher.is_url("https://a/b.png") and ImageFetcher.is_url(
        " HTTP://a/b "
    )
    assert not ImageFetcher.is_url("C:/art/b.png")
    assert not ImageFetcher.is_url(Path("x.png"))


def test_clear_images_keeps_the_ones_in_use(images_from_web, fake_web, figure_bytes):
    fake_web["https://example.com/a.png"] = figure_bytes()
    fake_web["https://example.com/b.png"] = figure_bytes()
    a = images_from_web.fetch_image("https://example.com/a.png")
    b = images_from_web.fetch_image("https://example.com/b.png")
    assert images_from_web.cached_images() == sorted([a, b])
    assert images_from_web.clear_images(keep=[a]) == 1
    assert images_from_web.cached_images() == [a] and not b.exists()
    # a cleared link is downloaded again
    assert images_from_web.fetch_image("https://example.com/b.png").exists()
    assert images_from_web.clear_images() == 2
    assert images_from_web.cached_images() == []
