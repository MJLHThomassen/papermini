"""Images from links (downloaded once into the cache) and WebP files. No real network."""

import io
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from papermini.cli import main
from papermini.project.figure_settings import FigureSettings
from papermini.project.project_files import load_project, save_project
from papermini.support import remote


def figure_bytes(fmt="PNG", size=(300, 450)) -> bytes:
    """A red oval on a transparent background: the alpha channel is the mask, no model needed."""
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse(
        (30, 30, size[0] - 30, size[1] - 30), fill=(200, 40, 30, 255)
    )
    buf = io.BytesIO()
    (im.convert("RGB") if fmt == "JPEG" else im).save(buf, fmt)
    return buf.getvalue()


def test_link_is_downloaded_once_and_named_after_the_link(fake_web):
    url = "https://example.com/art/Red%20Goblin.webp?size=large"
    fake_web[url] = figure_bytes("WEBP")
    p = remote.fetch_image(url)
    assert p.name == "Red Goblin.webp" and p.read_bytes() == fake_web[url]
    assert fake_web.asked == [(url, "papermini")]
    assert remote.fetch_image(url) == p and len(fake_web.asked) == 1  # from the cache
    assert remote.cached_image(url) == p


def test_link_without_extension_gets_one_from_the_content(fake_web):
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


def test_project_keeps_the_link_not_the_cached_file(fake_web, tmp_path):
    url = "https://example.com/goblin.png"
    fake_web[url] = figure_bytes()
    (tmp_path / "p.yaml").write_text(
        f"figures:\n  - image: {url}\n    strength: 50\n", encoding="utf-8"
    )
    proj = load_project(tmp_path / "p.yaml")
    f = proj.figures[0]
    assert (
        f.source == url
        and f.image == remote.cached_image(url)
        and f.settings.strength == 50
    )
    assert f.display_name == "goblin"
    save_project(proj, tmp_path / "q.yaml")
    assert f"image: {url}" in (tmp_path / "q.yaml").read_text(encoding="utf-8")


def test_project_with_a_dead_link_says_which(fake_web, tmp_path):
    (tmp_path / "p.yaml").write_text(
        "figures: [https://example.com/gone.png]\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="gone.png: 404"):
        load_project(tmp_path / "p.yaml")


def test_cli_makes_a_mini_from_a_link_into_the_current_folder(
    fake_web, tmp_path, monkeypatch
):
    url = "https://example.com/minis/hero.webp"
    fake_web[url] = figure_bytes("WEBP")
    monkeypatch.chdir(tmp_path)
    assert main(["make", url, "--model", "alpha"]) == 0
    assert (tmp_path / "hero.svg").is_file()  # here, not next to the cached download
    assert (
        main(["make", "https://example.com/nothing.png"]) == 2
    )  # a clear error, no traceback


def test_webp_file_works_like_any_other(tmp_path):
    from papermini.project.settings import build_mini

    (tmp_path / "ogre.webp").write_bytes(figure_bytes("WEBP"))
    m = build_mini(tmp_path / "ogre.webp", FigureSettings())
    assert m.name == "ogre" and abs(m.figure_height_mm - 32) < 0.5
    assert (
        main(["make", (tmp_path / "ogre.webp").as_uri()]) == 0
    )  # a file:// URI is a path
    assert (tmp_path / "ogre.svg").is_file()


def test_clear_images_keeps_the_ones_in_use(fake_web):
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
