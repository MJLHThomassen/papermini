"""Images from links (downloaded once into the cache) and WebP files. No real network."""

import io
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from papermini import remote
from papermini.cli import main
from papermini.settings import FigureSettings, load_project, save_project


def figure_bytes(fmt="PNG", size=(300, 450)) -> bytes:
    """A red oval on a transparent background: the alpha channel is the mask, no model needed."""
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((30, 30, size[0] - 30, size[1] - 30), fill=(200, 40, 30, 255))
    buf = io.BytesIO()
    (im.convert("RGB") if fmt == "JPEG" else im).save(buf, fmt)
    return buf.getvalue()


class Web(dict):
    asked: list


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.fixture
def web(monkeypatch):
    """A fake web: ``web[url] = bytes`` (or an exception); records every request."""
    pages, asked = Web(), []

    def urlopen(req, timeout=None):
        url = req.full_url
        asked.append((url, req.get_header("User-agent")))
        body = pages.get(url)
        if isinstance(body, Exception):
            raise body
        if body is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return FakeResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    pages.asked = asked
    return pages


def test_link_is_downloaded_once_and_named_after_the_link(web):
    url = "https://example.com/art/Red%20Goblin.webp?size=large"
    web[url] = figure_bytes("WEBP")
    p = remote.fetch_image(url)
    assert p.name == "Red Goblin.webp" and p.read_bytes() == web[url]
    assert web.asked == [(url, "papermini")]
    assert remote.fetch_image(url) == p and len(web.asked) == 1  # from the cache
    assert remote.cached_image(url) == p


def test_link_without_extension_gets_one_from_the_content(web):
    web["https://example.com/image?id=7"] = figure_bytes("JPEG")
    assert remote.fetch_image("https://example.com/image?id=7").name == "image.jpg"


def test_bad_links_give_readable_errors(web, monkeypatch):
    with pytest.raises(ValueError, match="404 Not Found"):
        remote.fetch_image("https://example.com/missing.png")
    web["https://example.com/page"] = b"<html><body>a web page</body></html>"
    with pytest.raises(ValueError, match="not an image"):
        remote.fetch_image("https://example.com/page")
    web["https://down.example/x.png"] = urllib.error.URLError("no route to host")
    with pytest.raises(ValueError, match="no route to host"):
        remote.fetch_image("https://down.example/x.png")
    monkeypatch.setattr(remote, "MAX_BYTES", 1000)
    web["https://example.com/huge.png"] = b"\0" * 5000
    with pytest.raises(ValueError, match="larger than"):
        remote.fetch_image("https://example.com/huge.png")
    assert not list((remote._cache_dir()).rglob("*.png"))  # nothing half-written is kept


def test_link_and_file_uri_helpers(tmp_path):
    assert remote.is_url("https://a/b.png") and remote.is_url(" HTTP://a/b ")
    assert not remote.is_url("C:/art/b.png") and not remote.is_url(Path("x.png"))
    f = tmp_path / "my art" / "x.webp"
    assert remote.local_path(f.as_uri()) == f
    assert remote.local_path("plain.png") == Path("plain.png")
    assert remote.is_image_file("A.WEBP") and not remote.is_image_file("a.gif")


def test_project_keeps_the_link_not_the_cached_file(web, tmp_path):
    url = "https://example.com/goblin.png"
    web[url] = figure_bytes()
    (tmp_path / "p.yaml").write_text(f"figures:\n  - image: {url}\n    strength: 50\n",
                                     encoding="utf-8")
    proj = load_project(tmp_path / "p.yaml")
    f = proj.figures[0]
    assert f.source == url and f.image == remote.cached_image(url) and f.settings.strength == 50
    assert f.display_name == "goblin"
    save_project(proj, tmp_path / "q.yaml")
    assert f"image: {url}" in (tmp_path / "q.yaml").read_text(encoding="utf-8")


def test_project_with_a_dead_link_says_which(web, tmp_path):
    (tmp_path / "p.yaml").write_text("figures: [https://example.com/gone.png]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="gone.png: 404"):
        load_project(tmp_path / "p.yaml")


def test_cli_makes_a_mini_from_a_link_into_the_current_folder(web, tmp_path, monkeypatch):
    url = "https://example.com/minis/hero.webp"
    web[url] = figure_bytes("WEBP")
    monkeypatch.chdir(tmp_path)
    assert main(["make", url, "--model", "alpha"]) == 0
    assert (tmp_path / "hero.svg").is_file()  # here, not next to the cached download
    assert main(["make", "https://example.com/nothing.png"]) == 2  # a clear error, no traceback


def test_webp_file_works_like_any_other(tmp_path):
    from papermini.settings import build_mini

    (tmp_path / "ogre.webp").write_bytes(figure_bytes("WEBP"))
    m = build_mini(tmp_path / "ogre.webp", FigureSettings())
    assert m.name == "ogre" and abs(m.figure_height_mm - 42) < 0.5
    assert main(["make", (tmp_path / "ogre.webp").as_uri()]) == 0  # a file:// URI is a path
    assert (tmp_path / "ogre.svg").is_file()
