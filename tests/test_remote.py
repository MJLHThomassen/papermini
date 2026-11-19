"""Tests of images from links and from folders. No real network."""

import urllib.error
import urllib.request
from pathlib import Path

import pytest

from papermini.support import remote


def test_link_is_downloaded_once_and_named_after_the_link(fake_web, figure_bytes):
    url = "https://example.com/art/Red%20Goblin.webp?size=large"
    fake_web[url] = figure_bytes("WEBP")
    p = remote.fetch_image(url)
    assert p.name == "Red Goblin.webp" and p.read_bytes() == fake_web[url]
    assert fake_web.asked == [(url, "papermini")]
    assert remote.fetch_image(url) == p and len(fake_web.asked) == 1  # from the cache
    assert remote.cached_image(url) == p


def test_link_without_extension_gets_one_from_the_content(fake_web, figure_bytes):
    fake_web["https://example.com/image?id=7"] = figure_bytes("JPEG")
    assert remote.fetch_image("https://example.com/image?id=7").name == "image.jpg"


def test_bad_links_give_readable_errors(fake_web, monkeypatch):
    with pytest.raises(ValueError, match="404 Not Found"):
        remote.fetch_image("https://example.com/missing.png")
    fake_web["https://example.com/page"] = b"<html><body>a web page</body></html>"
    with pytest.raises(ValueError, match="not an image"):
        remote.fetch_image("https://example.com/page")
    fake_web["https://down.example/x.png"] = urllib.error.URLError("no route to host")
    with pytest.raises(ValueError, match="no route to host"):
        remote.fetch_image("https://down.example/x.png")
    monkeypatch.setattr(remote, "MAX_BYTES", 1000)
    fake_web["https://example.com/huge.png"] = b"\0" * 5000
    with pytest.raises(ValueError, match="larger than"):
        remote.fetch_image("https://example.com/huge.png")
    assert not list(
        (remote._cache_dir()).rglob("*.png")
    )  # nothing half-written is kept


def test_link_and_file_uri_helpers(tmp_path):
    assert remote.is_url("https://a/b.png") and remote.is_url(" HTTP://a/b ")
    assert not remote.is_url("C:/art/b.png") and not remote.is_url(Path("x.png"))
    f = tmp_path / "my art" / "x.webp"
    assert remote.local_path(f.as_uri()) == f
    assert remote.local_path("plain.png") == Path("plain.png")
    assert remote.is_image_file("A.WEBP") and not remote.is_image_file("a.gif")


def test_clear_images_keeps_the_ones_in_use(fake_web, figure_bytes):
    fake_web["https://example.com/a.png"] = figure_bytes()
    fake_web["https://example.com/b.png"] = figure_bytes()
    a = remote.fetch_image("https://example.com/a.png")
    b = remote.fetch_image("https://example.com/b.png")
    assert remote.cached_images() == sorted([a, b])
    assert remote.clear_images(keep=[a]) == 1
    assert remote.cached_images() == [a] and not b.exists()
    # a cleared link is downloaded again
    assert remote.fetch_image("https://example.com/b.png").exists()
    assert remote.clear_images() == 2 and remote.cached_images() == []


def test_names_sort_in_natural_order():
    names = ["goblin 10", "Goblin 2", "goblin 1b", "ape"]
    assert sorted(names, key=remote.natural_key) == [
        "ape",
        "goblin 1b",
        "Goblin 2",
        "goblin 10",
    ]


def test_folder_images_own_first_then_subfolders(monsters):
    images, skipped = remote.folder_images(monsters)
    assert [p.relative_to(monsters).as_posix() for p in images] == [
        "leader.png",
        "goblins/goblin 2.png",
        "goblins/goblin 10.png",
        "goblins/leader.png",
        "orcs/leader.webp",
    ]
    assert (
        skipped == 2
    )  # notes.txt and orcs/readme.md; the hidden folder is not looked at
    only, skipped = remote.folder_images(monsters, subfolders=False)
    assert only == [monsters / "leader.png"] and skipped == 1


def test_same_names_get_their_subfolder(monsters):
    images, _ = remote.folder_images(monsters)
    assert remote.figure_names(images, monsters) == [
        None,
        None,
        None,
        "goblins-leader",
        "orcs-leader",
    ]  # leader.png keeps its name
    deep = [
        monsters / "a" / "b" / "x.png",
        monsters / "c" / "x.png",
        monsters / "y.png",
    ]
    assert remote.figure_names(deep, monsters) == ["a-b-x", "c-x", None]
